"""
Extract structured compliance obligations from regulatory circulars.

Usage:
    python scripts/extract_obligations.py                    # process 5 recent circulars
    python scripts/extract_obligations.py --id 739155        # process specific circular by DB id
    python scripts/extract_obligations.py --all              # process all unprocessed circulars

The extraction prompt converts raw circular text into structured JSON with:
  - summary, effective_date, issuing_authority
  - who it applies to (entity types, thresholds)
  - specific obligations (action, deadline, penalty, form, section)
  - supersession info
  - key numerical thresholds
"""

import argparse
import json
import os
import sys

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EXTRACTION_PROMPT = """\
You are a compliance analyst specializing in Indian financial regulation. \
Your job is to read a regulatory circular and extract every compliance obligation it creates.

IMPORTANT RULES:
- Extract ONLY what the circular explicitly states. Do NOT infer or add obligations not mentioned.
- If a field is not mentioned in the circular, use null.
- For deadlines, preserve the EXACT wording (e.g., "within 30 days of the event", "on or before January 02, 2027").
- For penalties, quote the exact text including amounts and formulas.
- Identify ALL entity types the circular applies to (banks, NBFCs, listed companies, merchant bankers, etc.).
- If the circular references other circulars/regulations being superseded or amended, capture those.

Return a JSON object with this exact structure:

{
  "circular_reference": "the circular number exactly as written",
  "issuing_authority": "RBI | SEBI | MCA | IRDAI | CBDT | CBIC",
  "date_issued": "YYYY-MM-DD",
  "effective_date": "YYYY-MM-DD or description if phased",
  "subject": "one-line subject",
  "summary": "2-3 sentence plain-English summary of what changed and why it matters",

  "applies_to": [
    {
      "entity_type": "e.g., Category-I Authorised Dealer Banks",
      "conditions": "any qualifying conditions, or null if applies to all of this type"
    }
  ],

  "obligations": [
    {
      "action": "what must be done — be specific",
      "deadline": "exact deadline as stated in circular",
      "penalty_for_non_compliance": "exact penalty text, or null",
      "form_or_filing": "specific form name if mentioned, or null",
      "section_reference": "Act/regulation section cited, or null",
      "is_new": true,
      "notes": "any important qualifications or exceptions"
    }
  ],

  "key_thresholds": [
    {
      "parameter": "what is being measured",
      "value": "the threshold value",
      "context": "when/how this threshold applies"
    }
  ],

  "supersedes": [
    {
      "circular_reference": "old circular number",
      "description": "what it replaces"
    }
  ],

  "amendments_to": [
    {
      "regulation_name": "name of regulation being amended",
      "specific_provisions": "which sections/rules are changed"
    }
  ],

  "compliance_risk_level": "HIGH | MEDIUM | LOW",
  "risk_rationale": "one sentence explaining the risk assessment"
}

Now extract obligations from the following circular:

---
{circular_text}
---

Return ONLY the JSON object, no other text.
"""


def get_db_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def fetch_circular(conn, doc_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, date, circular_number, content, crawler FROM scraped_documents WHERE id = %s",
            (doc_id,),
        )
        return cur.fetchone()


def fetch_recent_unprocessed(conn, limit=5):
    """Fetch recent circulars with content that haven't been obligation-extracted yet."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, date, circular_number, content, crawler
            FROM scraped_documents
            WHERE content IS NOT NULL AND content <> '' AND length(content) > 500
              AND length(content) < 30000
              AND (extra->>'obligations_extracted') IS NULL
            ORDER BY date DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def extract_obligations(circular_text, model="gpt-4o"):
    """Send circular text to LLM and get structured obligations back."""
    client = OpenAI()

    prompt = EXTRACTION_PROMPT.replace("{circular_text}", circular_text)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    usage = response.usage
    print(f"  Tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out")
    return result


def save_extraction(conn, doc_id, obligations_json):
    """Save extracted obligations back to the extra JSONB column."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraped_documents
            SET extra = extra || %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                json.dumps({
                    "obligations_extracted": True,
                    "obligations": obligations_json,
                }),
                doc_id,
            ),
        )
    conn.commit()


def print_obligations(result, title=""):
    """Pretty-print the extracted obligations."""
    if title:
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")

    print(f"\n  Circular: {result.get('circular_reference', 'N/A')}")
    print(f"  Authority: {result.get('issuing_authority', 'N/A')}")
    print(f"  Date: {result.get('date_issued', 'N/A')}")
    print(f"  Effective: {result.get('effective_date', 'N/A')}")
    print(f"  Risk: {result.get('compliance_risk_level', 'N/A')}")
    print(f"\n  Summary: {result.get('summary', 'N/A')}")

    applies_to = result.get("applies_to", [])
    if applies_to:
        print(f"\n  Applies to:")
        for a in applies_to:
            cond = f" (if {a['conditions']})" if a.get("conditions") else ""
            print(f"    - {a['entity_type']}{cond}")

    obligations = result.get("obligations", [])
    if obligations:
        print(f"\n  Obligations ({len(obligations)}):")
        for i, o in enumerate(obligations, 1):
            print(f"\n    {i}. {o['action']}")
            if o.get("deadline"):
                print(f"       Deadline: {o['deadline']}")
            if o.get("penalty_for_non_compliance"):
                print(f"       Penalty: {o['penalty_for_non_compliance']}")
            if o.get("form_or_filing"):
                print(f"       Form: {o['form_or_filing']}")
            if o.get("section_reference"):
                print(f"       Section: {o['section_reference']}")
            if o.get("notes"):
                print(f"       Note: {o['notes']}")

    thresholds = result.get("key_thresholds", [])
    if thresholds:
        print(f"\n  Key Thresholds:")
        for t in thresholds:
            print(f"    - {t['parameter']}: {t['value']} ({t.get('context', '')})")

    supersedes = result.get("supersedes", [])
    if supersedes:
        print(f"\n  Supersedes:")
        for s in supersedes:
            print(f"    - {s['circular_reference']}: {s.get('description', '')}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Extract compliance obligations from circulars")
    parser.add_argument("--id", type=int, help="Process a specific circular by DB id")
    parser.add_argument("--ids", type=str, help="Comma-separated list of DB ids")
    parser.add_argument("--all", action="store_true", help="Process all unprocessed circulars")
    parser.add_argument("--limit", type=int, default=5, help="Number of circulars to process (default: 5)")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model to use (default: gpt-4o)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't save to DB")
    parser.add_argument("--save-json", type=str, help="Save results to JSON file")
    args = parser.parse_args()

    conn = get_db_conn()

    circulars = []
    if args.id:
        row = fetch_circular(conn, args.id)
        if not row:
            print(f"Circular with id={args.id} not found")
            sys.exit(1)
        circulars = [row]
    elif args.ids:
        for doc_id in args.ids.split(","):
            row = fetch_circular(conn, int(doc_id.strip()))
            if row:
                circulars.append(row)
    else:
        circulars = fetch_recent_unprocessed(conn, args.limit)

    if not circulars:
        print("No circulars to process.")
        sys.exit(0)

    print(f"Processing {len(circulars)} circular(s) with model={args.model}...")

    all_results = []
    for row in circulars:
        doc_id, title, date, circ_num, content, crawler = row
        print(f"\n--- Processing ID={doc_id}: {title[:70]}... ---")

        result = extract_obligations(content, model=args.model)
        print_obligations(result, title=title)

        if not args.dry_run:
            save_extraction(conn, doc_id, result)
            print(f"  Saved to DB (id={doc_id})")

        all_results.append({"doc_id": doc_id, "title": title, "extraction": result})

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.save_json}")

    conn.close()
    print(f"\nDone. Processed {len(all_results)} circular(s).")


if __name__ == "__main__":
    main()
