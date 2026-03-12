#!/usr/bin/env python3
"""Index GST Council meeting minutes directly into Qdrant (bypassing PG).

Used when PostgreSQL storage is full but we still want GST Council data
searchable in the RAG system.

Usage:
    python scripts/index_gst_council_direct.py
    python scripts/index_gst_council_direct.py --dry-run
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from bs4 import BeautifulSoup
import re

import config
from utils.pdf_extract import extract_text_from_pdf

BASE_URL = "https://gstcouncil.gov.in"
MEETINGS_URL = f"{BASE_URL}/gst-council-meetings"

_MONTH_MAP = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}


def extract_date(text):
    """Parse date from '2nd August 2023' format."""
    m = re.search(
        r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        return f"{m.group(3)}-{_MONTH_MAP.get(m.group(2), '01')}-{m.group(1).zfill(2)}"
    return ""


def extract_meeting_number(title):
    m = re.search(r"(\d+)\s*(?:st|nd|rd|th)", title, re.IGNORECASE)
    return f"GST-COUNCIL-{m.group(1)}" if m else ""


def fetch_pdf_text(url, timeout=60):
    """Download PDF and extract text."""
    try:
        resp = requests.get(url, headers=config.HEADERS, timeout=timeout, verify=False)
        resp.raise_for_status()
        return extract_text_from_pdf(resp.content) or ""
    except Exception as e:
        print(f"  ERROR fetching {url[:60]}: {e}")
        return ""


def crawl_meetings():
    """Crawl GST Council meetings page and extract records with content."""
    print("Fetching GST Council meetings list...")
    resp = requests.get(MEETINGS_URL, headers=config.HEADERS, timeout=30, verify=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table")
    if not table:
        print("ERROR: No table found")
        return []

    rows = table.find_all("tr")[1:]
    print(f"Found {len(rows)} meeting rows")
    records = []

    for i, row in enumerate(rows):
        tds = row.find_all("td")
        if len(tds) < 5:
            continue

        meeting_name = tds[0].get_text(strip=True)
        date_text = tds[1].get_text(strip=True)
        venue = tds[2].get_text(strip=True)
        date = extract_date(date_text)
        meeting_number = extract_meeting_number(meeting_name)

        # Get Minutes PDFs (column 4)
        for a in tds[4].find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
            if not (href.lower().endswith(".pdf") or "/files/" in href.lower()):
                continue

            link_text = a.get_text(strip=True)
            print(f"  [{i+1}/{len(rows)}] Downloading: {link_text or meeting_name}...")
            content = fetch_pdf_text(href)

            if content and len(content) > 100:
                records.append({
                    "source": "gst_council",
                    "title": link_text or f"Minutes - {meeting_name}",
                    "date": date,
                    "department": "GST Council",
                    "link": href,
                    "circular_number": meeting_number,
                    "pdf_links": [href],
                    "doc_type": "Meeting Minutes",
                    "details": f"GST Council | {meeting_name} | {venue}",
                    "content": content,
                })

    print(f"Total: {len(records)} records with content")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = crawl_meetings()

    if args.dry_run:
        for r in records:
            print(f"  [{r['circular_number']}] {r['title'][:50]} ({len(r.get('content',''))} chars)")
        return

    if not records:
        print("No records to index.")
        return

    print(f"\nIndexing {len(records)} records directly into Qdrant...")
    from rag_app.services.rag_pipeline import RAGPipeline
    pipeline = RAGPipeline()
    chunks = pipeline.index_records(records)
    print(f"Indexed {chunks} chunks into Qdrant")


if __name__ == "__main__":
    main()
