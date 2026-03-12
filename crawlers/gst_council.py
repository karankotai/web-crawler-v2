"""Crawler for GST Council meeting press releases and decisions.

GST Council (gstcouncil.gov.in) publishes meeting minutes, press releases,
and rate recommendations. These are crucial for understanding the "why"
behind GST notifications — rate changes, exemptions, and procedural reforms
are announced here before becoming law.

Source: https://gstcouncil.gov.in/gst-council-meetings

Site structure: A single table listing all 51+ meetings with columns:
  MEETINGS | DATE of MEETING | VENUE | AGENDA | MINUTES
Each row contains PDF links for agenda docs and signed minutes.
"""

import re

from bs4 import BeautifulSoup

import config
from crawlers.base import BaseCrawler


BASE_URL = "https://gstcouncil.gov.in"
MEETINGS_URL = f"{BASE_URL}/gst-council-meetings"


class GSTCouncilCrawler(BaseCrawler):
    """Crawls GST Council meeting minutes and agenda documents."""

    name = "gst_council"

    def crawl(self):
        """Fetch the meetings table and extract all document records."""
        print("  Fetching GST Council meetings list...")
        resp = self.fetch(MEETINGS_URL)
        if not resp:
            print("  ERROR: Failed to fetch meetings page")
            return

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table")
        if not table:
            print("  ERROR: No table found on meetings page")
            return

        rows = table.find_all("tr")[1:]  # skip header row
        print(f"  Found {len(rows)} meeting rows")

        for i, row in enumerate(rows):
            tds = row.find_all("td")
            if len(tds) < 5:
                continue

            meeting_name = tds[0].get_text(strip=True)
            date_text = tds[1].get_text(strip=True)
            venue = tds[2].get_text(strip=True)
            date = self._extract_date_from_text(date_text)
            meeting_number = self._extract_meeting_number(meeting_name)

            # Collect all PDF links from Agenda (col 3) and Minutes (col 4)
            agenda_links = self._extract_pdf_links(tds[3])
            minutes_links = self._extract_pdf_links(tds[4])

            all_pdf_urls = [p["url"] for p in agenda_links + minutes_links]

            # Create a record for each PDF document
            for pdf in minutes_links:
                record = {
                    "source": "gst_council",
                    "title": pdf["text"] or f"Minutes - {meeting_name}",
                    "date": date,
                    "department": "GST Council",
                    "link": pdf["url"],
                    "circular_number": meeting_number,
                    "pdf_links": [pdf["url"]],
                    "doc_type": "Meeting Minutes",
                    "details": f"GST Council | {meeting_name} | {venue}",
                }
                if record["link"] not in self.existing_links:
                    self.results.append(record)

            for pdf in agenda_links:
                record = {
                    "source": "gst_council",
                    "title": pdf["text"] or f"Agenda - {meeting_name}",
                    "date": date,
                    "department": "GST Council",
                    "link": pdf["url"],
                    "circular_number": meeting_number,
                    "pdf_links": [pdf["url"]],
                    "doc_type": "Agenda",
                    "details": f"GST Council | {meeting_name} | {venue}",
                }
                if record["link"] not in self.existing_links:
                    self.results.append(record)

            if (i + 1) % 10 == 0:
                print(f"  Processed {i+1}/{len(rows)} meetings, {len(self.results)} records")

        print(f"  Total: {len(self.results)} new records from {len(rows)} meetings")

    def _extract_pdf_links(self, td_element) -> list[dict]:
        """Extract PDF links from a table cell."""
        links = []
        for a in td_element.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
            text = a.get_text(strip=True)
            if href.lower().endswith(".pdf") or "/files/" in href.lower():
                links.append({"url": href, "text": text})
        return links

    def parse_detail_page(self, soup, url):
        """Not used — all data is extracted from the meetings table."""
        return {}

    @staticmethod
    def _extract_meeting_number(title: str) -> str:
        """Extract meeting number like '51st' → 'GST-COUNCIL-51'."""
        match = re.search(r"(\d+)\s*(?:st|nd|rd|th)", title, re.IGNORECASE)
        if match:
            return f"GST-COUNCIL-{match.group(1)}"
        return ""

    @staticmethod
    def _extract_date_from_text(text: str) -> str:
        """Parse date from text like '2nd August 2023' or '28th & 29th June 2022'."""
        # Match "2nd August 2023" pattern (take the first date if range)
        patterns = [
            (r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
             lambda m: f"{m.group(3)}-{_MONTH_MAP.get(m.group(2), '01')}-{m.group(1).zfill(2)}"),
            (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
             lambda m: f"{m.group(3)}-{_MONTH_MAP.get(m.group(1), '01')}-{m.group(2).zfill(2)}"),
        ]

        for pattern, formatter in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return formatter(match)
                except Exception:
                    continue
        return ""


_MONTH_MAP = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}
