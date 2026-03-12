"""Tests for tiktok_faceless/agents/monetization.py — monetization_node."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.monetization import monetization_node
from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.models.shop import CommissionRecord
from tiktok_faceless.state import AgentError, PipelineState

_MOD = "tiktok_faceless.agents.monetization"

_PRODUCT = {
    "product_id": "prod_abc",
    "product_name": "Widget Pro",
    "product_url": "https://example.com/widget",
    "commission_rate": 0.15,
    "niche": "health",
    "sales_velocity_score": 0.8,
}


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok_123"
    cfg.tiktok_open_id = "open_123"
    return cfg


def _mock_session() -> MagicMock:
    mock_session_obj = MagicMock()
    first = mock_session_obj.query.return_value.filter_by.return_value.order_by.return_value.first
    first.return_value = None
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


class TestMonetizationNodeGuards:
    def test_missing_product_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=None)
        result = monetization_node(state)
        assert "errors" in result
        err = result["errors"][0]
        assert isinstance(err, AgentError)
        assert err.agent == "monetization"
        assert err.error_type == "MissingProduct"
        assert "product_validated" not in result


class TestMonetizationNodeSuccess:
    def test_returns_product_validated_true(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.monetization.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.monetization.TikTokAPIClient") as mock_tk_cls:
                mock_tk = MagicMock()
                mock_tk.generate_affiliate_link.return_value = "https://shop.tiktok.com/aff/123"
                mock_tk.get_affiliate_orders.return_value = []
                mock_tk_cls.return_value = mock_tk

                with patch(
                    "tiktok_faceless.agents.monetization.get_session",
                    return_value=_mock_session(),
                ):
                    result = monetization_node(state)

        assert result["product_validated"] is True
        assert "errors" not in result


class TestMonetizationNodeErrors:
    def test_tiktok_api_error_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.monetization.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.monetization.TikTokAPIClient") as mock_tk_cls:
                mock_tk = MagicMock()
                mock_tk.generate_affiliate_link.side_effect = TikTokAPIError("500 Server Error")
                mock_tk_cls.return_value = mock_tk

                result = monetization_node(state)

        assert "errors" in result
        assert result["errors"][0].error_type == "TikTokAPIError"
        assert "product_validated" not in result

    def test_tiktok_rate_limit_error_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.monetization.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.monetization.TikTokAPIClient") as mock_tk_cls:
                mock_tk = MagicMock()
                mock_tk.generate_affiliate_link.side_effect = TikTokRateLimitError("429 Too Many")
                mock_tk_cls.return_value = mock_tk

                result = monetization_node(state)

        assert "errors" in result
        assert result["errors"][0].error_type == "TikTokRateLimitError"

    def test_tiktok_auth_error_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.monetization.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.monetization.TikTokAPIClient") as mock_tk_cls:
                mock_tk = MagicMock()
                mock_tk.generate_affiliate_link.side_effect = TikTokAuthError("401 Unauthorized")
                mock_tk_cls.return_value = mock_tk

                result = monetization_node(state)

        assert "errors" in result
        assert result["errors"][0].error_type == "TikTokAuthError"


_BASE_STATE = PipelineState(
    account_id="acc1",
    selected_product={
        "product_id": "prod1",
        "product_name": "Widget",
        "product_url": "https://example.com/widget",
        "commission_rate": 0.10,
        "sales_velocity_score": 0.8,
        "niche": "fitness",
    },
    affiliate_commission_week=0.0,
)


def _make_orders(amounts: list[float]) -> list[CommissionRecord]:
    return [
        CommissionRecord(order_id=f"ord{i}", product_id="prod1", commission_amount=a)
        for i, a in enumerate(amounts)
    ]


class TestCommissionPolling:
    def _run(
        self,
        state: PipelineState,
        orders: list[CommissionRecord] | Exception,
    ) -> dict[str, Any]:
        """Helper: run monetization_node with mocked affiliate link + orders response."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=_mock_session()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.generate_affiliate_link.return_value = "https://affiliate.link/x"
            if isinstance(orders, Exception):
                mock_client.get_affiliate_orders.side_effect = orders
            else:
                mock_client.get_affiliate_orders.return_value = orders
            mock_client_cls.return_value = mock_client
            return monetization_node(state)

    def test_updates_affiliate_commission_week_when_orders_returned(self) -> None:
        """affiliate_commission_week is set to sum of commission_amount from orders."""
        orders = _make_orders([4.50, 2.00])
        result = self._run(_BASE_STATE, orders)

        assert result["product_validated"] is True
        assert result["affiliate_commission_week"] == pytest.approx(6.50)

    def test_sets_zero_when_no_orders(self) -> None:
        """affiliate_commission_week is 0.0 when orders list is empty."""
        result = self._run(_BASE_STATE, [])

        assert result["affiliate_commission_week"] == pytest.approx(0.0)

    def test_preserves_existing_commission_on_api_error(self) -> None:
        """When get_affiliate_orders raises, affiliate_commission_week is absent from delta."""
        state = PipelineState(
            account_id="acc1",
            selected_product=_BASE_STATE.selected_product,
            affiliate_commission_week=12.34,
        )
        result = self._run(state, Exception("network error"))

        assert "affiliate_commission_week" not in result
        assert result["product_validated"] is True

    def test_continues_pipeline_on_commission_polling_failure(self) -> None:
        """monetization_node always returns product_validated=True even if polling fails."""
        result = self._run(_BASE_STATE, RuntimeError("TikTok Shop down"))

        assert result["product_validated"] is True
        assert "errors" not in result

    def test_commission_polling_does_not_interfere_with_link_generation(self) -> None:
        """product_validated is True and affiliate_commission_week is present on happy path."""
        orders = _make_orders([1.00])
        result = self._run(_BASE_STATE, orders)

        assert result["product_validated"] is True
        assert result["affiliate_commission_week"] == pytest.approx(1.00)

    def test_video_query_filters_unassigned_product_id(self) -> None:
        """monetization_node must filter Video query to product_id IS NULL (orphan safety)."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session") as mock_get_session,
        ):
            mock_client = MagicMock()
            mock_client.generate_affiliate_link.return_value = "https://affiliate.link/x"
            mock_client.get_affiliate_orders.return_value = []
            mock_client_cls.return_value = mock_client

            # Build a mock session that records filter calls
            mock_session_obj = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_get_session.return_value = mock_ctx

            # Chain: query -> filter_by -> filter -> order_by -> first -> None
            query_chain = mock_session_obj.query.return_value
            filter_by_chain = query_chain.filter_by.return_value
            filter_chain = filter_by_chain.filter.return_value
            filter_chain.order_by.return_value.first.return_value = None

            monetization_node(state)

        # Verify .filter() was called (for product_id IS NULL)
        filter_by_chain.filter.assert_called_once()

    def test_missing_product_returns_error_without_polling(self) -> None:
        """MissingProduct error is returned immediately — commission polling never runs."""
        state = PipelineState(account_id="acc1", selected_product=None)
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            result = monetization_node(state)

        mock_client.get_affiliate_orders.assert_not_called()
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingProduct"
