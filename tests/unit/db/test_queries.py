"""Tests for tiktok_faceless/db/queries.py"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tiktok_faceless.db.models import Base, Error, Product, Video, VideoMetric
from tiktok_faceless.db.queries import (
    cache_product,
    flag_eliminated_niches,
    get_active_errors,
    get_archetype_scores,
    get_cached_products,
    get_commission_per_view,
    get_commission_totals,
    get_niche_scores,
    write_agent_errors,
)
from tiktok_faceless.models.shop import AffiliateProduct
from tiktok_faceless.state import AgentError


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


class TestGetCommissionTotals:
    def test_aggregates_by_niche_correctly(self, session) -> None:
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1",
            created_at=now,
        ))
        session.add(Video(
            id="v2", account_id="acc1", niche="beauty",
            lifecycle_state="posted", tiktok_video_id="tiktok-v2",
            created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, like_count=0, comment_count=0,
            share_count=0, average_time_watched=0.0,
            retention_3s=0.0, retention_15s=0.0, fyp_reach_pct=0.0,
            affiliate_clicks=10, affiliate_orders=3,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v2", account_id="acc1",
            recorded_at=now - timedelta(days=2),
            view_count=500, like_count=0, comment_count=0,
            share_count=0, average_time_watched=0.0,
            retention_3s=0.0, retention_15s=0.0, fyp_reach_pct=0.0,
            affiliate_clicks=5, affiliate_orders=1,
        ))
        session.commit()
        result = get_commission_totals(session, account_id="acc1")
        assert result["fitness"]["total_orders"] == 3
        assert result["fitness"]["total_views"] == 1000
        assert result["beauty"]["total_orders"] == 1
        assert result["beauty"]["total_views"] == 500

    def test_returns_empty_dict_when_no_data(self, session) -> None:
        result = get_commission_totals(session, account_id="acc1")
        assert result == {}

    def test_excludes_metrics_outside_window(self, session) -> None:
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1",
            created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=10),
            view_count=9999, like_count=0, comment_count=0,
            share_count=0, average_time_watched=0.0,
            retention_3s=0.0, retention_15s=0.0, fyp_reach_pct=0.0,
            affiliate_clicks=0, affiliate_orders=99,
        ))
        session.commit()
        result = get_commission_totals(session, account_id="acc1")
        assert result == {}


class TestGetNicheScores:

    def test_returns_ranked_scores_descending(self, session: Session) -> None:
        """Higher-performing niche appears first in output."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(Video(
            id="v2", account_id="acc1", niche="beauty",
            lifecycle_state="posted", tiktok_video_id="tiktok-v2", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=50, retention_3s=0.8, affiliate_orders=10,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v2", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=5, retention_3s=0.3, affiliate_orders=1,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")

        assert len(result) == 2
        assert result[0][0] == "fitness"
        assert result[1][0] == "beauty"
        assert result[0][1] > result[1][1]

    def test_returns_empty_list_when_no_data(self, session: Session) -> None:
        result = get_niche_scores(session, account_id="acc1")
        assert result == []

    def test_excludes_metrics_outside_window(self, session: Session) -> None:
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=10),
            view_count=1000, affiliate_clicks=100, retention_3s=0.9, affiliate_orders=20,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")
        assert result == []

    def test_min_video_count_filters_low_sample_niches(self, session: Session) -> None:
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=500, affiliate_clicks=10, retention_3s=0.5, affiliate_orders=2,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1", min_video_count=2)
        assert result == []

    def test_excludes_other_account_niches(self, session: Session) -> None:
        """Metrics from a different account_id do not affect scores for acc1."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(Video(
            id="v2", account_id="acc2", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v2", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=100, affiliate_clicks=5, retention_3s=0.5, affiliate_orders=2,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v2", account_id="acc2",
            recorded_at=now - timedelta(days=1),
            view_count=9999, affiliate_clicks=9999, retention_3s=0.99, affiliate_orders=999,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")

        assert len(result) == 1
        assert result[0][0] == "fitness"
        # Score should be based on acc1's metrics only, not acc2's inflated metrics
        assert result[0][1] < 0.5

    def test_scores_are_between_0_and_1(self, session: Session) -> None:
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=200, retention_3s=0.95, affiliate_orders=15,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")
        for _niche, score in result:
            assert 0.0 <= score <= 1.0


class TestFlagEliminatedNiches:

    def test_flags_low_score_niches(self, session: Session) -> None:
        session.add(Product(
            id="p1", account_id="acc1", niche="beauty",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        niche_scores = [("beauty", 0.0), ("fitness", 0.8)]
        eliminated = flag_eliminated_niches(session, "acc1", niche_scores, threshold_score=0.1)

        assert "beauty" in eliminated
        assert "fitness" not in eliminated
        product = session.query(Product).filter_by(product_id="prod1").first()
        assert product.eliminated is True

    def test_does_not_flag_above_threshold(self, session: Session) -> None:
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        eliminated = flag_eliminated_niches(
            session, "acc1", [("fitness", 0.5)], threshold_score=0.1
        )

        assert eliminated == []
        product = session.query(Product).filter_by(product_id="prod1").first()
        assert product.eliminated is False

    def test_returns_empty_list_when_no_eliminations(self, session: Session) -> None:
        result = flag_eliminated_niches(session, "acc1", [("fitness", 0.9)], threshold_score=0.0)
        assert result == []

    def test_does_not_flag_other_account_products(self, session: Session) -> None:
        """Products from acc2 are not affected when flagging for acc1."""
        session.add(Product(
            id="p1", account_id="acc1", niche="beauty",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.add(Product(
            id="p2", account_id="acc2", niche="beauty",
            product_id="prod2", product_name="Y", product_url="https://y.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        flag_eliminated_niches(session, "acc1", [("beauty", 0.0)], threshold_score=0.1)

        acc2_product = session.query(Product).filter_by(product_id="prod2").first()
        assert acc2_product.eliminated is False

    def test_idempotent_second_call_returns_empty(self, session: Session) -> None:
        """Calling flag_eliminated_niches twice returns [] on the second call."""
        session.add(Product(
            id="p1", account_id="acc1", niche="beauty",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        niche_scores = [("beauty", 0.0)]
        first = flag_eliminated_niches(session, "acc1", niche_scores, threshold_score=0.1)
        second = flag_eliminated_niches(session, "acc1", niche_scores, threshold_score=0.1)

        assert "beauty" in first
        assert second == []  # Already eliminated — not newly flagged


class TestGetCachedProductsExcludesEliminated:

    def test_excludes_eliminated_products(self, session: Session) -> None:
        now = datetime.utcnow()
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="Active Wear", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.8,
            cached_at=now, eliminated=True,
        ))
        session.add(Product(
            id="p2", account_id="acc1", niche="fitness",
            product_id="prod2", product_name="Yoga Mat", product_url="https://y.com",
            commission_rate=0.12, sales_velocity_score=0.7,
            cached_at=now, eliminated=False,
        ))
        session.commit()

        result = get_cached_products(session, account_id="acc1", niche="fitness")

        assert len(result) == 1
        assert result[0].product_id == "prod2"

    def test_returns_all_when_none_eliminated(self, session: Session) -> None:
        now = datetime.utcnow()
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="Gym Gloves", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.6,
            cached_at=now, eliminated=False,
        ))
        session.commit()

        result = get_cached_products(session, account_id="acc1", niche="fitness")
        assert len(result) == 1


class TestGetArchetypeScores:
    """Tests for get_archetype_scores query."""

    def _make_row(self, hook_archetype, avg_ret3, avg_ret15, avg_ctr, cnt):
        row = MagicMock()
        row.hook_archetype = hook_archetype
        row.avg_ret3 = avg_ret3
        row.avg_ret15 = avg_ret15
        row.avg_ctr = avg_ctr
        row.cnt = cnt
        return row

    def _mock_session(self, rows):
        mock_sess = MagicMock()
        (
            mock_sess.query.return_value
            .join.return_value
            .filter.return_value
            .group_by.return_value
            .all.return_value
        ) = rows
        return mock_sess

    def test_returns_empty_dict_when_no_rows(self):
        sess = self._mock_session([])
        result = get_archetype_scores(sess, account_id="acc1")
        assert result == {}

    def test_single_archetype_score_computed_correctly(self):
        # score = 0.50 * 0.6 + 0.30 * 0.4 + 0.20 * 0.1 = 0.3 + 0.12 + 0.02 = 0.44
        row = self._make_row("curiosity_gap", 0.6, 0.4, 0.1, 10)
        sess = self._mock_session([row])
        result = get_archetype_scores(sess, account_id="acc1")
        assert "curiosity_gap" in result
        score, count = result["curiosity_gap"]
        assert abs(score - 0.44) < 1e-6
        assert count == 10

    def test_all_three_archetypes_returned(self):
        rows = [
            self._make_row("curiosity_gap", 0.5, 0.3, 0.05, 8),
            self._make_row("social_proof", 0.6, 0.4, 0.08, 12),
            self._make_row("controversy", 0.4, 0.2, 0.03, 6),
        ]
        sess = self._mock_session(rows)
        result = get_archetype_scores(sess, account_id="acc1")
        assert set(result.keys()) == {"curiosity_gap", "social_proof", "controversy"}

    def test_null_avg_ctr_treated_as_zero(self):
        row = self._make_row("social_proof", 0.5, 0.3, None, 5)
        sess = self._mock_session([row])
        result = get_archetype_scores(sess, account_id="acc1")
        score, _ = result["social_proof"]
        expected = 0.50 * 0.5 + 0.30 * 0.3 + 0.20 * 0.0
        assert abs(score - expected) < 1e-6

    def test_video_count_in_result(self):
        row = self._make_row("controversy", 0.3, 0.2, 0.01, 7)
        sess = self._mock_session([row])
        result = get_archetype_scores(sess, account_id="acc1")
        _, count = result["controversy"]
        assert count == 7


def test_cache_product_upsert_updates_niche(session: Session) -> None:
    """Upserting a product with a changed niche must update the niche field, not create a duplicate."""
    product_v1 = AffiliateProduct(
        product_id="p1", product_name="Widget", product_url="https://u.com",
        commission_rate=0.1, sales_velocity_score=0.5, niche="health"
    )
    product_v2 = AffiliateProduct(
        product_id="p1", product_name="Widget Updated", product_url="https://u.com",
        commission_rate=0.15, sales_velocity_score=0.7, niche="fitness"
    )
    cache_product(session, account_id="acc1", product=product_v1)
    cache_product(session, account_id="acc1", product=product_v2)

    rows = session.query(Product).filter_by(account_id="acc1", product_id="p1").all()
    assert len(rows) == 1, "Upsert must not create duplicate rows"
    assert rows[0].niche == "fitness", "Niche must be updated on upsert"
    assert rows[0].product_name == "Widget Updated"


class TestWriteAgentErrors:
    def _mock_session(self):
        return MagicMock()

    def test_writes_each_error_to_session(self):
        errors = [
            AgentError(agent="production", error_type="RenderError", message="fail"),
            AgentError(agent="script", error_type="LLMError", message="timeout"),
        ]
        sess = self._mock_session()
        write_agent_errors(sess, "acc1", errors)
        assert sess.add.call_count == 2

    def test_empty_errors_no_adds(self):
        sess = self._mock_session()
        write_agent_errors(sess, "acc1", [])
        sess.add.assert_not_called()
        sess.commit.assert_not_called()

    def test_recovery_suggestion_set_on_error_row(self):
        errors = [AgentError(
            agent="monetization",
            error_type="TikTokRateLimitError",
            message="429",
            recovery_suggestion="retry on next cycle",
        )]
        sess = self._mock_session()
        write_agent_errors(sess, "acc1", errors)
        added = sess.add.call_args[0][0]
        assert added.recovery_suggestion == "retry on next cycle"

    def test_maps_all_fields(self):
        errors = [AgentError(
            agent="publishing",
            error_type="TikTokAuthError",
            message="401 Unauthorized",
            video_id="vid_xyz",
            recovery_suggestion="refresh token",
        )]
        sess = self._mock_session()
        write_agent_errors(sess, "acc1", errors)
        added = sess.add.call_args[0][0]
        assert added.agent == "publishing"
        assert added.error_type == "TikTokAuthError"
        assert added.message == "401 Unauthorized"
        assert added.video_id == "vid_xyz"
        assert added.account_id == "acc1"


class TestGetActiveErrors:
    def test_filters_by_account_and_unresolved(self):
        sess = MagicMock()
        sess.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = get_active_errors(sess, "acc1")
        assert result == []
        sess.query.assert_called_once()

    def test_returns_unresolved_rows_only(self, session: Session) -> None:
        session.add(Error(
            account_id="acc1",
            agent="production",
            error_type="RenderError",
            message="render failed",
            resolved_at=None,
        ))
        session.add(Error(
            account_id="acc1",
            agent="publishing",
            error_type="TikTokAuthError",
            message="auth failed",
            resolved_at=datetime.utcnow(),
        ))
        session.commit()
        result = get_active_errors(session, "acc1")
        assert len(result) == 1
        assert result[0].error_type == "RenderError"

    def test_filters_by_account_id(self, session: Session) -> None:
        session.add(Error(
            account_id="acc1",
            agent="script",
            error_type="LLMError",
            message="failed",
            resolved_at=None,
        ))
        session.add(Error(
            account_id="acc2",
            agent="script",
            error_type="LLMError",
            message="failed",
            resolved_at=None,
        ))
        session.commit()
        result = get_active_errors(session, "acc1")
        assert len(result) == 1
        assert result[0].account_id == "acc1"
