#!/usr/bin/env python3
"""Ingest GST Act texts into the RAG system, split by section.

Each section becomes a separate document in PostgreSQL and Qdrant,
enabling precise section-level retrieval for queries like
"What does Section 16 of CGST Act say?"

Usage:
    python scripts/ingest_gst_acts.py                  # Ingest all acts (incremental)
    python scripts/ingest_gst_acts.py --force           # Delete + re-ingest
    python scripts/ingest_gst_acts.py --dry-run         # Preview section splits
    python scripts/ingest_gst_acts.py --acts cgst igst  # Specific acts only
    python scripts/ingest_gst_acts.py --pdf-dir ./pdfs  # Use local PDFs
"""

import argparse
import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import config
from utils.pdf_extract import extract_text_from_pdf

CRAWLER_NAME = "gst_acts_ingest"

GST_ACTS = [
    {
        "act_id": "cgst",
        "act_name": "Central Goods and Services Tax Act, 2017",
        "short_name": "CGST Act",
        "pdf_filename": "cgst_act.pdf",
        "url": "https://cbic-gst.gov.in/pdf/cgst-act-updated-30092020.pdf",
        "date": "2017-04-12",
    },
    {
        "act_id": "igst",
        "act_name": "Integrated Goods and Services Tax Act, 2017",
        "short_name": "IGST Act",
        "pdf_filename": "igst_act.pdf",
        "url": "https://cbic-gst.gov.in/pdf/igst-act-updated-30092020.pdf",
        "date": "2017-04-12",
    },
    {
        "act_id": "utgst",
        "act_name": "Union Territory Goods and Services Tax Act, 2017",
        "short_name": "UTGST Act",
        "pdf_filename": "utgst_act.pdf",
        "url": "https://cbic-gst.gov.in/pdf/utgst-act.pdf",
        "date": "2017-04-12",
    },
    {
        "act_id": "gst_compensation",
        "act_name": "Goods and Services Tax (Compensation to States) Act, 2017",
        "short_name": "GST Compensation Act",
        "pdf_filename": "gst_compensation_act.pdf",
        "url": "https://cbic-gst.gov.in/pdf/gst-compensation-to-states-act.pdf",
        "date": "2017-04-12",
    },
]

# Map act_id to manifest entry
_ACT_MAP = {a["act_id"]: a for a in GST_ACTS}


# ── Section splitting ────────────────────────────────────────


def split_into_sections(full_text: str) -> list[dict]:
    """Split act text into individual sections.

    Returns list of dicts: {section_number, section_title, content}
    Also captures Preamble (before Section 1) and Schedules (after last section).
    """
    # Match patterns like:
    #   "Section 16. — Eligibility and conditions..."
    #   "16. Eligibility and conditions for taking input tax credit.—"
    #   "SECTION 16A.—..."
    pattern = re.compile(
        r"(?:^|\n)\s*(?:SECTION|Section|section)\s+(\d+[A-Z]?)\s*[.\u2014\u2013\-]+\s*(.+?)(?=\s*[.\u2014\u2013\-])",
        re.MULTILINE,
    )

    matches = list(pattern.finditer(full_text))

    if not matches:
        # Fallback: try simpler numbered pattern "1. Short title..."
        pattern2 = re.compile(
            r"(?:^|\n)\s*(\d+[A-Z]?)\s*\.\s+([A-Z][^.\n]{3,60})\s*[.\u2014\u2013\-]",
            re.MULTILINE,
        )
        matches = list(pattern2.finditer(full_text))

    if not matches:
        return [{"section_number": "0", "section_title": "Full Text", "content": full_text.strip()}]

    sections = []

    # Capture preamble (text before first section)
    preamble_text = full_text[: matches[0].start()].strip()
    if preamble_text and len(preamble_text) > 100:
        sections.append({
            "section_number": "PREAMBLE",
            "section_title": "Preamble",
            "content": preamble_text,
        })

    # Extract each section
    for i, match in enumerate(matches):
        sec_num = match.group(1)
        sec_title = match.group(2).strip().rstrip(".\u2014\u2013\u2010-")

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        # Check if remaining text after last section contains schedules
        if i == len(matches) - 1:
            schedule_match = re.search(r"\n\s*SCHEDULE", content, re.IGNORECASE)
            if schedule_match:
                schedule_text = content[schedule_match.start():].strip()
                content = content[:schedule_match.start()].strip()
                # Add schedule as separate entry
                sections.append({
                    "section_number": sec_num,
                    "section_title": sec_title,
                    "content": content,
                })
                sections.append({
                    "section_number": "SCHEDULES",
                    "section_title": "Schedules",
                    "content": schedule_text,
                })
                continue

        sections.append({
            "section_number": sec_num,
            "section_title": sec_title,
            "content": content,
        })

    return sections


# ── Record building ──────────────────────────────────────────


def build_records(act: dict, sections: list[dict]) -> list[dict]:
    """Build PG-ready record dicts from parsed sections."""
    records = []
    for sec in sections:
        sec_num = sec["section_number"]
        sec_title = sec["section_title"]
        # Build circular_number for retrieval
        act_prefix = act["act_id"].upper()
        if sec_num in ("PREAMBLE", "SCHEDULES"):
            circ_num = f"{act_prefix}-{sec_num}"
            title = f"{sec_title} ({act['short_name']})"
            link_suffix = sec_num.lower()
        else:
            circ_num = f"{act_prefix}-S{sec_num}"
            title = f"Section {sec_num} - {sec_title} ({act['short_name']})"
            link_suffix = f"section-{sec_num}"

        records.append({
            "source": "legislation",
            "title": title,
            "date": act["date"],
            "department": "CBIC - GST",
            "link": f"legislation://{act['act_id']}/{link_suffix}",
            "content": sec["content"],
            "circular_number": circ_num,
            "details": f"{act['short_name']} | {sec_title}",
            "pdf_links": [act["url"]],
            # Extra fields (go into JSONB automatically)
            "act_name": act["act_name"],
            "act_id": act["act_id"],
            "section_number": sec_num,
            "section_title": sec_title,
            "doc_type": "Legislation",
        })
    return records


# ── PDF fetching ─────────────────────────────────────────────


def fetch_pdf_text(act: dict, pdf_dir: str | None) -> str:
    """Download or read a GST Act PDF and extract text."""
    if pdf_dir:
        pdf_path = os.path.join(pdf_dir, act["pdf_filename"])
        if not os.path.exists(pdf_path):
            # Also try act_id-based name
            alt_path = os.path.join(pdf_dir, f"{act['act_id']}.pdf")
            if os.path.exists(alt_path):
                pdf_path = alt_path
            else:
                print(f"  ERROR: PDF not found at {pdf_path} or {alt_path}")
                return ""
        print(f"  Reading from {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    else:
        print(f"  Downloading from {act['url']}")
        resp = requests.get(act["url"], headers=config.HEADERS, timeout=config.PDF_TIMEOUT, verify=False)
        resp.raise_for_status()
        pdf_bytes = resp.content

    text = extract_text_from_pdf(pdf_bytes)
    if not text or len(text) < 200:
        print(f"  WARNING: Extracted very little text ({len(text or '')} chars)")
    return text or ""


# ── Database operations ──────────────────────────────────────


def delete_legislation_records(conn, act_ids: list[str] | None = None):
    """Delete existing legislation records for clean re-ingest."""
    with conn.cursor() as cur:
        if act_ids:
            placeholders = ", ".join(["%s"] * len(act_ids))
            links = [f"legislation://{aid}/%" for aid in act_ids]
            conditions = " OR ".join(["link LIKE %s"] * len(links))
            cur.execute(
                f"DELETE FROM scraped_documents WHERE crawler = %s AND ({conditions})",
                [CRAWLER_NAME] + links,
            )
        else:
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


def delete_and_save(records: list[dict], act_ids: list[str]):
    """Delete old records then insert new ones."""
    from crawlers.base import _get_db_conn, _ensure_table, _upsert_records

    conn = _get_db_conn()
    if not conn:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    try:
        _ensure_table(conn)
        deleted = delete_legislation_records(conn, act_ids)
        print(f"Deleted {deleted} existing records")
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
    parser = argparse.ArgumentParser(description="Ingest GST Act texts into the RAG system")
    parser.add_argument("--acts", nargs="+", choices=list(_ACT_MAP.keys()),
                        help="Specific acts to ingest (default: all)")
    parser.add_argument("--pdf-dir", help="Directory with local PDF files instead of downloading")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing legislation records before re-ingesting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview section splits without writing to DB")
    parser.add_argument("--no-index", action="store_true",
                        help="Save to PG only, skip Qdrant indexing")
    args = parser.parse_args()

    act_ids = args.acts or list(_ACT_MAP.keys())
    acts = [_ACT_MAP[aid] for aid in act_ids]

    all_records = []

    for act in acts:
        print(f"\n{'='*60}")
        print(f"Processing: {act['act_name']}")
        print(f"{'='*60}")

        text = fetch_pdf_text(act, args.pdf_dir)
        if not text:
            print(f"  SKIPPED: No text extracted for {act['short_name']}")
            continue

        print(f"  Extracted {len(text)} chars")

        sections = split_into_sections(text)
        print(f"  Split into {len(sections)} sections")

        if args.dry_run:
            print(f"\n  --- Section Preview for {act['short_name']} ---")
            for sec in sections:
                content_preview = sec["content"][:80].replace("\n", " ")
                print(f"  [{sec['section_number']:>10}] {sec['section_title'][:50]:<50} ({len(sec['content'])} chars) | {content_preview}...")
            continue

        records = build_records(act, sections)
        all_records.extend(records)
        print(f"  Built {len(records)} records")

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN complete. Total sections found: {sum(len(split_into_sections(fetch_pdf_text(a, args.pdf_dir))) for a in acts if fetch_pdf_text(a, args.pdf_dir))}" if False else "DRY RUN complete.")
        return

    if not all_records:
        print("\nNo records to ingest.")
        return

    print(f"\n{'='*60}")
    print(f"Saving {len(all_records)} records to PostgreSQL...")

    if args.force:
        saved = delete_and_save(all_records, act_ids)
    else:
        saved = save_to_pg(all_records)
    print(f"Saved {saved} records to PostgreSQL")

    if not args.no_index:
        print(f"\nIndexing {len(all_records)} records into Qdrant...")
        chunks = index_to_qdrant(all_records)
        print(f"Indexed {chunks} chunks into Qdrant")

    print(f"\nDone! Ingested {len(all_records)} sections from {len(act_ids)} GST Act(s).")


if __name__ == "__main__":
    main()
