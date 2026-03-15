"""Video Performance Table component — Story 6.4."""

import pandas as pd
import streamlit as st

from tiktok_faceless.db.queries import get_top_videos_by_commission


def render_video_table(session, account_id: str) -> None:
    """Render the top videos by commission earned as a dataframe."""
    try:
        rows = get_top_videos_by_commission(session, account_id)
        if rows:
            df = pd.DataFrame(rows)
        else:
            df = pd.DataFrame(
                columns=[
                    "hook_archetype",
                    "retention_3s_pct",
                    "affiliate_ctr_pct",
                    "commission_earned",
                    "lifecycle_state",
                ]
            )
        df["retention_3s_pct"] = (df["retention_3s_pct"] * 100).round(1)
        df["affiliate_ctr_pct"] = (df["affiliate_ctr_pct"] * 100).round(1)
        df["commission_earned"] = df["commission_earned"].round(2)
        df = df.rename(
            columns={
                "hook_archetype": "Hook Archetype",
                "retention_3s_pct": "3s Retention %",
                "affiliate_ctr_pct": "Affiliate CTR %",
                "commission_earned": "Commission ($)",
                "lifecycle_state": "Status",
            }
        )
        st.subheader("Top Videos by Commission")
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Video table failed: {e}")
