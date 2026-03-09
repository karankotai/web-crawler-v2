"""Crawler for IBBI (Insolvency and Bankruptcy Board of India).

ibbi.gov.in uses PHP with simple HTML tables. PDF links are in onclick handlers:
onclick="javascript:newwindow1('https://ibbi.gov.in//uploads/legalframwork/HASH.pdf')"

Two table formats:
  5 columns: Sr. No. | Date | Subject | PDF(English) | PDF(Hindi)  (circulars, regulations, guidelines)
  3 columns: Sr. No. | Date | Subject (with PDF link inside)       (notifications)

Pagination: /legal-framework/circulars?page=2 (20 items/page)
Regulations URL: /legal-framework/updated (not /regulations)
"""

import re
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


IBBI_SECTIONS = [
    {
        "path": "/en/legal-framework/circulars",
        "label": "circulars",
        "doc_type": "Circular",
    },
    {
        "path": "/en/legal-framework/updated",
        "label": "regulations",
        "doc_type": "Regulation",
    },
    {
        "path": "/en/legal-framework/notifications",
        "label": "notifications",
        "doc_type": "Notification",
    },
    {
        "path": "/en/legal-framework/guidelines",
        "label": "guidelines",
        "doc_type": "Guideline",
    },
]


class IBBICrawler(BaseCrawler):
    """Crawls circulars and regulations from ibbi.gov.in"""

    name = "ibbi"
    BASE_URL = "https://ibbi.gov.in"

    def crawl(self):
        for section in IBBI_SECTIONS:
            self._crawl_section(section)

    def _crawl_section(self, section):
        """Crawl an IBBI section with pagination."""
        label = section["label"]
        doc_type = section["doc_type"]
        base_path = section["path"]

        page = 1
        while page <= config.MAX_PAGES:
            # Pagination links omit /en/ prefix, so use both forms
            if page > 1:
                # Pagination uses /legal-framework/circulars?page=N (no /en/)
                path_no_en = base_path.replace("/en/", "/")
                url = f"{self.BASE_URL}{path_no_en}?page={page}"
            else:
                url = f"{self.BASE_URL}{base_path}"

            print(f"  Fetching IBBI {label} page {page}...")
            resp = self.fetch(url)
            if not resp:
                break

            soup = self.parse_html(resp.text)
            before = len(self.results)
            self._parse_table(soup, label, doc_type)

            found = len(self.results) - before
            print(f"  IBBI {label} page {page}: {found} records")

            if found > 0:
                self.save_progress()
            else:
                break

            # Check for next page
            if not self._has_next_page(soup, page):
                break
            page += 1

        total = len([r for r in self.results if r.get("doc_type") == doc_type])
        print(f"  Total IBBI {label}: {total}")

    def _parse_table(self, soup, label, doc_type):
        """Parse IBBI table rows.

        Two formats:
          5-col (circulars/regulations/guidelines):
            td — Sr.No. | td — Date | td — Subject | td — PDF(English) | td — PDF(Hindi)
          3-col (notifications):
            td — Sr.No. | td — Date | td — Subject (PDF link embedded inside)
        """
        table = soup.find("table")
        if not table:
            return

        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Date
            date = cells[1].get_text(strip=True)

            # Title (subject) — clean up PDF size text like "(1.52 MB)"
            raw_title = cells[2].get_text(strip=True)
            title = re.sub(r'\(\d+(?:\.\d+)?\s*[KMG]?B\)\s*$', '', raw_title).strip()
            if not title or len(title) < 5:
                continue

            # Extract PDF URLs from onclick handlers — search ALL cells
            # (5-col: PDFs in cells[3:], 3-col: PDF embedded in cells[2])
            pdf_links = []
            search_cells = cells[3:] if len(cells) >= 5 else cells[2:]
            for cell in search_cells:
                for a in cell.find_all("a"):
                    onclick = a.get("onclick", "")
                    pdf_match = re.search(r"newwindow1\(['\"]([^'\"]+\.pdf)['\"]", onclick, re.I)
                    if pdf_match:
                        pdf_url = pdf_match.group(1)
                        if not pdf_url.startswith("http"):
                            pdf_url = urljoin(self.BASE_URL, pdf_url)
                        pdf_links.append(pdf_url)

            # Use first PDF URL as unique link, fallback to generated URL
            link = pdf_links[0] if pdf_links else f"{self.BASE_URL}/legal-framework/{label}/{date}"

            if link not in self.existing_links:
                self.results.append({
                    "source": f"IBBI ({label})",
                    "title": title,
                    "date": date,
                    "department": "IBBI",
                    "link": link,
                    "pdf_links": pdf_links,
                    "doc_type": doc_type,
                })

    def _has_next_page(self, soup, current_page):
        """Check if there's a next page in pagination."""
        # IBBI uses ul.pagination with li > a[href="/legal-framework/X?page=N"]
        for a in soup.select("ul.pagination a"):
            href = a.get("href", "")
            if f"page={current_page + 1}" in href:
                return True
            text = a.get_text(strip=True)
            if text == ">":
                # "Next" button — check it's not disabled
                parent_li = a.parent
                if parent_li and "disabled" not in " ".join(parent_li.get("class", [])):
                    return True
        return False

    def parse_detail_page(self, soup, url):
        """IBBI circulars are direct PDFs — no detail page parsing needed."""
        return {}

    def crawl_details(self):
        """Download PDFs and extract text."""
        if not self.results:
            return

        pdf_results = [r for r in self.results if r.get("pdf_links") and not r.get("content")]
        if not pdf_results:
            return

        print(f"  Deep crawling {len(pdf_results)} IBBI PDFs...")
        updated = 0
        for i, record in enumerate(pdf_results):
            pdf_links = record.get("pdf_links", [])
            if not pdf_links:
                continue

            print(f"  [{i+1}/{len(pdf_results)}] {record.get('title', '')[:50]}...")
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
            print(f"  Deep crawl complete: {updated} IBBI records with content")
