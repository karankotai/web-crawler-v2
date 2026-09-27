"""Populate Neo4j graph from Qdrant vector store metadata.

Extracts circulars, relationships (SUPERSEDES, AMENDS, APPLIES_TO, ABOUT),
topic clustering, and entity hierarchy from chunk text using regex patterns.

Usage:
    python3 scripts/populate_graph_from_qdrant.py [--stats] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_app.services.graph_store import GraphStore
from rag_app.services.vector_store import VectorStore

# ── Regex patterns for relationship extraction ──────────────

# Supersedes: "supersedes circular RBI/2023-24/45" etc.
_CIRCULAR_REF_PATTERN = re.compile(
    r"(?:RBI|SEBI|IRDAI|MCA|CBIC|CBDT|ICAI|IBBI|DGFT)"
    r"[/\-]"
    r"\d{4}[\-]\d{2,4}"
    r"[/\-]"
    r"\d+",
    re.IGNORECASE,
)

_SUPERSEDES_PATTERN = re.compile(
    r"(?:supersede[sd]?|replace[sd]?|revoke[sd]?|withdraw[sn]?|repeal(?:ed|s)?|"
    r"rescind(?:ed|s)?|cancel(?:led|s)?|in\s+(?:supersession|replacement)\s+of)"
    r"\s+(?:the\s+)?(?:earlier\s+)?(?:circular\s+(?:no\.?\s*)?|notification\s+(?:no\.?\s*)?|"
    r"direction\s+(?:no\.?\s*)?|master\s+direction\s+(?:no\.?\s*)?)?",
    re.IGNORECASE,
)

_AMENDS_PATTERN = re.compile(
    r"(?:amend(?:s|ed|ment|ing)?|modif(?:y|ies|ied|ication)|"
    r"insert(?:s|ed|ing)?|substitut(?:e[sd]?|ing|ion))"
    r"\s+(?:the\s+)?(?:following\s+)?(?:provision[s]?\s+(?:of\s+)?(?:the\s+)?)?"
    r"((?:[\w\s\(\)]+?)(?:Act|Rules?|Regulations?|Direction[s]?|Guidelines?|Norms?))"
    r"(?:\s*,\s*\d{4})?",
    re.IGNORECASE,
)

_APPLIES_TO_PATTERN = re.compile(
    r"(?:appli(?:es|cable|cability)\s+to|shall\s+apply\s+to|"
    r"applicable\s+to\s+all|directed\s+to\s+all)\s+"
    r"([\w\s\(\)/\-,]+?)(?:\.|,\s*(?:who|which|that|as|with)|$)",
    re.IGNORECASE,
)

# Known entity types to extract from APPLIES_TO matches
_ENTITY_KEYWORDS = [
    "Scheduled Commercial Banks", "Commercial Banks", "Banks",
    "Urban Cooperative Banks", "UCBs", "Regional Rural Banks", "RRBs",
    "Small Finance Banks", "SFBs", "Payments Banks",
    "NBFCs", "Non-Banking Financial Companies",
    "All India Financial Institutions", "AIFIs",
    "Housing Finance Companies", "HFCs",
    "Payment System Operators", "Payment Aggregators",
    "Insurance Companies", "Insurers",
    "Stock Brokers", "Trading Members", "Clearing Members",
    "Depository Participants", "Depositories",
    "Mutual Funds", "AMCs", "Asset Management Companies",
    "Listed Companies", "Listed Entities",
    "Merchant Bankers", "Credit Rating Agencies",
    "Regulated Entities",
]

_ENTITY_KEYWORD_SET = {kw.lower() for kw in _ENTITY_KEYWORDS}


def _scroll_all_chunks(vs: VectorStore) -> list[dict]:
    """Scroll through all Qdrant points and return payload dicts."""
    all_payloads = []
    offset = None
    batch = 0
    while True:
        points, offset = vs.client.scroll(
            collection_name=vs.collection_name,
            scroll_filter=None,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            all_payloads.append(point.payload)
        batch += 1
        if batch % 20 == 0:
            print(f"  Scrolled {len(all_payloads)} chunks...")
        if offset is None:
            break
    return all_payloads


def _group_by_circular(payloads: list[dict]) -> dict[str, dict]:
    """Group chunks by circular_number, collecting best metadata per circular.

    Returns {circular_number: {number, title, date, source, link, texts}}.
    """
    circulars: dict[str, dict] = {}
    for p in payloads:
        cn = p.get("circular_number", "")
        if not cn or not cn.strip():
            continue
        cn = cn.strip()
        if cn not in circulars:
            circulars[cn] = {
                "number": cn,
                "title": p.get("title", ""),
                "date": p.get("date", ""),
                "source": p.get("source", ""),
                "link": p.get("link", ""),
                "texts": [],
            }
        # Keep longer title (chunk 0 usually has the best title)
        if len(p.get("title", "")) > len(circulars[cn]["title"]):
            circulars[cn]["title"] = p["title"]
        # Keep earliest date
        if p.get("date") and (not circulars[cn]["date"] or p["date"] < circulars[cn]["date"]):
            circulars[cn]["date"] = p["date"]
        # Collect text for relationship extraction (limit to first 5 chunks)
        if len(circulars[cn]["texts"]) < 5:
            circulars[cn]["texts"].append(p.get("text", ""))
    return circulars


def _extract_supersedes(circular_number: str, combined_text: str) -> list[str]:
    """Extract circular references that this circular supersedes.

    Looks for supersession language and finds circular references both
    before and after the keyword within a reasonable window.
    """
    refs = []
    cn_upper = circular_number.upper()
    for match in _SUPERSEDES_PATTERN.finditer(combined_text):
        # Look for circular references in a window around the keyword
        # Before: "RBI/2023-24/45 is hereby superseded"
        # After: "supersedes circular RBI/2023-24/45"
        window_start = max(0, match.start() - 300)
        window_end = min(len(combined_text), match.end() + 400)
        window = combined_text[window_start:window_end]
        for ref_match in _CIRCULAR_REF_PATTERN.finditer(window):
            ref = ref_match.group(0).upper()
            # Normalize: 2023-2024 → 2023-24
            ref = re.sub(r"(\d{4})-(\d{4})", lambda m: f"{m.group(1)}-{m.group(2)[2:]}", ref)
            if ref != cn_upper:
                refs.append(ref)

    # Also scan all text for any circular ref that appears with "earlier" / "previous"
    _EARLIER_PATTERN = re.compile(
        r"(?:earlier|previous|old|erstwhile)\s+(?:circular|direction|notification|master\s+direction)"
        r"\s+(?:no\.?\s*)?",
        re.IGNORECASE,
    )
    for match in _EARLIER_PATTERN.finditer(combined_text):
        window = combined_text[match.end():match.end() + 200]
        for ref_match in _CIRCULAR_REF_PATTERN.finditer(window):
            ref = ref_match.group(0).upper()
            ref = re.sub(r"(\d{4})-(\d{4})", lambda m: f"{m.group(1)}-{m.group(2)[2:]}", ref)
            if ref != cn_upper:
                refs.append(ref)

    return list(set(refs))


def _extract_amends(combined_text: str) -> list[str]:
    """Extract regulation/act names that this circular amends."""
    regulations = []
    for match in _AMENDS_PATTERN.finditer(combined_text):
        reg_name = match.group(1).strip()
        # Clean up: remove leading conjunctions
        reg_name = re.sub(r"^(?:the|of|in|to)\s+", "", reg_name, flags=re.IGNORECASE)
        # Must be at least 10 chars and contain Act/Rules/Regulations etc.
        if len(reg_name) >= 10 and len(reg_name) <= 150:
            regulations.append(reg_name)
    return list(set(regulations))


def _extract_applies_to(combined_text: str) -> list[str]:
    """Extract entity types this circular applies to."""
    entities = []
    for match in _APPLIES_TO_PATTERN.finditer(combined_text):
        entity_text = match.group(1).strip()
        # Try to match known entity keywords within the extracted text
        entity_lower = entity_text.lower()
        for kw in _ENTITY_KEYWORDS:
            if kw.lower() in entity_lower:
                entities.append(kw)
    return list(set(entities))


def _load_topic_taxonomy() -> list[dict]:
    """Load topic taxonomy from data/topic_taxonomy.json."""
    path = Path(__file__).resolve().parent.parent / "data" / "topic_taxonomy.json"
    if not path.exists():
        print(f"Warning: {path} not found, skipping topic assignment")
        return []
    return json.loads(path.read_text())


def _load_entity_taxonomy() -> dict:
    """Load entity taxonomy from data/entity_taxonomy.json."""
    path = Path(__file__).resolve().parent.parent / "data" / "entity_taxonomy.json"
    if not path.exists():
        print(f"Warning: {path} not found, skipping entity hierarchy")
        return {}
    return json.loads(path.read_text())


def _assign_topics(title: str, combined_text: str, taxonomy: list[dict]) -> list[str]:
    """Match circular against topic taxonomy. Returns up to 3 topic names."""
    # Combine title (weighted 3x) and first chunk text for matching
    search_text = (title.lower() + " ") * 3 + combined_text[:2000].lower()
    scored = []
    for topic in taxonomy:
        score = sum(1 for kw in topic["keywords"] if kw.lower() in search_text)
        if score >= 2:  # Require at least 2 keyword matches
            scored.append((topic["name"], score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:3]]


def _build_alias_map(taxonomy: dict) -> dict[str, str]:
    """Build a map of alias → canonical entity name from the taxonomy."""
    alias_map = {}
    for canonical, info in taxonomy.items():
        # Map the canonical name itself
        alias_map[canonical.lower()] = canonical
        # Map all aliases
        for alias in info.get("aliases", []):
            alias_map[alias.lower()] = canonical
    return alias_map


def _normalize_entity(entity_name: str, alias_map: dict[str, str]) -> str | None:
    """Normalize an entity name using the alias map."""
    return alias_map.get(entity_name.lower())


def populate_graph(dry_run: bool = False):
    """Main function to populate Neo4j graph from Qdrant metadata."""
    print("=" * 60)
    print("Populating Neo4j graph from Qdrant vector store")
    print("=" * 60)

    # Initialize stores
    vs = VectorStore()
    gs = GraphStore() if not dry_run else None

    # Step 1: Scroll all chunks from Qdrant
    print("\n[1/6] Scrolling Qdrant chunks...")
    payloads = _scroll_all_chunks(vs)
    print(f"  Total chunks: {len(payloads)}")

    # Step 2: Group by circular number
    print("\n[2/6] Grouping by circular_number...")
    circulars = _group_by_circular(payloads)
    print(f"  Unique circulars: {len(circulars)}")

    # Load taxonomies
    topic_taxonomy = _load_topic_taxonomy()
    entity_taxonomy = _load_entity_taxonomy()
    alias_map = _build_alias_map(entity_taxonomy) if entity_taxonomy else {}

    # Step 3: Upsert Circular nodes
    print("\n[3/6] Upserting Circular nodes...")
    for i, (cn, meta) in enumerate(circulars.items()):
        if gs:
            gs.upsert_circular({
                "number": cn,
                "title": meta["title"],
                "date": meta["date"],
                "source": meta["source"],
                "effective_date": "",
                "risk_level": "",
                "doc_id": "",
                "link": meta["link"],
                "summary": "",
                "subject": meta["title"],
            })
        if (i + 1) % 100 == 0:
            print(f"  Upserted {i + 1}/{len(circulars)} circulars...")
    print(f"  Done: {len(circulars)} Circular nodes")

    # Step 4: Extract and create relationships
    print("\n[4/6] Extracting relationships from chunk text...")
    stats = {"supersedes": 0, "amends": 0, "applies_to": 0, "about": 0, "is_a": 0}

    for cn, meta in circulars.items():
        combined_text = "\n".join(meta["texts"])

        # SUPERSEDES
        superseded = _extract_supersedes(cn, combined_text)
        for older_ref in superseded:
            if gs:
                gs.create_supersedes(cn, older_ref)
            stats["supersedes"] += 1

        # AMENDS
        regulations = _extract_amends(combined_text)
        for reg in regulations:
            if gs:
                gs.create_amends(cn, reg)
            stats["amends"] += 1

        # APPLIES_TO
        entities = _extract_applies_to(combined_text)
        for entity in entities:
            # Normalize entity name using taxonomy
            canonical = _normalize_entity(entity, alias_map) if alias_map else entity
            if canonical and gs:
                gs.create_applies_to(cn, canonical)
            elif gs:
                gs.create_applies_to(cn, entity)
            stats["applies_to"] += 1

    print(f"  SUPERSEDES edges: {stats['supersedes']}")
    print(f"  AMENDS edges: {stats['amends']}")
    print(f"  APPLIES_TO edges: {stats['applies_to']}")

    # Step 5: Assign topics from taxonomy
    print("\n[5/6] Assigning topics from taxonomy...")
    if topic_taxonomy:
        for cn, meta in circulars.items():
            combined_text = "\n".join(meta["texts"])
            topics = _assign_topics(meta["title"], combined_text, topic_taxonomy)
            for topic_name in topics:
                if gs:
                    gs.create_about(cn, topic_name)
                stats["about"] += 1
        print(f"  ABOUT edges: {stats['about']}")
    else:
        print("  Skipped (no taxonomy file)")

    # Step 6: Build entity hierarchy from taxonomy
    print("\n[6/6] Building entity IS_A hierarchy...")
    if entity_taxonomy:
        for parent_type, info in entity_taxonomy.items():
            for child_type in info.get("children", []):
                if gs:
                    gs.create_is_a(child_type, parent_type)
                stats["is_a"] += 1
        print(f"  IS_A edges: {stats['is_a']}")
    else:
        print("  Skipped (no taxonomy file)")

    # Summary
    print("\n" + "=" * 60)
    print("Graph population complete!")
    print(f"  Circulars: {len(circulars)}")
    for rel_type, count in stats.items():
        print(f"  {rel_type.upper()}: {count}")

    if gs:
        print("\nNeo4j stats:")
        final_stats = gs.get_stats()
        for k, v in final_stats.items():
            print(f"  {k}: {v}")
        gs.close()


def show_stats():
    """Show current graph stats."""
    gs = GraphStore()
    stats = gs.get_stats()
    print("Current Neo4j graph stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    gs.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate Neo4j graph from Qdrant")
    parser.add_argument("--stats", action="store_true", help="Show current graph stats and exit")
    parser.add_argument("--dry-run", action="store_true", help="Extract data but don't write to Neo4j")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        populate_graph(dry_run=args.dry_run)
