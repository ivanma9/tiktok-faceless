"""Tests for Story 6.6 — milestone query functions."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import AgentDecision, Base, Product, Video, VideoMetric
from tiktok_faceless.db.queries import (
    get_first_commission_amount,
    get_latest_phase_transition,
    get_monthly_revenue,
)

_ACCOUNT = "acc_milestone_test"
_OTHER = "acc_other"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _make_product(
    session, account_id: str = _ACCOUNT, product_id: str = "prod1", commission_rate: float = 0.10
) -> Product:
    p = Product(
        id=str(uuid.uuid4()),
        account_id=account_id,
        product_id=product_id,
        commission_rate=commission_rate,
        niche="test",
        product_name="Test Product",
        product_url="http://example.com",
    )
    session.add(p)
    session.flush()
    return p


def _make_video(
    session, account_id: str = _ACCOUNT, tiktok_video_id: str = "vid1", product_id: str = "prod1"
) -> Video:
    v = Video(
        id=str(uuid.uuid4()),
        account_id=account_id,
        tiktok_video_id=tiktok_video_id,
        product_id=product_id,
        niche="test",
    )
    session.add(v)
    session.flush()
    return v


def _make_metric(
    session,
    account_id: str = _ACCOUNT,
    video_id: str = "vid1",
    affiliate_orders: int = 5,
    recorded_at: datetime | None = None,
) -> VideoMetric:
    m = VideoMetric(
        account_id=account_id,
        video_id=video_id,
        affiliate_orders=affiliate_orders,
        recorded_at=recorded_at or datetime.utcnow(),
    )
    session.add(m)
    session.flush()
    return m


def _make_decision(
    session,
    account_id: str = _ACCOUNT,
    decision_type: str = "phase_transition",
    created_at: datetime | None = None,
) -> AgentDecision:
    d = AgentDecision(
        account_id=account_id,
        agent="orchestrator",
        decision_type=decision_type,
        from_value="warmup",
        to_value="tournament",
        rationale="CTR threshold met",
        created_at=created_at or datetime.utcnow(),
    )
    session.add(d)
    session.flush()
    return d


# --- get_first_commission_amount ---


def test_get_first_commission_amount_returns_none_when_no_data(session):
    result = get_first_commission_amount(session, _ACCOUNT)
    assert result is None


def test_get_first_commission_amount_returns_total_when_commission_exists(session):
    _make_product(session, commission_rate=0.10)
    _make_video(session)
    _make_metric(session, affiliate_orders=5)
    result = get_first_commission_amount(session, _ACCOUNT)
    assert result == pytest.approx(0.50)


def test_get_first_commission_amount_returns_none_when_commission_is_zero(session):
    _make_product(session, commission_rate=0.10)
    _make_video(session)
    _make_metric(session, affiliate_orders=0)
    result = get_first_commission_amount(session, _ACCOUNT)
    assert result is None


# --- get_latest_phase_transition ---


def test_get_latest_phase_transition_returns_none_when_no_recent_transition(session):
    _make_decision(session, created_at=datetime.utcnow() - timedelta(hours=48))
    result = get_latest_phase_transition(session, _ACCOUNT)
    assert result is None


def test_get_latest_phase_transition_returns_most_recent_within_24h(session):
    now = datetime.utcnow()
    _make_decision(session, created_at=now - timedelta(hours=12))
    newer = _make_decision(session, created_at=now - timedelta(hours=1))
    result = get_latest_phase_transition(session, _ACCOUNT)
    assert result is not None
    assert result.id == newer.id


# --- get_monthly_revenue ---


def test_get_monthly_revenue_returns_zero_when_no_data(session):
    result = get_monthly_revenue(session, _ACCOUNT)
    assert result == 0.0


def test_get_monthly_revenue_returns_sum_for_current_month_only(session):
    now = datetime.utcnow()
    prior_month = now.replace(day=1) - timedelta(days=1)

    _make_product(session, commission_rate=0.10, product_id="prod1")
    _make_video(session, tiktok_video_id="vid1", product_id="prod1")
    _make_video(session, tiktok_video_id="vid2", product_id="prod1")

    # 2 rows in current month
    _make_metric(session, video_id="vid1", affiliate_orders=5, recorded_at=now)
    _make_metric(session, video_id="vid2", affiliate_orders=5, recorded_at=now - timedelta(days=3))
    # 1 row in prior month — should be excluded
    _make_metric(session, video_id="vid1", affiliate_orders=100, recorded_at=prior_month)

    result = get_monthly_revenue(session, _ACCOUNT)
    assert result == pytest.approx(1.0)  # (5 + 5) * 0.10


def test_get_monthly_revenue_scoped_to_account_id(session):
    now = datetime.utcnow()
    _make_product(session, account_id=_ACCOUNT, product_id="prod1", commission_rate=0.10)
    _make_video(session, account_id=_ACCOUNT, tiktok_video_id="vid1", product_id="prod1")
    _make_metric(
        session, account_id=_ACCOUNT, video_id="vid1", affiliate_orders=10, recorded_at=now
    )

    result = get_monthly_revenue(session, _OTHER)
    assert result == 0.0
