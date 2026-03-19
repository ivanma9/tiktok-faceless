"""Account summary table component — Story 7.3."""

import streamlit as st

_PHASE_COLORS = {
    "commit": ("#6366f1", "#fff"),
    "scale": ("#6366f1", "#fff"),
    "tournament": ("#f59e0b", "#000"),
    "warmup": ("#71717a", "#fff"),
}


def _phase_badge(phase: str) -> str:
    bg, fg = _PHASE_COLORS.get(phase, ("#71717a", "#fff"))
    return (
        f'<span style="padding:2px 8px;border-radius:4px;font-size:0.85em;'
        f'background:{bg};color:{fg}">{phase}</span>'
    )


def _format_timedelta(td) -> str:
    if td is None:
        return "Never"
    total_seconds = td.total_seconds()
    if total_seconds < 60:
        return "just now"
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    return f"{h}h {m}m ago"


def render_account_summary_table(summaries: list) -> None:
    st.subheader("Portfolio Overview")
    for summary in summaries:
        cols = st.columns([2, 2, 1, 2, 2])
        with cols[0]:
            st.markdown(summary["account_id"])
        with cols[1]:
            st.markdown(_phase_badge(summary["phase"]), unsafe_allow_html=True)
        with cols[2]:
            dot = "🟢" if summary["pipeline_healthy"] else "🔴"
            st.markdown(dot)
        with cols[3]:
            st.markdown(f"${summary['revenue_today']:,.2f}")
        with cols[4]:
            st.markdown(_format_timedelta(summary["last_post_timedelta"]))
