"""
Streamlit entry point for the TikTok Faceless monitoring dashboard.

Implementation: Story 6.1 — Dashboard Foundation & Auth
Implementation: Story 6.2 — Status Top Bar & Alert Zone
"""

from datetime import datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.auth import check_password
from dashboard.components.milestone_banner import render_milestone_banners
from dashboard.components.phase_badge import render_phase_badge
from dashboard.components.suppression_alert import render_suppression_alert
from dashboard.components.time_utils import humanize_timedelta
from tiktok_faceless.db.queries import (
    get_account_phase,
    get_account_summary_row,
    get_active_accounts,
    get_active_suppression,
    get_first_commission_amount,
    get_last_post_time,
    get_latest_phase_transition,
    get_monthly_revenue,
    get_phase_started_at,
    get_unresolved_errors,
    get_videos_posted_today,
)
from tiktok_faceless.db.session import get_session
from dashboard.components.account_summary_table import render_account_summary_table

if not check_password():
    st.stop()

st_autorefresh(interval=60_000, key="autorefresh")

# --- Load active accounts and build summaries ---
with get_session() as session:
    active_accounts = get_active_accounts(session)
    account_ids = [a.account_id for a in active_accounts]
    summaries = [get_account_summary_row(session, aid) for aid in account_ids]

if not account_ids:
    st.warning("No active accounts. Run --provision-account first.")
    st.stop()

if "selected_account_id" not in st.session_state:
    st.session_state["selected_account_id"] = account_ids[0]

# Sidebar account selector — key="selected_account_id" lets Streamlit write the value directly
account_id = st.sidebar.selectbox(
    "Account",
    account_ids,
    key="selected_account_id",
)

# --- Fetch top bar data ---
with get_session() as session:
    phase = get_account_phase(session, account_id)
    phase_started_at = get_phase_started_at(session, account_id)
    last_post_time = get_last_post_time(session, account_id)
    videos_today = get_videos_posted_today(session, account_id)
    unresolved_errors = get_unresolved_errors(session, account_id)
    active_suppression = get_active_suppression(session, account_id)
    # Story 6.6 — milestone data
    first_commission = get_first_commission_amount(session, account_id)
    phase_transition = get_latest_phase_transition(session, account_id)
    monthly_revenue = get_monthly_revenue(session, account_id)

# --- Top Bar ---
col_phase, col_status, col_last_post, col_today, col_refresh = st.columns([2, 2, 2, 2, 2])

with col_phase:
    render_phase_badge(phase, phase_started_at)

with col_status:
    if unresolved_errors:
        st.markdown("🔴 **Degraded**")
    else:
        st.markdown("🟢 **Healthy**")

with col_last_post:
    if last_post_time is None:
        st.markdown(":orange[Last post: Never]")
    else:
        elapsed = datetime.utcnow() - last_post_time
        label = humanize_timedelta(elapsed)
        if elapsed.total_seconds() > 86400:
            st.markdown(f":orange[Last post: {label}]")
        else:
            st.markdown(f"Last post: {label}")

with col_today:
    st.metric("Posted Today", videos_today)

with col_refresh:
    st.caption(f"Refreshed {datetime.utcnow().strftime('%H:%M:%S')} UTC")

# --- Alert Zone ---
_no_post_24h = last_post_time is None or (
    (datetime.utcnow() - last_post_time).total_seconds() > 86400
)

if active_suppression is not None:
    render_suppression_alert(active_suppression)
elif _no_post_24h:
    st.warning("No posts in 24h — pipeline may be stalled")
elif unresolved_errors:
    st.warning(f"{len(unresolved_errors)} unresolved error(s) — check the Errors tab")
else:
    st.success("All systems healthy · Last checked just now")

# Milestone banners render below the primary alert, independently of its state
render_milestone_banners(
    phase_transition=phase_transition,
    first_commission=first_commission,
    monthly_revenue=monthly_revenue,
)

st.title("TikTok Faceless Dashboard")

render_account_summary_table(summaries)
