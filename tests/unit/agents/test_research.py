"""Tests for tiktok_faceless/agents/research.py — research_node (Story 2.1)."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.research import research_node
from tiktok_faceless.models.shop import AffiliateProduct
from tiktok_faceless.state import AgentError, PipelineState

_PRODUCT = AffiliateProduct(
    product_id="p1",
    product_name="Widget Pro",
    product_url="https://shop.tiktok.com/p1",
    commission_rate=0.15,
    sales_velocity_score=0.8,
    niche="health",
)

_PRODUCT_WITH_VIDEO = AffiliateProduct(
    product_id="p1",
    product_name="Widget Pro",
    product_url="https://shop.tiktok.com/p1",
    commission_rate=0.15,
    sales_velocity_score=0.8,
    niche="health",
    top_video_id="vid_abc123",
)

_STATE = PipelineState(
    account_id="acc1",
    phase="commit",
    committed_niche="health",
)

_MOD = "tiktok_faceless.agents.research"


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok"
    cfg.tiktok_open_id = "oid"
    cfg.min_commission_rate = 0.05
    cfg.min_sales_velocity = 0.3
    return cfg


def _mock_session_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=MagicMock())
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestResearchNodeSuccess:
    def test_sets_selected_product_and_validated(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["product_id"] == "p1"
        assert "errors" not in result

    def test_uses_cache_when_within_ttl(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[_PRODUCT]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        mock_client.get_validated_products.assert_not_called()
        assert result["product_validated"] is True


class TestResearchNodeNoProducts:
    def test_returns_agent_error_when_no_validated_products(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = []
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result.get("product_validated") is False
        assert "errors" in result
        assert isinstance(result["errors"][0], AgentError)
        assert result["errors"][0].agent == "research"
        assert result["errors"][0].recovery_suggestion is not None

    def test_no_committed_niche_returns_error(self) -> None:
        state = PipelineState(account_id="acc1", phase="commit", committed_niche=None)
        with patch(f"{_MOD}.load_account_config", return_value=_mock_config()):
            result = research_node(state)
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingNiche"


class TestCommentMining:
    def test_buyer_language_added_to_selected_product(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT_WITH_VIDEO]
            mock_client.get_video_comments.return_value = ["where can I get this", "does it work"]
            mock_client_cls.return_value = mock_client
            result = research_node(_STATE)

        assert "buyer_language" in result["selected_product"]
        assert len(result["selected_product"]["buyer_language"]) == 2

    def test_comment_mining_skipped_when_no_top_video_id(self) -> None:
        """get_video_comments is NOT called when product.top_video_id is None."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client_cls.return_value = mock_client
            result = research_node(_STATE)

        mock_client.get_video_comments.assert_not_called()
        assert result["selected_product"]["buyer_language"] == []

    def test_empty_comments_does_not_halt_pipeline(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["buyer_language"] == []
        assert "errors" not in result


class TestTournamentMode:
    def test_scans_all_candidate_niches(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=["health", "fitness"],
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert mock_client.get_validated_products.call_count == 2
        assert result["product_validated"] is True

    def test_picks_highest_score_across_niches(self) -> None:
        low = AffiliateProduct(
            product_id="p_low", product_name="Low", product_url="u",
            commission_rate=0.1, sales_velocity_score=0.4, niche="fitness"
        )
        high = AffiliateProduct(
            product_id="p_high", product_name="High", product_url="u",
            commission_rate=0.2, sales_velocity_score=0.9, niche="health"
        )
        state = PipelineState(
            account_id="acc1", phase="tournament", candidate_niches=["health", "fitness"]
        )
        call_count = 0
        def side_effect(**kwargs: object) -> list[AffiliateProduct]:
            nonlocal call_count
            call_count += 1
            return [high] if call_count == 1 else [low]

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = side_effect
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert result["selected_product"]["product_id"] == "p_high"

    def test_commit_mode_ignores_candidate_niches(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            candidate_niches=["fitness"],  # should be ignored
            committed_niche="health",
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            research_node(state)

        call_niches = [
            call.kwargs.get("niche") or call.args[1]
            for call in mock_client.get_validated_products.call_args_list
        ]
        assert "fitness" not in call_niches
        assert "health" in call_niches

    def test_empty_candidate_niches_returns_error(self) -> None:
        state = PipelineState(
            account_id="acc1", phase="tournament", candidate_niches=[]
        )
        with patch(f"{_MOD}.load_account_config", return_value=_mock_config()):
            result = research_node(state)
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingNiche"

    def test_live_api_path_picks_highest_score_not_first(self) -> None:
        """When API returns unsorted products, live path must pick highest score."""
        import pytest
        low = AffiliateProduct(
            product_id="p_low", product_name="Low", product_url="u",
            commission_rate=0.1, sales_velocity_score=0.2, niche="health"
        )
        high = AffiliateProduct(
            product_id="p_high", product_name="High", product_url="u",
            commission_rate=0.2, sales_velocity_score=0.9, niche="health"
        )
        state = PipelineState(
            account_id="acc1", phase="tournament", candidate_niches=["health"]
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            # Return low first, high second — deliberately unsorted
            mock_client.get_validated_products.return_value = [low, high]
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert result["selected_product"]["product_id"] == "p_high"
        assert result["selected_product"]["sales_velocity_score"] == pytest.approx(0.9)

    def test_one_niche_failure_does_not_block_others(self) -> None:
        from tiktok_faceless.clients import TikTokAPIError
        state = PipelineState(
            account_id="acc1", phase="tournament", candidate_niches=["health", "fitness"]
        )
        call_count = 0
        def side_effect(**kwargs: object) -> list[AffiliateProduct]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TikTokAPIError("niche 1 failed")
            return [_PRODUCT]

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = side_effect
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert result["product_validated"] is True
        assert "errors" not in result


class TestDecayDetection:
    def test_alert_set_after_two_consecutive_intervals(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=1,  # already had one detection
        )
        mock_cfg = _mock_config()
        mock_cfg.decay_threshold = 0.001
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_cfg),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.0001),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)
        assert result.get("niche_decay_alert") is True
        assert result.get("consecutive_decay_count") == 2

    def test_no_alert_on_first_detection(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=0,
        )
        mock_cfg = _mock_config()
        mock_cfg.decay_threshold = 0.001
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_cfg),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.0001),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)
        assert result.get("niche_decay_alert") is not True
        assert result.get("consecutive_decay_count") == 1

    def test_counter_resets_when_above_threshold(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=1,
        )
        mock_cfg = _mock_config()
        mock_cfg.decay_threshold = 0.001
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_cfg),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.01),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)
        assert result.get("niche_decay_alert") is not True
        assert result.get("consecutive_decay_count") == 0

    def test_decay_alert_cleared_on_recovery(self) -> None:
        """niche_decay_alert must be explicitly set to False when cpv recovers above threshold."""
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=1,
            niche_decay_alert=True,  # previously fired
        )
        mock_cfg = _mock_config()
        mock_cfg.decay_threshold = 0.001
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_cfg),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.01),  # above threshold
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert result.get("niche_decay_alert") is False
        assert result.get("consecutive_decay_count") == 0

    def test_decay_skipped_in_tournament_phase(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=["health"],
        )
        with (
            patch(
                "tiktok_faceless.agents.research.load_account_config",
                return_value=_mock_config(),
            ),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view") as mock_cpv,
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            research_node(state)
        mock_cpv.assert_not_called()

    def test_rate_limit_errors_surfaced_in_no_products_message(self) -> None:
        """When all niches are rate-limited, error message must mention rate limiting."""
        from tiktok_faceless.clients import TikTokRateLimitError
        state = PipelineState(
            account_id="acc1", phase="tournament", candidate_niches=["health", "fitness"]
        )
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.side_effect = TikTokRateLimitError("rate limited")
            mock_client_cls.return_value = mock_client
            result = research_node(state)

        assert "errors" in result
        assert "rate" in result["errors"][0].message.lower()
