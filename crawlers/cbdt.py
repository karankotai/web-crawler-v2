"""Crawler for CBDT (Central Board of Direct Taxes) — Income Tax circulars and notifications.

incometaxindia.gov.in uses SharePoint/ASP.NET and returns 503 for non-browser
requests, so we use Playwright (similar to MCA crawler).

Sections: Circulars, Notifications, Press Releases, Orders
"""

import json
import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

import config
from crawlers.base import BaseCrawler


CBDT_SECTIONS = [
    {
        "path": "/Pages/communications/circulars.aspx",
        "label": "circulars",
        "doc_type": "Circular",
    },
    {
        "path": "/Pages/communications/notifications.aspx",
        "label": "notifications",
        "doc_type": "Notification",
    },
    {
        "path": "/Pages/communications/press-releases.aspx",
        "label": "press releases",
        "doc_type": "Press Release",
    },
    {
        "path": "/Pages/communications/orders.aspx",
        "label": "orders",
        "doc_type": "Order",
    },
]


class CBDTCrawler(BaseCrawler):
    """Crawls circulars and notifications from incometaxindia.gov.in using Playwright."""

    name = "cbdt"
    BASE_URL = "https://incometaxindia.gov.in"

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

            for section in CBDT_SECTIONS:
                self._crawl_section(page, section)
                self.save_progress()

            # Deep crawl PDFs while browser is open
            if config.DEEP_CRAWL:
                self._deep_crawl_pdfs(page)

            browser.close()

    def crawl_details(self):
        """Override: deep crawl is handled inside crawl() while browser is open."""
        pass

    def _crawl_section(self, page, section):
        """Navigate to a CBDT section and extract records."""
        url = f"{self.BASE_URL}{section['path']}"
        label = section["label"]
        doc_type = section["doc_type"]

        print(f"  Loading CBDT {label}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)
        except Exception as e:
            print(f"  [ERROR] Failed to load {label}: {e}")
            return

        page_num = 1
        while page_num <= config.MAX_PAGES:
            print(f"  Parsing CBDT {label} page {page_num}...")
            before = len(self.results)

            # Extract records from the current page
            try:
                content = page.content()
            except Exception:
                break

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, "lxml")
            self._parse_listing(soup, label, doc_type)

            found = len(self.results) - before
            print(f"  CBDT {label} page {page_num}: {found} records")

            if found == 0:
                break

            # Try to navigate to next page
            if not self._goto_next_page(page, page_num):
                break
            page_num += 1

    def _parse_listing(self, soup, label, doc_type):
        """Parse a CBDT listing page for records."""
        # CBDT pages typically use tables or div-based listings
        # Try table rows first
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                link_tag = row.find("a", href=True)
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = link_tag["href"]
                if not href.startswith("http"):
                    href = urljoin(self.BASE_URL, href)

                if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # Extract date and circular number from cells
                date = ""
                circular_number = ""
                for t in texts:
                    if re.search(r'\d{2}[/-]\d{2}[/-]\d{4}', t):
                        date = t
                    elif re.search(r'(?:Circular|Notification)\s*(?:No\.?)?\s*\d+', t, re.I):
                        circular_number = t

                # Detect PDF links
                pdf_links = []
                for a in row.find_all("a", href=True):
                    if ".pdf" in a["href"].lower():
                        pdf_href = a["href"]
                        if not pdf_href.startswith("http"):
                            pdf_href = urljoin(self.BASE_URL, pdf_href)
                        pdf_links.append(pdf_href)

                if href not in self.existing_links:
                    self.results.append({
                        "source": f"CBDT ({label})",
                        "title": title,
                        "date": date,
                        "department": "CBDT - Income Tax",
                        "link": href,
                        "details": " | ".join(t for t in texts if t),
                        "circular_number": circular_number,
                        "pdf_links": pdf_links,
                        "doc_type": doc_type,
                    })

        # Fallback: div-based listings
        for div in soup.select(".comm-list li, .listing-content li, .content-area li"):
            link_tag = div.find("a", href=True)
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = urljoin(self.BASE_URL, href)

            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                continue

            date = ""
            date_el = div.find("span", class_="date") or div.find("small")
            if date_el:
                date = date_el.get_text(strip=True)

            pdf_links = []
            for a in div.find_all("a", href=True):
                if ".pdf" in a["href"].lower():
                    pdf_href = a["href"]
                    if not pdf_href.startswith("http"):
                        pdf_href = urljoin(self.BASE_URL, pdf_href)
                    pdf_links.append(pdf_href)

            if href not in self.existing_links:
                self.results.append({
                    "source": f"CBDT ({label})",
                    "title": title,
                    "date": date,
                    "department": "CBDT - Income Tax",
                    "link": href,
                    "pdf_links": pdf_links,
                    "doc_type": doc_type,
                })

    def _goto_next_page(self, page, current_page):
        """Try to navigate to the next page. Returns True on success."""
        try:
            # Try query parameter pagination
            next_url = f"?c={current_page + 1}"
            next_link = page.query_selector(f'a[href*="c={current_page + 1}"]')
            if next_link:
                next_link.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                return True

            # Try ASP.NET postback pagination
            next_link = page.query_selector(f'a[href*="Page${current_page + 1}"]')
            if next_link:
                next_link.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                return True

            # Try "Next" link
            for text in ["Next", "Next >", ">>"]:
                next_link = page.query_selector(f'a:text-is("{text}")')
                if next_link:
                    next_link.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    return True
        except Exception:
            pass
        return False

    def _deep_crawl_pdfs(self, page):
        """Download PDFs and extract text while browser is still open."""
        pdf_results = [r for r in self.results if r.get("pdf_links")]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} CBDT PDFs...")
        updated = 0
        for i, record in enumerate(pdf_results):
            if record.get("content"):
                continue

            pdf_links = record.get("pdf_links", [])
            if not pdf_links:
                continue

            print(f"  [{i+1}/{len(pdf_results)}] {record.get('title', '')[:60]}...")

            # Download and extract all PDFs
            content, method, _ = self._download_and_extract_all_pdfs(
                pdf_links, record["link"], concurrent=False
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
            print(f"  Deep crawl complete: {updated} CBDT records with content")

    def parse_detail_page(self, soup, url):
        """Not primarily used — CBDT deep crawl is handled via _deep_crawl_pdfs."""
        return {}
