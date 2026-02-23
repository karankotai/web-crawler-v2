"""Crawler for RBI (Reserve Bank of India) circulars and notifications."""

import re
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


class RBICrawler(BaseCrawler):
    """Crawls circulars from rbi.org.in"""

    name = "rbi_circulars"
    BASE_URL = "https://www.rbi.org.in"
    NOTIFICATIONS_URL = f"{BASE_URL}/Scripts/NotificationUser.aspx"
    CIRCULARS_URL = f"{BASE_URL}/Scripts/BS_CircularIndexDisplay.aspx"

    def crawl(self):
        self._crawl_notifications()
        self._crawl_circulars()

    def parse_detail_page(self, soup, url):
        """Extract full content from an RBI notification/circular detail page.

        RBI detail pages have content in div#example-min containing:
        - Title, RBI reference number, date, addressed-to
        - Full body text of the circular
        - PDF download links
        """
        detail = {"content": "", "circular_number": "", "date": "", "addressed_to": "", "pdf_links": []}

        # Main content lives in div#example-min
        content_div = soup.select_one("#example-min") or soup.select_one("#doublescroll")
        if not content_div:
            # fallback
            content_div = soup.select_one("#pnlDetails") or soup.body

        if not content_div:
            return detail

        # Extract full text
        detail["content"] = content_div.get_text(separator="\n", strip=True)

        # Extract PDF links
        for a in content_div.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                detail["pdf_links"].append(href)

        # Try to parse structured fields from the text
        lines = detail["content"].split("\n")
        for line in lines:
            line = line.strip()
            # RBI reference: RBI/2025-26/207
            if line.startswith("RBI/") and not detail["circular_number"]:
                detail["circular_number"] = line
            # Date line: February 11, 2026
            if not detail["date"]:
                for month in ["January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]:
                    if line.startswith(month) and len(line) < 30:
                        detail["date"] = line
                        break

        return detail

    def _crawl_notifications(self):
        """Crawl the notifications listing page with ASP.NET pagination."""
        print("  Fetching RBI notifications...")
        resp = self.fetch(self.NOTIFICATIONS_URL)
        if not resp:
            return

        page_num = 1
        current_url = self.NOTIFICATIONS_URL
        while page_num <= config.MAX_PAGES:
            soup = self.parse_html(resp.text)
            rows = soup.select("table.tablebg tr") or soup.select("#divContent table tr")

            before = len(self.results)
            if rows:
                self._parse_table_rows(rows, source="notification")
            else:
                self._parse_link_listing(soup, source="notification")

            found = len(self.results) - before
            print(f"  Notifications page {page_num}: {found} records")
            self.save_progress()

            if found == 0:
                break

            next_link = self._find_next_page(soup, page_num + 1)
            if not next_link:
                break

            form_data = self._get_hidden_fields(soup)
            form_data["__EVENTTARGET"] = next_link["target"]
            form_data["__EVENTARGUMENT"] = next_link["argument"]

            resp = self.session.post(
                current_url, data=form_data, timeout=config.REQUEST_TIMEOUT
            )
            page_num += 1

    def _crawl_circulars(self):
        """Crawl the circulars index page with ASP.NET pagination."""
        print("  Fetching RBI circulars...")
        resp = self.fetch(self.CIRCULARS_URL)
        if not resp:
            return

        page_num = 1
        current_url = self.CIRCULARS_URL
        while page_num <= config.MAX_PAGES:
            soup = self.parse_html(resp.text)
            rows = soup.select("table.tablebg tr") or soup.select("#divContent table tr")

            before = len(self.results)
            if rows:
                self._parse_table_rows(rows, source="circular")
            else:
                self._parse_link_listing(soup, source="circular")

            found = len(self.results) - before
            print(f"  Circulars page {page_num}: {found} records")
            self.save_progress()

            if found == 0:
                break

            next_link = self._find_next_page(soup, page_num + 1)
            if not next_link:
                break

            form_data = self._get_hidden_fields(soup)
            form_data["__EVENTTARGET"] = next_link["target"]
            form_data["__EVENTARGUMENT"] = next_link["argument"]

            resp = self.session.post(
                current_url, data=form_data, timeout=config.REQUEST_TIMEOUT
            )
            page_num += 1

    def _parse_table_rows(self, rows, source):
        """Parse table rows from RBI pages."""
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            if row.find("th") or row.find("strong"):
                text = row.get_text(strip=True).lower()
                if any(h in text for h in ["date", "subject", "circular"]):
                    continue

            link_tag = row.find("a", href=True)
            link = ""
            title = ""
            if link_tag:
                link = link_tag.get("href", "")
                if link and not link.startswith("http"):
                    link = f"{self.BASE_URL}/Scripts/{link}"
                title = link_tag.get_text(strip=True)

            texts = [c.get_text(strip=True) for c in cells]

            record = {
                "source": f"RBI ({source})",
                "title": title or texts[0] if texts else "",
                "date": "",
                "department": "",
                "link": link,
                "details": " | ".join(t for t in texts if t),
            }

            for t in texts:
                if any(m in t for m in [
                    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                    "/20", "/19",
                ]):
                    record["date"] = t
                    break

            if record["title"]:
                self.results.append(record)

    def _parse_link_listing(self, soup, source):
        """Fallback parser: extract all content links from page."""
        content_div = soup.select_one("#divContent") or soup.select_one("#wrapper") or soup
        links = content_div.find_all("a", href=True)

        for a in links:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#", "login", "home"]):
                continue

            if not href.startswith("http"):
                href = f"{self.BASE_URL}/Scripts/{href}"

            date = ""
            parent = a.parent
            if parent:
                sibling_text = parent.get_text(strip=True)
                for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
                    if month in sibling_text:
                        idx = sibling_text.find(month)
                        date = sibling_text[max(0, idx - 4):idx + 12].strip()
                        break

            self.results.append({
                "source": f"RBI ({source})",
                "title": title,
                "date": date,
                "department": "",
                "link": href,
                "details": "",
            })

        print(f"  Found {len(self.results)} RBI records so far.")

    def _find_next_page(self, soup, next_page_num):
        """Find ASP.NET postback link for the next page.

        Looks for page number links containing __doPostBack or a 'Next' anchor.
        Returns dict with 'target' and 'argument' keys, or None.
        """
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "__doPostBack" not in href:
                continue
            # Match page number links like __doPostBack('GridView1','Page$3')
            match = re.search(r"__doPostBack\('([^']+)','Page\$(\d+)'\)", href)
            if match and int(match.group(2)) == next_page_num:
                return {"target": match.group(1), "argument": f"Page${next_page_num}"}
            # Match "Next" links
            text = a.get_text(strip=True).lower()
            if text in ("next", ">>", ">", "..."):
                match = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", href)
                if match:
                    return {"target": match.group(1), "argument": match.group(2)}
        return None

    def _get_hidden_fields(self, soup):
        """Extract all hidden form fields for ASP.NET postback."""
        form = soup.find("form")
        if not form:
            return {}
        data = {}
        for inp in form.find_all("input", type="hidden"):
            name = inp.get("name", "")
            if name:
                data[name] = inp.get("value", "")
        return data
