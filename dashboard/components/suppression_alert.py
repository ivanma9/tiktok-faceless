"""Suppression alert component — Story 6.2."""

from datetime import datetime

import streamlit as st

from dashboard.components.time_utils import humanize_timedelta


def render_suppression_alert(suppression_error) -> None:
    """Render rose suppression banner if suppression_error is active; no-op otherwise."""
    if suppression_error is None:
        return

    auto_action = (
        suppression_error.recovery_suggestion
        or "Pipeline has paused new posts automatically"
    )
    time_label = humanize_timedelta(datetime.utcnow() - suppression_error.timestamp)

    st.error(
        f"**Suppression Detected** — {suppression_error.message}  \n"
        f"{auto_action}  \n"
        f"*Detected {time_label}*"
    )
