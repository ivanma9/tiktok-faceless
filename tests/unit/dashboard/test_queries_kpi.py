"""Tests for Story 6.3 KPI query functions in tiktok_faceless.db.queries."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Base, VideoMetric
from tiktok_faceless.db.queries import (
    get_kpi_affiliate_ctr,
    get_kpi_freshness,
    get_kpi_fyp_reach_rate,
    get_kpi_retention_3s,
    get_kpi_retention_15s,
    get_kpi_revenue,
    get_kpi_sparkline,
)

_ACCOUNT = "acc_kpi"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _metric(
    account_id: str = _ACCOUNT,
    recorded_at: datetime | None = None,
    view_count: int = 1000,
    affiliate_clicks: int = 0,
    affiliate_orders: int = 0,
    retention_3s: float = 0.0,
    retention_15s: float = 0.0,
    fyp_reach_pct: float = 0.0,
) -> VideoMetric:
    return VideoMetric(
        video_id=str(uuid.uuid4()),
        account_id=account_id,
        recorded_at=recorded_at or datetime.utcnow(),
        view_count=view_count,
        affiliate_clicks=affiliate_clicks,
        affiliate_orders=affiliate_orders,
        retention_3s=retention_3s,
        retention_15s=retention_15s,
        fyp_reach_pct=fyp_reach_pct,
    )


# --- Revenue ---


def test_get_kpi_revenue_returns_zero_when_no_data(session):
    assert get_kpi_revenue(session, _ACCOUNT) == 0.0


def test_get_kpi_revenue_sums_clicks_times_orders_over_view_count(session):
    # Fallback path: no products linked, returns SUM(affiliate_orders)
    session.add(_metric(affiliate_orders=3))
    session.add(_metric(affiliate_orders=5))
    session.commit()
    result = get_kpi_revenue(session, _ACCOUNT)
    assert result == 8.0


# --- 3s Retention ---


def test_get_kpi_retention_3s_returns_none_when_no_data(session):
    assert get_kpi_retention_3s(session, _ACCOUNT) is None


def test_get_kpi_retention_3s_averages_window(session):
    session.add(_metric(retention_3s=0.6))
    session.add(_metric(retention_3s=0.8))
    session.commit()
    result = get_kpi_retention_3s(session, _ACCOUNT)
    assert result is not None
    assert abs(result - 0.7) < 1e-6


def test_get_kpi_retention_3s_excludes_rows_outside_window(session):
    within = _metric(retention_3s=0.6, recorded_at=datetime.utcnow() - timedelta(days=3))
    outside = _metric(retention_3s=0.9, recorded_at=datetime.utcnow() - timedelta(days=9))
    session.add(within)
    session.add(outside)
    session.commit()
    result = get_kpi_retention_3s(session, _ACCOUNT)
    assert result is not None
    assert abs(result - 0.6) < 1e-6


# --- 15s Retention ---


def test_get_kpi_retention_15s_returns_average(session):
    session.add(_metric(retention_15s=0.3))
    session.add(_metric(retention_15s=0.5))
    session.commit()
    result = get_kpi_retention_15s(session, _ACCOUNT)
    assert result is not None
    assert abs(result - 0.4) < 1e-6


# --- Affiliate CTR ---


def test_get_kpi_affiliate_ctr_computes_ratio(session):
    session.add(_metric(affiliate_clicks=50, view_count=1000))
    session.commit()
    result = get_kpi_affiliate_ctr(session, _ACCOUNT)
    assert result is not None
    assert abs(result - 0.05) < 1e-6


def test_get_kpi_affiliate_ctr_returns_none_when_no_data(session):
    assert get_kpi_affiliate_ctr(session, _ACCOUNT) is None


# --- FYP Reach Rate ---


def test_get_kpi_fyp_reach_rate_averages_pct(session):
    session.add(_metric(fyp_reach_pct=0.4))
    session.add(_metric(fyp_reach_pct=0.6))
    session.commit()
    result = get_kpi_fyp_reach_rate(session, _ACCOUNT)
    assert result is not None
    assert abs(result - 0.5) < 1e-6


# --- Sparkline ---


def test_get_kpi_sparkline_returns_7_elements(session):
    now = datetime.utcnow()
    for i in range(7):
        session.add(
            _metric(
                retention_3s=0.5,
                recorded_at=now - timedelta(days=i),
            )
        )
    session.commit()
    result = get_kpi_sparkline(session, _ACCOUNT, "retention_3s")
    assert len(result) == 7


def test_get_kpi_sparkline_fills_missing_days_with_zero(session):
    now = datetime.utcnow()
    # Add data only for days 1, 3, 5 back (3 of 7)
    for days_ago in [1, 3, 5]:
        session.add(
            _metric(
                retention_3s=0.5,
                recorded_at=now - timedelta(days=days_ago),
            )
        )
    session.commit()
    result = get_kpi_sparkline(session, _ACCOUNT, "retention_3s")
    assert len(result) == 7
    zero_count = sum(1 for v in result if v == 0.0)
    assert zero_count >= 4


# --- Freshness ---


def test_get_kpi_freshness_returns_max_recorded_at(session):
    earlier = datetime.utcnow() - timedelta(hours=2)
    later = datetime.utcnow() - timedelta(hours=1)
    session.add(_metric(recorded_at=earlier))
    session.add(_metric(recorded_at=later))
    session.commit()
    result = get_kpi_freshness(session, _ACCOUNT)
    assert result is not None
    # SQLite may lose microseconds; compare to minute precision
    assert abs((result - later).total_seconds()) < 2


def test_get_kpi_freshness_returns_none_when_empty(session):
    assert get_kpi_freshness(session, _ACCOUNT) is None
