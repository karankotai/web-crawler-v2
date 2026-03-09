"""Crawler for ICAI (Institute of Chartered Accountants of India).

Crawls announcements, accounting standards, guidance notes, and exposure drafts.
ICAI uses simple static HTML — no anti-bot, no Playwright needed.

Page structure:
- Announcements: ul.list-group > li.list-group-item > a (dates in text as "- (DD-MM-YYYY)")
- Standards/Guidance: direct PDF links from resource.cdn.icai.org
- Pagination: /category/announcements/2, /category/announcements/3, etc.
"""

import re
from urllib.parse import urljoin

import config
from crawlers.base import BaseCrawler


class ICAICrawler(BaseCrawler):
    """Crawls announcements and standards from icai.org"""

    name = "icai"
    BASE_URL = "https://www.icai.org"

    SECTIONS = [
        {
            "url": f"{BASE_URL}/category/announcements",
            "label": "announcements",
            "paginated": True,
            "max_pages": 20,
        },
        {
            "url": f"{BASE_URL}/post/accounting-standards-as",
            "label": "accounting standards (AS)",
            "paginated": False,
        },
        {
            "url": f"{BASE_URL}/post/indian-accounting-standards-indas",
            "label": "accounting standards (Ind AS)",
            "paginated": False,
        },
        {
            "url": f"{BASE_URL}/post/guidance-notes",
            "label": "guidance notes",
            "paginated": False,
        },
    ]

    def crawl(self):
        for section in self.SECTIONS:
            if section.get("paginated"):
                self._crawl_paginated(section)
            else:
                self._crawl_single_page(section)

    def _crawl_paginated(self, section):
        """Crawl a paginated ICAI section."""
        label = section["label"]
        max_pages = min(section.get("max_pages", 20), config.MAX_PAGES)
        base_url = section["url"]

        for page in range(1, max_pages + 1):
            url = f"{base_url}/{page}" if page > 1 else base_url
            print(f"  Fetching ICAI {label} page {page}...")
            resp = self.fetch(url)
            if not resp:
                break

            soup = self.parse_html(resp.text)
            before = len(self.results)
            self._parse_list_group(soup, label)

            found = len(self.results) - before
            print(f"  ICAI {label} page {page}: {found} records")
            if found > 0:
                self.save_progress()
            else:
                break

    def _crawl_single_page(self, section):
        """Crawl a single-page ICAI section (standards, guidance notes)."""
        label = section["label"]
        print(f"  Fetching ICAI {label}...")
        resp = self.fetch(section["url"])
        if not resp:
            return

        soup = self.parse_html(resp.text)
        before = len(self.results)
        self._parse_content_links(soup, label)
        found = len(self.results) - before
        print(f"  ICAI {label}: {found} records")
        if found > 0:
            self.save_progress()

    def _parse_list_group(self, soup, label):
        """Parse ICAI list-group pattern (used by announcements).

        Structure: ul.list-group > li.list-group-item > a
        Date embedded in link text: "Title text - (DD-MM-YYYY)"
        """
        items = soup.select("li.list-group-item")
        for item in items:
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue

            raw_text = link_tag.get_text(strip=True)
            if not raw_text or len(raw_text) < 10:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = urljoin(self.BASE_URL, href)

            # Skip navigation/non-content links
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                continue

            # Extract date from text: "Title - (DD-MM-YYYY)"
            title = raw_text
            date = ""
            date_match = re.search(r'-\s*\((\d{2}-\d{2}-\d{4})\)\s*$', raw_text)
            if date_match:
                date = date_match.group(1)
                title = raw_text[:date_match.start()].strip()

            # Determine if link is a direct PDF
            pdf_links = []
            if ".pdf" in href.lower():
                pdf_links = [href]

            if href not in self.existing_links:
                self.results.append({
                    "source": f"ICAI ({label})",
                    "title": title,
                    "date": date,
                    "department": "ICAI",
                    "link": href,
                    "pdf_links": pdf_links,
                    "doc_type": label,
                })

    def _parse_content_links(self, soup, label):
        """Parse direct PDF and content links (used by standards/guidance pages).

        These pages have direct links to resource.cdn.icai.org PDFs and
        sub-category links to /post/ pages inside div.shadow or the main content.
        """
        # Find main content container
        shadow = soup.select_one("div.shadow")
        container = shadow or soup.select_one("div.container.mx-3") or soup.body
        if not container:
            return

        seen_hrefs = set()
        for a in container.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            if not href.startswith("http"):
                href = urljoin(self.BASE_URL, href)

            # Only collect content links (PDFs and /post/ pages), skip nav
            is_pdf = ".pdf" in href.lower()
            is_post = "/post/" in href
            if not is_pdf and not is_post:
                continue

            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                continue

            if href in seen_hrefs or href in self.existing_links:
                continue
            seen_hrefs.add(href)

            pdf_links = [href] if is_pdf else []

            self.results.append({
                "source": f"ICAI ({label})",
                "title": title,
                "date": "",
                "department": "ICAI",
                "link": href,
                "pdf_links": pdf_links,
                "doc_type": label,
            })

    def parse_detail_page(self, soup, url):
        """Extract content from an ICAI detail page."""
        detail = {"content": "", "pdf_links": []}

        # Find main content area
        content_div = (
            soup.select_one("div.shadow") or
            soup.select_one(".post-content") or
            soup.select_one(".content-area") or
            soup.select_one("#content") or
            soup.body
        )
        if not content_div:
            return detail

        # Collect PDF links
        for a in content_div.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                if not href.startswith("http"):
                    href = urljoin(url, href)
                if href not in detail["pdf_links"]:
                    detail["pdf_links"].append(href)

        # Download PDFs and extract text
        if detail["pdf_links"]:
            content, method, _ = self._download_and_extract_all_pdfs(
                detail["pdf_links"], url
            )
            if content:
                detail["content"] = content
                detail["extraction_method"] = method
                detail["extraction_status"] = "success"
                return detail

        # Fallback to HTML content
        detail["content"] = self._extract_html_content(soup)
        detail["extraction_method"] = "html"
        detail["extraction_status"] = "success" if detail["content"] else "failed"
        return detail
