#!/usr/bin/env python3
"""Re-extract PDF content for existing DB records using the improved table-aware extractor.

Now checks raw_content_cache before downloading from the internet,
processes ALL PDFs in pdf_links (not just the first), and updates
extraction metadata columns.

Usage:
    python scripts/reextract_pdfs.py --id 644955
    python scripts/reextract_pdfs.py --id 644955 644960 644970
    python scripts/reextract_pdfs.py --all
    python scripts/reextract_pdfs.py --all --dry-run
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import psycopg2
import config
from utils.pdf_extract import extract_text_from_pdf_with_metadata


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


def get_cached_bytes(conn, document_link, source_url):
    """Check raw_content_cache for previously cached PDF bytes."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT raw_bytes FROM raw_content_cache WHERE document_link = %s AND source_url = %s",
                (document_link, source_url),
            )
            row = cur.fetchone()
            if row and row[0]:
                return bytes(row[0])
    except Exception:
        pass
    return None


def cache_bytes(conn, document_link, source_url, pdf_bytes):
    """Store downloaded PDF bytes in cache for future use."""
    try:
        content_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO raw_content_cache
                    (document_link, source_url, content_type, content_sha256, raw_bytes, file_size)
                VALUES (%s, %s, 'pdf', %s, %s, %s)
                ON CONFLICT (document_link, source_url) DO UPDATE SET
                    content_sha256 = EXCLUDED.content_sha256,
                    raw_bytes = EXCLUDED.raw_bytes,
                    file_size = EXCLUDED.file_size
            """, (document_link, source_url, content_sha256, pdf_bytes, len(pdf_bytes)))
        conn.commit()
    except Exception as e:
        print(f"       [WARN] Failed to cache: {e}")


def download_pdf(url):
    """Download PDF bytes from a URL."""
    resp = requests.get(
        url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (compatible; GovCircularBot/1.0)"}
    )
    resp.raise_for_status()
    if len(resp.content) < 500:
        raise ValueError(f"PDF too small ({len(resp.content)} bytes)")
    return resp.content


def update_content(conn, record_id, content, method, error=""):
    """Update content and extraction metadata for a record."""
    content_hash = hashlib.sha256(content.encode()).hexdigest() if content else ""
    status = "success" if content else "failed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE scraped_documents
               SET content = %s,
                   extraction_status = %s,
                   extraction_method = %s,
                   extraction_error = %s,
                   extraction_attempts = extraction_attempts + 1,
                   extraction_timestamp = NOW(),
                   content_length = %s,
                   content_hash = %s,
                   updated_at = NOW()
               WHERE id = %s""",
            (content, status, method, error, len(content), content_hash, record_id),
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
    cached_hits = 0

    for rec_id, title, pdf_links, link in records:
        # Determine ALL PDF URLs
        urls = pdf_links if isinstance(pdf_links, list) else []
        if not urls and link and link.lower().endswith(".pdf"):
            urls = [link]
        if not urls:
            print(f"[{rec_id}] SKIP (no PDF URL): {title}")
            continue

        print(f"[{rec_id}] {title}")
        print(f"       PDFs: {len(urls)} URL(s)")

        all_text_parts = []
        method = "pdfplumber"

        for pdf_url in urls:
            print(f"       PDF: {pdf_url}")

            try:
                # Check cache first
                pdf_bytes = get_cached_bytes(conn, link, pdf_url)
                if pdf_bytes:
                    print(f"       Source: cache ({len(pdf_bytes)} bytes)")
                    cached_hits += 1
                else:
                    pdf_bytes = download_pdf(pdf_url)
                    print(f"       Source: download ({len(pdf_bytes)} bytes)")
                    # Cache for future use
                    if not args.dry_run:
                        cache_bytes(conn, link, pdf_url, pdf_bytes)

                text, metadata = extract_text_from_pdf_with_metadata(pdf_bytes)
                method = metadata.get("method", method)
                print(f"       Extracted: {len(text)} chars (method: {metadata.get('method', '?')})")

                if text and text.strip():
                    if len(urls) > 1:
                        all_text_parts.append(f"--- PDF: {pdf_url} ---\n{text}")
                    else:
                        all_text_parts.append(text)

            except Exception as e:
                print(f"       ERROR: {e}")

        content = "\n\n".join(all_text_parts)
        has_tables = "|" in content and "---" in content
        print(f"       Total: {len(content)} chars | Tables: {'yes' if has_tables else 'no'}")

        if args.dry_run:
            print(f"       DRY RUN - would update content")
            print(f"       Preview: {content[:300]}...")
        else:
            update_content(conn, rec_id, content, method)
            print(f"       UPDATED")

        if content:
            success += 1
        else:
            failed += 1

        print()

    conn.close()
    print(f"Done: {success} updated, {failed} failed, {cached_hits} cache hits")


if __name__ == "__main__":
    main()
