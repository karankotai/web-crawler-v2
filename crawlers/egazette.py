"""Crawler for eGazette (The Gazette of India) notifications.

egazette.gov.in is an ASP.NET site that uses cookieless sessions (session ID
embedded in the URL) and __doPostBack for navigation and pagination.

Flow:
  1. GET homepage → extract session token from URL
  2. POST homepage with __doPostBack('lnk_Extra_All') → Extra Ordinary listing
  3. Parse the ASP.NET GridView table, paginate with __doPostBack('gvGazetteList','Page$N')
  4. Repeat for Weekly gazettes via __doPostBack('lnk_Week_All')

PDFs are available at: https://egazette.gov.in/WriteReadData/{year}/{number}.pdf
where {year} and {number} are extracted from the Gazette ID
(e.g. CG-DL-E-16022026-270189 → 2026/270189.pdf).
"""

import re
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


# Gazette types to crawl (homepage postback target → label)
GAZETTE_TYPES = [
    ("lnk_Extra_All", "Extra Ordinary"),
    ("lnk_Week_All", "Weekly"),
]


class EGazetteCrawler(BaseCrawler):
    """Crawls gazette notifications from egazette.gov.in"""

    name = "egazette_notifications"
    BASE_URL = "https://egazette.gov.in"

    def crawl(self):
        for postback_target, label in GAZETTE_TYPES:
            self._crawl_gazette_type(postback_target, label)

    def _postback(self, url, form_data, referer):
        """POST an ASP.NET postback with the required Referer header."""
        return self.session.post(
            url, data=form_data, headers={"Referer": referer}, timeout=60,
        )

    def _crawl_gazette_type(self, postback_target, label):
        """Navigate to a gazette listing and paginate through all pages."""
        count = 0
        # Step 1: GET homepage to start a session
        print(f"  Loading eGazette homepage for {label} gazettes...")
        resp = self.fetch(self.BASE_URL)
        if not resp:
            return

        session_id = self._extract_session_id(resp.url)
        if not session_id:
            print("  [ERROR] Could not extract session ID from URL.")
            return
        base = f"{self.BASE_URL}/{session_id}"

        soup = self.parse_html(resp.text)
        form_data = self._get_hidden_fields(soup)

        # Step 2: POST to navigate to the listing page
        form_data["__EVENTTARGET"] = postback_target
        form_data["__EVENTARGUMENT"] = ""

        print(f"  Navigating to {label} gazette listing...")
        resp = self._postback(f"{base}/default.aspx", form_data, resp.url)
        if not resp or resp.status_code != 200 or "error" in resp.url.lower():
            print(f"  [ERROR] Failed to load {label} listing.")
            return

        # Step 3: Parse page 1 and paginate
        page_num = 1
        while page_num <= config.MAX_PAGES:
            soup = self.parse_html(resp.text)
            rows = self._find_data_rows(soup)
            if not rows:
                break

            found = 0
            for row in rows:
                record = self._parse_row(row, label)
                if record:
                    self.results.append(record)
                    found += 1
                    count += 1

            print(f"  {label} page {page_num}: found {found} gazettes.")
            self.save_progress()

            if found == 0:
                break

            # Check if next page exists
            next_page = page_num + 1
            has_next = self._has_page_link(soup, next_page)
            if not has_next:
                break

            # Navigate to next page via postback
            form_data = self._get_hidden_fields(soup)
            form_data["__EVENTTARGET"] = "gvGazetteList"
            form_data["__EVENTARGUMENT"] = f"Page${next_page}"

            form_action = soup.find("form").get("action", "")
            post_url = f"{base}/{form_action.lstrip('./')}"

            prev_url = resp.url
            resp = self._postback(post_url, form_data, prev_url)
            if not resp or resp.status_code != 200 or "error" in resp.url.lower():
                break

            page_num += 1

        print(f"  Total {label} gazettes collected so far: {len(self.results)}")

    def _extract_session_id(self, url):
        """Extract the cookieless session token from the URL, e.g. (S(abc123))."""
        match = re.search(r"\(S\([^)]+\)\)", url)
        return match.group() if match else None

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

    def _find_data_rows(self, soup):
        """Find the data table and return its data rows (skip header and pager)."""
        for table in soup.find_all("table"):
            header_row = table.find("tr")
            if not header_row:
                continue
            cells = header_row.find_all(["th", "td"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            if "S. No." in cell_texts and "Gazette ID" in cell_texts:
                rows = table.find_all("tr")
                # Skip header (row 0) and pager (last row if it has page links)
                data_rows = []
                for row in rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) == 10:
                        data_rows.append(row)
                return data_rows
        return []

    def _has_page_link(self, soup, page_num):
        """Check if a pagination link exists for the given page number."""
        for a in soup.find_all("a", href=True):
            if f"Page${page_num}" in a["href"]:
                return True
        return False

    def _parse_row(self, row, gazette_type):
        """Parse a GridView data row into a gazette record.

        Columns: S.No. | Ministry | Department | Office | Subject |
                 Part & Section | Issue Date | Publish Date | Gazette ID | Download
        """
        cells = row.find_all("td")
        if len(cells) < 10:
            return None

        ministry = cells[1].get_text(strip=True)
        department = cells[2].get_text(strip=True)
        office = cells[3].get_text(strip=True)
        subject = cells[4].get_text(strip=True)
        part_section = cells[5].get_text(strip=True)
        issue_date = cells[6].get_text(strip=True)
        publish_date = cells[7].get_text(strip=True)
        gazette_id = cells[8].get_text(strip=True)
        file_size = cells[9].get_text(strip=True)

        if not gazette_id:
            return None

        pdf_url = self._build_pdf_url(gazette_id)

        return {
            "source": f"eGazette ({gazette_type})",
            "title": subject,
            "date": publish_date,
            "department": ministry,
            "link": pdf_url,
            "gazette_id": gazette_id,
            "ministry": ministry,
            "dept": department,
            "office": office,
            "part_section": part_section,
            "issue_date": issue_date,
            "publish_date": publish_date,
            "file_size": file_size,
        }

    def _build_pdf_url(self, gazette_id):
        """Build a direct PDF download URL from a Gazette ID.

        Gazette ID format: CG-DL-E-16022026-270189
        PDF URL: https://egazette.gov.in/WriteReadData/2026/270189.pdf
        """
        parts = gazette_id.rsplit("-", 1)
        if len(parts) != 2:
            return ""
        number = parts[1]

        # Extract year from the date portion (e.g. 16022026 -> 2026)
        date_segment = gazette_id.split("-")[3] if len(gazette_id.split("-")) >= 5 else ""
        year = date_segment[-4:] if len(date_segment) >= 4 else ""

        if not year or not number:
            return ""

        return f"{self.BASE_URL}/WriteReadData/{year}/{number}.pdf"

    def parse_detail_page(self, soup, url):
        """Not used — gazette PDFs are downloaded directly via _build_pdf_url."""
        return {}

    def crawl_details(self):
        """Download gazette PDFs and extract text (deep crawl)."""
        if not self.results:
            return

        pdf_results = [r for r in self.results if r.get("link")]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} gazette PDFs...")
        for i, record in enumerate(pdf_results):
            pdf_url = record["link"]
            print(f"  [{i+1}/{len(pdf_results)}] {record['gazette_id']}")
            resp = self.fetch(pdf_url)
            if not resp:
                continue
            if resp.content[:4] != b"%PDF":
                print(f"    [WARN] Not a PDF, skipping.")
                continue
            try:
                from utils.pdf_extract import extract_text_from_pdf
                record["content"] = extract_text_from_pdf(resp.content)
                record["pdf_links"] = [pdf_url]
                print(f"    OK: {len(pdf.pages)} pages, {len(record['content'])} chars")
            except Exception as e:
                print(f"    [ERROR] Failed to parse PDF: {e}")
