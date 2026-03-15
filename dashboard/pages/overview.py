"""Overview page — Story 6.2."""

import streamlit as st

from dashboard.components.agent_panel import render_agent_panel
from dashboard.components.kpi_strip import render_kpi_strip
from dashboard.components.tournament_table import render_tournament_table
from dashboard.components.video_table import render_video_table
from tiktok_faceless.db.queries import get_account_phase
from tiktok_faceless.db.session import get_session


def render() -> None:
    """Render the overview dashboard page."""
    account_id: str = st.session_state.get("selected_account_id", "")

    # Top bar and alert zone (Story 6.2 — stubs for now)

    st.divider()
    try:
        with get_session() as session:
            render_kpi_strip(session, account_id)
    except Exception as e:
        st.error(f"KPI strip failed to load: {e}")
    st.divider()

    # Agent pipeline panel / video table (Story 6.4)
    with get_session() as session:
        left_col, right_col = st.columns(2)
        with left_col:
            try:
                render_agent_panel(session, account_id)
            except Exception as e:
                st.error(f"Agent panel failed to load: {e}")

        with right_col:
            try:
                render_video_table(session, account_id)
            except Exception as e:
                st.error(f"Video table failed to load: {e}")

        try:
            phase = get_account_phase(session, account_id)
            if phase == "tournament":
                st.divider()
                render_tournament_table(session, account_id)
        except Exception as e:
            st.error(f"Tournament table failed to load: {e}")
