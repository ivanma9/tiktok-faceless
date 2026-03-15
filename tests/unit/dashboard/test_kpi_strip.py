"""Tests for Story 6.3 KPI strip component functions."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from dashboard.components.kpi_strip import (
    build_kpi_cards,
    format_delta,
    format_kpi_value,
    render_freshness,
)

# --- format_kpi_value ---


def test_format_kpi_value_none_returns_dash():
    assert format_kpi_value(None, "%") == "\u2014"


def test_format_kpi_value_revenue():
    assert format_kpi_value(1234.5, "$") == "$1,234.50"


def test_format_kpi_value_percentage():
    assert format_kpi_value(0.756, "%") == "75.6%"


# --- format_delta ---


def test_format_delta_none_returns_empty():
    assert format_delta(None, "%") == ""


def test_format_delta_positive_revenue():
    assert format_delta(25.0, "$") == "+$25.00"


def test_format_delta_negative_pct():
    assert format_delta(-0.05, "%") == "-5.0%"


# --- build_kpi_cards ---


@patch("dashboard.components.kpi_strip.get_kpi_revenue", return_value=100.0)
@patch("dashboard.components.kpi_strip.get_kpi_retention_3s", return_value=0.6)
@patch("dashboard.components.kpi_strip.get_kpi_retention_15s", return_value=0.4)
@patch("dashboard.components.kpi_strip.get_kpi_affiliate_ctr", return_value=0.05)
@patch("dashboard.components.kpi_strip.get_kpi_fyp_reach_rate", return_value=0.5)
@patch("dashboard.components.kpi_strip.get_kpi_sparkline", return_value=[0.0] * 7)
def test_build_kpi_cards_returns_five_cards(
    mock_spark, mock_fyp, mock_ctr, mock_ret15, mock_ret3, mock_rev
):
    session = MagicMock()
    # Stub out session.query chain for prior window
    mock_result = MagicMock()
    mock_result.scalar.return_value = None
    mock_result.first.return_value = MagicMock(clicks=None, views=0, total=None)
    session.query.return_value.filter.return_value.scalar.return_value = None
    session.query.return_value.filter.return_value.first.return_value = MagicMock(
        clicks=None, views=0
    )
    cards = build_kpi_cards(session, "acc1")
    assert len(cards) == 5


@patch("dashboard.components.kpi_strip.get_kpi_revenue", return_value=0.0)
@patch("dashboard.components.kpi_strip.get_kpi_retention_3s", return_value=0.6)
@patch("dashboard.components.kpi_strip.get_kpi_retention_15s", return_value=0.4)
@patch("dashboard.components.kpi_strip.get_kpi_affiliate_ctr", return_value=0.5)
@patch("dashboard.components.kpi_strip.get_kpi_fyp_reach_rate", return_value=0.5)
@patch("dashboard.components.kpi_strip.get_kpi_sparkline", return_value=[0.0] * 7)
def test_build_kpi_cards_computes_delta(
    mock_spark, mock_fyp, mock_ctr, mock_ret15, mock_ret3, mock_rev
):
    session = MagicMock()
    # Stub prior window queries: return 0.5 for retention_3s via avg
    session.query.return_value.filter.return_value.scalar.return_value = 0.5
    session.query.return_value.filter.return_value.first.return_value = MagicMock(
        clicks=None, views=0
    )
    cards = build_kpi_cards(session, "acc1")
    # 3s retention card is index 1; current=0.6, prior=0.5 → delta=0.1
    ret3_card = cards[1]
    assert ret3_card.delta is not None
    assert abs(ret3_card.delta - 0.1) < 1e-6


# --- render_freshness ---


@patch("dashboard.components.kpi_strip.st")
def test_render_freshness_amber_at_7_minutes(mock_st):
    last_recorded_at = datetime.utcnow() - timedelta(minutes=7)
    render_freshness(last_recorded_at)
    mock_st.markdown.assert_called_once()
    call_arg = mock_st.markdown.call_args[0][0]
    assert ":orange[" in call_arg
    assert "7m ago" in call_arg


@patch("dashboard.components.kpi_strip.st")
def test_render_freshness_rose_at_20_minutes(mock_st):
    last_recorded_at = datetime.utcnow() - timedelta(minutes=20)
    render_freshness(last_recorded_at)
    mock_st.markdown.assert_called_once()
    call_arg = mock_st.markdown.call_args[0][0]
    assert ":red[" in call_arg
    assert "20m ago" in call_arg


@patch("dashboard.components.kpi_strip.st")
def test_render_freshness_none_renders_nothing(mock_st):
    render_freshness(None)
    mock_st.markdown.assert_not_called()
    mock_st.caption.assert_not_called()
