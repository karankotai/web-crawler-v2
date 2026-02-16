"""Generic crawler for any government notification/circular page."""

from urllib.parse import urljoin

from crawlers.base import BaseCrawler


class GenericGovCrawler(BaseCrawler):
    """
    Generic crawler that extracts circular/notification links from any government page.

    Usage:
        crawler = GenericGovCrawler(
            url="https://example.gov.in/circulars",
            site_name="Example Dept",
        )
        crawler.run()
    """

    def __init__(self, url, site_name="generic_gov"):
        super().__init__()
        self.url = url
        self.name = site_name.lower().replace(" ", "_")

    def crawl(self):
        print(f"  Fetching {self.url}...")
        resp = self.fetch(self.url)
        if not resp:
            return

        soup = self.parse_html(resp.text)

        # Strategy 1: Try tables first (most gov sites use tables)
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            self._parse_table(rows)

        # Strategy 2: If no table results, try list-based extraction
        if not self.results:
            self._parse_links(soup)

        print(f"  Found {len(self.results)} records from {self.name}.")

    def _parse_table(self, rows):
        """Extract data from HTML table rows."""
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            link_tag = row.find("a", href=True)
            title = ""
            link = ""
            if link_tag:
                title = link_tag.get_text(strip=True)
                link = link_tag.get("href", "")
                if link and not link.startswith("http"):
                    link = urljoin(self.url, link)

            texts = [c.get_text(strip=True) for c in cells]

            if not title:
                # Use the longest cell text as the title
                title = max(texts, key=len) if texts else ""

            if not title or len(title) < 5:
                continue

            date = self._extract_date(texts)

            self.results.append({
                "source": self.name,
                "title": title,
                "date": date,
                "department": "",
                "link": link,
                "details": " | ".join(t for t in texts if t),
            })

    def _parse_links(self, soup):
        """Fallback: extract all meaningful links from the page."""
        # Focus on the main content area
        main = (
            soup.select_one("main")
            or soup.select_one("#content")
            or soup.select_one(".content")
            or soup.select_one("#wrapper")
            or soup.body
        )
        if not main:
            return

        seen = set()
        for a in main.find_all("a", href=True):
            href = a.get("href", "")
            title = a.get_text(strip=True)

            if not title or len(title) < 10 or title in seen:
                continue
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#", "login"]):
                continue

            seen.add(title)
            if not href.startswith("http"):
                href = urljoin(self.url, href)

            self.results.append({
                "source": self.name,
                "title": title,
                "date": "",
                "department": "",
                "link": href,
                "details": "",
            })

    def _extract_date(self, texts):
        """Try to find a date string in a list of cell texts."""
        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        for t in texts:
            if any(m in t for m in months):
                return t
            # Check dd/mm/yyyy or dd-mm-yyyy patterns
            if len(t) <= 12 and ("/" in t or "-" in t):
                parts = t.replace("-", "/").split("/")
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    return t
        return ""
