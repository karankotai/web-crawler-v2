"""Crawler for ICAI (Institute of Chartered Accountants of India).

Crawls announcements, accounting standards, guidance notes, and exposure drafts.
ICAI uses simple static HTML + jQuery — no anti-bot, no Playwright needed.
"""

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
            "url": f"{BASE_URL}/category/accounting-standards",
            "label": "accounting standards",
            "paginated": False,
        },
        {
            "url": f"{BASE_URL}/post/guidance-notes",
            "label": "guidance notes",
            "paginated": False,
        },
        {
            "url": f"{BASE_URL}/category/list-of-exposure-drafts",
            "label": "exposure drafts",
            "paginated": True,
            "max_pages": 5,
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
            self._parse_listing_page(soup, label)

            found = len(self.results) - before
            print(f"  ICAI {label} page {page}: {found} records")
            if found > 0:
                self.save_progress()
            else:
                break

    def _crawl_single_page(self, section):
        """Crawl a single-page ICAI section."""
        label = section["label"]
        print(f"  Fetching ICAI {label}...")
        resp = self.fetch(section["url"])
        if not resp:
            return

        soup = self.parse_html(resp.text)
        before = len(self.results)
        self._parse_listing_page(soup, label)
        found = len(self.results) - before
        print(f"  ICAI {label}: {found} records")
        if found > 0:
            self.save_progress()

    def _parse_listing_page(self, soup, label):
        """Parse an ICAI listing page for announcements/standards."""
        # Try multiple content patterns used across ICAI sections

        # Pattern 1: <li> items with links (announcements)
        for li in soup.select("ul.listing li, ul.post-listing li, .announcements li, .content-area li"):
            link_tag = li.find("a", href=True)
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = urljoin(self.BASE_URL, href)

            # Skip navigation/non-content links
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#", "login"]):
                continue

            # Extract date if present (often in a span or nearby text)
            date = ""
            date_el = li.find("span", class_="date") or li.find("small")
            if date_el:
                date = date_el.get_text(strip=True)
            else:
                # Try to extract from parent text
                li_text = li.get_text(strip=True)
                import re
                date_match = re.search(r'\d{2}-\d{2}-\d{4}', li_text)
                if date_match:
                    date = date_match.group()

            # Check for PDF links
            pdf_links = []
            for a in li.find_all("a", href=True):
                if ".pdf" in a["href"].lower():
                    pdf_href = a["href"]
                    if not pdf_href.startswith("http"):
                        pdf_href = urljoin(self.BASE_URL, pdf_href)
                    pdf_links.append(pdf_href)

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

        # Pattern 2: Table rows (some standards pages use tables)
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                link_tag = row.find("a", href=True)
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = link_tag["href"]
                if not href.startswith("http"):
                    href = urljoin(self.BASE_URL, href)

                if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                pdf_links = []
                for a in row.find_all("a", href=True):
                    if ".pdf" in a["href"].lower():
                        pdf_href = a["href"]
                        if not pdf_href.startswith("http"):
                            pdf_href = urljoin(self.BASE_URL, pdf_href)
                        pdf_links.append(pdf_href)

                if href not in self.existing_links:
                    self.results.append({
                        "source": f"ICAI ({label})",
                        "title": title,
                        "date": "",
                        "department": "ICAI",
                        "link": href,
                        "details": " | ".join(t for t in texts if t),
                        "pdf_links": pdf_links,
                        "doc_type": label,
                    })

    def parse_detail_page(self, soup, url):
        """Extract content from an ICAI detail page."""
        detail = {"content": "", "pdf_links": []}

        # Find main content area
        content_div = (
            soup.select_one(".post-content") or
            soup.select_one(".content-area") or
            soup.select_one("#content") or
            soup.select_one("article") or
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
