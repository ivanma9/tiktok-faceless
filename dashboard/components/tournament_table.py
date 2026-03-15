"""Tournament Niche Table component — Story 6.4."""

import pandas as pd
import streamlit as st

from tiktok_faceless.db.queries import get_tournament_niche_table


def render_tournament_table(session, account_id: str) -> None:
    """Render the niche tournament rankings table (phase-gated by caller)."""
    try:
        rows = get_tournament_niche_table(session, account_id)
        if not rows:
            return
        df = pd.DataFrame(rows)
        df["avg_ctr_pct"] = (df["avg_ctr_pct"] * 100).round(1)
        df["avg_retention_3s_pct"] = (df["avg_retention_3s_pct"] * 100).round(1)
        df["total_revenue"] = df["total_revenue"].round(2)
        df = df.rename(
            columns={
                "rank": "Rank",
                "niche": "Niche",
                "video_count": "Videos",
                "avg_ctr_pct": "Avg CTR %",
                "avg_retention_3s_pct": "Avg 3s Ret %",
                "total_revenue": "Revenue ($)",
                "status": "Status",
            }
        )
        st.subheader("Tournament: Niche Rankings")
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Tournament table failed: {e}")
