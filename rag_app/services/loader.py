import json
import re
from datetime import datetime
from pathlib import Path


def load_all_records(output_dir: str = "output") -> list[dict]:
    """Load all JSON files from output directory and return flat list of records."""
    records = []
    output_path = Path(output_dir)

    for json_file in sorted(output_path.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            for record in data:
                record["_file_name"] = json_file.name
            records.extend(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Skipping {json_file.name}: {e}")

    return records


def load_all_records_from_pg(database_url: str) -> list[dict]:
    """Load all scraped records from PostgreSQL."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(database_url)
    records = []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM scraped_documents ORDER BY id")
            for row in cur:
                record = dict(row)
                # Merge extra JSONB back into the record dict
                extra = record.pop("extra", {}) or {}
                if isinstance(extra, str):
                    extra = json.loads(extra)
                record.update(extra)
                # Remove internal columns not needed by the RAG pipeline
                record.pop("id", None)
                record.pop("created_at", None)
                record.pop("updated_at", None)
                # Set _file_name from crawler for compatibility
                record["_file_name"] = record.get("crawler", "")
                records.append(record)
    finally:
        conn.close()
    return records


def load_all_records_from_db(uri: str, db_name: str) -> list[dict]:
    """Load all circular records from MongoDB."""
    from pymongo import MongoClient

    client = MongoClient(uri)
    db = client[db_name]
    records = []
    for collection_name in db.list_collection_names():
        for doc in db[collection_name].find({}, {"_id": 0}):
            doc["_file_name"] = collection_name
            records.append(doc)
    client.close()
    return records


def _clean_content(text: str) -> str:
    """Strip file-size prefix and collapse excess newlines."""
    if not text:
        return ""
    # Remove leading file-size prefix like "(\n269 kb\n)\n"
    text = re.sub(r"^\(\s*\d+\s*kb\s*\)\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_DATE_FORMATS = [
    "%B %d, %Y",      # February 18, 2026
    "%b %d, %Y",      # Feb 11, 2026
    "%d-%m-%Y",        # 10-01-2026
    "%d-%b-%Y",        # 19-Feb-2026
]


def _normalize_date(date_str: str) -> str:
    """Try multiple date formats and return ISO YYYY-MM-DD, or original on failure."""
    if not date_str:
        return ""
    cleaned = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def _extract_circular_number(record: dict) -> str:
    """Extract circular number from record fields."""
    if record.get("circular_number"):
        return record["circular_number"]

    # Try to extract from content - common patterns like "RBI/2025-26/223"
    content = record.get("content", "")
    if content:
        match = re.search(
            r"(?:RBI|SEBI|IRDAI|MCA)[/\-][\w\-/]+(?:\d{2,})",
            content[:500],
        )
        if match:
            return match.group(0)
    return ""


def build_document_text(record: dict) -> str:
    """Build full document text with metadata header for chunking."""
    source = record.get("source", "Unknown")
    title = record.get("title", "Untitled")
    date = _normalize_date(record.get("date", ""))
    circular_number = _extract_circular_number(record)
    link = record.get("link", "")

    header_parts = [f"Source: {source}", f"Title: {title}"]
    if date:
        header_parts.append(f"Date: {date}")
    if circular_number:
        header_parts.append(f"Circular Number: {circular_number}")
    if link:
        header_parts.append(f"Link: {link}")

    header = " | ".join(header_parts)

    content = _clean_content(record.get("content", ""))
    if not content:
        # Fallback: use title + details
        parts = [title]
        details = record.get("details", "")
        if details:
            parts.append(details)
        content = "\n\n".join(parts)

    return f"[{header}]\n\n{content}"
