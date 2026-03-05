"""Crawler for MCA (Ministry of Corporate Affairs) circulars and notifications.

MCA uses Akamai bot protection, so we need a headless browser (Playwright)
to bypass it. The circular data is loaded via AJAX calls to /bin/dms/tablist
when tabs are clicked on the homepage.

For deep crawl (PDF text extraction), we use the browser's own JS fetch()
to download PDFs — this inherits the session cookies needed to bypass Akamai.
"""

import base64
import json
import time

from playwright.sync_api import sync_playwright
from urllib.parse import quote

from crawlers.base import BaseCrawler
import config


# Tab CSS class -> label mapping for MCA homepage tabs
MCA_TABS = {
    "circulars-assign": "circulars",
    "notice-circular": "notices",
}

# JS snippet to fetch a URL as base64 from within the browser context
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


class MCACrawler(BaseCrawler):
    """Crawls circulars and notifications from mca.gov.in using a headless browser."""

    name = "mca_circulars"
    BASE_URL = "https://www.mca.gov.in"
    HOME_URL = f"{BASE_URL}/content/mca/global/en/home.html"

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

            print("  Loading MCA homepage (headless browser)...")
            page.goto(self.HOME_URL, wait_until="networkidle", timeout=45000)
            time.sleep(3)

            for tab_class, label in MCA_TABS.items():
                self._crawl_tab(page, tab_class, label)
                self.save_progress()
                time.sleep(config.DELAY_BETWEEN_REQUESTS)

            # Deep crawl: download PDFs and extract text while browser is still open
            if config.DEEP_CRAWL:
                self._deep_crawl_pdfs(page)

            browser.close()

    def crawl_details(self):
        """Override: MCA deep crawl is handled inside crawl() while browser is open."""
        pass

    def _crawl_tab(self, page, tab_class, label):
        """Click a tab and capture the API response."""
        print(f"  Clicking '{label}' tab...")
        try:
            js = f'document.querySelector("li.{tab_class} a.nav-link").click()'
            with page.expect_response("**/bin/dms/tablist**", timeout=15000) as resp_info:
                page.evaluate(js)
            resp = resp_info.value
            data = json.loads(resp.text())
            docs = json.loads(data.get("documentDetails", "[]"))
        except Exception as e:
            print(f"  [ERROR] Failed to load {label} tab: {e}")
            return

        print(f"  Found {len(docs)} {label}.")

        for doc in docs:
            title = doc.get("column1", "").strip()
            date = doc.get("column2", "").strip()
            doc_type = doc.get("docType", "").strip()
            doc_size = doc.get("docSize", "").strip()
            doc_id = doc.get("docID", "").strip()

            if not title:
                continue

            self.results.append({
                "source": f"MCA ({label})",
                "title": title,
                "date": date,
                "department": "Ministry of Corporate Affairs",
                "link": f"{self.BASE_URL}/bin/dms/getdocument?mds={quote(doc_id, safe='')}&type=open",
                "details": f"Type: {doc_type} | Size: {doc_size}",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "doc_size": doc_size,
            })

    def _deep_crawl_pdfs(self, page):
        """Download each PDF using browser JS fetch and extract text."""
        pdf_results = [r for r in self.results if r.get("doc_type", "").lower() == "pdf"]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} PDFs...")
        for i, record in enumerate(pdf_results):
            doc_id = record.get("doc_id", "")
            if not doc_id:
                continue

            double_encoded = quote(doc_id, safe="")
            url = f"{self.BASE_URL}/bin/dms/getdocument?mds={double_encoded}&type=open"

            print(f"  [{i+1}/{len(pdf_results)}] Downloading PDF...")
            try:
                b64_data = page.evaluate(JS_FETCH_BASE64, url)
                pdf_bytes = base64.b64decode(b64_data)

                if len(pdf_bytes) < 500:
                    print(f"    [WARN] PDF too small ({len(pdf_bytes)} bytes), skipping.")
                    continue

                from utils.pdf_extract import extract_text_from_pdf
                record["content"] = extract_text_from_pdf(pdf_bytes)
                record["pdf_links"] = [url]
                print(f"    OK: {len(pdf.pages)} pages, {len(record['content'])} chars")
            except Exception as e:
                print(f"    [ERROR] Failed: {e}")

            time.sleep(config.DELAY_BETWEEN_REQUESTS)
