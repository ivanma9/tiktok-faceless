"""Phase badge component — Story 6.2."""

from datetime import datetime

import streamlit as st

_PHASE_LABELS: dict[str, str] = {
    "warmup": "Warmup",
    "tournament": "Tournament",
    "commit": "Commit",
    "scale": "Scale",
}

_PHASE_COLORS: dict[str, str] = {
    "warmup": "#71717a",  # zinc-500
    "tournament": "#d97706",  # amber-600
    "commit": "#4338ca",  # indigo-700
    "scale": "#059669",  # emerald-600
}


def render_phase_badge(phase: str, phase_started_at: datetime | None) -> None:
    """Render a colored pill badge showing the current phase and optional day counter."""
    label = _PHASE_LABELS.get(phase, phase.capitalize())
    color = _PHASE_COLORS.get(phase, "#71717a")

    if phase_started_at is not None:
        day_num = (datetime.utcnow() - phase_started_at).days + 1
        label = f"{label} · Day {day_num}"

    st.markdown(
        f'<span style="'
        f"background-color:{color};"
        f"color:#fff;"
        f"padding:4px 10px;"
        f"border-radius:9999px;"
        f"font-size:0.85rem;"
        f'font-weight:600;">'
        f"{label}"
        f"</span>",
        unsafe_allow_html=True,
    )
