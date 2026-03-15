"""Agent Pipeline Panel component — Story 6.4."""

import streamlit as st

from tiktok_faceless.db.queries import get_agent_health_from_errors

AGENT_ORDER: list[str] = [
    "orchestrator",
    "research",
    "script",
    "production",
    "publishing",
    "analytics",
]

AGENT_DISPLAY_NAMES: dict[str, str] = {
    "orchestrator": "Orchestrator",
    "research": "Research",
    "script": "Script",
    "production": "Production",
    "publishing": "Publishing",
    "analytics": "Analytics",
}

STATUS_COLORS: dict[str, str] = {
    "healthy": "#10b981",
    "error": "#f43f5e",
    "waiting": "#71717a",
}


def _agent_status(health_map: dict[str, bool], agent: str) -> tuple[str, str]:
    """Return (status_key, status_note) for a given agent."""
    if agent not in health_map:
        return ("waiting", "Waiting — not yet run")
    if health_map[agent]:
        return ("healthy", "Healthy — no active errors")
    return ("error", "Error — check error log")


def render_agent_panel(session, account_id: str) -> None:
    """Render the Agent Pipeline Panel with per-agent health status rows."""
    try:
        health_map = get_agent_health_from_errors(session, account_id)
        st.subheader("Agent Pipeline")
        for agent in AGENT_ORDER:
            status_key, status_note = _agent_status(health_map, agent)
            color = STATUS_COLORS[status_key]
            dot = f'<span style="color:{color}; font-size:20px;">●</span>'
            col_dot, col_text = st.columns([0.08, 0.92])
            with col_dot:
                st.markdown(dot, unsafe_allow_html=True)
            with col_text:
                st.markdown(f"**{AGENT_DISPLAY_NAMES[agent]}** — {status_note}")
    except Exception as e:
        st.error(f"Agent panel failed: {e}")
