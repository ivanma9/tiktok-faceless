"""Tests for tiktok_faceless/agents/monetization.py — monetization_node."""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.monetization import monetization_node
from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.db.models import Error
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
    cfg.reconciliation_interval_hours = 24
    cfg.commission_discrepancy_tolerance = 0.10
    return cfg


def _mock_session() -> MagicMock:
    mock_session_obj = MagicMock()
    first = mock_session_obj.query.return_value.filter_by.return_value.order_by.return_value.first
    first.return_value = None
    # Support reconciliation path: query(VideoMetric).filter(...).all() → []
    mock_session_obj.query.return_value.filter.return_value.all.return_value = []
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
        result = self._run(state, TikTokAPIError("network error"))

        assert "affiliate_commission_week" not in result
        assert result["product_validated"] is True

    def test_continues_pipeline_on_commission_polling_failure(self) -> None:
        """monetization_node always returns product_validated=True even if polling fails."""
        result = self._run(_BASE_STATE, TikTokRateLimitError("TikTok Shop down"))

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


def _mock_order(commission_amount: float = 10.0):
    o = MagicMock()
    o.commission_amount = commission_amount
    o.order_id = "ord1"
    o.product_id = "prod1"
    return o


class TestCommissionReconciliation:
    """Tests for Story 4.5 reconciliation logic."""

    def _make_state(self, last_reconciliation_at: float = 0.0):
        return PipelineState(
            account_id="acc1",
            last_reconciliation_at=last_reconciliation_at,
            selected_product={"product_id": "prod1"},
        )

    def _mock_session(self):
        mock_ctx = MagicMock()
        mock_sess = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_sess)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx, mock_sess

    def _run(self, state, orders=None, raise_error=None):
        if orders is None:
            orders = [_mock_order()]
        mock_ctx, mock_sess = self._mock_session()
        mock_client = MagicMock()
        if raise_error:
            mock_client.get_affiliate_orders.side_effect = raise_error
        else:
            mock_client.get_affiliate_orders.return_value = orders
        mock_client.generate_affiliate_link.return_value = "https://link"

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.time") as mock_time,
        ):
            mock_time.time.return_value = 99999.0
            result = monetization_node(state)
        return result, mock_sess, mock_client

    def test_reconciliation_runs_when_interval_elapsed(self):
        """last_reconciliation_at=0.0 → interval elapsed → reconciliation runs."""
        state = self._make_state(last_reconciliation_at=0.0)
        result, _, mock_client = self._run(state)
        mock_client.get_affiliate_orders.assert_called_once()
        assert "last_reconciliation_at" in result

    def test_reconciliation_skipped_when_interval_not_elapsed(self):
        """last_reconciliation_at=now → interval not elapsed → skip."""
        state = self._make_state(last_reconciliation_at=99999.0)  # same as mock time
        result, _, mock_client = self._run(state)
        mock_client.get_affiliate_orders.assert_not_called()
        assert "last_reconciliation_at" not in result

    def test_affiliate_commission_week_updated_on_success(self):
        state = self._make_state()
        orders = [_mock_order(5.0), _mock_order(3.0)]
        result, _, _ = self._run(state, orders=orders)
        assert result.get("affiliate_commission_week") == pytest.approx(8.0)

    def test_api_error_skips_cycle_preserves_timestamp(self):
        """TikTokAPIError → last_reconciliation_at NOT updated."""
        state = self._make_state()
        result, _, _ = self._run(state, raise_error=TikTokAPIError("fail"))
        assert "last_reconciliation_at" not in result
        assert "affiliate_commission_week" not in result

    def test_auth_error_skips_cycle(self):
        """TikTokAuthError → same non-fatal skip behavior."""
        state = self._make_state()
        result, _, _ = self._run(state, raise_error=TikTokAuthError("auth"))
        assert "last_reconciliation_at" not in result

    def test_discrepancy_above_tolerance_writes_error_row(self):
        """High discrepancy → Error row written."""
        state = self._make_state()
        # 10 orders, 0 system clicks → 100% discrepancy > 10% tolerance
        orders = [_mock_order() for _ in range(10)]
        mock_metric = MagicMock()
        mock_metric.affiliate_clicks = 0
        mock_metric.recorded_at = datetime.utcnow()
        mock_metric.account_id = "acc1"

        link_ctx = MagicMock()
        link_sess = MagicMock()
        link_ctx.__enter__ = MagicMock(return_value=link_sess)
        link_ctx.__exit__ = MagicMock(return_value=False)

        rec_ctx = MagicMock()
        rec_sess = MagicMock()
        rec_ctx.__enter__ = MagicMock(return_value=rec_sess)
        rec_ctx.__exit__ = MagicMock(return_value=False)
        rec_sess.query.return_value.filter.return_value.all.return_value = [mock_metric]

        mock_client = MagicMock()
        mock_client.generate_affiliate_link.return_value = "https://link"
        mock_client.get_affiliate_orders.return_value = orders

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", side_effect=[link_ctx, rec_ctx]),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.time") as mock_time,
        ):
            mock_time.time.return_value = 99999.0
            monetization_node(state)

        rec_sess.add.assert_called()
        added = rec_sess.add.call_args[0][0]
        assert added.error_type == "commission_discrepancy"

    def test_discrepancy_within_tolerance_no_error_row(self):
        """Low discrepancy → no Error row."""
        state = self._make_state()
        orders = [_mock_order()]  # 1 order
        mock_metric = MagicMock()
        mock_metric.affiliate_clicks = 1  # 1 click, 1 order → 0% diff
        mock_metric.recorded_at = datetime.utcnow()
        mock_metric.account_id = "acc1"

        link_ctx = MagicMock()
        link_sess = MagicMock()
        link_ctx.__enter__ = MagicMock(return_value=link_sess)
        link_ctx.__exit__ = MagicMock(return_value=False)

        rec_ctx = MagicMock()
        rec_sess = MagicMock()
        rec_ctx.__enter__ = MagicMock(return_value=rec_sess)
        rec_ctx.__exit__ = MagicMock(return_value=False)
        rec_sess.query.return_value.filter.return_value.all.return_value = [mock_metric]

        mock_client = MagicMock()
        mock_client.generate_affiliate_link.return_value = "https://link"
        mock_client.get_affiliate_orders.return_value = orders

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", side_effect=[link_ctx, rec_ctx]),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.time") as mock_time,
        ):
            mock_time.time.return_value = 99999.0
            monetization_node(state)

        # Check no Error row added to reconciliation session
        for call in rec_sess.add.call_args_list:
            obj = call[0][0]
            assert not isinstance(obj, Error)


class TestRecoverySuggestions:
    def test_missing_product_has_recovery_suggestion(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=None)
        result = monetization_node(state)
        err = result["errors"][0]
        assert err.recovery_suggestion is not None
        assert "research" in err.recovery_suggestion.lower()

    def test_rate_limit_error_has_recovery_suggestion(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_cls,
        ):
            mock_tk = MagicMock()
            mock_tk.generate_affiliate_link.side_effect = TikTokRateLimitError("429")
            mock_cls.return_value = mock_tk
            result = monetization_node(state)
        err = result["errors"][0]
        assert err.recovery_suggestion is not None
        assert err.recovery_suggestion != ""
