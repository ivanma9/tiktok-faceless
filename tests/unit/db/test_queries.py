"""Tests for tiktok_faceless/db/queries.py"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Base, Product, Video, VideoMetric
from tiktok_faceless.db.queries import cache_product, get_cached_products, get_commission_per_view
from tiktok_faceless.models.shop import AffiliateProduct


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def _make_product(niche: str = "health", score: float = 0.8) -> AffiliateProduct:
    return AffiliateProduct(
        product_id=str(uuid.uuid4()),
        product_name="Widget",
        product_url="https://shop.tiktok.com/w",
        commission_rate=0.15,
        sales_velocity_score=score,
        niche=niche,
    )


class TestCacheProduct:
    def test_cache_writes_product_row(self, session) -> None:
        p = _make_product()
        cache_product(session, account_id="acc1", product=p)
        row = session.query(Product).filter_by(account_id="acc1").first()
        assert row is not None
        assert row.product_id == p.product_id
        assert row.niche == p.niche

    def test_cache_upserts_on_duplicate_product_id(self, session) -> None:
        p = _make_product()
        cache_product(session, account_id="acc1", product=p)
        cache_product(session, account_id="acc1", product=p)
        count = session.query(Product).filter_by(account_id="acc1").count()
        assert count == 1


class TestGetCachedProducts:
    def test_returns_products_within_24h(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 1
        assert results[0].product_id == p.product_id

    def test_excludes_products_older_than_24h(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        row = session.query(Product).first()
        row.cached_at = datetime.utcnow() - timedelta(hours=25)
        session.commit()
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 0

    def test_scoped_by_account_id(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc2", niche="health")
        assert len(results) == 0

    def test_scoped_by_niche(self, session) -> None:
        p = _make_product(niche="fitness")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 0


class TestGetCommissionPerView:
    def test_returns_correct_ratio(self, session) -> None:
        vid = Video(
            id="v1", account_id="acc1", niche="health",
            lifecycle_state="posted", tiktok_video_id="tv1",
        )
        session.add(vid)
        metric = VideoMetric(
            video_id="tv1", account_id="acc1",
            recorded_at=datetime.utcnow(),
            view_count=1000, like_count=0, comment_count=0,
            share_count=0, average_time_watched=0.0,
            retention_3s=0.0, retention_15s=0.0, fyp_reach_pct=0.0,
            affiliate_clicks=10, affiliate_orders=2,
        )
        session.add(metric)
        session.commit()
        cpv = get_commission_per_view(session, account_id="acc1", niche="health")
        assert cpv == pytest.approx(2 / 1000)

    def test_returns_zero_when_no_data(self, session) -> None:
        cpv = get_commission_per_view(session, account_id="acc1", niche="health")
        assert cpv == 0.0
