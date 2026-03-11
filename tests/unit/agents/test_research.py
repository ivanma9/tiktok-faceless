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
