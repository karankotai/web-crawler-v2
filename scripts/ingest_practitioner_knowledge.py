#!/usr/bin/env python3
"""Ingest curated practitioner knowledge documents into the RAG system.

Reads markdown files from data/practitioner_knowledge/ and indexes them
into PostgreSQL and Qdrant. These documents cover practical GST knowledge
that isn't found in circulars — portal workarounds, law-vs-system gaps,
reconciliation procedures, etc.

Usage:
    python scripts/ingest_practitioner_knowledge.py            # Ingest all docs (incremental)
    python scripts/ingest_practitioner_knowledge.py --force     # Delete + re-ingest
    python scripts/ingest_practitioner_knowledge.py --dry-run   # Preview without writing
"""

import argparse
import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


CRAWLER_NAME = "practitioner_knowledge_ingest"
KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "practitioner_knowledge",
)


def load_markdown_files(directory: str) -> list[dict]:
    """Load all markdown files from the knowledge directory."""
    if not os.path.exists(directory):
        print(f"ERROR: Knowledge directory not found: {directory}")
        return []

    files = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(directory, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse frontmatter-style metadata from the first lines
        metadata = _parse_metadata(content, fname)
        files.append({
            "filename": fname,
            "filepath": filepath,
            "content": content,
            **metadata,
        })

    return files


def _parse_metadata(content: str, filename: str) -> dict:
    """Extract metadata from markdown frontmatter (lines starting with '# ' or YAML-style).

    Expected format at top of file:
    ---
    title: IMS Issues and Workarounds
    topic: IMS, Invoice Management System
    tags: G6, G16, IMS, QRMP
    date: 2026-03-11
    ---
    """
    metadata = {
        "title": filename.replace(".md", "").replace("_", " ").title(),
        "topic": "",
        "tags": [],
        "date": "2026-03-11",
    }

    # Try YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).split("\n"):
            line = line.strip()
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "title":
                metadata["title"] = val
            elif key == "topic":
                metadata["topic"] = val
            elif key == "tags":
                metadata["tags"] = [t.strip() for t in val.split(",")]
            elif key == "date":
                metadata["date"] = val
    else:
        # Fallback: use first H1 as title
        h1_match = re.match(r"^#\s+(.+)", content)
        if h1_match:
            metadata["title"] = h1_match.group(1).strip()

    return metadata


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL).strip()


def split_by_sections(content: str, filename: str) -> list[dict]:
    """Split a markdown document into sections by H2 headers.

    If the document is short (< 2000 chars), keep it as a single chunk.
    Otherwise split at ## headers for better retrieval granularity.
    """
    clean_content = _strip_frontmatter(content)

    if len(clean_content) < 2000:
        return [{"section_number": "0", "section_title": "Full Document", "content": clean_content}]

    # Split at ## headers
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(clean_content))

    if not matches:
        return [{"section_number": "0", "section_title": "Full Document", "content": clean_content}]

    sections = []

    # Text before first H2
    preamble = clean_content[:matches[0].start()].strip()
    if preamble and len(preamble) > 50:
        sections.append({
            "section_number": "0",
            "section_title": "Overview",
            "content": preamble,
        })

    for i, match in enumerate(matches):
        sec_title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_content)
        sec_content = clean_content[start:end].strip()

        sections.append({
            "section_number": str(i + 1),
            "section_title": sec_title,
            "content": sec_content,
        })

    return sections


def build_records(doc: dict) -> list[dict]:
    """Build PG-ready record dicts from a practitioner knowledge document."""
    sections = split_by_sections(doc["content"], doc["filename"])
    base_id = doc["filename"].replace(".md", "")

    records = []
    for sec in sections:
        sec_num = sec["section_number"]
        if sec_num == "0":
            circ_num = f"PKB-{base_id.upper()}"
            link_suffix = "overview"
        else:
            circ_num = f"PKB-{base_id.upper()}-S{sec_num}"
            link_suffix = f"section-{sec_num}"

        title = f"{sec['section_title']} ({doc['title']})" if sec_num != "0" else doc["title"]

        records.append({
            "source": "practitioner_knowledge",
            "title": title,
            "date": doc.get("date", "2026-03-11"),
            "department": "Practitioner Knowledge Base",
            "link": f"knowledge://{base_id}/{link_suffix}",
            "content": sec["content"],
            "circular_number": circ_num,
            "details": f"Practitioner Knowledge | {doc['title']}",
            "pdf_links": [],
            "doc_type": "Practitioner Knowledge",
            "topic": doc.get("topic", ""),
            "tags": ",".join(doc.get("tags", [])),
        })

    return records


# ── Database operations ──────────────────────────────────────


def delete_knowledge_records(conn):
    """Delete existing practitioner knowledge records."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM scraped_documents WHERE crawler = %s",
            (CRAWLER_NAME,),
        )
        deleted = cur.rowcount
        conn.commit()
        return deleted


def save_to_pg(records: list[dict]):
    """Save records to PostgreSQL."""
    from crawlers.base import _get_db_conn, _ensure_table, _upsert_records

    conn = _get_db_conn()
    if not conn:
        print("ERROR: DATABASE_URL not set, cannot save to PostgreSQL")
        sys.exit(1)
    try:
        _ensure_table(conn)
        _upsert_records(conn, records, CRAWLER_NAME)
        return len(records)
    finally:
        conn.close()


def delete_and_save(records: list[dict]):
    """Delete old records then insert new ones."""
    from crawlers.base import _get_db_conn, _ensure_table, _upsert_records

    conn = _get_db_conn()
    if not conn:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    try:
        _ensure_table(conn)
        deleted = delete_knowledge_records(conn)
        print(f"Deleted {deleted} existing knowledge records")
        _upsert_records(conn, records, CRAWLER_NAME)
        return len(records)
    finally:
        conn.close()


def index_to_qdrant(records: list[dict]):
    """Index records into Qdrant vector store."""
    from rag_app.services.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline()
    total = pipeline.index_records(records)
    return total


# ── Main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Ingest practitioner knowledge documents into the RAG system"
    )
    parser.add_argument("--force", action="store_true",
                        help="Delete existing knowledge records before re-ingesting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview documents without writing to DB")
    parser.add_argument("--no-index", action="store_true",
                        help="Save to PG only, skip Qdrant indexing")
    parser.add_argument("--dir", default=KNOWLEDGE_DIR,
                        help=f"Knowledge directory (default: {KNOWLEDGE_DIR})")
    args = parser.parse_args()

    docs = load_markdown_files(args.dir)
    if not docs:
        print(f"No markdown files found in {args.dir}")
        return

    print(f"Found {len(docs)} knowledge documents")

    all_records = []

    for doc in docs:
        print(f"\n  Processing: {doc['filename']}")
        print(f"    Title: {doc['title']}")
        print(f"    Topic: {doc.get('topic', 'N/A')}")

        records = build_records(doc)

        if args.dry_run:
            for r in records:
                print(f"    [{r['circular_number']}] {r['title'][:60]} ({len(r['content'])} chars)")
            continue

        all_records.extend(records)
        print(f"    Built {len(records)} records")

    if args.dry_run:
        print(f"\nDRY RUN complete.")
        return

    if not all_records:
        print("\nNo records to ingest.")
        return

    print(f"\n{'='*60}")
    print(f"Saving {len(all_records)} records to PostgreSQL...")

    if args.force:
        saved = delete_and_save(all_records)
    else:
        saved = save_to_pg(all_records)
    print(f"Saved {saved} records to PostgreSQL")

    if not args.no_index:
        print(f"\nIndexing {len(all_records)} records into Qdrant...")
        chunks = index_to_qdrant(all_records)
        print(f"Indexed {chunks} chunks into Qdrant")

    print(f"\nDone! Ingested {len(all_records)} sections from {len(docs)} knowledge document(s).")


if __name__ == "__main__":
    main()
