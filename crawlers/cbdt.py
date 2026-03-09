"""Crawler for CBDT (Central Board of Direct Taxes) — Income Tax circulars and notifications.

incometaxindia.gov.in is a SharePoint site that returns 503 for non-browser requests.
Uses Playwright to render pages.

Page structure:
- Items: div.search_result
- Title: h3.search_title > a (with onclick containing PDF URL)
- Circular number: span.NotificationNumber
- Date: span.publishDate
- PDF URL: extracted from onclick="javascript:OpenFormByType('URL&k=&opt=')"
- Year filter: dropdown with __doPostBack
"""

import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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
        """Load a CBDT section and extract all div.search_result items.

        The default view shows "All" years. We parse that first, then
        optionally iterate by year if needed for completeness.
        """
        url = f"{self.BASE_URL}{section['path']}"
        label = section["label"]
        doc_type = section["doc_type"]

        print(f"  Loading CBDT {label}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(5)
        except Exception as e:
            print(f"  [ERROR] Failed to load {label}: {e}")
            return

        # Parse the default "All" view
        before = len(self.results)
        content = page.content()
        soup = BeautifulSoup(content, "lxml")
        self._parse_search_results(soup, label, doc_type)
        found = len(self.results) - before
        print(f"  CBDT {label} (all years): {found} records")

        # If the default view seems truncated (SharePoint often limits to 10-30),
        # iterate year by year using the dropdown
        if found > 0 and found <= 30:
            self._crawl_by_year(page, soup, label, doc_type)

    def _crawl_by_year(self, page, initial_soup, label, doc_type):
        """Iterate through years using the year dropdown to get complete listing."""
        # Find the year dropdown
        select = initial_soup.find("select", id=re.compile(r"ddlYear", re.I))
        if not select:
            return

        years = [opt["value"] for opt in select.find_all("option") if opt["value"] != "All"]
        print(f"  Crawling {len(years)} years for {label}...")

        for year in years:
            # Select the year via JavaScript
            try:
                select_id = select.get("id", "")
                page.select_option(f"#{select_id}", year)
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(3)
            except Exception as e:
                print(f"  [WARN] Failed to select year {year}: {e}")
                continue

            before = len(self.results)
            content = page.content()
            soup = BeautifulSoup(content, "lxml")
            self._parse_search_results(soup, label, doc_type)
            found = len(self.results) - before
            if found > 0:
                print(f"  CBDT {label} {year}: {found} new records")

    def _parse_search_results(self, soup, label, doc_type):
        """Parse div.search_result items from the page.

        Structure:
            div.search_result
                h3.search_title
                    a[onclick="javascript:OpenFormByType('PDF_URL&k=&opt=')"]
                        span > span.NotificationNumber
                        span.publishDate
                p.search_description (preview text)
        """
        items = soup.select("div.search_result")
        for item in items:
            title_link = item.select_one("h3.search_title a")
            if not title_link:
                continue

            # Extract PDF URL from onclick handler
            onclick = title_link.get("onclick", "")
            pdf_url = ""
            url_match = re.search(r"OpenFormByType\('([^']+?)(?:&k=|&amp;k=)", onclick)
            if url_match:
                pdf_url = url_match.group(1)
                # Clean up HTML entities
                pdf_url = pdf_url.replace("&amp;", "&")

            # Extract circular number
            notif_span = item.select_one("span.NotificationNumber")
            circular_number = notif_span.get_text(strip=True).rstrip(":").strip() if notif_span else ""

            # Extract date
            date_span = item.select_one("span.publishDate")
            date = date_span.get_text(strip=True) if date_span else ""

            # Extract title (full text minus the number and date)
            full_text = title_link.get_text(strip=True)
            title = full_text
            # Remove the circular number prefix and date suffix for cleaner title
            if circular_number and title.startswith(circular_number):
                title = title[len(circular_number):].lstrip(": \u200b")
            if date and title.endswith(date):
                title = title[:-len(date)].strip()
            title = title.strip("\u200b :")

            if not title or len(title) < 5:
                continue

            # Use PDF URL as the unique link, or construct one
            link = pdf_url if pdf_url else f"{self.BASE_URL}/communications/{label}/{circular_number}"
            pdf_links = [pdf_url] if pdf_url else []

            if link not in self.existing_links:
                self.results.append({
                    "source": f"CBDT ({label})",
                    "title": title,
                    "date": date,
                    "department": "CBDT - Income Tax",
                    "link": link,
                    "details": circular_number,
                    "circular_number": circular_number,
                    "pdf_links": pdf_links,
                    "doc_type": doc_type,
                })

    def _deep_crawl_pdfs(self, page):
        """Download PDFs and extract text."""
        pdf_results = [r for r in self.results if r.get("pdf_links") and not r.get("content")]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} CBDT PDFs...")
        updated = 0
        for i, record in enumerate(pdf_results):
            pdf_links = record.get("pdf_links", [])
            if not pdf_links:
                continue

            print(f"  [{i+1}/{len(pdf_results)}] {record.get('circular_number', '')[:40]}...")

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
        """Not primarily used — CBDT deep crawl handled via _deep_crawl_pdfs."""
        return {}
