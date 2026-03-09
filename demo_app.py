"""
Compliance Engine Demo — Regulatory Circular Decoder

Shows how AI extracts structured compliance obligations from government circulars.
Run: streamlit run demo_app.py
"""

import json
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="Compliance Decoder",
    page_icon="⚖️",
    layout="wide",
)

# --- Load data ---
@st.cache_data
def load_obligations():
    with open("demo_obligations.json", "r", encoding="utf-8") as f:
        return json.load(f)


data = load_obligations()

# --- Styling ---
st.markdown("""
<style>
    .risk-high { color: #fff; background: #dc3545; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.85em; }
    .risk-medium { color: #fff; background: #fd7e14; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.85em; }
    .risk-low { color: #fff; background: #28a745; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.85em; }
    .obligation-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        background: #fafafa;
    }
    .threshold-badge {
        display: inline-block;
        background: #e8f4fd;
        border: 1px solid #b8daff;
        padding: 4px 12px;
        border-radius: 16px;
        margin: 4px;
        font-size: 0.85em;
    }
    .entity-tag {
        display: inline-block;
        background: #f0e6ff;
        border: 1px solid #d4b5ff;
        padding: 2px 10px;
        border-radius: 12px;
        margin: 2px;
        font-size: 0.85em;
    }
    .stat-number {
        font-size: 2.5em;
        font-weight: 700;
        color: #1a1a2e;
        line-height: 1;
    }
    .stat-label {
        font-size: 0.85em;
        color: #666;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# --- Header ---
st.title("Regulatory Circular Decoder")
st.markdown("AI-powered compliance obligation extraction from Indian regulatory circulars")

# --- Summary stats ---
total_obligations = sum(len(d["extraction"].get("obligations", [])) for d in data)
total_thresholds = sum(len(d["extraction"].get("key_thresholds", [])) for d in data)
high_risk = sum(1 for d in data if d["extraction"].get("compliance_risk_level") == "HIGH")
authorities = set(d["extraction"].get("issuing_authority", "") for d in data)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div><div class="stat-number">{len(data)}</div><div class="stat-label">Circulars Analyzed</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div><div class="stat-number">{total_obligations}</div><div class="stat-label">Obligations Extracted</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div><div class="stat-number">{total_thresholds}</div><div class="stat-label">Key Thresholds</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div><div class="stat-number">{high_risk}</div><div class="stat-label">High Risk Items</div></div>', unsafe_allow_html=True)

st.divider()

# --- Filter ---
filter_col1, filter_col2 = st.columns([1, 1])
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

filtered_data = data
if selected_authority != "All":
    filtered_data = [d for d in filtered_data if d["extraction"].get("issuing_authority") == selected_authority]
if selected_risk != "All":
    filtered_data = [d for d in filtered_data if d["extraction"].get("compliance_risk_level") == selected_risk]

# --- Circular cards ---
for item in filtered_data:
    ext = item["extraction"]
    risk = ext.get("compliance_risk_level", "MEDIUM")
    risk_class = f"risk-{risk.lower()}"

    with st.container():
        # Header row
        header_col1, header_col2 = st.columns([5, 1])
        with header_col1:
            st.subheader(ext.get("subject", item["title"]))
        with header_col2:
            st.markdown(f'<span class="{risk_class}">{risk} RISK</span>', unsafe_allow_html=True)

        # Metadata row
        meta_col1, meta_col2, meta_col3 = st.columns(3)
        with meta_col1:
            st.markdown(f"**Authority:** {ext.get('issuing_authority', 'N/A')}")
            circ_ref = ext.get("circular_reference", "N/A")
            pdf_links = item.get("pdf_links", [])
            source_url = item.get("source_url", "")
            # Link to PDF if available, otherwise to source page
            circ_link = pdf_links[0] if pdf_links else source_url
            if circ_link:
                st.markdown(f"**Circular:** [{circ_ref}]({circ_link})")
            else:
                st.markdown(f"**Circular:** `{circ_ref}`")
        with meta_col2:
            st.markdown(f"**Date Issued:** {ext.get('date_issued', 'N/A')}")
            st.markdown(f"**Effective:** {ext.get('effective_date', 'N/A')}")
        with meta_col3:
            st.markdown(f"**Risk Rationale:** {ext.get('risk_rationale', 'N/A')}")

        # Summary
        st.info(ext.get("summary", ""))

        # Applies to
        applies_to = ext.get("applies_to", [])
        if applies_to:
            entities_html = " ".join(
                f'<span class="entity-tag">{a["entity_type"]}</span>'
                for a in applies_to
            )
            st.markdown(f"**Applies to:** {entities_html}", unsafe_allow_html=True)

        # Obligations
        obligations = ext.get("obligations", [])
        if obligations:
            st.markdown(f"**Compliance Obligations ({len(obligations)}):**")
            for i, obl in enumerate(obligations, 1):
                with st.expander(f"{i}. {obl['action'][:100]}", expanded=(i <= 3)):
                    cols = st.columns(2)
                    with cols[0]:
                        if obl.get("deadline"):
                            st.markdown(f"**Deadline:** {obl['deadline']}")
                        if obl.get("form_or_filing"):
                            st.markdown(f"**Form:** `{obl['form_or_filing']}`")
                    with cols[1]:
                        if obl.get("penalty_for_non_compliance"):
                            st.markdown(f"**Penalty:** {obl['penalty_for_non_compliance']}")
                        if obl.get("section_reference"):
                            st.markdown(f"**Section:** {obl['section_reference']}")
                    if obl.get("notes"):
                        st.caption(f"Note: {obl['notes']}")

        # Key thresholds
        thresholds = ext.get("key_thresholds", [])
        if thresholds:
            st.markdown("**Key Thresholds:**")
            threshold_html = " ".join(
                f'<span class="threshold-badge"><b>{t["parameter"]}:</b> {t["value"]}</span>'
                for t in thresholds
            )
            st.markdown(threshold_html, unsafe_allow_html=True)

        # Supersedes
        supersedes = ext.get("supersedes", [])
        if supersedes:
            st.markdown("**Supersedes:**")
            for s in supersedes:
                st.markdown(f"- `{s.get('circular_reference', 'N/A')}` — {s.get('description', '')}")

        # Amendments
        amendments = ext.get("amendments_to", [])
        if amendments:
            st.markdown("**Amends:**")
            for a in amendments:
                st.markdown(f"- {a.get('regulation_name', 'N/A')} — {a.get('specific_provisions', '')}")

        st.divider()

# --- Footer ---
st.caption("Built with regulatory data from RBI, SEBI, MCA. Obligation extraction powered by AI.")
