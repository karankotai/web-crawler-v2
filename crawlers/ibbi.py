"""Crawler for IBBI (Insolvency and Bankruptcy Board of India).

ibbi.gov.in uses PHP + jQuery/AJAX with CSRF tokens.
Sections: Circulars, Regulations, Notifications, Guidelines
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
        "path": "/en/legal-framework/regulations",
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

    def __init__(self):
        super().__init__()
        self._csrf_token = None

    def crawl(self):
        for section in IBBI_SECTIONS:
            self._crawl_section(section)

    def _get_csrf_token(self, soup):
        """Extract CSRF token from page meta tag or hidden input."""
        # Try meta tag
        meta = soup.find("meta", attrs={"name": "csrf-token"})
        if meta and meta.get("content"):
            return meta["content"]
        # Try hidden input
        inp = soup.find("input", attrs={"name": "_token"})
        if inp and inp.get("value"):
            return inp["value"]
        return None

    def _crawl_section(self, section):
        """Crawl an IBBI section with pagination."""
        label = section["label"]
        doc_type = section["doc_type"]
        base_url = f"{self.BASE_URL}{section['path']}"

        page = 1
        while page <= config.MAX_PAGES:
            url = f"{base_url}?page={page}" if page > 1 else base_url
            print(f"  Fetching IBBI {label} page {page}...")
            resp = self.fetch(url)
            if not resp:
                break

            soup = self.parse_html(resp.text)

            # Extract CSRF token on first page
            if page == 1:
                self._csrf_token = self._get_csrf_token(soup)
                if self._csrf_token:
                    self.session.headers["X-CSRF-Token"] = self._csrf_token

            before = len(self.results)
            self._parse_listing(soup, label, doc_type)

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

        print(f"  Total IBBI {label}: {len([r for r in self.results if r.get('doc_type') == doc_type])}")

    def _parse_listing(self, soup, label, doc_type):
        """Parse an IBBI listing page for records."""
        # IBBI uses HTML tables for document listings
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                # Extract title and link
                link_tag = row.find("a", href=True)
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = link_tag["href"]

                # Handle javascript:void(0) links — try to find onclick handler
                if "javascript:" in href.lower():
                    onclick = link_tag.get("onclick", "")
                    href_match = re.search(r"(?:window\.open|location\.href)\s*[=(]\s*['\"]([^'\"]+)['\"]", onclick)
                    if href_match:
                        href = href_match.group(1)
                    else:
                        # Try data attributes
                        href = link_tag.get("data-href", "") or link_tag.get("data-url", "")

                if not href or "javascript:" in href.lower():
                    continue

                if not href.startswith("http"):
                    href = urljoin(self.BASE_URL, href)

                texts = [c.get_text(strip=True) for c in cells]

                # Parse date (format: DD MMM, YYYY)
                date = ""
                for t in texts:
                    if re.search(r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*,?\s+\d{4}', t, re.I):
                        date = t.strip()
                        break

                # Collect PDF links
                pdf_links = []
                for a in row.find_all("a", href=True):
                    a_href = a["href"]
                    if ".pdf" in a_href.lower():
                        if not a_href.startswith("http"):
                            a_href = urljoin(self.BASE_URL, a_href)
                        pdf_links.append(a_href)
                    # Check onclick for PDF URLs
                    onclick = a.get("onclick", "")
                    pdf_match = re.search(r"['\"]([^'\"]+\.pdf)['\"]", onclick, re.I)
                    if pdf_match:
                        pdf_url = pdf_match.group(1)
                        if not pdf_url.startswith("http"):
                            pdf_url = urljoin(self.BASE_URL, pdf_url)
                        if pdf_url not in pdf_links:
                            pdf_links.append(pdf_url)

                if href not in self.existing_links:
                    self.results.append({
                        "source": f"IBBI ({label})",
                        "title": title,
                        "date": date,
                        "department": "IBBI",
                        "link": href,
                        "details": " | ".join(t for t in texts if t),
                        "pdf_links": pdf_links,
                        "doc_type": doc_type,
                    })

        # Also try div-based listings
        for item in soup.select(".views-row, .view-content .item-list li, .legal-framework-list li"):
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue

            title = link_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            if not href.startswith("http"):
                href = urljoin(self.BASE_URL, href)
            if "javascript:" in href.lower():
                continue

            date = ""
            date_el = item.find("span", class_="date") or item.find(class_="views-field-created")
            if date_el:
                date = date_el.get_text(strip=True)

            pdf_links = []
            for a in item.find_all("a", href=True):
                if ".pdf" in a["href"].lower():
                    pdf_href = a["href"]
                    if not pdf_href.startswith("http"):
                        pdf_href = urljoin(self.BASE_URL, pdf_href)
                    pdf_links.append(pdf_href)

            if href not in self.existing_links:
                self.results.append({
                    "source": f"IBBI ({label})",
                    "title": title,
                    "date": date,
                    "department": "IBBI",
                    "link": href,
                    "pdf_links": pdf_links,
                    "doc_type": doc_type,
                })

    def _has_next_page(self, soup, current_page):
        """Check if there's a next page link."""
        # Check for ?page=N+1 links
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if f"page={current_page + 1}" in href:
                return True
            text = a.get_text(strip=True).lower()
            if text in ("next", "next >", ">>", str(current_page + 1)):
                return True

        # Check pagination nav
        pager = soup.select_one(".pagination, .pager, nav.pager")
        if pager:
            for a in pager.find_all("a", href=True):
                if f"page={current_page + 1}" in a["href"]:
                    return True
                if a.get_text(strip=True) == str(current_page + 1):
                    return True

        return False

    def parse_detail_page(self, soup, url):
        """Extract content from an IBBI detail page."""
        detail = {"content": "", "pdf_links": []}

        # Collect PDF links
        content_div = soup.select_one(".field-item") or soup.select_one("#content") or soup.body
        if content_div:
            for a in content_div.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower():
                    if not href.startswith("http"):
                        href = urljoin(url, href)
                    if href not in detail["pdf_links"]:
                        detail["pdf_links"].append(href)

        # Download PDFs
        if detail["pdf_links"]:
            content, method, _ = self._download_and_extract_all_pdfs(
                detail["pdf_links"], url
            )
            if content:
                detail["content"] = content
                detail["extraction_method"] = method
                detail["extraction_status"] = "success"
                return detail

        # Fallback to HTML
        detail["content"] = self._extract_html_content(soup)
        detail["extraction_method"] = "html"
        detail["extraction_status"] = "success" if detail["content"] else "failed"
        return detail
