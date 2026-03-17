#!/usr/bin/env python3
"""Ingest targeted RBI Master Directions into the RAG system.

Fetches specific Master Direction pages from rbi.org.in, splits by chapter,
and indexes into PostgreSQL + Qdrant for precise retrieval.

Usage:
    python scripts/ingest_rbi_master_directions.py              # Ingest all targeted MDs
    python scripts/ingest_rbi_master_directions.py --dry-run     # Preview chapter splits
    python scripts/ingest_rbi_master_directions.py --force       # Delete + re-ingest
    python scripts/ingest_rbi_master_directions.py --ids 13028   # Specific MD only
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup

import config
from utils.pdf_extract import extract_text_from_pdf

CRAWLER_NAME = "rbi_master_directions_ingest"
BASE_URL = "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# Targeted Master Directions relevant to our evaluation questions
MASTER_DIRECTIONS = [
    {
        "id": 13028,
        "title": "Reserve Bank of India (Urban Co-operative Banks – Credit Facilities) Directions, 2025",
        "short_name": "UCB Credit Facilities MD",
        "relevance": "Gold lending norms, LTV ratios, exposure limits for UCBs (Q8)",
    },
    {
        "id": 13030,
        "title": "Reserve Bank of India (Urban Co-operative Banks – Prudential Norms on Capital Adequacy) Directions, 2025",
        "short_name": "UCB Capital Adequacy MD",
        "relevance": "Risk weights, CRAR requirements, exposure limits (Q8)",
    },
    {
        "id": 13024,
        "title": "Reserve Bank of India (Urban Co-operative Banks – Concentration Risk Management) Directions, 2025",
        "short_name": "UCB Concentration Risk MD",
        "relevance": "Single/group borrower exposure limits for UCBs (Q8)",
    },
    {
        "id": 12943,
        "title": "Reserve Bank of India (Non-Banking Financial Companies – Know Your Customer) Directions, 2025",
        "short_name": "NBFC KYC MD",
        "relevance": "KYC/AML/STR obligations for NBFCs, FIU-IND filing (Q9)",
    },
    {
        "id": 13014,
        "title": "Reserve Bank of India (Urban Co-operative Banks – Know Your Customer) Directions, 2025",
        "short_name": "UCB KYC MD",
        "relevance": "KYC/AML/STR for UCBs — comparison with NBFCs (Q9)",
    },
    {
        "id": 12957,
        "title": "Reserve Bank of India (Non-Banking Financial Companies – Credit Facilities) Directions, 2025",
        "short_name": "NBFC Credit Facilities MD",
        "relevance": "Lending norms, collateral rules for NBFCs (Q10)",
    },
    {
        "id": 12931,
        "title": "Reserve Bank of India (Non-Banking Financial Companies – Miscellaneous) Directions, 2025",
        "short_name": "NBFC Miscellaneous MD",
        "relevance": "General NBFC regulatory framework, SBR classification (Q9, Q10)",
    },
]

_MD_MAP = {md["id"]: md for md in MASTER_DIRECTIONS}


# ── Chapter splitting ────────────────────────────────────────


def split_into_chapters(full_text: str) -> list[dict]:
    """Split Master Direction text into chapters.

    Returns list of dicts: {chapter_number, chapter_title, content}
    """
    # Pattern: "Chapter I - Title" or "Chapter IV - Lending against Gold"
    pattern = re.compile(
        r"(?:^|\n)\s*(Chapter\s+[IVXLC]+(?:\s*[-–—.:]\s*|\s+))([^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = list(pattern.finditer(full_text))

    if not matches:
        # Try numbered chapters: "1. Title", "2. Title"
        pattern2 = re.compile(
            r"(?:^|\n)\s*(\d+)\s*[.\-–]\s+([A-Z][^\n]{5,80})",
            re.MULTILINE,
        )
        matches = list(pattern2.finditer(full_text))

    if not matches:
        return [{"chapter_number": "FULL", "chapter_title": "Full Text", "content": full_text.strip()}]

    chapters = []

    # Capture preamble
    preamble = full_text[: matches[0].start()].strip()
    if preamble and len(preamble) > 200:
        chapters.append({
            "chapter_number": "PREAMBLE",
            "chapter_title": "Preamble and Definitions",
            "content": preamble,
        })

    for i, match in enumerate(matches):
        chapter_label = match.group(1).strip().rstrip("-–—.: ")
        chapter_title = match.group(2).strip()

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        # Further split very long chapters into sub-sections
        sub_sections = _split_long_chapter(content, chapter_label)
        if sub_sections:
            chapters.extend(sub_sections)
        else:
            chapters.append({
                "chapter_number": chapter_label,
                "chapter_title": chapter_title,
                "content": content,
            })

    return chapters


def _split_long_chapter(content: str, chapter_label: str, max_chars: int = 8000) -> list[dict] | None:
    """Split a chapter that exceeds max_chars into sub-sections (A, B, C, etc.)."""
    if len(content) <= max_chars:
        return None

    # Try splitting by lettered sub-sections: "A. General Provisions"
    pattern = re.compile(
        r"(?:^|\n)\s*([A-Z])\s*[.\-–]\s+([^\n]{5,80})",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(content))

    if len(matches) < 2:
        return None

    sections = []
    for i, match in enumerate(matches):
        sec_letter = match.group(1)
        sec_title = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sec_content = content[start:end].strip()

        sections.append({
            "chapter_number": f"{chapter_label} ({sec_letter})",
            "chapter_title": sec_title,
            "content": sec_content,
        })

    return sections if sections else None


# ── Fetching ─────────────────────────────────────────────────


def fetch_master_direction(md: dict) -> str:
    """Fetch a Master Direction page and extract text content."""
    url = f"{BASE_URL}?id={md['id']}"
    print(f"  Fetching: {md['short_name']} (id={md['id']})...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ERROR: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    # Primary content is in .tablebg
    content_el = soup.select_one(".tablebg")
    if not content_el:
        content_el = soup.select_one("#divContent") or soup.body

    if not content_el:
        print("  WARNING: No content found")
        return ""

    text = content_el.get_text(separator="\n", strip=True)

    # Also check for PDF links
    pdf_links = []
    for a in content_el.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            if not href.startswith("http"):
                href = f"https://www.rbi.org.in/Scripts/{href}"
            pdf_links.append(href)

    # If PDF content is substantially longer, prefer it
    if pdf_links:
        print(f"  Found {len(pdf_links)} PDF link(s), checking...")
        for pdf_url in pdf_links[:2]:  # Check first 2 PDFs
            try:
                pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
                if pdf_resp.status_code == 200:
                    pdf_text = extract_text_from_pdf(pdf_resp.content)
                    if pdf_text and len(pdf_text) > len(text) * 1.5:
                        print(f"  Using PDF content ({len(pdf_text)} chars vs HTML {len(text)} chars)")
                        text = pdf_text
                        break
            except Exception as e:
                print(f"  PDF fetch failed: {e}")

    print(f"  Extracted {len(text)} chars")
    return text


# ── Record building ──────────────────────────────────────────


def build_records(md: dict, chapters: list[dict]) -> list[dict]:
    """Build PG-ready record dicts from parsed chapters."""
    records = []
    for ch in chapters:
        ch_num = ch["chapter_number"]
        ch_title = ch["chapter_title"]

        # Build a circular_number-like ID for retrieval
        safe_name = re.sub(r"[^a-zA-Z0-9]", "_", md["short_name"])[:30]
        if ch_num in ("PREAMBLE", "FULL"):
            circ_num = f"RBI_MD-{safe_name}-{ch_num}"
        else:
            safe_ch = re.sub(r"[^a-zA-Z0-9]", "_", ch_num)[:20]
            circ_num = f"RBI_MD-{safe_name}-{safe_ch}"

        title = f"{ch_title} ({md['short_name']})"

        records.append({
            "source": "rbi",
            "title": title,
            "date": "2025-01-01",  # Master Directions are current as of 2025
            "link": f"https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id={md['id']}",
            "circular_number": circ_num,
            "content": ch["content"],
            "pdf_links": [],
        })

    return records


# ── Database operations ──────────────────────────────────────


def delete_md_records(conn, md_ids: list[int] | None = None):
    """Delete existing Master Direction records for clean re-ingest."""
    with conn.cursor() as cur:
        if md_ids:
            conditions = " OR ".join(["link LIKE %s"] * len(md_ids))
            links = [f"%id={mid}%" for mid in md_ids]
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


def index_in_qdrant(records: list[dict]):
    """Index records directly in Qdrant via the RAG pipeline."""
    from rag_app.services.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline()
    result = pipeline.index_records(records)
    return result


# ── Main ─────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Ingest RBI Master Directions")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force", action="store_true", help="Delete existing + re-ingest")
    parser.add_argument("--ids", nargs="*", type=int, help="Specific MD IDs to ingest")
    args = parser.parse_args()

    # Select which MDs to process
    if args.ids:
        mds = [_MD_MAP[mid] for mid in args.ids if mid in _MD_MAP]
        if not mds:
            print(f"ERROR: None of {args.ids} found in manifest")
            sys.exit(1)
    else:
        mds = MASTER_DIRECTIONS

    print(f"Processing {len(mds)} Master Direction(s)...")

    all_records = []
    for md in mds:
        print(f"\n{'=' * 60}")
        print(f"  {md['title'][:80]}")
        print(f"  Relevance: {md['relevance']}")
        print(f"{'=' * 60}")

        # Fetch content
        text = fetch_master_direction(md)
        if not text or len(text) < 500:
            print(f"  SKIP: Too little content ({len(text or '')} chars)")
            continue

        # Split into chapters
        chapters = split_into_chapters(text)
        print(f"  Split into {len(chapters)} chapter(s)")

        if args.dry_run:
            for ch in chapters:
                content_preview = ch["content"][:80].replace("\n", " ")
                print(f"  [{ch['chapter_number']:>15}] {ch['chapter_title'][:50]:50s} ({len(ch['content'])} chars) | {content_preview}...")
            continue

        # Build records
        records = build_records(md, chapters)
        all_records.extend(records)
        print(f"  Built {len(records)} records")

        time.sleep(2)  # Rate limit

    if args.dry_run:
        print(f"\nDRY RUN complete. Would ingest {len(all_records)} records from {len(mds)} MD(s).")
        return

    if not all_records:
        print("No records to ingest.")
        return

    # Save to PostgreSQL
    if args.force:
        from crawlers.base import _get_db_conn
        conn = _get_db_conn()
        if conn:
            deleted = delete_md_records(conn, [md["id"] for md in mds])
            print(f"\nDeleted {deleted} existing MD records")
            conn.close()

    print(f"\nSaving {len(all_records)} records to PostgreSQL...")
    saved = save_to_pg(all_records)
    print(f"Saved {saved} records to PostgreSQL")

    # Index in Qdrant
    print(f"\nIndexing {len(all_records)} records into Qdrant...")
    index_in_qdrant(all_records)

    print(f"\nDone! Ingested {len(all_records)} chapters from {len(mds)} Master Direction(s).")


if __name__ == "__main__":
    main()
