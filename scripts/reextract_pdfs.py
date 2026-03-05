#!/usr/bin/env python3
"""Re-extract PDF content for existing DB records using the improved table-aware extractor.

Usage:
    # Re-extract a single record by ID
    python scripts/reextract_pdfs.py --id 644955

    # Re-extract multiple records
    python scripts/reextract_pdfs.py --id 644955 644960 644970

    # Re-extract ALL records that have pdf_links
    python scripts/reextract_pdfs.py --all

    # Dry run (show what would be updated, don't write)
    python scripts/reextract_pdfs.py --id 644955 --dry-run
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import psycopg2
import config
from utils.pdf_extract import extract_text_from_pdf


def get_conn():
    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(config.DATABASE_URL)


def fetch_records(conn, record_ids=None):
    """Fetch records that have pdf_links."""
    with conn.cursor() as cur:
        if record_ids:
            cur.execute(
                "SELECT id, title, pdf_links, link FROM scraped_documents WHERE id = ANY(%s)",
                (record_ids,),
            )
        else:
            cur.execute(
                "SELECT id, title, pdf_links, link FROM scraped_documents "
                "WHERE pdf_links IS NOT NULL AND pdf_links != '[]'::jsonb"
            )
        return cur.fetchall()


def download_pdf(url):
    """Download PDF bytes from a URL."""
    resp = requests.get(
        url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (compatible; GovCircularBot/1.0)"}
    )
    resp.raise_for_status()
    if len(resp.content) < 500:
        raise ValueError(f"PDF too small ({len(resp.content)} bytes)")
    return resp.content


def update_content(conn, record_id, content):
    """Update content and timestamp for a record."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE scraped_documents SET content = %s, updated_at = NOW() WHERE id = %s",
            (content, record_id),
        )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Re-extract PDF content with table-aware extraction")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, nargs="+", help="Record ID(s) to re-extract")
    group.add_argument("--all", action="store_true", help="Re-extract all records with pdf_links")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without writing")
    args = parser.parse_args()

    conn = get_conn()
    records = fetch_records(conn, args.id if args.id else None)
    print(f"Found {len(records)} record(s) to process\n")

    success = 0
    failed = 0

    for rec_id, title, pdf_links, link in records:
        # Determine PDF URL
        urls = pdf_links if isinstance(pdf_links, list) else []
        if not urls and link and link.lower().endswith(".pdf"):
            urls = [link]
        if not urls:
            print(f"[{rec_id}] SKIP (no PDF URL): {title}")
            continue

        pdf_url = urls[0]
        print(f"[{rec_id}] {title}")
        print(f"       PDF: {pdf_url}")

        try:
            pdf_bytes = download_pdf(pdf_url)
            content = extract_text_from_pdf(pdf_bytes)
            print(f"       Extracted: {len(content)} chars")

            # Show table detection
            has_tables = "|" in content and "---" in content
            print(f"       Tables detected: {'yes' if has_tables else 'no'}")

            if args.dry_run:
                print(f"       DRY RUN - would update content")
                # Show first 300 chars of new content
                print(f"       Preview: {content[:300]}...")
            else:
                update_content(conn, rec_id, content)
                print(f"       UPDATED")

            success += 1
        except Exception as e:
            print(f"       ERROR: {e}")
            failed += 1

        print()

    conn.close()
    print(f"Done: {success} updated, {failed} failed")


if __name__ == "__main__":
    main()
