#!/usr/bin/env python3
"""Database schema migration: adds extraction metadata, raw content cache, and dead letter queue.

Usage:
    python scripts/migrate_schema.py
    python scripts/migrate_schema.py --dry-run   # show SQL without executing
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import config


DDL_STATEMENTS = [
    # --- New columns on scraped_documents ---
    """
    ALTER TABLE scraped_documents
        ADD COLUMN IF NOT EXISTS extraction_status TEXT DEFAULT 'pending',
        ADD COLUMN IF NOT EXISTS extraction_method TEXT DEFAULT '',
        ADD COLUMN IF NOT EXISTS extraction_error TEXT DEFAULT '',
        ADD COLUMN IF NOT EXISTS extraction_attempts INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS extraction_timestamp TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS content_hash TEXT DEFAULT '',
        ADD COLUMN IF NOT EXISTS content_length INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS pdf_count INTEGER DEFAULT 0
    """,

    # --- Raw content cache ---
    """
    CREATE TABLE IF NOT EXISTS raw_content_cache (
        id              SERIAL PRIMARY KEY,
        document_link   TEXT NOT NULL,
        content_type    TEXT NOT NULL,
        source_url      TEXT NOT NULL,
        content_sha256  TEXT NOT NULL,
        raw_bytes       BYTEA,
        file_size       INTEGER DEFAULT 0,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(document_link, source_url)
    )
    """,

    # --- Dead letter queue for failed extractions ---
    """
    CREATE TABLE IF NOT EXISTS failed_extractions (
        id              SERIAL PRIMARY KEY,
        document_link   TEXT NOT NULL,
        source_url      TEXT NOT NULL,
        crawler         TEXT NOT NULL,
        error_type      TEXT NOT NULL,
        error_message   TEXT DEFAULT '',
        attempt_number  INTEGER DEFAULT 1,
        resolved        BOOLEAN DEFAULT FALSE,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        resolved_at     TIMESTAMPTZ
    )
    """,

    # --- Indexes ---
    "CREATE INDEX IF NOT EXISTS idx_raw_cache_doc_link ON raw_content_cache(document_link)",
    "CREATE INDEX IF NOT EXISTS idx_failed_ext_unresolved ON failed_extractions(resolved) WHERE resolved = FALSE",
    "CREATE INDEX IF NOT EXISTS idx_scraped_docs_extraction_status ON scraped_documents(extraction_status)",
]

BACKFILL_SQL = """
    UPDATE scraped_documents
    SET extraction_status = CASE
        WHEN content IS NOT NULL AND content != '' THEN 'success'
        WHEN pdf_links IS NOT NULL AND pdf_links != '[]'::jsonb THEN 'pending'
        ELSE 'skipped'
    END,
    content_length = COALESCE(LENGTH(content), 0),
    content_hash = CASE
        WHEN content IS NOT NULL AND content != ''
        THEN encode(sha256(convert_to(content, 'UTF8')), 'hex')
        ELSE ''
    END
    WHERE extraction_status = 'pending' OR extraction_status IS NULL
"""


def main():
    parser = argparse.ArgumentParser(description="Run database schema migration")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN — SQL to execute ===\n")
        for stmt in DDL_STATEMENTS:
            print(stmt.strip() + ";\n")
        print("--- Backfill ---")
        print(BACKFILL_SQL.strip() + ";\n")
        return

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for stmt in DDL_STATEMENTS:
                print(f"  Running: {stmt.strip()[:80]}...")
                cur.execute(stmt)
            conn.commit()
            print("  Schema migration complete.")

            print("  Running backfill...")
            cur.execute(BACKFILL_SQL)
            updated = cur.rowcount
            conn.commit()
            print(f"  Backfill complete: {updated} rows updated.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

    print("\nMigration finished successfully.")


if __name__ == "__main__":
    main()
