"""Sparkline component — Story 6.3."""

import altair as alt
import pandas as pd
import streamlit as st


def render_sparkline(values: list[float], color: str = "#10b981") -> None:
    """Render a compact inline sparkline chart using Altair.

    Args:
        values: Daily metric values, oldest first.
        color: Hex color string. Defaults to emerald (#10b981).
    """
    if not values or all(v == 0.0 for v in values):
        return
    try:
        df = pd.DataFrame({"day": range(len(values)), "value": values})
        chart = (
            alt.Chart(df)
            .mark_line(color=color, strokeWidth=2)
            .encode(
                x=alt.X("day:Q", axis=None),
                y=alt.Y("value:Q", axis=None, scale=alt.Scale(zero=False)),
            )
            .properties(height=60)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.caption("Sparkline unavailable")
