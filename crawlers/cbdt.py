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

import base64
import json
import re
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

import config
from crawlers.base import BaseCrawler, _get_db_conn

# JS snippet to fetch a URL as base64 from within the browser context.
# Used as fallback when Chrome's PDF viewer intercepts the response listener.
JS_FETCH_BASE64 = """
async (url) => {
    const resp = await fetch(url);
    const buf = await resp.arrayBuffer();
    const arr = new Uint8Array(buf);
    let binary = '';
    for (let i = 0; i < arr.length; i++) {
        binary += String.fromCharCode(arr[i]);
    }
    return btoa(binary);
}
"""

_SESSION_REFRESH_INTERVAL = 50  # Refresh browser session every N PDFs
_CONSECUTIVE_FAIL_THRESHOLD = 5  # Force refresh after N consecutive failures


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
        self._session_links = set()  # Track links within this crawl to prevent duplicates
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

            # Check both DB links and current session to avoid duplicates
            # (year-by-year crawl can return same items across multiple years)
            if link not in self.existing_links and link not in self._session_links:
                self._session_links.add(link)
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
        """Download documents via Playwright with AES challenge resolution.

        incometaxindia.gov.in serves a per-URL AES JavaScript challenge:
        1. First response is 503 with JS that loads aes.min.js from S3
        2. JS decrypts a token, sets a cookie, reloads the page
        3. Second response is 200 with actual content

        For .htm: navigate, wait ~8s for challenge, read page.content()
        For .pdf: navigate, wait for challenge, intercept the 200 response body
        """
        from utils.pdf_extract import extract_text_from_pdf_with_metadata

        # Combine new results + existing DB records missing content
        pdf_items = []
        for r in self.results:
            if r.get("pdf_links") and not r.get("content"):
                pdf_items.append({"link": r["link"], "pdf_links": r["pdf_links"],
                                  "label": r.get("circular_number", "") or r.get("title", "")[:40],
                                  "record": r})

        db_items = self._load_db_records_missing_content()
        for item in db_items:
            pdf_items.append({"link": item["link"], "pdf_links": item["pdf_links"],
                              "label": item.get("label", item["link"].split("/")[-1][:40]),
                              "record": None})

        if not pdf_items:
            return

        print(f"  Deep crawling {len(pdf_items)} CBDT documents (via browser + AES challenge)...")

        dl_page = page.context.new_page()
        updated = 0
        failed = 0
        consecutive_fails = 0
        for i, item in enumerate(pdf_items):
            pdf_links = item["pdf_links"]
            if not pdf_links:
                continue

            # Periodic session refresh to prevent cookie/state accumulation
            needs_refresh = (
                (i + 1) % _SESSION_REFRESH_INTERVAL == 0
                or consecutive_fails >= _CONSECUTIVE_FAIL_THRESHOLD
            )
            if needs_refresh and i > 0:
                reason = "consecutive failures" if consecutive_fails >= _CONSECUTIVE_FAIL_THRESHOLD else "periodic"
                dl_page.close()
                try:
                    page.goto(
                        self.BASE_URL + "/Pages/communications/circulars.aspx",
                        wait_until="networkidle", timeout=60000,
                    )
                    time.sleep(3)
                except Exception:
                    pass
                dl_page = page.context.new_page()
                consecutive_fails = 0
                print(f"  [session refresh] Refreshed browser session at {i+1}/{len(pdf_items)} ({reason})")

            print(f"  [{i+1}/{len(pdf_items)}] {item['label']}...")

            all_text = []
            method = "pdfplumber"
            for doc_url in pdf_links:
                text = self._fetch_with_challenge(
                    dl_page, doc_url, item["link"], extract_text_from_pdf_with_metadata
                )
                if text:
                    if isinstance(text, tuple):
                        text, meta = text
                        method = meta.get("method", method)
                    else:
                        method = "html"
                    all_text.append(text)

            content = "\n\n".join(all_text)
            if content:
                consecutive_fails = 0
                if item["record"]:
                    item["record"]["content"] = content
                    item["record"]["extraction_status"] = "success"
                    item["record"]["extraction_method"] = method
                if config.DATABASE_URL:
                    self._update_record_content(item["link"], {
                        "content": content,
                        "extraction_status": "success",
                        "extraction_method": method,
                    })
                updated += 1
                if updated % 25 == 0:
                    print(f"  [deep checkpoint] {updated}/{len(pdf_items)} records with content")
            else:
                failed += 1
                consecutive_fails += 1

        dl_page.close()
        print(f"  Deep crawl complete: {updated} success, {failed} failed out of {len(pdf_items)}")

    def _fetch_with_challenge(self, dl_page, doc_url, document_link, pdf_extractor):
        """Navigate to a URL, resolve the AES challenge, and extract content.

        Retries once on failure — the first attempt warms the AES challenge cookie,
        so the second attempt often succeeds immediately.

        Returns:
          - (text, metadata) tuple for PDFs
          - text string for HTM pages
          - None on failure
        """
        is_pdf = doc_url.lower().endswith(".pdf")

        for attempt in range(2):
            try:
                if is_pdf:
                    result = self._fetch_pdf_with_challenge(dl_page, doc_url, document_link, pdf_extractor)
                else:
                    result = self._fetch_htm_with_challenge(dl_page, doc_url, document_link)

                if result is not None:
                    return result

                if attempt == 0:
                    # Warm up session before retry — navigate to a known page
                    # to refresh AES cookies, then retry the actual URL
                    try:
                        dl_page.goto(
                            self.BASE_URL + "/Pages/communications/circulars.aspx",
                            wait_until="networkidle", timeout=30000,
                        )
                        time.sleep(3)
                    except Exception:
                        pass
                    print(f"  [RETRY] {doc_url.split('/')[-1]} — retrying after session warm-up...")
                    continue
            except Exception as e:
                if attempt == 0:
                    try:
                        dl_page.goto(
                            self.BASE_URL + "/Pages/communications/circulars.aspx",
                            wait_until="networkidle", timeout=30000,
                        )
                        time.sleep(3)
                    except Exception:
                        pass
                    print(f"  [RETRY] {doc_url.split('/')[-1]} error: {e} — retrying after session warm-up...")
                    continue
                print(f"  [ERROR] {doc_url.split('/')[-1]}: {e}")
                self._log_extraction_failure(document_link, doc_url, "aes_challenge", str(e))

        return None

    def _fetch_htm_with_challenge(self, dl_page, doc_url, document_link):
        """Fetch .htm page: navigate → wait for AES challenge → extract HTML."""
        dl_page.goto(doc_url, wait_until="domcontentloaded", timeout=30000)
        # AES challenge needs ~8s to execute JS, set cookie, and reload
        time.sleep(8)

        html_content = dl_page.content()
        if len(html_content) < 200:
            return None

        soup = BeautifulSoup(html_content, "lxml")
        text = self._extract_html_content(soup)
        if text and len(text.strip()) > 50:
            return text
        return None

    def _fetch_pdf_with_challenge(self, dl_page, doc_url, document_link, pdf_extractor):
        """Fetch .pdf: navigate → resolve AES challenge → capture PDF from viewer.

        The AES challenge loops 503→aes.min.js→503→... (10-22 times, 10-20s).
        After challenge resolves:
        1. 200 on original URL — but Chrome PDF viewer intercepts, body is viewer HTML
        2. Viewer loads (pdf_embedder.css, index.html, main.js, etc.)
        3. 200 on a UUID URL — Chrome viewer re-fetches the actual PDF bytes
        We capture the UUID response by checking for %PDF magic bytes.

        Fallback: if response listener misses the PDF (Chrome viewer intercepted),
        use browser-context fetch() to download directly (AES cookie is already set).
        """
        captured = {}

        def on_response(response):
            if response.status == 200 and "body" not in captured:
                ct = response.headers.get("content-type", "")
                if "pdf" in ct or "octet-stream" in ct:
                    try:
                        body = response.body()
                        # Filter: Chrome viewer intercepts the first 200 and returns HTML.
                        # The REAL PDF comes from a UUID URL with actual %PDF bytes.
                        if body[:4] == b"%PDF" and len(body) > 1000:
                            captured["body"] = body
                    except Exception:
                        pass

        dl_page.on("response", on_response)
        try:
            try:
                dl_page.goto(doc_url, wait_until="commit", timeout=15000)
            except Exception:
                pass  # Timeout OK — challenge loops in background

            # Wait for: AES challenge loops (10-20s) + viewer load + UUID re-fetch
            for _ in range(45):
                if "body" in captured:
                    break
                time.sleep(1)

            # Fallback: if response listener didn't capture PDF, try fetch() directly.
            # If the AES challenge resolved (cookie is set), fetch() returns 200 immediately.
            if "body" not in captured:
                print(f"  [WARN] No PDF via listener for {doc_url.split('/')[-1]}, trying fetch() fallback...")
                try:
                    b64 = dl_page.evaluate(JS_FETCH_BASE64, doc_url)
                    pdf_bytes = base64.b64decode(b64)
                    if pdf_bytes[:4] == b"%PDF" and len(pdf_bytes) > 1000:
                        captured["body"] = pdf_bytes
                        print(f"    fetch() fallback OK: {len(pdf_bytes)} bytes")
                except Exception as e:
                    print(f"    fetch() fallback failed: {e}")

            if "body" not in captured:
                print(f"  [WARN] No PDF for {doc_url.split('/')[-1]} (challenge didn't resolve in 45s)")
                return None

            pdf_bytes = captured["body"]
            self._cache_raw_content(document_link, doc_url, "pdf", pdf_bytes)
            text, meta = pdf_extractor(pdf_bytes)
            if text:
                return (text, meta)
            return None

        finally:
            dl_page.remove_listener("response", on_response)

    def _load_db_records_missing_content(self):
        """Load existing DB records that have pdf_links but no content."""
        conn = _get_db_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT link, pdf_links, circular_number
                       FROM scraped_documents
                       WHERE crawler = %s
                         AND (content IS NULL OR content = '')
                         AND pdf_links IS NOT NULL
                         AND pdf_links != '[]'::jsonb
                         AND pdf_links != 'null'::jsonb""",
                    (self.name,),
                )
                rows = cur.fetchall()
                items = []
                for link, pdf_links_raw, circ_num in rows:
                    if isinstance(pdf_links_raw, str):
                        pdf_links = json.loads(pdf_links_raw)
                    elif isinstance(pdf_links_raw, list):
                        pdf_links = pdf_links_raw
                    else:
                        continue
                    if pdf_links:
                        items.append({
                            "link": link,
                            "pdf_links": pdf_links,
                            "label": circ_num or link.split("/")[-1][:40],
                        })
                return items
        except Exception as e:
            print(f"  [WARN] Failed to load DB records: {e}")
            return []
        finally:
            conn.close()

    def _deep_crawl_missing_content(self):
        """Override: skip base class requests-based deep crawl (SharePoint returns 503).
        All deep crawling is handled via Playwright in _deep_crawl_pdfs().
        """
        pass

    def parse_detail_page(self, soup, url):
        """Not primarily used — CBDT deep crawl handled via _deep_crawl_pdfs."""
        return {}
