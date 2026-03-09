"""Crawler for DGFT (Directorate General of Foreign Trade) notifications.

dgft.gov.in uses a Spring/Java backend with CAPTCHA on initial page load.
Playwright renders the page (bypasses CAPTCHA), then we parse DataTables HTML.

Table structure: Sl.No. | Number | Year | Description | Date | CRT DT | Attachment
PDF links: Direct CDN URLs like https://content.dgft.gov.in/Website/dgftprod/{UUID}/{file}.pdf
Pagination: DataTables jQuery plugin (client-side or AJAX)
"""

import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

import config
from crawlers.base import BaseCrawler


DGFT_SECTIONS = [
    {
        "opt": "notification",
        "label": "notifications",
        "doc_type": "Notification",
    },
    {
        "opt": "public-notice",
        "label": "public notices",
        "doc_type": "Public Notice",
    },
    {
        "opt": "circular",
        "label": "circulars",
        "doc_type": "Circular",
    },
    {
        "opt": "trade-notice",
        "label": "trade notices",
        "doc_type": "Trade Notice",
    },
]


class DGFTCrawler(BaseCrawler):
    """Crawls notifications and circulars from dgft.gov.in using Playwright."""

    name = "dgft"
    BASE_URL = "https://www.dgft.gov.in"
    LISTING_URL = f"{BASE_URL}/CP/"

    def crawl(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=config.HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            for section in DGFT_SECTIONS:
                self._crawl_section(page, section)
                self.save_progress()

            browser.close()

    def crawl_details(self):
        """Override: DGFT PDFs are on CDN — download directly without browser."""
        if not config.DEEP_CRAWL:
            return
        self._deep_crawl_pdfs()

    def _crawl_section(self, page, section):
        """Navigate to a DGFT section and extract all records via DataTables pagination."""
        opt = section["opt"]
        label = section["label"]
        doc_type = section["doc_type"]

        url = f"{self.LISTING_URL}?opt={opt}"
        print(f"  Loading DGFT {label}...")

        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(8)  # Allow CAPTCHA/JS/DataTables to resolve
        except Exception as e:
            print(f"  [ERROR] Failed to load {label}: {e}")
            return

        page_num = 1
        while page_num <= config.MAX_PAGES:
            print(f"  Parsing DGFT {label} page {page_num}...")
            before = len(self.results)

            try:
                content = page.content()
            except Exception:
                break

            soup = BeautifulSoup(content, "lxml")
            self._parse_datatable(soup, label, doc_type)

            found = len(self.results) - before
            print(f"  DGFT {label} page {page_num}: {found} records")

            if found == 0:
                break

            # Try DataTables "Next" button
            if not self._goto_next_page_dt(page):
                break
            page_num += 1

    def _parse_datatable(self, soup, label, doc_type):
        """Parse DGFT DataTable rows.

        Structure:
            tr.odd/tr.even
                td — Sl.No.
                td — Number (notification number like "60/2025-26")
                td — Year
                td — Description
                td.sorting_1 — Date (DD/MM/YYYY)
                td[style=display:none] — CRT DT (hidden)
                td — Attachment: a.attachmentBtn[href=CDN_URL]
        """
        table = soup.find("table")
        if not table:
            return

        rows = table.find_all("tr", class_=re.compile(r"odd|even"))
        if not rows:
            # Fallback: all data rows after header
            all_rows = table.find_all("tr")
            rows = all_rows[1:] if len(all_rows) > 1 else []

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Parse columns based on DGFT table structure
            number = cells[1].get_text(strip=True)
            year = cells[2].get_text(strip=True)
            description = cells[3].get_text(strip=True)
            date = cells[4].get_text(strip=True)

            title = description or number
            if not title or len(title) < 3:
                continue

            circular_number = number
            if year and year not in number:
                circular_number = f"{number}/{year}" if number else year

            # Extract PDF download link from attachment cell
            pdf_links = []
            for a in row.find_all("a", href=True):
                href = a["href"]
                if "content.dgft.gov.in" in href or ".pdf" in href.lower():
                    if not href.startswith("http"):
                        href = urljoin(self.BASE_URL, href)
                    pdf_links.append(href)

            # Use PDF URL as link if available, otherwise generate one
            link = pdf_links[0] if pdf_links else f"{self.BASE_URL}/CP/?opt={label}&num={circular_number}"

            if link not in self.existing_links:
                self.results.append({
                    "source": f"DGFT ({label})",
                    "title": title,
                    "date": date,
                    "department": "DGFT",
                    "link": link,
                    "circular_number": circular_number,
                    "pdf_links": pdf_links,
                    "doc_type": doc_type,
                })

    def _goto_next_page_dt(self, page):
        """Click the DataTables 'Next' button. Returns True on success."""
        try:
            next_btn = page.query_selector("#metaTable_next:not(.disabled)")
            if not next_btn:
                # Try generic DataTables next
                next_btn = page.query_selector(".paginate_button.next:not(.disabled) a")
            if next_btn:
                next_btn.click()
                time.sleep(2)  # DataTables client-side pagination is instant
                return True
        except Exception:
            pass
        return False

    def _deep_crawl_pdfs(self):
        """Download PDFs from CDN and extract text (no browser needed for CDN)."""
        pdf_results = [r for r in self.results if r.get("pdf_links") and not r.get("content")]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} DGFT PDFs (CDN download)...")
        updated = 0
        for i, record in enumerate(pdf_results):
            pdf_links = record.get("pdf_links", [])
            if not pdf_links:
                continue

            print(f"  [{i+1}/{len(pdf_results)}] {record.get('circular_number', '') or record.get('title', '')[:40]}...")

            content, method, _ = self._download_and_extract_all_pdfs(
                pdf_links, record["link"]
            )
            if content:
                record["content"] = content
                record["extraction_status"] = "success"
                record["extraction_method"] = method
                if config.DATABASE_URL:
                    self._update_record_content(record["link"], record)
                updated += 1
                if updated % 25 == 0:
                    print(f"  [deep checkpoint] {updated} records with content")

        if updated:
            print(f"  Deep crawl complete: {updated} DGFT records with content")

    def parse_detail_page(self, soup, url):
        """Not used — DGFT PDFs are downloaded directly from CDN."""
        return {}
