"""Tests for get_account_summary_row — Story 7.3."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Account, Base, Error, Product, Video, VideoMetric
from tiktok_faceless.db.queries import get_account_summary_row


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_account(session, account_id, phase="warmup"):
    acc = Account(
        id=str(uuid.uuid4()),
        account_id=account_id,
        tiktok_access_token="tok",
        tiktok_open_id="oid",
        phase=phase,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(acc)
    session.commit()
    return acc


def test_get_account_summary_row_returns_correct_phase(session):
    _make_account(session, "acc1", phase="tournament")
    result = get_account_summary_row(session, "acc1")
    assert result["phase"] == "tournament"


def test_get_account_summary_row_pipeline_healthy_true(session):
    _make_account(session, "acc2")
    result = get_account_summary_row(session, "acc2")
    assert result["pipeline_healthy"] is True


def test_get_account_summary_row_pipeline_healthy_false(session):
    _make_account(session, "acc3")
    err = Error(
        account_id="acc3",
        agent="test_agent",
        error_type="test_error",
        message="something broke",
        timestamp=datetime.utcnow(),
        resolved_at=None,
    )
    session.add(err)
    session.commit()
    result = get_account_summary_row(session, "acc3")
    assert result["pipeline_healthy"] is False


def test_get_account_summary_row_revenue_today(session):
    _make_account(session, "acc4")
    product_id = "prod1"
    video_id = "vid1"
    product = Product(
        id=str(uuid.uuid4()),
        product_id=product_id,
        account_id="acc4",
        niche="tech",
        product_name="Widget",
        product_url="http://example.com",
        commission_rate=5.0,
        sales_velocity_score=1.0,
        cached_at=datetime.utcnow(),
        eliminated=False,
    )
    session.add(product)
    video = Video(
        id=str(uuid.uuid4()),
        account_id="acc4",
        niche="tech",
        lifecycle_state="posted",
        tiktok_video_id=video_id,
        product_id=product_id,
        created_at=datetime.utcnow(),
        posted_at=datetime.utcnow(),
    )
    session.add(video)
    metric = VideoMetric(
        video_id=video_id,
        account_id="acc4",
        recorded_at=datetime.utcnow(),
        affiliate_orders=2,
    )
    session.add(metric)
    session.commit()
    result = get_account_summary_row(session, "acc4")
    assert result["revenue_today"] == 10.0


def test_get_account_summary_row_revenue_today_excludes_yesterday(session):
    _make_account(session, "acc5")
    product_id = "prod2"
    video_id = "vid2"
    product = Product(
        id=str(uuid.uuid4()),
        product_id=product_id,
        account_id="acc5",
        niche="tech",
        product_name="Widget2",
        product_url="http://example.com",
        commission_rate=5.0,
        sales_velocity_score=1.0,
        cached_at=datetime.utcnow(),
        eliminated=False,
    )
    session.add(product)
    video = Video(
        id=str(uuid.uuid4()),
        account_id="acc5",
        niche="tech",
        lifecycle_state="posted",
        tiktok_video_id=video_id,
        product_id=product_id,
        created_at=datetime.utcnow(),
        posted_at=datetime.utcnow() - timedelta(days=2),
    )
    session.add(video)
    metric = VideoMetric(
        video_id=video_id,
        account_id="acc5",
        recorded_at=datetime.utcnow() - timedelta(days=1),
        affiliate_orders=2,
    )
    session.add(metric)
    session.commit()
    result = get_account_summary_row(session, "acc5")
    assert result["revenue_today"] == 0.0


def test_get_account_summary_row_last_post_timedelta_is_timedelta(session):
    _make_account(session, "acc6")
    posted_at = datetime.utcnow() - timedelta(hours=2)
    video = Video(
        id=str(uuid.uuid4()),
        account_id="acc6",
        niche="tech",
        lifecycle_state="posted",
        created_at=datetime.utcnow(),
        posted_at=posted_at,
    )
    session.add(video)
    session.commit()
    result = get_account_summary_row(session, "acc6")
    assert isinstance(result["last_post_timedelta"], timedelta)
    assert abs(result["last_post_timedelta"].total_seconds() - 7200) < 10


def test_get_account_summary_row_last_post_timedelta_none(session):
    _make_account(session, "acc7")
    result = get_account_summary_row(session, "acc7")
    assert result["last_post_timedelta"] is None


def test_get_account_summary_row_unknown_account(session):
    result = get_account_summary_row(session, "nonexistent")
    assert result["phase"] == "unknown"
    assert result["pipeline_healthy"] is True
    assert result["revenue_today"] == 0.0
    assert result["last_post_timedelta"] is None
