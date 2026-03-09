#!/usr/bin/env python3
"""Retry failed extractions using cached raw content.

Queries the failed_extractions dead letter queue, checks raw_content_cache
for cached bytes, re-extracts with improved logic, and marks resolved.

Usage:
    python scripts/retry_failed.py
    python scripts/retry_failed.py --dry-run
    python scripts/retry_failed.py --limit 50
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import config
from utils.pdf_extract import extract_text_from_pdf_with_metadata


def get_conn():
    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(config.DATABASE_URL)


def main():
    parser = argparse.ArgumentParser(description="Retry failed extractions using cached content")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be retried")
    parser.add_argument("--limit", type=int, default=0, help="Max failures to retry (0=all)")
    args = parser.parse_args()

    conn = get_conn()

    # Fetch unresolved failures
    with conn.cursor() as cur:
        query = """
            SELECT DISTINCT fe.id, fe.document_link, fe.source_url, fe.crawler,
                   fe.error_type, fe.attempt_number
            FROM failed_extractions fe
            WHERE fe.resolved = FALSE
            ORDER BY fe.id
        """
        if args.limit:
            query += f" LIMIT {args.limit}"
        cur.execute(query)
        failures = cur.fetchall()

    print(f"Found {len(failures)} unresolved failures\n")

    resolved = 0
    still_failed = 0
    no_cache = 0

    for fail_id, doc_link, source_url, crawler, error_type, attempt_num in failures:
        print(f"[{fail_id}] {crawler} | {error_type}")
        print(f"       doc: {doc_link[:80]}")
        print(f"       src: {source_url[:80]}")

        # Check cache for raw bytes
        with conn.cursor() as cur:
            cur.execute(
                "SELECT raw_bytes, content_type FROM raw_content_cache WHERE document_link = %s AND source_url = %s",
                (doc_link, source_url),
            )
            cache_row = cur.fetchone()

        if not cache_row or not cache_row[0]:
            # Try with the #pdf suffix variant (used by CBIC)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT raw_bytes, content_type FROM raw_content_cache WHERE document_link = %s AND source_url LIKE %s",
                    (doc_link, source_url + "%"),
                )
                cache_row = cur.fetchone()

        if not cache_row or not cache_row[0]:
            print(f"       SKIP - no cached content")
            no_cache += 1
            print()
            continue

        raw_bytes = bytes(cache_row[0])
        content_type = cache_row[1]
        print(f"       Cache hit: {len(raw_bytes)} bytes ({content_type})")

        if args.dry_run:
            print(f"       DRY RUN - would retry extraction")
            print()
            continue

        try:
            if content_type == "pdf" or source_url.lower().endswith(".pdf"):
                text, metadata = extract_text_from_pdf_with_metadata(raw_bytes)
                method = metadata.get("method", "pdfplumber")
            else:
                # HTML content — extract text
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw_bytes, "lxml")
                body = soup.select_one("main") or soup.select_one("#content") or soup.body
                text = body.get_text(separator="\n", strip=True) if body else ""
                method = "html"

            if text and len(text.strip()) > 10:
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                # Update the document
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE scraped_documents
                        SET content = %s,
                            extraction_status = 'success',
                            extraction_method = %s,
                            extraction_error = '',
                            extraction_attempts = extraction_attempts + 1,
                            extraction_timestamp = NOW(),
                            content_length = %s,
                            content_hash = %s,
                            updated_at = NOW()
                        WHERE link = %s
                    """, (text, method, len(text), content_hash, doc_link))

                    # Mark failure as resolved
                    cur.execute(
                        "UPDATE failed_extractions SET resolved = TRUE, resolved_at = NOW() WHERE id = %s",
                        (fail_id,),
                    )
                conn.commit()
                resolved += 1
                print(f"       RESOLVED: {len(text)} chars ({method})")
            else:
                still_failed += 1
                print(f"       STILL FAILED: extraction returned {len(text.strip()) if text else 0} chars")

        except Exception as e:
            still_failed += 1
            print(f"       STILL FAILED: {e}")

        print()

    conn.close()
    print(f"\nDone: {resolved} resolved, {still_failed} still failed, {no_cache} no cache")


if __name__ == "__main__":
    main()
