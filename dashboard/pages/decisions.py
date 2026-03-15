"""Decisions page — Story 6.5."""

import json

import streamlit as st

from tiktok_faceless.db.queries import get_agent_decisions

DECISION_TYPE_LABELS: dict[str, str] = {
    "phase_transition": "Phase Transition",
    "niche_commit": "Niche Committed",
    "niche_decay_detected": "Niche Decay Detected",
    "retournament_triggered": "Re-tournament Triggered",
    "kill_switch": "Kill Switch Activated",
    "promoted": "Video Promoted",
    "suppression_detected": "Suppression Detected",
    "product_selected": "Product Selected",
    "product_eliminated": "Product Eliminated",
    "archetype_selected": "Hook Archetype Selected",
    "commission_discrepancy": "Commission Discrepancy",
    "pipeline_resumed": "Pipeline Resumed",
}

_PHASE_TRANSITION_KEY = "phase_transition"
_INDIGO = "#6366f1"


def _format_summary(decision) -> str:
    """Return a one-line human-readable summary of the decision.

    For phase transitions: "orchestrator: warmup → tournament"
    For all others: first 120 chars of rationale.
    """
    if decision.from_value and decision.to_value:
        return f"{decision.agent}: {decision.from_value} → {decision.to_value}"
    return (decision.rationale or "")[:120]


def render_decisions_page(session, account_id: str) -> None:
    st.header("Decision Audit Log")

    try:
        decisions = get_agent_decisions(session, account_id)
    except Exception as e:
        st.error(f"Failed to load decisions: {e}")
        return

    if not decisions:
        st.info("No decisions recorded yet.")
        return

    for decision in decisions:
        label = DECISION_TYPE_LABELS.get(
            decision.decision_type,
            decision.decision_type.replace("_", " ").title(),
        )
        summary = _format_summary(decision)
        ts = decision.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")

        is_phase_transition = decision.decision_type == _PHASE_TRANSITION_KEY

        if is_phase_transition:
            header_html = (
                f'<div style="border-left: 4px solid {_INDIGO}; padding-left: 10px;">'
                f"<strong>{label}</strong> &nbsp;|&nbsp; {ts}<br/>"
                f"<span style='color:{_INDIGO};'>{summary}</span>"
                f"</div>"
            )
            st.markdown(header_html, unsafe_allow_html=True)
        else:
            st.markdown(f"**{label}** &nbsp;|&nbsp; {ts}  \n{summary}")

        if decision.supporting_data:
            with st.expander("View supporting data"):
                try:
                    parsed = json.loads(decision.supporting_data)
                    st.json(parsed)
                except (ValueError, TypeError):
                    st.code(decision.supporting_data, language="text")

        st.divider()
