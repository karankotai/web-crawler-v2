"""
Compliance Engine Demo — Regulatory Circular Decoder

Shows how AI extracts structured compliance obligations from government circulars.
Run: streamlit run demo_app.py
"""

import json
import os

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from ui_components import CARD_CSS, render_stats_row, render_circular_card

st.set_page_config(
    page_title="Compliance Decoder",
    page_icon="⚖️",
    layout="wide",
)

# --- Load data ---
@st.cache_data(ttl=300)
def load_obligations():
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT doc_id, title, source_url, pdf_links, chain_type,
                           repealed_by, extraction
                    FROM extracted_obligations
                    ORDER BY created_at DESC
                    """
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    with open("demo_obligations.json", "r", encoding="utf-8") as f:
        return json.load(f)


data = load_obligations()


def is_linked(item):
    """Check if a circular was specifically selected for its regulatory chain relationship."""
    return bool(item.get("chain_type"))


# --- Styling ---
st.markdown(CARD_CSS, unsafe_allow_html=True)

# --- Header ---
st.title("Regulatory Circular Decoder")
st.markdown("AI-powered compliance obligation extraction from Indian regulatory circulars")

# --- Summary stats ---
render_stats_row(data)
st.divider()

# --- Filter ---
authorities = set(d["extraction"].get("issuing_authority", "") for d in data)

filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
with filter_col1:
    selected_authority = st.selectbox(
        "Filter by Authority",
        ["All"] + sorted(authorities),
    )
with filter_col2:
    selected_risk = st.selectbox(
        "Filter by Risk Level",
        ["All", "HIGH", "MEDIUM", "LOW"],
    )
with filter_col3:
    selected_linkage = st.selectbox(
        "Show",
        ["All", "Standalone", "Linked"],
    )

filtered_data = data
if selected_authority != "All":
    filtered_data = [d for d in filtered_data if d["extraction"].get("issuing_authority") == selected_authority]
if selected_risk != "All":
    filtered_data = [d for d in filtered_data if d["extraction"].get("compliance_risk_level") == selected_risk]
if selected_linkage == "Linked":
    filtered_data = [d for d in filtered_data if is_linked(d)]
elif selected_linkage == "Standalone":
    filtered_data = [d for d in filtered_data if not is_linked(d)]

# --- Circular cards ---
for item in filtered_data:
    render_circular_card(item)

# --- Footer ---
st.caption("Built with regulatory data from RBI, SEBI, MCA. Obligation extraction powered by AI.")
