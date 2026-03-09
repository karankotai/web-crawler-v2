#!/usr/bin/env python3
"""Database migration: creates extracted_obligations table.

Usage:
    python scripts/migrate_obligations.py
    python scripts/migrate_obligations.py --dry-run   # show SQL without executing
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import config


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS extracted_obligations (
        id              SERIAL PRIMARY KEY,
        doc_id          INTEGER REFERENCES scraped_documents(id) ON DELETE SET NULL,
        title           TEXT NOT NULL DEFAULT '',
        source_url      TEXT NOT NULL DEFAULT '',
        pdf_links       JSONB NOT NULL DEFAULT '[]',
        chain_type      TEXT,
        repealed_by     TEXT,
        extraction      JSONB NOT NULL DEFAULT '{}',
        model_used      TEXT NOT NULL DEFAULT 'gpt-4o',
        token_count_in  INTEGER DEFAULT 0,
        token_count_out INTEGER DEFAULT 0,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_eo_doc_id ON extracted_obligations(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_eo_chain_type ON extracted_obligations(chain_type)",
    "CREATE INDEX IF NOT EXISTS idx_eo_created_at ON extracted_obligations(created_at DESC)",
]


def main():
    parser = argparse.ArgumentParser(description="Create extracted_obligations table")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN — SQL to execute ===\n")
        for stmt in DDL_STATEMENTS:
            print(stmt.strip() + ";\n")
        return

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for stmt in DDL_STATEMENTS:
                print(f"  Running: {stmt.strip()[:80]}...")
                cur.execute(stmt)
            conn.commit()
            print("  Schema migration complete.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

    print("\nMigration finished successfully.")


if __name__ == "__main__":
    main()
