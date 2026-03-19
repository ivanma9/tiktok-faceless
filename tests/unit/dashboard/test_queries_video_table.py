"""Tests for Story 6.4 video table and tournament query functions."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Base, Product, Video, VideoMetric
from tiktok_faceless.db.queries import get_top_videos_by_commission, get_tournament_niche_table

_ACCOUNT = "acc_video_table"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _make_video(
    session,
    account_id: str = _ACCOUNT,
    niche: str = "fitness",
    hook_archetype: str = "hook_a",
    lifecycle_state: str = "live",
    product_id: str | None = None,
) -> Video:
    vid_id = str(uuid.uuid4())
    tiktok_id = str(uuid.uuid4())
    v = Video(
        id=vid_id,
        account_id=account_id,
        niche=niche,
        hook_archetype=hook_archetype,
        lifecycle_state=lifecycle_state,
        tiktok_video_id=tiktok_id,
        product_id=product_id,
    )
    session.add(v)
    session.flush()
    return v


def _make_metric(
    session,
    video: Video,
    account_id: str = _ACCOUNT,
    affiliate_orders: int = 0,
    affiliate_clicks: int = 0,
    view_count: int = 1000,
    retention_3s: float = 0.5,
    recorded_at: datetime | None = None,
) -> VideoMetric:
    m = VideoMetric(
        video_id=video.tiktok_video_id,
        account_id=account_id,
        recorded_at=recorded_at or datetime.utcnow(),
        view_count=view_count,
        affiliate_clicks=affiliate_clicks,
        affiliate_orders=affiliate_orders,
        retention_3s=retention_3s,
    )
    session.add(m)
    session.flush()
    return m


def _make_product(
    session,
    account_id: str = _ACCOUNT,
    niche: str = "fitness",
    commission_rate: float = 0.1,
    eliminated: bool = False,
) -> Product:
    product_id = str(uuid.uuid4())
    p = Product(
        id=str(uuid.uuid4()),
        product_id=product_id,
        account_id=account_id,
        niche=niche,
        product_name="Test Product",
        product_url="https://example.com",
        commission_rate=commission_rate,
        eliminated=eliminated,
    )
    session.add(p)
    session.flush()
    return p


# --- get_top_videos_by_commission ---


def test_get_top_videos_by_commission_returns_empty_when_no_data(session):
    result = get_top_videos_by_commission(session, _ACCOUNT)
    assert result == []


def test_get_top_videos_by_commission_orders_by_commission_desc(session):
    p = _make_product(session, commission_rate=1.0)
    v1 = _make_video(session, product_id=p.product_id)
    v2 = _make_video(session, product_id=p.product_id)
    v3 = _make_video(session, product_id=p.product_id)
    _make_metric(session, v1, affiliate_orders=5)
    _make_metric(session, v2, affiliate_orders=10)
    _make_metric(session, v3, affiliate_orders=1)
    result = get_top_videos_by_commission(session, _ACCOUNT)
    commissions = [r["commission_earned"] for r in result]
    assert commissions == sorted(commissions, reverse=True)


def test_get_top_videos_by_commission_limits_to_20(session):
    for _ in range(25):
        v = _make_video(session)
        _make_metric(session, v)
    result = get_top_videos_by_commission(session, _ACCOUNT)
    assert len(result) == 20


def test_get_top_videos_by_commission_includes_required_keys(session):
    v = _make_video(session)
    _make_metric(session, v)
    result = get_top_videos_by_commission(session, _ACCOUNT)
    assert len(result) == 1
    row = result[0]
    for key in (
        "hook_archetype",
        "retention_3s_pct",
        "affiliate_ctr_pct",
        "commission_earned",
        "lifecycle_state",
    ):
        assert key in row


# --- get_tournament_niche_table ---


def test_get_tournament_niche_table_returns_empty_when_no_data(session):
    result = get_tournament_niche_table(session, _ACCOUNT)
    assert result == []


def test_get_tournament_niche_table_assigns_leading_to_top_niche(session):
    v1 = _make_video(session, niche="fitness")
    v2 = _make_video(session, niche="beauty")
    _make_metric(session, v1, affiliate_orders=100, view_count=1000)
    _make_metric(session, v2, affiliate_orders=1, view_count=1000)
    result = get_tournament_niche_table(session, _ACCOUNT)
    assert result[0]["status"] == "Leading"


def test_get_tournament_niche_table_assigns_eliminated_status(session):
    v1 = _make_video(session, niche="fitness")
    v2 = _make_video(session, niche="beauty")
    _make_metric(session, v1, affiliate_orders=100, view_count=1000)
    _make_metric(session, v2, affiliate_orders=50, view_count=1000)
    _make_product(session, niche="beauty", eliminated=True)
    result = get_tournament_niche_table(session, _ACCOUNT)
    beauty_row = next(r for r in result if r["niche"] == "beauty")
    assert beauty_row["status"] == "Eliminated"


def test_get_tournament_niche_table_assigns_trailing_to_middle_niches(session):
    for niche, orders in [("fitness", 100), ("beauty", 50), ("cooking", 10)]:
        v = _make_video(session, niche=niche)
        _make_metric(session, v, affiliate_orders=orders, view_count=1000)
    result = get_tournament_niche_table(session, _ACCOUNT)
    middle = next(r for r in result if r["rank"] == 2)
    assert middle["status"] == "Trailing"


def test_get_tournament_niche_table_includes_required_keys(session):
    v = _make_video(session, niche="fitness")
    _make_metric(session, v, view_count=1000)
    result = get_tournament_niche_table(session, _ACCOUNT)
    assert len(result) == 1
    row = result[0]
    for key in (
        "rank",
        "niche",
        "video_count",
        "avg_ctr_pct",
        "avg_retention_3s_pct",
        "total_revenue",
        "status",
    ):
        assert key in row
