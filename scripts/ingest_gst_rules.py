#!/usr/bin/env python3
"""Ingest GST Rules texts into the RAG system, split by rule.

Each rule becomes a separate document in PostgreSQL and Qdrant,
enabling precise rule-level retrieval for queries like
"What does Rule 89 of CGST Rules say about inverted duty refund?"

Usage:
    python scripts/ingest_gst_rules.py                   # Ingest all rule sets (incremental)
    python scripts/ingest_gst_rules.py --force            # Delete + re-ingest
    python scripts/ingest_gst_rules.py --dry-run          # Preview rule splits
    python scripts/ingest_gst_rules.py --rules cgst       # Specific rule set only
    python scripts/ingest_gst_rules.py --pdf-dir ./pdfs   # Use local PDFs
"""

import argparse
import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import config
from utils.pdf_extract import extract_text_from_pdf

CRAWLER_NAME = "gst_rules_ingest"

GST_RULES = [
    {
        "rules_id": "cgst_rules",
        "rules_name": "Central Goods and Services Tax Rules, 2017",
        "short_name": "CGST Rules",
        "pdf_filename": "cgst_rules.pdf",
        "url": "https://gstcouncil.gov.in/sites/default/files/2024-04/01062021-cgst-rules-2017-part-a-rules.pdf",
        "date": "2017-06-28",
    },
]

# Map rules_id to manifest entry
_RULES_MAP = {r["rules_id"]: r for r in GST_RULES}


# ── Rule splitting ──────────────────────────────────────────


def split_into_rules(full_text: str) -> list[dict]:
    """Split rules text into individual rules.

    Returns list of dicts: {rule_number, rule_title, content}
    Also captures Preamble (before Rule 1) and Forms/Annexures (after last rule).
    """
    # Try multiple patterns in order of specificity
    patterns = [
        # "Rule 89. — Refund of Input Tax Credit..."
        re.compile(
            r"(?:^|\n)\s*(?:RULE|Rule|rule)\s+(\d+[A-Z]?)\s*[.\u2014\u2013\-]+\s*(.+?)(?=\s*[.\u2014\u2013\-])",
            re.MULTILINE,
        ),
        # "89. Application for refund of input tax credit.—"
        re.compile(
            r"(?:^|\n)\s*(\d+[A-Z]?)\s*\.\s+([A-Z][^.\n]{3,80})\s*[.\u2014\u2013\-]",
            re.MULTILINE,
        ),
    ]

    matches = []
    for pattern in patterns:
        matches = list(pattern.finditer(full_text))
        if len(matches) >= 5:  # need a reasonable number to confirm correct pattern
            break

    if not matches:
        return [{"rule_number": "0", "rule_title": "Full Text", "content": full_text.strip()}]

    rules = []

    # Capture preamble (text before first rule)
    preamble_text = full_text[: matches[0].start()].strip()
    if preamble_text and len(preamble_text) > 100:
        rules.append({
            "rule_number": "PREAMBLE",
            "rule_title": "Preamble",
            "content": preamble_text,
        })

    # Extract each rule
    for i, match in enumerate(matches):
        rule_num = match.group(1)
        rule_title = match.group(2).strip().rstrip(".\u2014\u2013\u2010-")

        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        # Check if remaining text after last rule contains forms/annexures
        if i == len(matches) - 1:
            forms_match = re.search(r"\n\s*(?:FORM|ANNEXURE|SCHEDULE)", content, re.IGNORECASE)
            if forms_match:
                forms_text = content[forms_match.start():].strip()
                content = content[:forms_match.start()].strip()
                rules.append({
                    "rule_number": rule_num,
                    "rule_title": rule_title,
                    "content": content,
                })
                rules.append({
                    "rule_number": "FORMS",
                    "rule_title": "Forms and Annexures",
                    "content": forms_text,
                })
                continue

        rules.append({
            "rule_number": rule_num,
            "rule_title": rule_title,
            "content": content,
        })

    return rules


# ── Record building ──────────────────────────────────────────


def build_records(ruleset: dict, rules: list[dict]) -> list[dict]:
    """Build PG-ready record dicts from parsed rules."""
    records = []
    for rule in rules:
        rule_num = rule["rule_number"]
        rule_title = rule["rule_title"]
        # Build circular_number for retrieval (e.g., CGST_RULES-R89)
        rules_prefix = ruleset["rules_id"].upper()
        if rule_num in ("PREAMBLE", "FORMS"):
            circ_num = f"{rules_prefix}-{rule_num}"
            title = f"{rule_title} ({ruleset['short_name']})"
            link_suffix = rule_num.lower()
        else:
            circ_num = f"{rules_prefix}-R{rule_num}"
            title = f"Rule {rule_num} - {rule_title} ({ruleset['short_name']})"
            link_suffix = f"rule-{rule_num}"

        records.append({
            "source": "legislation",
            "title": title,
            "date": ruleset["date"],
            "department": "CBIC - GST",
            "link": f"legislation://{ruleset['rules_id']}/{link_suffix}",
            "content": rule["content"],
            "circular_number": circ_num,
            "details": f"{ruleset['short_name']} | {rule_title}",
            "pdf_links": [ruleset["url"]],
            # Extra fields (go into JSONB automatically)
            "rules_name": ruleset["rules_name"],
            "rules_id": ruleset["rules_id"],
            "rule_number": rule_num,
            "rule_title": rule_title,
            "doc_type": "Legislation",
        })
    return records


# ── PDF fetching ─────────────────────────────────────────────


def fetch_pdf_text(ruleset: dict, pdf_dir: str | None) -> str:
    """Download or read a GST Rules PDF and extract text."""
    if pdf_dir:
        pdf_path = os.path.join(pdf_dir, ruleset["pdf_filename"])
        if not os.path.exists(pdf_path):
            alt_path = os.path.join(pdf_dir, f"{ruleset['rules_id']}.pdf")
            if os.path.exists(alt_path):
                pdf_path = alt_path
            else:
                print(f"  ERROR: PDF not found at {pdf_path} or {alt_path}")
                return ""
        print(f"  Reading from {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    else:
        print(f"  Downloading from {ruleset['url']}")
        resp = requests.get(
            ruleset["url"],
            headers=config.HEADERS,
            timeout=config.PDF_TIMEOUT,
            verify=False,
        )
        resp.raise_for_status()
        pdf_bytes = resp.content

    text = extract_text_from_pdf(pdf_bytes)
    if not text or len(text) < 200:
        print(f"  WARNING: Extracted very little text ({len(text or '')} chars)")
    return text or ""


# ── Database operations ──────────────────────────────────────


def delete_rules_records(conn, rules_ids: list[str] | None = None):
    """Delete existing rules records for clean re-ingest."""
    with conn.cursor() as cur:
        if rules_ids:
            conditions = " OR ".join(["link LIKE %s"] * len(rules_ids))
            links = [f"legislation://{rid}/%" for rid in rules_ids]
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


def delete_and_save(records: list[dict], rules_ids: list[str]):
    """Delete old records then insert new ones."""
    from crawlers.base import _get_db_conn, _ensure_table, _upsert_records

    conn = _get_db_conn()
    if not conn:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    try:
        _ensure_table(conn)
        deleted = delete_rules_records(conn, rules_ids)
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
    parser = argparse.ArgumentParser(description="Ingest GST Rules texts into the RAG system")
    parser.add_argument("--rules", nargs="+", choices=list(_RULES_MAP.keys()),
                        help="Specific rule sets to ingest (default: all)")
    parser.add_argument("--pdf-dir", help="Directory with local PDF files instead of downloading")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing rules records before re-ingesting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview rule splits without writing to DB")
    parser.add_argument("--no-index", action="store_true",
                        help="Save to PG only, skip Qdrant indexing")
    args = parser.parse_args()

    rules_ids = args.rules or list(_RULES_MAP.keys())
    rulesets = [_RULES_MAP[rid] for rid in rules_ids]

    all_records = []

    for ruleset in rulesets:
        print(f"\n{'='*60}")
        print(f"Processing: {ruleset['rules_name']}")
        print(f"{'='*60}")

        text = fetch_pdf_text(ruleset, args.pdf_dir)
        if not text:
            print(f"  SKIPPED: No text extracted for {ruleset['short_name']}")
            continue

        print(f"  Extracted {len(text)} chars")

        rules = split_into_rules(text)
        print(f"  Split into {len(rules)} rules")

        if args.dry_run:
            print(f"\n  --- Rule Preview for {ruleset['short_name']} ---")
            for rule in rules:
                content_preview = rule["content"][:80].replace("\n", " ")
                print(f"  [{rule['rule_number']:>10}] {rule['rule_title'][:50]:<50} ({len(rule['content'])} chars) | {content_preview}...")
            continue

        records = build_records(ruleset, rules)
        all_records.extend(records)
        print(f"  Built {len(records)} records")

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN complete.")
        return

    if not all_records:
        print("\nNo records to ingest.")
        return

    print(f"\n{'='*60}")
    print(f"Saving {len(all_records)} records to PostgreSQL...")

    if args.force:
        saved = delete_and_save(all_records, rules_ids)
    else:
        saved = save_to_pg(all_records)
    print(f"Saved {saved} records to PostgreSQL")

    if not args.no_index:
        print(f"\nIndexing {len(all_records)} records into Qdrant...")
        chunks = index_to_qdrant(all_records)
        print(f"Indexed {chunks} chunks into Qdrant")

    print(f"\nDone! Ingested {len(all_records)} rules from {len(rules_ids)} GST Rule set(s).")


if __name__ == "__main__":
    main()
