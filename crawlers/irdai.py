"""Crawler for IRDAI (Insurance Regulatory and Development Authority of India) circulars.

IRDAI uses a Liferay-based portal. Circulars are listed in a table with pagination
controlled via query parameters. Each page shows 60 items (max delta).
"""

import io
from urllib.parse import urljoin

import pdfplumber

from crawlers.base import BaseCrawler


class IRDAICrawler(BaseCrawler):
    """Crawls circulars from irdai.gov.in"""

    name = "irdai_circulars"
    BASE_URL = "https://irdai.gov.in"
    PORTLET_NS = "_com_irdai_document_media_IRDAIDocumentMediaPortlet_"
    CIRCULARS_URL = (
        f"{BASE_URL}/circulars"
        f"?p_p_id=com_irdai_document_media_IRDAIDocumentMediaPortlet"
        f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        f"&{PORTLET_NS}delta=60"
        f"&{PORTLET_NS}resetCur=false"
    )

    MAX_PAGES = 15  # safety limit

    def crawl(self):
        seen_links = set()
        page = 1
        while page <= self.MAX_PAGES:
            url = f"{self.CIRCULARS_URL}&{self.PORTLET_NS}cur={page}"
            print(f"  Fetching IRDAI circulars page {page}...")
            resp = self.fetch(url)
            if not resp:
                break

            soup = self.parse_html(resp.text)
            # Data rows live inside <tbody class="table-data">
            tbody = soup.find("tbody", class_="table-data")
            if not tbody:
                print("  No data table found on page.")
                break
            rows = tbody.find_all("tr")

            found = 0
            for row in rows:
                record = self._parse_row(row)
                if not record:
                    continue
                # IRDAI pagination loops instead of returning empty;
                # stop when we see links we already collected.
                if record["link"] in seen_links:
                    continue
                seen_links.add(record["link"])
                self.results.append(record)
                found += 1

            print(f"  Page {page}: found {found} new circulars.")
            if found == 0:
                break

            page += 1

        print(f"  Total IRDAI circulars found: {len(self.results)}")

    def _parse_row(self, row):
        """Parse a single table row into a circular record.

        Columns (by CSS class):
          0  nosort              - checkbox (skip)
          1  table-col-archive   - Archive / Non-Archived
          2  table-col-shortDesc - plain-text title
          3  table-col-subTitle  - linked title (detail page)
          4  table-col-lastUpdated - date (dd-mm-yyyy)
          5  table-col-documents - PDF download link
        """
        # Title + detail link (cell with class table-col-subTitle)
        title_cell = row.find("td", class_="table-col-subTitle")
        if not title_cell:
            return None
        link_tag = title_cell.find("a", href=True)
        if not link_tag:
            return None
        title = link_tag.get_text(strip=True)
        if not title or len(title) < 5:
            return None
        detail_link = link_tag["href"]
        if not detail_link.startswith("http"):
            detail_link = urljoin(self.BASE_URL, detail_link)

        # Archive status
        archive_cell = row.find("td", class_="table-col-archive-nonarchive")
        archive_status = archive_cell.get_text(strip=True) if archive_cell else ""

        # Date
        date_cell = row.find("td", class_="table-col-lastUpdated")
        date = date_cell.get_text(strip=True) if date_cell else ""

        # PDF download link
        pdf_link = ""
        doc_cell = row.find("td", class_="table-col-documents")
        if doc_cell:
            pdf_tag = doc_cell.find("a", href=True)
            if pdf_tag:
                pdf_link = pdf_tag["href"]
                if not pdf_link.startswith("http"):
                    pdf_link = urljoin(self.BASE_URL, pdf_link)

        return {
            "source": "IRDAI",
            "title": title,
            "date": date,
            "department": "IRDAI",
            "link": detail_link,
            "pdf_link": pdf_link,
            "archive_status": archive_status,
        }

    def parse_detail_page(self, soup, url):
        """Extract content from an IRDAI circular detail page.

        The detail page embeds the PDF in an iframe. We extract the PDF URL
        and download it to get the full text.
        """
        detail = {"content": "", "pdf_links": []}

        # Look for embedded PDF iframe
        iframe = soup.find("iframe", id=lambda x: x and "pdfIfrme" in x)
        if iframe and iframe.get("src"):
            pdf_url = iframe["src"]
            if not pdf_url.startswith("http"):
                pdf_url = urljoin(url, pdf_url)
            detail["pdf_links"].append(pdf_url)

        # Also check for direct PDF download links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower() and "download=true" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                if href not in detail["pdf_links"]:
                    detail["pdf_links"].append(href)

        # Download first available PDF and extract text
        if detail["pdf_links"]:
            detail["content"] = self._extract_pdf_text(detail["pdf_links"][0])

        return detail

    def _extract_pdf_text(self, pdf_url):
        """Download a PDF and extract its text content."""
        print(f"    Downloading PDF: {pdf_url.split('/')[-1][:60]}")
        resp = self.fetch(pdf_url)
        if not resp:
            return ""
        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            pdf.close()
            return "\n\n".join(pages_text)
        except Exception as e:
            print(f"    [ERROR] Failed to parse PDF: {e}")
            return ""
