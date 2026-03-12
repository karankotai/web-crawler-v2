#!/usr/bin/env python3
"""Extract PDF content for CBIC records that have pdf_links but no content.

Focused version that:
- Only targets GST records (or optionally all)
- Skips raw_content_cache to save storage
- Has proper timeouts to avoid hanging
- Processes in batches with progress tracking

Usage:
    python scripts/extract_cbic_content.py                    # GST records only
    python scripts/extract_cbic_content.py --all              # All CBIC records
    python scripts/extract_cbic_content.py --limit 100        # First 100 records
    python scripts/extract_cbic_content.py --dry-run          # Preview only
"""

import argparse
import base64
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import config
from utils.pdf_extract import extract_text_from_pdf

BASE_URL = "https://taxinformation.cbic.gov.in"
SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update(config.HEADERS)


def get_records_needing_content(conn, gst_only=True, limit=None):
    """Fetch CBIC records with pdf_links but no content."""
    query = """
        SELECT id, link, title, pdf_links, department
        FROM scraped_documents
        WHERE crawler = 'cbic'
          AND (content IS NULL OR content = '')
          AND pdf_links IS NOT NULL
          AND pdf_links != '[]'::jsonb
          AND jsonb_array_length(pdf_links) > 0
    """
    if gst_only:
        query += " AND department LIKE '%GST%'"
    query += " ORDER BY date DESC"
    if limit:
        query += f" LIMIT {limit}"

    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def fetch_and_extract(pdf_url, timeout=30):
    """Download base64 PDF from CBIC API and extract text."""
    if not pdf_url.startswith(BASE_URL + "/content/pdf/"):
        return ""
    try:
        resp = SESSION.get(pdf_url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        b64 = data.get("data", "")
        if not b64:
            return ""
        pdf_bytes = base64.b64decode(b64)
        text = extract_text_from_pdf(pdf_bytes)
        return (text or "").strip()
    except requests.exceptions.Timeout:
        return ""
    except Exception as e:
        print(f"    ERROR: {e}")
        return ""


def update_content(conn, record_id, content):
    """Update content for a single record."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scraped_documents
               SET content = %s,
                   extraction_status = 'success',
                   extraction_method = 'pdfplumber',
                   content_length = %s
               WHERE id = %s""",
            (content, len(content), record_id),
        )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Extract CBIC PDF content")
    parser.add_argument("--all", action="store_true", help="Process all CBIC records, not just GST")
    parser.add_argument("--limit", type=int, help="Max records to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without extracting")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout per request (seconds)")
    args = parser.parse_args()

    from crawlers.base import _get_db_conn
    conn = _get_db_conn()
    if not conn:
        print("ERROR: No DATABASE_URL")
        sys.exit(1)

    gst_only = not args.all
    records = get_records_needing_content(conn, gst_only=gst_only, limit=args.limit)
    label = "GST" if gst_only else "all"
    print(f"Found {len(records)} CBIC ({label}) records needing content extraction")

    if args.dry_run:
        for rec in records[:20]:
            print(f"  [{rec[0]}] {rec[2][:60]} | {rec[4]} | {rec[3][0][:60] if rec[3] else 'no pdf'}...")
        if len(records) > 20:
            print(f"  ... and {len(records) - 20} more")
        conn.close()
        return

    extracted = 0
    failed = 0
    start = time.time()

    for i, (rec_id, link, title, pdf_links, dept) in enumerate(records):
        pdf_url = pdf_links[0] if pdf_links else ""
        if not pdf_url:
            continue

        content = fetch_and_extract(pdf_url, timeout=args.timeout)
        if content and len(content) > 50:
            update_content(conn, rec_id, content)
            extracted += 1
        else:
            failed += 1

        if (i + 1) % 25 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed * 60
            print(f"  [{i+1}/{len(records)}] extracted={extracted} failed={failed} ({rate:.0f}/min)")

        # Small delay to be polite to CBIC servers
        time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s: {extracted} extracted, {failed} failed out of {len(records)}")
    conn.close()


if __name__ == "__main__":
    main()
