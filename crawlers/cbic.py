"""Crawler for CBIC (Central Board of Indirect Taxes and Customs) circulars and notifications.

CBIC Tax Information Portal (taxinformation.cbic.gov.in) is an Angular SPA
backed by a JHipster/Spring Boot REST API. All data is fetched via JSON APIs.

Document types: Circulars, Notifications, Orders, Instructions
Tax types: GST, Customs, Central Excise, Service Tax
"""

import base64
import json
import gc

import config
from crawlers.base import BaseCrawler

# SSL certs on CBIC are self-signed
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


TAX_TYPES = {
    1000001: "GST",
    1000002: "Customs",
    1000003: "Central Excise",
    1000004: "Service Tax",
}

# Notification categories per tax type (discovered via API probing)
NOTIFICATION_CATEGORIES = {
    1000001: [
        "Central Tax", "Central Tax (Rate)",
        "Integrated Tax", "Integrated Tax (Rate)",
        "Union Territory Tax", "Union Territory Tax (Rate)",
        "Compensation Cess", "Compensation Cess (Rate)",
    ],
    1000002: ["Tariff", "Non Tariff", "Anti Dumping Duty", "CVD"],
    1000003: ["Tariff", "Non Tariff"],
    1000004: [],  # Service Tax notification categories unknown/broken
}

BASE_URL = "https://taxinformation.cbic.gov.in"
API_URL = f"{BASE_URL}/api"


class CBICCrawler(BaseCrawler):
    """Crawls circulars, notifications, orders, and instructions from CBIC."""

    name = "cbic"

    def __init__(self):
        super().__init__()
        self.session.verify = False

    def fetch_json(self, url):
        """Fetch a URL and return parsed JSON, or None on failure."""
        resp = self.fetch(url)
        if not resp:
            return None
        try:
            return resp.json()
        except Exception as e:
            print(f"  [ERROR] JSON parse failed for {url[:80]}: {e}")
            return None

    def crawl(self):
        for tax_id, tax_name in TAX_TYPES.items():
            print(f"\n  --- {tax_name} (taxId={tax_id}) ---")
            self._crawl_circulars(tax_id, tax_name)
            self._crawl_notifications(tax_id, tax_name)
        self._crawl_orders()
        self._crawl_instructions()

    def _crawl_circulars(self, tax_id, tax_name):
        url = f"{API_URL}/cbic-circular-msts/fetchAllCircularsByTaxId/{tax_id}"
        print(f"  Fetching {tax_name} circulars...")
        data = self.fetch_json(url)
        if not data:
            return
        count = 0
        for item in data:
            record = self._parse_circular(item, tax_name)
            if record and record["link"] not in self.existing_links:
                self.results.append(record)
                count += 1
        print(f"  {tax_name} circulars: {count} new records")
        if count:
            self.save_progress()

    def _crawl_notifications(self, tax_id, tax_name):
        categories = NOTIFICATION_CATEGORIES.get(tax_id, [])
        if not categories:
            print(f"  Skipping {tax_name} notifications (no known categories)")
            return
        for category in categories:
            url = f"{API_URL}/cbic-notification-msts/fetchNotificationByCategory/{tax_id}/{category}"
            print(f"  Fetching {tax_name} notifications [{category}]...")
            data = self.fetch_json(url)
            if not data:
                continue
            count = 0
            for item in data:
                record = self._parse_notification(item, tax_name, category)
                if record and record["link"] not in self.existing_links:
                    self.results.append(record)
                    count += 1
            print(f"  {tax_name} [{category}]: {count} new records")
            if count:
                self.save_progress()

    def _crawl_orders(self):
        print(f"\n  --- Orders ---")
        page = 0
        total = 0
        while True:
            url = f"{API_URL}/cbic-order-msts?page={page}&size=500&sort=id,desc"
            data = self.fetch_json(url)
            if not data:
                break
            count = 0
            for item in data:
                record = self._parse_order(item)
                if record and record["link"] not in self.existing_links:
                    self.results.append(record)
                    count += 1
            total += count
            print(f"  Orders page {page}: {len(data)} fetched, {count} new")
            if count:
                self.save_progress()
            if len(data) < 500:
                break
            page += 1
        print(f"  Orders total: {total} new records")

    def _crawl_instructions(self):
        print(f"\n  --- Instructions ---")
        page = 0
        total = 0
        while True:
            url = f"{API_URL}/cbic-instruction-msts?page={page}&size=500&sort=id,desc"
            data = self.fetch_json(url)
            if not data:
                break
            count = 0
            for item in data:
                record = self._parse_instruction(item)
                if record and record["link"] not in self.existing_links:
                    self.results.append(record)
                    count += 1
            total += count
            print(f"  Instructions page {page}: {len(data)} fetched, {count} new")
            if count:
                self.save_progress()
            if len(data) < 500:
                break
            page += 1
        print(f"  Instructions total: {total} new records")

    # --- Record parsers ---

    def _parse_circular(self, item, tax_name):
        circular_no = item.get("circularNo") or ""
        name = item.get("circularName") or ""
        if not name:
            return None
        date = self._parse_date(item.get("circularDt"))
        category = item.get("circularCategory") or ""
        doc_path = self._normalize_path(item.get("docFilePath") or "")
        link = self._make_pdf_url(doc_path) if doc_path else f"{BASE_URL}/view-pdf/{item['id']}/ENG/Circulars"
        return {
            "source": f"CBIC ({tax_name})",
            "title": name,
            "date": date,
            "department": f"CBIC - {tax_name}",
            "link": link,
            "details": f"{circular_no} | {category}".strip(" |"),
            "circular_number": circular_no,
            "pdf_links": [link] if doc_path else [],
            "doc_type": "Circular",
            "tax_type": tax_name,
            "category": category,
            "cbic_id": item.get("id"),
        }

    def _parse_notification(self, item, tax_name, category):
        notif_no = item.get("notificationNo") or ""
        name = item.get("notificationName") or item.get("notificationNameToBeDisplay") or ""
        if not name:
            return None
        date = self._parse_date(item.get("notificationDt"))
        doc_path = self._normalize_path(item.get("docFilePath") or "")
        link = self._make_pdf_url(doc_path) if doc_path else f"{BASE_URL}/view-pdf/{item['id']}/ENG/Notifications"
        return {
            "source": f"CBIC ({tax_name})",
            "title": name,
            "date": date,
            "department": f"CBIC - {tax_name}",
            "link": link,
            "details": f"{notif_no} | {category}".strip(" |"),
            "circular_number": notif_no,
            "pdf_links": [link] if doc_path else [],
            "doc_type": "Notification",
            "tax_type": tax_name,
            "category": category,
            "cbic_id": item.get("id"),
        }

    def _parse_order(self, item):
        order_no = item.get("orderNo") or ""
        name = item.get("orderName") or ""
        if not name:
            return None
        tax_id = (item.get("tax") or {}).get("id")
        tax_name = TAX_TYPES.get(tax_id, "Unknown")
        date = self._parse_date(item.get("orderDt"))
        category = item.get("orderCategory") or ""
        doc_path = self._normalize_path(item.get("docFilePath") or "")
        link = self._make_pdf_url(doc_path) if doc_path else f"{BASE_URL}/view-pdf/{item['id']}/ENG/Orders"
        return {
            "source": f"CBIC ({tax_name})",
            "title": name,
            "date": date,
            "department": f"CBIC - {tax_name}",
            "link": link,
            "details": f"{order_no} | {category}".strip(" |"),
            "circular_number": order_no,
            "pdf_links": [link] if doc_path else [],
            "doc_type": "Order",
            "tax_type": tax_name,
            "category": category,
            "cbic_id": item.get("id"),
        }

    def _parse_instruction(self, item):
        inst_no = item.get("instructionNo") or ""
        name = item.get("instructionName") or ""
        if not name:
            return None
        tax_id = (item.get("tax") or {}).get("id")
        tax_name = TAX_TYPES.get(tax_id, "Unknown")
        date = self._parse_date(item.get("instructionDt"))
        category = item.get("instructionCategory") or ""
        doc_path = self._normalize_path(item.get("docFilePath") or "")
        link = self._make_pdf_url(doc_path) if doc_path else f"{BASE_URL}/view-pdf/{item['id']}/ENG/Instructions"
        return {
            "source": f"CBIC ({tax_name})",
            "title": name,
            "date": date,
            "department": f"CBIC - {tax_name}",
            "link": link,
            "details": f"{inst_no} | {category}".strip(" |"),
            "circular_number": inst_no,
            "pdf_links": [link] if doc_path else [],
            "doc_type": "Instruction",
            "tax_type": tax_name,
            "category": category,
            "cbic_id": item.get("id"),
        }

    # --- PDF content extraction ---

    def parse_detail_page(self, soup, url):
        """Not used for CBIC — content is fetched via API/PDF, not HTML."""
        return {}

    def crawl_details(self):
        """Override: fetch PDF content via CBIC's base64 PDF API."""
        if not self.results:
            return
        print(f"  Deep crawling {len(self.results)} CBIC documents...")
        updated = 0
        for i, record in enumerate(self.results):
            if record.get("content"):
                continue
            pdf_links = record.get("pdf_links", [])
            if not pdf_links:
                continue
            pdf_url = pdf_links[0]
            if not pdf_url.startswith(BASE_URL + "/content/pdf/"):
                continue
            print(f"  [{i+1}/{len(self.results)}] {record.get('circular_number', '')[:40]}...")
            content = self._fetch_pdf_content(pdf_url, record.get("link", ""))
            if content:
                record["content"] = content
                record["extraction_status"] = "success"
                record["extraction_method"] = "pdfplumber"
                if config.DATABASE_URL:
                    self._update_record_content(record["link"], {
                        "content": content,
                        "pdf_links": pdf_links,
                        "circular_number": record.get("circular_number", ""),
                        "extraction_status": "success",
                        "extraction_method": "pdfplumber",
                    })
                updated += 1
                if updated % 25 == 0:
                    print(f"  [deep checkpoint] {updated} records with content")
        if updated:
            print(f"  Deep crawl complete: {updated} records with content")

    def _fetch_pdf_content(self, pdf_url, document_link):
        """Fetch PDF via CBIC's base64 JSON endpoint and extract text."""
        resp = self.fetch(pdf_url)
        if not resp:
            return ""
        try:
            data = resp.json()
            b64 = data.get("data", "")
            if not b64:
                return ""
            pdf_bytes = base64.b64decode(b64)

            # Cache the raw PDF bytes and API JSON
            self._cache_raw_content(document_link, pdf_url, "json_api", resp.content)
            self._cache_raw_content(document_link, pdf_url + "#pdf", "pdf", pdf_bytes)

            from utils.pdf_extract import extract_text_from_pdf
            text = extract_text_from_pdf(pdf_bytes)
            del pdf_bytes
            gc.collect()
            return text.strip()  # No truncation — removed [:10000] limit
        except Exception as e:
            print(f"    [ERROR] PDF extraction failed: {e}")
            self._log_extraction_failure(document_link, pdf_url, "cbic_pdf_extraction", str(e))
            return ""

    # --- Helpers ---

    @staticmethod
    def _normalize_path(path):
        """Convert backslash Windows paths to forward slashes."""
        return path.replace("\\", "/").strip() if path else ""

    @staticmethod
    def _make_pdf_url(doc_path):
        """Build the full PDF content URL from a document path."""
        if not doc_path:
            return ""
        return f"{BASE_URL}/content/pdf/{doc_path}"

    @staticmethod
    def _parse_date(dt_str):
        """Parse ISO 8601 date string to DD-Mon-YYYY format."""
        if not dt_str:
            return ""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%d-%b-%Y")
        except Exception:
            return dt_str
