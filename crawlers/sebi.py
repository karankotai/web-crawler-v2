"""Crawler for SEBI (Securities and Exchange Board of India) circulars."""

import gc
from urllib.parse import urljoin

import config
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

        # Download ALL PDFs and extract text (not just the first)
        if detail["pdf_links"]:
            content, method, _ = self._download_and_extract_all_pdfs(
                detail["pdf_links"], url
            )
            detail["content"] = content
            detail["extraction_method"] = method
            detail["extraction_status"] = "success" if content else "failed"

        return detail

    def _crawl_listing_page(self, base_url, label):
        """Crawl a SEBI listing page with pagination."""
        page_num = 1
        while page_num <= config.MAX_PAGES:
            url = f"{base_url}&pageNo={page_num}" if page_num > 1 else base_url
            print(f"  Fetching SEBI {label} page {page_num}...")
            resp = self.fetch(url)
            if not resp:
                break

            soup = self.parse_html(resp.text)

            before = len(self.results)
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

            found = len(self.results) - before
            print(f"  SEBI {label} page {page_num}: {found} records")
            self.save_progress()

            if found == 0:
                break

            if not self._has_next_page(soup, page_num):
                break
            page_num += 1

    def _has_next_page(self, soup, current_page):
        """Check if there's a next page link in the SEBI pagination."""
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if text in ("next", "next >", ">>"):
                return True
            href = a.get("href", "")
            if f"pageNo={current_page + 1}" in href:
                return True

        import re
        for div in soup.select(".pagination_inner"):
            m = re.search(r"(\d+)\s+to\s+(\d+)\s+of\s+(\d+)", div.get_text())
            if m:
                end_idx = int(m.group(2))
                total = int(m.group(3))
                if end_idx < total:
                    return True

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "searchFormNewsList" in href:
                text = a.get_text(strip=True).lower()
                if text in ("next", "next >", ">>"):
                    return True

        return False
