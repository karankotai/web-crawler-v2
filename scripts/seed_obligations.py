#!/usr/bin/env python3
"""Seed extracted_obligations table from demo_obligations.json.

Usage:
    python scripts/seed_obligations.py
    python scripts/seed_obligations.py --dry-run
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
import config

JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_obligations.json")


def main():
    parser = argparse.ArgumentParser(description="Seed extracted_obligations from demo JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted")
    args = parser.parse_args()

    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} items from demo_obligations.json")

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            inserted = 0
            skipped = 0
            for item in data:
                doc_id = item.get("doc_id")

                # Dedup: skip if doc_id already exists
                if doc_id:
                    cur.execute(
                        "SELECT 1 FROM extracted_obligations WHERE doc_id = %s",
                        (doc_id,),
                    )
                    if cur.fetchone():
                        print(f"  Skipping doc_id={doc_id} (already exists)")
                        skipped += 1
                        continue

                if args.dry_run:
                    print(f"  Would insert: doc_id={doc_id}, title={item['title'][:60]}...")
                    inserted += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO extracted_obligations
                        (doc_id, title, source_url, pdf_links, chain_type, repealed_by, extraction, model_used)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        doc_id,
                        item.get("title", ""),
                        item.get("source_url", ""),
                        json.dumps(item.get("pdf_links", [])),
                        item.get("chain_type"),
                        item.get("repealed_by"),
                        json.dumps(item.get("extraction", {})),
                        "gpt-4o",
                    ),
                )
                inserted += 1

            if not args.dry_run:
                conn.commit()

            print(f"\nDone. Inserted: {inserted}, Skipped: {skipped}")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: Seeding failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
