#!/usr/bin/env python3
"""Audit data quality across all crawlers.

Reports per crawler:
1. Coverage: total records, records with content, records with empty content
2. Truncation detection: records with content_length exactly 5000 or 10000
3. PDF processing gaps: records with pdf_links but no content
4. Dead letter queue: unresolved failures by error_type
5. Cache completeness: records with pdf_links but no cached bytes
6. Extraction method distribution: pdfplumber vs ocr vs html_fallback
7. Short content flags: records with content < 500 chars

Usage:
    python scripts/audit_data_quality.py
    python scripts/audit_data_quality.py --crawler rbi_circulars
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import config


def get_conn():
    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(config.DATABASE_URL)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def audit_coverage(conn, crawler_filter):
    """Report record counts and content coverage."""
    print_section("1. COVERAGE")
    where = f"WHERE crawler = '{crawler_filter}'" if crawler_filter else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler,
                   COUNT(*) as total,
                   COUNT(CASE WHEN content IS NOT NULL AND content != '' THEN 1 END) as with_content,
                   COUNT(CASE WHEN content IS NULL OR content = '' THEN 1 END) as empty_content,
                   ROUND(100.0 * COUNT(CASE WHEN content IS NOT NULL AND content != '' THEN 1 END) / NULLIF(COUNT(*), 0), 1) as pct
            FROM scraped_documents
            {where}
            GROUP BY crawler
            ORDER BY crawler
        """)
        rows = cur.fetchall()
    print(f"\n  {'Crawler':<25} {'Total':>8} {'Content':>8} {'Empty':>8} {'Coverage':>8}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for crawler, total, with_content, empty, pct in rows:
        print(f"  {crawler:<25} {total:>8} {with_content:>8} {empty:>8} {pct:>7}%")


def audit_truncation(conn, crawler_filter):
    """Detect records likely truncated by old limits."""
    print_section("2. TRUNCATION DETECTION")
    where = f"AND crawler = '{crawler_filter}'" if crawler_filter else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler,
                   COUNT(CASE WHEN LENGTH(content) = 5000 THEN 1 END) as at_5000,
                   COUNT(CASE WHEN LENGTH(content) = 10000 THEN 1 END) as at_10000,
                   COUNT(CASE WHEN LENGTH(content) BETWEEN 4990 AND 5010 THEN 1 END) as near_5000,
                   COUNT(CASE WHEN LENGTH(content) BETWEEN 9990 AND 10010 THEN 1 END) as near_10000
            FROM scraped_documents
            WHERE content IS NOT NULL AND content != '' {where}
            GROUP BY crawler
            HAVING COUNT(CASE WHEN LENGTH(content) IN (5000, 10000) THEN 1 END) > 0
               OR COUNT(CASE WHEN LENGTH(content) BETWEEN 4990 AND 5010 THEN 1 END) > 0
               OR COUNT(CASE WHEN LENGTH(content) BETWEEN 9990 AND 10010 THEN 1 END) > 0
            ORDER BY crawler
        """)
        rows = cur.fetchall()
    if not rows:
        print("\n  No truncation detected!")
        return
    print(f"\n  {'Crawler':<25} {'=5000':>8} {'=10000':>8} {'~5000':>8} {'~10000':>8}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for crawler, at_5k, at_10k, near_5k, near_10k in rows:
        print(f"  {crawler:<25} {at_5k:>8} {at_10k:>8} {near_5k:>8} {near_10k:>8}")


def audit_pdf_gaps(conn, crawler_filter):
    """Find records with PDF links but no content."""
    print_section("3. PDF PROCESSING GAPS")
    where = f"AND crawler = '{crawler_filter}'" if crawler_filter else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler,
                   COUNT(*) as total_with_pdfs,
                   COUNT(CASE WHEN content IS NULL OR content = '' THEN 1 END) as no_content
            FROM scraped_documents
            WHERE pdf_links IS NOT NULL AND pdf_links != '[]'::jsonb {where}
            GROUP BY crawler
            ORDER BY crawler
        """)
        rows = cur.fetchall()
    print(f"\n  {'Crawler':<25} {'Has PDFs':>10} {'No Content':>12}")
    print(f"  {'-'*25} {'-'*10} {'-'*12}")
    for crawler, total, no_content in rows:
        flag = " <<<" if no_content > 0 else ""
        print(f"  {crawler:<25} {total:>10} {no_content:>12}{flag}")


def audit_dead_letter(conn, crawler_filter):
    """Report unresolved failures from dead letter queue."""
    print_section("4. DEAD LETTER QUEUE")
    where = f"AND crawler = '{crawler_filter}'" if crawler_filter else ""

    # Check if table exists
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'failed_extractions')"
        )
        if not cur.fetchone()[0]:
            print("\n  Table 'failed_extractions' does not exist yet.")
            return

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler, error_type, COUNT(*) as cnt
            FROM failed_extractions
            WHERE resolved = FALSE {where}
            GROUP BY crawler, error_type
            ORDER BY crawler, cnt DESC
        """)
        rows = cur.fetchall()
    if not rows:
        print("\n  No unresolved failures!")
        return
    print(f"\n  {'Crawler':<25} {'Error Type':<30} {'Count':>8}")
    print(f"  {'-'*25} {'-'*30} {'-'*8}")
    for crawler, error_type, cnt in rows:
        print(f"  {crawler:<25} {error_type:<30} {cnt:>8}")


def audit_cache(conn, crawler_filter):
    """Check cache completeness."""
    print_section("5. CACHE COMPLETENESS")

    # Check if table exists
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'raw_content_cache')"
        )
        if not cur.fetchone()[0]:
            print("\n  Table 'raw_content_cache' does not exist yet.")
            return

    where = f"AND sd.crawler = '{crawler_filter}'" if crawler_filter else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT sd.crawler,
                   COUNT(DISTINCT sd.link) as total_with_pdfs,
                   COUNT(DISTINCT rcc.document_link) as cached
            FROM scraped_documents sd
            LEFT JOIN raw_content_cache rcc ON sd.link = rcc.document_link
            WHERE sd.pdf_links IS NOT NULL AND sd.pdf_links != '[]'::jsonb {where}
            GROUP BY sd.crawler
            ORDER BY sd.crawler
        """)
        rows = cur.fetchall()
    print(f"\n  {'Crawler':<25} {'Has PDFs':>10} {'Cached':>10} {'Missing':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}")
    for crawler, total, cached in rows:
        missing = total - cached
        flag = " <<<" if missing > 0 else ""
        print(f"  {crawler:<25} {total:>10} {cached:>10} {missing:>10}{flag}")


def audit_extraction_methods(conn, crawler_filter):
    """Report extraction method distribution."""
    print_section("6. EXTRACTION METHOD DISTRIBUTION")
    where = f"AND crawler = '{crawler_filter}'" if crawler_filter else ""

    # Check if column exists
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scraped_documents' AND column_name = 'extraction_method'
            )
        """)
        if not cur.fetchone()[0]:
            print("\n  Column 'extraction_method' does not exist yet. Run migration first.")
            return

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler,
                   extraction_method,
                   COUNT(*) as cnt
            FROM scraped_documents
            WHERE extraction_method IS NOT NULL AND extraction_method != '' {where}
            GROUP BY crawler, extraction_method
            ORDER BY crawler, cnt DESC
        """)
        rows = cur.fetchall()
    if not rows:
        print("\n  No extraction method data yet.")
        return
    print(f"\n  {'Crawler':<25} {'Method':<20} {'Count':>8}")
    print(f"  {'-'*25} {'-'*20} {'-'*8}")
    for crawler, method, cnt in rows:
        print(f"  {crawler:<25} {method:<20} {cnt:>8}")


def audit_short_content(conn, crawler_filter):
    """Flag records with suspiciously short content."""
    print_section("7. SHORT CONTENT FLAGS (<500 chars)")
    where = f"AND crawler = '{crawler_filter}'" if crawler_filter else ""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT crawler,
                   COUNT(*) as short_count,
                   MIN(LENGTH(content)) as min_len,
                   AVG(LENGTH(content))::int as avg_len
            FROM scraped_documents
            WHERE content IS NOT NULL AND content != ''
              AND LENGTH(content) < 500 {where}
            GROUP BY crawler
            ORDER BY short_count DESC
        """)
        rows = cur.fetchall()
    if not rows:
        print("\n  No suspiciously short content found!")
        return
    print(f"\n  {'Crawler':<25} {'Count':>8} {'Min Len':>8} {'Avg Len':>8}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
    for crawler, count, min_len, avg_len in rows:
        print(f"  {crawler:<25} {count:>8} {min_len:>8} {avg_len:>8}")


def main():
    parser = argparse.ArgumentParser(description="Audit data quality across all crawlers")
    parser.add_argument("--crawler", type=str, default=None, help="Filter to a specific crawler")
    args = parser.parse_args()

    conn = get_conn()

    print("\n" + "="*60)
    print("  DATA QUALITY AUDIT REPORT")
    print("="*60)

    audit_coverage(conn, args.crawler)
    audit_truncation(conn, args.crawler)
    audit_pdf_gaps(conn, args.crawler)
    audit_dead_letter(conn, args.crawler)
    audit_cache(conn, args.crawler)
    audit_extraction_methods(conn, args.crawler)
    audit_short_content(conn, args.crawler)

    print(f"\n{'='*60}")
    print("  Audit complete.")
    print(f"{'='*60}\n")

    conn.close()


if __name__ == "__main__":
    main()
