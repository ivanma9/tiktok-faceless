"""KPI Strip component — Story 6.3."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import streamlit as st

from dashboard.components.sparkline import render_sparkline
from tiktok_faceless.db.queries import (
    get_kpi_affiliate_ctr,
    get_kpi_freshness,
    get_kpi_fyp_reach_rate,
    get_kpi_prior_affiliate_ctr,
    get_kpi_prior_fyp_reach_rate,
    get_kpi_prior_retention_3s,
    get_kpi_prior_retention_15s,
    get_kpi_prior_revenue,
    get_kpi_retention_3s,
    get_kpi_retention_15s,
    get_kpi_revenue,
    get_kpi_sparkline,
)

# Threshold constants — display-only copies (source of truth: config.py for pipeline logic)
_REVENUE_OK = 0.0
_REVENUE_WARN = 0.0
_RETENTION_3S_OK = 0.50
_RETENTION_3S_WARN = 0.30
_RETENTION_15S_OK = 0.35
_RETENTION_15S_WARN = 0.20
_AFFILIATE_CTR_OK = 0.03
_AFFILIATE_CTR_WARN = 0.01
_FYP_REACH_OK = 0.40
_FYP_REACH_WARN = 0.25

# Sparkline colors
_COLOR_EMERALD = "#10b981"
_COLOR_AMBER = "#f59e0b"
_COLOR_ROSE = "#f43f5e"
_COLOR_ZINC = "#71717a"


@dataclass
class KPICard:
    label: str
    value: float | None
    prior: float | None
    sparkline: list[float] = field(default_factory=list)
    unit: str = "%"
    threshold_ok: float = 0.0
    threshold_warn: float = 0.0

    @property
    def delta(self) -> float | None:
        if self.value is None or self.prior is None:
            return None
        return self.value - self.prior


def format_kpi_value(value: float | None, unit: str) -> str:
    """Format a KPI value for display."""
    if value is None:
        return "\u2014"
    if unit == "$":
        return f"${value:,.2f}"
    return f"{value * 100:.1f}%"


def format_delta(delta: float | None, unit: str) -> str:
    """Format a KPI delta for display."""
    if delta is None:
        return ""
    if unit == "$":
        if delta >= 0:
            return f"+${delta:,.2f}"
        return f"-${abs(delta):,.2f}"
    if delta >= 0:
        return f"+{delta * 100:.1f}%"
    return f"-{abs(delta) * 100:.1f}%"


def render_freshness(last_recorded_at: datetime | None) -> None:
    """Render a freshness timestamp below the KPI strip."""
    if last_recorded_at is None:
        return
    age = datetime.utcnow() - last_recorded_at
    minutes = int(age.total_seconds() / 60)
    if age < timedelta(minutes=5):
        st.caption("Updated just now")
    elif age < timedelta(minutes=15):
        st.markdown(f":orange[\u26a0 Updated {minutes}m ago]")
    else:
        st.markdown(f":red[\u26a0 Updated {minutes}m ago]")


def _threshold_color(card: KPICard) -> str:
    """Return sparkline color based on current value vs thresholds."""
    if card.value is None:
        return _COLOR_ZINC
    if card.value >= card.threshold_ok:
        return _COLOR_EMERALD
    if card.value >= card.threshold_warn:
        return _COLOR_AMBER
    return _COLOR_ROSE


def build_kpi_cards(session, account_id: str) -> list[KPICard]:
    """Build list of 5 KPICard objects with current and prior 7-day window data."""
    # Current window: last 7 days; prior window: days 8–14 back
    # Query functions use days=7 for current and days=14 minus days=7 for prior.
    # We call the query functions twice: once for current window (days=7) and once
    # for the prior window by temporarily using a helper approach.

    # Current values
    rev_curr = get_kpi_revenue(session, account_id, days=7)
    ret3_curr = get_kpi_retention_3s(session, account_id, days=7)
    ret15_curr = get_kpi_retention_15s(session, account_id, days=7)
    ctr_curr = get_kpi_affiliate_ctr(session, account_id, days=7)
    fyp_curr = get_kpi_fyp_reach_rate(session, account_id, days=7)

    # Prior values: days 8–14 ago (delegated to db/queries — no direct SQLAlchemy in dashboard)
    rev_prior = get_kpi_prior_revenue(session, account_id, days=7)
    ret3_prior = get_kpi_prior_retention_3s(session, account_id, days=7)
    ret15_prior = get_kpi_prior_retention_15s(session, account_id, days=7)
    ctr_prior = get_kpi_prior_affiliate_ctr(session, account_id, days=7)
    fyp_prior = get_kpi_prior_fyp_reach_rate(session, account_id, days=7)

    # Sparklines
    rev_spark = get_kpi_sparkline(session, account_id, "revenue")
    ret3_spark = get_kpi_sparkline(session, account_id, "retention_3s")
    ret15_spark = get_kpi_sparkline(session, account_id, "retention_15s")
    ctr_spark = get_kpi_sparkline(session, account_id, "affiliate_ctr")
    fyp_spark = get_kpi_sparkline(session, account_id, "fyp_reach_pct")

    return [
        KPICard(
            label="Revenue",
            value=rev_curr,
            prior=rev_prior,
            sparkline=rev_spark,
            unit="$",
            threshold_ok=_REVENUE_OK,
            threshold_warn=_REVENUE_WARN,
        ),
        KPICard(
            label="3s Retention",
            value=ret3_curr,
            prior=ret3_prior,
            sparkline=ret3_spark,
            unit="%",
            threshold_ok=_RETENTION_3S_OK,
            threshold_warn=_RETENTION_3S_WARN,
        ),
        KPICard(
            label="15s Retention",
            value=ret15_curr,
            prior=ret15_prior,
            sparkline=ret15_spark,
            unit="%",
            threshold_ok=_RETENTION_15S_OK,
            threshold_warn=_RETENTION_15S_WARN,
        ),
        KPICard(
            label="Affiliate CTR",
            value=ctr_curr,
            prior=ctr_prior,
            sparkline=ctr_spark,
            unit="%",
            threshold_ok=_AFFILIATE_CTR_OK,
            threshold_warn=_AFFILIATE_CTR_WARN,
        ),
        KPICard(
            label="FYP Reach Rate",
            value=fyp_curr,
            prior=fyp_prior,
            sparkline=fyp_spark,
            unit="%",
            threshold_ok=_FYP_REACH_OK,
            threshold_warn=_FYP_REACH_WARN,
        ),
    ]


def render_kpi_strip(session, account_id: str) -> None:
    """Render the full 5-column KPI strip with sparklines and freshness timestamp."""
    cards = build_kpi_cards(session, account_id)
    freshness_ts = get_kpi_freshness(session, account_id)

    cols = st.columns(5)
    for col, card in zip(cols, cards):
        with col:
            value_str = format_kpi_value(card.value, card.unit)
            delta_str = format_delta(card.delta, card.unit)

            if card.value is None:
                st.metric(label=card.label, value="\u2014", help="No data yet")
            else:
                # Neutral state: delta exists but no meaningful change
                if card.delta is not None and abs(card.delta) < 0.01 and card.unit == "%":
                    st.metric(label=card.label, value=value_str, delta=None)
                    st.markdown(f":orange[{delta_str}]" if delta_str else "")
                else:
                    st.metric(
                        label=card.label,
                        value=value_str,
                        delta=delta_str if delta_str else None,
                        delta_color="normal",
                    )

            render_sparkline(card.sparkline, color=_threshold_color(card))

    render_freshness(freshness_ts)
