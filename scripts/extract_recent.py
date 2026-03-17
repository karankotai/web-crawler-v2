"""
Background job: extract obligations for recent unprocessed circulars.

Finds circulars in scraped_documents that don't yet have an entry in
extracted_obligations, runs LLM extraction, and saves with doc_id linked.

Usage:
    python scripts/extract_recent.py                   # 10 unprocessed
    python scripts/extract_recent.py --batch-size 20   # custom batch
    python scripts/extract_recent.py --source sebi     # filter by source
    python scripts/extract_recent.py --dry-run          # preview only
"""

import argparse
import json
import os
import sys
import time

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# Re-use extraction logic from the existing script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.extract_obligations import extract_obligations, print_obligations


def get_db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def fetch_unprocessed(conn, batch_size=10, source_filter=None):
    """Find recent circulars that have no matching extracted_obligations row."""
    query = """
        SELECT sd.id, sd.title, sd.date, sd.link, sd.content, sd.source,
               sd.circular_number, sd.pdf_links
        FROM scraped_documents sd
        LEFT JOIN extracted_obligations eo ON eo.doc_id = sd.id
        WHERE eo.id IS NULL
          AND sd.content IS NOT NULL AND sd.content != ''
          AND length(sd.content) > 500
    """
    params = []

    if source_filter:
        query += " AND LOWER(sd.source) LIKE %s"
        params.append(f"%{source_filter.lower()}%")

    query += " ORDER BY sd.date DESC, sd.created_at DESC LIMIT %s"
    params.append(batch_size)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def save_extraction(conn, doc, extraction, usage):
    """Insert into extracted_obligations with doc_id linking back to scraped_documents."""
    pdf_links = doc.get("pdf_links")
    if isinstance(pdf_links, str):
        try:
            pdf_links = json.loads(pdf_links)
        except (json.JSONDecodeError, TypeError):
            pdf_links = [pdf_links] if pdf_links else []
    elif not isinstance(pdf_links, list):
        pdf_links = []

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO extracted_obligations
                (doc_id, title, source_url, pdf_links, extraction,
                 model_used, token_count_in, token_count_out)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                doc["id"],
                doc["title"],
                doc.get("link", ""),
                json.dumps(pdf_links),
                json.dumps(extraction),
                "gpt-4o",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            ),
        )
        row_id = cur.fetchone()[0]
    conn.commit()
    return row_id


def main():
    parser = argparse.ArgumentParser(
        description="Extract obligations for recent unprocessed circulars"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Number of circulars to process (default: 10)"
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help="Filter by source (e.g., 'sebi', 'rbi')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview unprocessed circulars without extracting"
    )
    parser.add_argument(
        "--model", type=str, default="gpt-4o",
        help="Model to use for extraction (default: gpt-4o)"
    )
    args = parser.parse_args()

    conn = get_db_conn()
    docs = fetch_unprocessed(conn, args.batch_size, args.source)

    if not docs:
        print("No unprocessed circulars found.")
        return

    print(f"Found {len(docs)} unprocessed circular(s)")
    print()

    if args.dry_run:
        for doc in docs:
            content_len = len(doc["content"]) if doc["content"] else 0
            print(
                f"  ID={doc['id']:>8}  {doc['source']:<20} "
                f"{doc['date'] or 'no-date':<12} "
                f"[{content_len:>6} chars]  {doc['title'][:60]}"
            )
        print(f"\n{len(docs)} circulars would be processed. Use without --dry-run to extract.")
        conn.close()
        return

    processed = 0
    failed = 0

    for i, doc in enumerate(docs, 1):
        print(f"[{i}/{len(docs)}] ID={doc['id']}: {doc['title'][:70]}...")
        try:
            extraction, usage = extract_obligations(doc["content"], model=args.model)
            print_obligations(extraction, title=doc["title"])

            row_id = save_extraction(conn, doc, extraction, usage)
            print(f"  Saved as extracted_obligations.id={row_id}")
            processed += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

        # Rate-limit between calls
        if i < len(docs):
            time.sleep(1)

    conn.close()
    print(f"\nDone. Processed: {processed}, Failed: {failed}")


if __name__ == "__main__":
    main()
