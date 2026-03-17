"""
Regulatory Pulse — Latest Circulars

Automatically surfaces the most recent circulars across all sources,
with full obligation detail extracted by background job.

Run: streamlit run recent_circulars.py
"""

import json
import os
import re
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from ui_components import CARD_CSS, render_stats_row, render_circular_card

st.set_page_config(
    page_title="Regulatory Pulse",
    page_icon="⚡",
    layout="wide",
)


# --- Helpers ---

def normalize_source(source):
    """Normalize source names like 'RBI (notification)' to 'RBI'."""
    if not source:
        return "Unknown"
    # Take everything before first parenthesis, hyphen, or slash
    clean = re.split(r"[\(\-/]", source)[0].strip().upper()
    return clean if clean else source.strip().upper()


# --- Load data ---

@st.cache_data(ttl=300)
def load_recent_circulars(limit=50):
    """Load recent circulars from DB (joined with scraped_documents) or fallback JSON."""
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT eo.id, eo.doc_id, eo.title, eo.source_url, eo.pdf_links,
                           eo.chain_type, eo.repealed_by, eo.extraction, eo.created_at,
                           sd.source, sd.date, sd.circular_number
                    FROM extracted_obligations eo
                    LEFT JOIN scraped_documents sd ON sd.id = eo.doc_id
                    ORDER BY COALESCE(sd.date, eo.created_at::text) DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

            results = []
            for r in rows:
                item = dict(r)
                # Parse JSON fields stored as text
                if isinstance(item.get("extraction"), str):
                    item["extraction"] = json.loads(item["extraction"])
                if isinstance(item.get("pdf_links"), str):
                    try:
                        item["pdf_links"] = json.loads(item["pdf_links"])
                    except (json.JSONDecodeError, TypeError):
                        item["pdf_links"] = []
                # Attach source metadata
                item["_source"] = normalize_source(item.get("source", ""))
                item["_date"] = item.get("date") or (
                    item["created_at"].strftime("%Y-%m-%d") if item.get("created_at") else "N/A"
                )
                results.append(item)
            return results
        finally:
            conn.close()

    # Fallback: static demo data
    with open("demo_obligations.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        item["_source"] = normalize_source(
            item.get("extraction", {}).get("issuing_authority", "")
        )
        item["_date"] = item.get("extraction", {}).get("date_issued", "N/A")
    return data


# --- Styling ---
st.markdown(CARD_CSS, unsafe_allow_html=True)

# --- Header ---
header_col, refresh_col = st.columns([5, 1])
with header_col:
    st.title("Regulatory Pulse")
    st.markdown("Live compliance intelligence across 11 sources")
with refresh_col:
    st.write("")  # spacing
    if st.button("Refresh", type="primary"):
        st.cache_data.clear()
        st.rerun()

# --- Load data ---
all_data = load_recent_circulars()

# --- Stats ---
render_stats_row(all_data)
st.divider()

# --- Filters ---
all_sources = sorted(set(d["_source"] for d in all_data if d.get("_source")))

filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
with filter_col1:
    selected_source = st.selectbox(
        "Filter by Authority",
        ["All"] + all_sources,
    )
with filter_col2:
    selected_risk = st.selectbox(
        "Filter by Risk Level",
        ["All", "HIGH", "MEDIUM", "LOW"],
    )
with filter_col3:
    display_count = st.slider(
        "Circulars to show",
        min_value=5, max_value=50, value=5, step=5,
    )

# --- Apply filters ---
filtered = all_data
if selected_source != "All":
    filtered = [d for d in filtered if d.get("_source") == selected_source]
if selected_risk != "All":
    filtered = [
        d for d in filtered
        if d.get("extraction", {}).get("compliance_risk_level") == selected_risk
    ]

# Limit display
filtered = filtered[:display_count]

if not filtered:
    st.warning("No circulars match your filters. Try adjusting the filters above.")
else:
    for item in filtered:
        render_circular_card(item, show_deep_dive=True)

# --- Footer ---
source_count = len(all_sources) if all_sources else 11
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
st.caption(f"Last updated: {now} | {source_count} sources monitored")
