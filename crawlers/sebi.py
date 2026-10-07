"""Crawler for SEBI (Securities and Exchange Board of India) circulars."""

import gc
import re
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


class SEBICrawler(BaseCrawler):
    """Crawls circulars from sebi.gov.in

    SEBI uses AJAX POST pagination via /sebiweb/ajax/home/getnewslistinfo.jsp.
    The initial GET sets up the JSESSIONID cookie, then subsequent pages are
    fetched via POST with nextValue/doDirect parameters.
    """

    name = "sebi_circulars"
    BASE_URL = "https://www.sebi.gov.in"
    AJAX_URL = f"{BASE_URL}/sebiweb/ajax/home/getnewslistinfo.jsp"
    # ssid=7 = Circulars, ssid=6 = Master Circulars
    SECTIONS = [
        {"ssid": "7", "label": "circulars", "ssText": "Circulars"},
        {"ssid": "6", "label": "master circulars", "ssText": "Master Circulars"},
    ]

    def crawl(self):
        for section in self.SECTIONS:
            self._crawl_section(section)

    def parse_detail_page(self, soup, url):
        """Extract full content from a SEBI circular detail page.

        SEBI embeds the actual circular as a PDF inside an iframe.
        This method extracts the PDF URL, downloads it, and pulls out the text.
        """
        detail = {"content": "", "circular_number": "", "date": "", "pdf_links": []}

        # Date from .m_section (format: "Feb 11, 2026")
        date_section = soup.select_one(".m_section")
        if date_section:
            text = date_section.get_text(strip=True)
            if "|" in text:
                detail["date"] = text.split("|")[0].strip()

        # Circular number from .id_area
        id_area = soup.select_one(".id_area")
        if id_area:
            text = id_area.get_text(strip=True)
            detail["circular_number"] = text.replace("Circular No.:", "").strip()

        # Extract PDF URL from the iframe
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if "file=" in src:
                pdf_url = src.split("file=", 1)[1].split("&")[0]
                if pdf_url and pdf_url not in detail["pdf_links"]:
                    detail["pdf_links"].append(pdf_url)

        # Also check direct anchor PDF links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                if href not in detail["pdf_links"]:
                    detail["pdf_links"].append(href)

        # Download ALL PDFs and extract text (not just the first)
        if detail["pdf_links"]:
            content, method, _ = self._download_and_extract_all_pdfs(
                detail["pdf_links"], url
            )
            detail["content"] = content
            detail["extraction_method"] = method
            detail["extraction_status"] = "success" if content else "failed"

        return detail

    def _crawl_section(self, section):
        """Crawl a SEBI section using AJAX POST pagination."""
        ssid = section["ssid"]
        label = section["label"]

        # Initial GET to establish JSESSIONID cookie
        initial_url = f"{self.BASE_URL}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid={ssid}&smid=0"
        print(f"  Fetching SEBI {label} page 1...")
        self.session.headers["Referer"] = initial_url
        resp = self.fetch(initial_url)
        if not resp:
            print(f"  [ERROR] Failed to load SEBI {label} initial page")
            return

        soup = self.parse_html(resp.text)
        found = self._parse_listing(soup, label, 1)
        if found == 0:
            return

        # AJAX pagination for subsequent pages
        page_num = 2
        consecutive_failures = 0
        while page_num <= config.MAX_PAGES:
            if not self._has_next_page(soup, page_num - 1):
                break

            print(f"  Fetching SEBI {label} page {page_num}...")
            post_data = {
                "nextValue": str(page_num - 1),
                "next": "n",
                "search": "",
                "fromDate": "",
                "toDate": "",
                "fromYear": "",
                "toYear": "",
                "deptId": "",
                "sid": "1",
                "ssid": ssid,
                "smid": "0",
                "ssidhidden": ssid,
                "intmid": "-1",
                "sText": "Legal",
                "ssText": section["ssText"],
                "smText": "",
                "doDirect": str(page_num - 1),
            }

            resp = self.fetch(self.AJAX_URL, method="POST", data=post_data, timeout=30)
            if not resp:
                consecutive_failures += 1
                print(f"  [ERROR] Failed to fetch SEBI {label} page {page_num} ({consecutive_failures} consecutive failures)")
                if consecutive_failures >= 3:
                    print(f"  [STOP] Too many consecutive failures, stopping {label}")
                    break
                page_num += 1
                continue

            consecutive_failures = 0
            soup = self.parse_html(resp.text)
            found = self._parse_listing(soup, label, page_num)
            if found == 0:
                break

            page_num += 1

    def _parse_listing(self, soup, label, page_num):
        """Parse records from a listing page. Returns count of new records."""
        before = len(self.results)
        rows = soup.select("table tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            link_tag = row.find("a", href=True)
            link = ""
            title = ""
            if link_tag:
                link = link_tag.get("href", "")
                if link and not link.startswith("http"):
                    link = f"{self.BASE_URL}{link}" if link.startswith("/") else f"{self.BASE_URL}/{link}"
                title = link_tag.get_text(strip=True)

            texts = [c.get_text(strip=True) for c in cells]
            date = texts[0] if texts else ""

            if title and len(title) > 5:
                self.results.append({
                    "source": "SEBI",
                    "title": title,
                    "date": date,
                    "department": "",
                    "link": link,
                    "details": " | ".join(t for t in texts if t),
                })

        found = len(self.results) - before
        print(f"  SEBI {label} page {page_num}: {found} records")
        self.save_progress()
        return found

    def _has_next_page(self, soup, current_page):
        """Check if there's a next page by parsing 'X to Y of Z records' text."""
        page_text = soup.get_text()
        m = re.search(r"(\d+)\s+to\s+(\d+)\s+of\s+(\d+)", page_text)
        if m:
            end_idx = int(m.group(2))
            total = int(m.group(3))
            return end_idx < total
        return False
