"""Crawler for SEBI (Securities and Exchange Board of India) circulars."""

import io
from urllib.parse import urljoin

import pdfplumber

from crawlers.base import BaseCrawler


class SEBICrawler(BaseCrawler):
    """Crawls circulars from sebi.gov.in"""

    name = "sebi_circulars"
    BASE_URL = "https://www.sebi.gov.in"
    # ssid=7 = Circulars, ssid=6 = Master Circulars, ssid=5 = Guidelines
    CIRCULARS_URL = f"{BASE_URL}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0"
    MASTER_CIRCULARS_URL = f"{BASE_URL}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0"

    def crawl(self):
        self._crawl_listing_page(self.CIRCULARS_URL, "circulars")
        self._crawl_listing_page(self.MASTER_CIRCULARS_URL, "master circulars")

    def parse_detail_page(self, soup, url):
        """Extract full content from a SEBI circular detail page.

        SEBI embeds the actual circular as a PDF inside an iframe.
        This method extracts the PDF URL, downloads it, and pulls out the text.
        """
        detail = {"content": "", "circular_number": "", "date": "", "pdf_links": []}

        # Date from .m_section (format: "Feb 11, 2026")
        date_section = soup.select_one(".m_section")
        if date_section:
            text = date_section.get_text(strip=True)
            if "|" in text:
                detail["date"] = text.split("|")[0].strip()

        # Circular number from .id_area
        id_area = soup.select_one(".id_area")
        if id_area:
            text = id_area.get_text(strip=True)
            detail["circular_number"] = text.replace("Circular No.:", "").strip()

        # Extract PDF URL from the iframe
        # iframe src: ../../../web/?file=https://www.sebi.gov.in/sebi_data/attachdocs/...pdf
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")
            if "file=" in src:
                pdf_url = src.split("file=", 1)[1].split("&")[0]
                if pdf_url and pdf_url not in detail["pdf_links"]:
                    detail["pdf_links"].append(pdf_url)

        # Also check direct anchor PDF links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                if href not in detail["pdf_links"]:
                    detail["pdf_links"].append(href)

        # Download the PDF and extract text
        if detail["pdf_links"]:
            pdf_url = detail["pdf_links"][0]
            detail["content"] = self._extract_pdf_text(pdf_url)

        return detail

    def _extract_pdf_text(self, pdf_url):
        """Download a PDF and extract its text content."""
        print(f"    Downloading PDF: {pdf_url.split('/')[-1]}")
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

    def _crawl_listing_page(self, url, label):
        """Crawl a SEBI listing page."""
        print(f"  Fetching SEBI {label}...")
        resp = self.fetch(url)
        if not resp:
            return

        soup = self.parse_html(resp.text)

        rows = soup.select("table tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            link_tag = row.find("a", href=True)
            link = ""
            title = ""
            if link_tag:
                link = link_tag.get("href", "")
                if link and not link.startswith("http"):
                    link = f"{self.BASE_URL}{link}" if link.startswith("/") else f"{self.BASE_URL}/{link}"
                title = link_tag.get_text(strip=True)

            texts = [c.get_text(strip=True) for c in cells]
            date = texts[0] if texts else ""

            if title and len(title) > 5:
                self.results.append({
                    "source": "SEBI",
                    "title": title,
                    "date": date,
                    "department": "",
                    "link": link,
                    "details": " | ".join(t for t in texts if t),
                })

        print(f"  Found {len(self.results)} SEBI records so far.")
