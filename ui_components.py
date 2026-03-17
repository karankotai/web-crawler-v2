"""
Shared UI components for Streamlit compliance apps.

Extracted from demo_app.py so both the demo and recent_circulars pages
render obligation cards identically.
"""

import streamlit as st

CARD_CSS = """
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
    .chain-repeal {
        background: #fff3f3;
        border: 2px solid #dc3545;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
    }
    .chain-repeal .chain-label { color: #dc3545; font-weight: 700; }
    .chain-supersession {
        background: #fff8e1;
        border: 2px solid #f59e0b;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
    }
    .chain-supersession .chain-label { color: #b45309; font-weight: 700; }
    .chain-amendment {
        background: #eff6ff;
        border: 2px solid #3b82f6;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
    }
    .chain-amendment .chain-label { color: #1d4ed8; font-weight: 700; }
    .chain-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85em;
        margin-left: 8px;
    }
    .chain-badge-repeal { color: #fff; background: #dc3545; }
    .chain-badge-supersession { color: #fff; background: #f59e0b; }
    .chain-badge-amendment { color: #fff; background: #3b82f6; }
</style>
"""


def render_stats_row(data):
    """Render the summary metrics bar (circulars, obligations, thresholds, risk, chains)."""
    total_obligations = sum(len(d["extraction"].get("obligations", [])) for d in data)
    total_thresholds = sum(len(d["extraction"].get("key_thresholds", [])) for d in data)
    high_risk = sum(1 for d in data if d["extraction"].get("compliance_risk_level") == "HIGH")
    linked_count = sum(1 for d in data if bool(d.get("chain_type")))

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f'<div><div class="stat-number">{len(data)}</div><div class="stat-label">Circulars Analyzed</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div><div class="stat-number">{total_obligations}</div><div class="stat-label">Obligations Extracted</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div><div class="stat-number">{total_thresholds}</div><div class="stat-label">Key Thresholds</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div><div class="stat-number">{high_risk}</div><div class="stat-label">High Risk Items</div></div>', unsafe_allow_html=True)
    with col5:
        st.markdown(f'<div><div class="stat-number">{linked_count}</div><div class="stat-label">Regulatory Chains</div></div>', unsafe_allow_html=True)


def render_circular_card(item, show_deep_dive=False):
    """Render a single circular card with full obligation detail.

    Args:
        item: Dict with keys: extraction, title, chain_type, repealed_by, pdf_links, source_url
        show_deep_dive: If True, show a "Deep Dive" link button to the source URL.
    """
    ext = item["extraction"]
    risk = ext.get("compliance_risk_level", "MEDIUM")
    risk_class = f"risk-{risk.lower()}"

    with st.container():
        # Header row with chain badge
        chain_type = item.get("chain_type", "")
        header_col1, header_col2 = st.columns([5, 1])
        with header_col1:
            chain_badge = ""
            if chain_type:
                chain_labels = {"repeal": "REPEALED", "supersession": "SUPERSEDES", "amendment": "AMENDMENT"}
                chain_badge = f' <span class="chain-badge chain-badge-{chain_type}">{chain_labels.get(chain_type, chain_type.upper())}</span>'
            st.markdown(f'<h3 style="margin:0">{ext.get("subject", item.get("title", ""))}{chain_badge}</h3>', unsafe_allow_html=True)
        with header_col2:
            st.markdown(f'<span class="{risk_class}">{risk} RISK</span>', unsafe_allow_html=True)

        # Metadata row
        meta_col1, meta_col2, meta_col3 = st.columns(3)
        with meta_col1:
            st.markdown(f"**Authority:** {ext.get('issuing_authority', 'N/A')}")
            circ_ref = ext.get("circular_reference", "N/A")
            pdf_links = item.get("pdf_links", [])
            source_url = item.get("source_url", "")
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

        # Regulatory Lineage
        supersedes = ext.get("supersedes", [])
        amendments = ext.get("amendments_to", [])
        repealed_by = item.get("repealed_by", "")

        if repealed_by or supersedes or amendments or chain_type:
            lineage_parts = []

            if repealed_by:
                lineage_parts.append(
                    f'<div class="chain-repeal">'
                    f'<span class="chain-label">REPEALED</span> — '
                    f'This circular has been repealed and replaced by: <b>{repealed_by}</b>'
                    f'</div>'
                )

            if supersedes:
                for s in supersedes:
                    ref = s.get("circular_reference", "N/A")
                    desc = s.get("description", "")
                    lineage_parts.append(
                        f'<div class="chain-supersession">'
                        f'<span class="chain-label">SUPERSEDES</span> — '
                        f'<code>{ref}</code>: {desc}'
                        f'</div>'
                    )

            if amendments:
                for a in amendments:
                    reg = a.get("regulation_name", "N/A")
                    prov = a.get("specific_provisions", "")
                    lineage_parts.append(
                        f'<div class="chain-amendment">'
                        f'<span class="chain-label">AMENDS</span> — '
                        f'<b>{reg}</b> ({prov})'
                        f'</div>'
                    )

            if lineage_parts:
                st.markdown("**Regulatory Lineage:**")
                st.markdown("\n".join(lineage_parts), unsafe_allow_html=True)

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

        # Deep Dive link
        if show_deep_dive:
            source_url = item.get("source_url", "")
            if source_url:
                st.link_button("Deep Dive →", source_url)

        st.divider()
