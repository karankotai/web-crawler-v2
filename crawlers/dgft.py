"""Crawler for DGFT (Directorate General of Foreign Trade) notifications.

dgft.gov.in uses a Spring/Java backend with CAPTCHA protection on page rendering.
We use Playwright to bypass the CAPTCHA, then extract PDF URLs from the rendered
tables and download PDFs directly from the CDN (no auth needed).

Sections: Notifications, Public Notices, Circulars, Trade Notices
"""

import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

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

            # Deep crawl PDFs (download from CDN directly)
            if config.DEEP_CRAWL:
                self._deep_crawl_pdfs()

            browser.close()

    def crawl_details(self):
        """Override: DGFT PDFs are on CDN — download directly without browser."""
        if not config.DEEP_CRAWL:
            return
        self._deep_crawl_pdfs()

    def _crawl_section(self, page, section):
        """Navigate to a DGFT section using Playwright and extract records."""
        opt = section["opt"]
        label = section["label"]
        doc_type = section["doc_type"]

        url = f"{self.LISTING_URL}?opt={opt}"
        print(f"  Loading DGFT {label}...")

        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(5)  # Allow CAPTCHA/JS to resolve
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

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            self._parse_listing(soup, label, doc_type)

            found = len(self.results) - before
            print(f"  DGFT {label} page {page_num}: {found} records")

            if found == 0:
                break

            # Try to navigate to next page
            if not self._goto_next_page(page, page_num):
                break
            page_num += 1

    def _parse_listing(self, soup, label, doc_type):
        """Parse a DGFT listing page for records."""
        # DGFT typically uses tables with: Number | Year | Description | Date | Attachment
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # Skip empty rows or header-like rows
                if not any(t for t in texts):
                    continue

                # Find title — usually the longest text cell
                title = ""
                for t in texts:
                    if len(t) > len(title) and len(t) > 10:
                        title = t

                if not title:
                    continue

                # Extract notification number (format: 61/2025-26)
                circular_number = ""
                for t in texts:
                    if re.match(r'\d+/\d{4}(?:-\d{2})?', t):
                        circular_number = t
                        break

                # Extract date
                date = ""
                for t in texts:
                    if re.search(r'\d{2}[./-]\d{2}[./-]\d{4}', t):
                        date = t
                        break

                # Collect PDF links
                pdf_links = []
                link_url = ""
                for a in row.find_all("a", href=True):
                    href = a["href"]
                    if ".pdf" in href.lower():
                        if not href.startswith("http"):
                            href = urljoin(self.BASE_URL, href)
                        pdf_links.append(href)
                        if not link_url:
                            link_url = href
                    elif not link_url:
                        if not href.startswith("http"):
                            href = urljoin(self.BASE_URL, href)
                        if "javascript:" not in href.lower():
                            link_url = href

                if not link_url:
                    # Generate a unique link from number + doc_type
                    link_url = f"{self.BASE_URL}/CP/?opt={label}&num={circular_number}"

                if link_url not in self.existing_links:
                    self.results.append({
                        "source": f"DGFT ({label})",
                        "title": title,
                        "date": date,
                        "department": "DGFT",
                        "link": link_url,
                        "circular_number": circular_number,
                        "pdf_links": pdf_links,
                        "doc_type": doc_type,
                    })

    def _goto_next_page(self, page, current_page):
        """Try to navigate to the next page."""
        try:
            # Try numbered pagination links
            next_link = page.query_selector(f'a:text-is("{current_page + 1}")')
            if next_link:
                next_link.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(3)
                return True

            # Try "Next" button
            for text in ["Next", "Next >", ">>", "next"]:
                next_link = page.query_selector(f'a:text-is("{text}")')
                if next_link:
                    next_link.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(3)
                    return True

            # Try arrow/icon-based next button
            next_btn = page.query_selector('.pagination .next a, .page-next a, a.next-page')
            if next_btn:
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(3)
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

            # Download and extract all PDFs (CDN allows concurrent)
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
        """Not primarily used — DGFT PDFs are downloaded directly from CDN."""
        return {}
