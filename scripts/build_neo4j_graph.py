#!/usr/bin/env python3
"""Build Neo4j knowledge graph from extracted_obligations data.

Usage:
    python scripts/build_neo4j_graph.py                    # process all obligations
    python scripts/build_neo4j_graph.py --since 2025-01-01 # incremental since date
    python scripts/build_neo4j_graph.py --demo             # use demo_obligations.json
    python scripts/build_neo4j_graph.py --stats            # show graph stats only
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv

from rag_app.services.graph_store import GraphStore

load_dotenv()


def normalize_topic(subject: str) -> str:
    """Normalize a subject string into a canonical topic name."""
    topic = subject.strip().lower()
    # Remove common prefixes
    for prefix in ("regarding ", "re: ", "circular on ", "notification on "):
        if topic.startswith(prefix):
            topic = topic[len(prefix):]
    # Collapse whitespace
    topic = re.sub(r"\s+", " ", topic).strip()
    # Title case for display
    return topic.title() if topic else ""


def load_from_db(since: str | None = None) -> list[dict]:
    """Load obligations from PostgreSQL extracted_obligations table."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            query = """
                SELECT eo.id, eo.doc_id, eo.title, eo.source_url, eo.pdf_links,
                       eo.chain_type, eo.repealed_by, eo.extraction,
                       sd.circular_number, sd.date, sd.crawler
                FROM extracted_obligations eo
                LEFT JOIN scraped_documents sd ON eo.doc_id = sd.id
            """
            params: list = []
            if since:
                query += " WHERE eo.created_at >= %s"
                params.append(since)
            query += " ORDER BY eo.id"

            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


def load_from_demo() -> list[dict]:
    """Load obligations from demo_obligations.json."""
    demo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "demo_obligations.json",
    )
    with open(demo_path) as f:
        obligations = json.load(f)

    # Normalize to match DB shape
    result = []
    for ob in obligations:
        ext = ob.get("extraction", {})
        result.append({
            "doc_id": ob.get("doc_id"),
            "title": ob.get("title", ""),
            "source_url": ob.get("source_url", ""),
            "pdf_links": ob.get("pdf_links", []),
            "chain_type": ob.get("chain_type"),
            "repealed_by": ob.get("repealed_by"),
            "extraction": ext if isinstance(ext, dict) else json.loads(ext) if isinstance(ext, str) else {},
            "circular_number": ext.get("circular_reference", ""),
            "date": ext.get("date_issued", ""),
            "crawler": ext.get("issuing_authority", "").lower(),
        })
    return result


def build_graph(obligations: list[dict], graph: GraphStore) -> dict:
    """Process obligations and populate the Neo4j graph. Returns stats."""
    stats = {
        "circulars": 0,
        "supersedes": 0,
        "amends": 0,
        "applies_to": 0,
        "topics": 0,
        "skipped": 0,
    }

    for ob in obligations:
        ext = ob.get("extraction", {})
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except json.JSONDecodeError:
                stats["skipped"] += 1
                continue

        # Determine circular number — prefer extraction field, fall back to DB
        circular_number = (
            ext.get("circular_reference", "")
            or ob.get("circular_number", "")
        )
        if not circular_number:
            stats["skipped"] += 1
            continue

        # Upsert circular node
        graph.upsert_circular({
            "number": circular_number,
            "title": ob.get("title", ""),
            "date": ext.get("date_issued", ob.get("date", "")),
            "source": ext.get("issuing_authority", ob.get("crawler", "")).upper(),
            "effective_date": ext.get("effective_date", ""),
            "risk_level": ext.get("compliance_risk_level", ""),
            "doc_id": ob.get("doc_id"),
            "link": ob.get("source_url", ""),
            "summary": ext.get("summary", ""),
            "subject": ext.get("subject", ""),
        })
        stats["circulars"] += 1

        # SUPERSEDES relationships
        for sup in ext.get("supersedes", []):
            older_ref = sup.get("circular_reference", "")
            if older_ref:
                graph.create_supersedes(
                    newer_number=circular_number,
                    older_ref=older_ref,
                    description=sup.get("description", ""),
                )
                stats["supersedes"] += 1

        # AMENDS relationships
        for amend in ext.get("amendments_to", []):
            reg_name = amend.get("regulation_name", "")
            if reg_name:
                graph.create_amends(
                    circular_number=circular_number,
                    regulation_name=reg_name,
                    provisions=amend.get("specific_provisions", ""),
                )
                stats["amends"] += 1

        # APPLIES_TO relationships
        for applies in ext.get("applies_to", []):
            entity_type = applies.get("entity_type", "")
            if entity_type:
                graph.create_applies_to(
                    circular_number=circular_number,
                    entity_type=entity_type,
                    conditions=applies.get("conditions") or "",
                )
                stats["applies_to"] += 1

        # ABOUT relationships (from subject)
        subject = ext.get("subject", "")
        if subject:
            topic = normalize_topic(subject)
            if topic:
                graph.create_about(circular_number, topic)
                stats["topics"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Build Neo4j graph from extracted obligations")
    parser.add_argument("--since", help="Only process obligations created after this date (YYYY-MM-DD)")
    parser.add_argument("--demo", action="store_true", help="Use demo_obligations.json instead of DB")
    parser.add_argument("--stats", action="store_true", help="Show graph stats and exit")
    args = parser.parse_args()

    print("Connecting to Neo4j...")
    graph = GraphStore()

    if args.stats:
        stats = graph.get_stats()
        print(f"\nGraph stats:")
        for key, val in stats.items():
            print(f"  {key}: {val}")
        graph.close()
        return

    # Load data
    if args.demo:
        print("Loading from demo_obligations.json...")
        obligations = load_from_demo()
    else:
        print(f"Loading from PostgreSQL{' (since ' + args.since + ')' if args.since else ''}...")
        obligations = load_from_db(since=args.since)

    print(f"Loaded {len(obligations)} obligations")

    if not obligations:
        print("No obligations to process.")
        graph.close()
        return

    # Build graph
    print("Building graph...")
    stats = build_graph(obligations, graph)

    print(f"\nBuild complete:")
    for key, val in stats.items():
        print(f"  {key}: {val}")

    # Show final graph stats
    graph_stats = graph.get_stats()
    print(f"\nFinal graph state:")
    for key, val in graph_stats.items():
        print(f"  {key}: {val}")

    graph.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
