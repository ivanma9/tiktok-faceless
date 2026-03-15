"""
Unit tests for compute_fyp_reach_rate — Story 4.3: Shadowban & FYP Reach Monitoring.
"""

from unittest.mock import MagicMock

import pytest

from tiktok_faceless.utils.suppression import compute_fyp_reach_rate

_MOD = "tiktok_faceless.utils.suppression"


def _mock_session_with_rows(fyp_values: list[float]) -> MagicMock:
    """Build mock session returning VideoMetric rows with given fyp_reach_pct values."""
    rows = []
    for v in fyp_values:
        row = MagicMock()
        row.fyp_reach_pct = v
        rows.append(row)
    mock_sess = MagicMock()
    (
        mock_sess.query.return_value
        .filter_by.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = rows
    return mock_sess


class TestComputeFypReachRate:
    def test_returns_average_of_last_n_rows(self) -> None:
        sess = _mock_session_with_rows([0.6, 0.8, 1.0])
        result = compute_fyp_reach_rate(sess, account_id="acc1", window=3)
        assert result == pytest.approx(0.8)

    def test_returns_1_0_when_no_rows(self) -> None:
        sess = _mock_session_with_rows([])
        result = compute_fyp_reach_rate(sess, account_id="acc1", window=10)
        assert result == 1.0

    def test_window_limits_query(self) -> None:
        sess = _mock_session_with_rows([0.5])
        compute_fyp_reach_rate(sess, account_id="acc1", window=7)
        limit_mock = sess.query.return_value.filter_by.return_value.order_by.return_value.limit
        limit_mock.assert_called_once_with(7)

    def test_single_row_returns_exact_value(self) -> None:
        sess = _mock_session_with_rows([0.5])
        result = compute_fyp_reach_rate(sess, account_id="acc1", window=10)
        assert result == pytest.approx(0.5)
