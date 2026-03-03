"""Crawler for RBI (Reserve Bank of India) circulars and notifications."""

import re
import time
from datetime import datetime
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


class RBICrawler(BaseCrawler):
    """Crawls circulars from rbi.org.in"""

    name = "rbi_circulars"
    BASE_URL = "https://www.rbi.org.in"
    NOTIFICATIONS_URL = f"{BASE_URL}/Scripts/NotificationUser.aspx"
    CIRCULARS_URL = f"{BASE_URL}/Scripts/BS_CircularIndexDisplay.aspx"
    PRESS_RELEASES_URL = f"{BASE_URL}/Scripts/BS_PressReleaseDisplay.aspx"

    # Year range: current year down to START_YEAR (controlled by --max-pages as year count)
    START_YEAR = 2016

    def crawl(self):
        current_year = datetime.now().year
        end_year = max(self.START_YEAR, current_year - config.MAX_PAGES + 1)
        years = list(range(current_year, end_year - 1, -1))

        self._crawl_by_year(self.NOTIFICATIONS_URL, years, source="notification")
        self._crawl_by_year(self.CIRCULARS_URL, years, source="circular")
        self._crawl_by_year(self.PRESS_RELEASES_URL, years, source="press release")

    def _crawl_by_year(self, url, years, source):
        """Crawl an RBI listing page year by year using the hdnYear form POST."""
        label = source + "s"
        print(f"  Fetching RBI {label}...")

        # Initial GET to establish session and get form fields
        resp = self.fetch(url)
        if not resp:
            return

        for year in years:
            soup = self.parse_html(resp.text)
            form_data = self._get_hidden_fields(soup)
            form_data["hdnYear"] = str(year)
            form_data["hdnMonth"] = "0"  # All months
            form_data["UsrFontCntr$btn"] = ""

            time.sleep(config.DELAY_BETWEEN_REQUESTS)
            try:
                resp = self.session.post(url, data=form_data, timeout=config.REQUEST_TIMEOUT)
                resp.raise_for_status()
            except Exception as e:
                print(f"  [ERROR] Failed to fetch {label} for {year}: {e}")
                continue

            soup = self.parse_html(resp.text)
            rows = soup.select("table.tablebg tr") or soup.select("#divContent table tr")

            before = len(self.results)
            if rows:
                self._parse_table_rows(rows, source=source)
            else:
                self._parse_link_listing(soup, source=source)

            found = len(self.results) - before
            print(f"  {label.capitalize()} {year}: {found} records")
            if found > 0:
                self.save_progress()

    def parse_detail_page(self, soup, url):
        """Extract full content from an RBI notification/circular detail page."""
        detail = {"content": "", "circular_number": "", "date": "", "addressed_to": "", "pdf_links": []}

        content_div = soup.select_one("#example-min") or soup.select_one("#doublescroll")
        if not content_div:
            content_div = soup.select_one("#pnlDetails") or soup.body

        if not content_div:
            return detail

        detail["content"] = content_div.get_text(separator="\n", strip=True)

        for a in content_div.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                detail["pdf_links"].append(href)

        lines = detail["content"].split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("RBI/") and not detail["circular_number"]:
                detail["circular_number"] = line
            if not detail["date"]:
                for month in ["January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]:
                    if line.startswith(month) and len(line) < 30:
                        detail["date"] = line
                        break

        return detail

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
