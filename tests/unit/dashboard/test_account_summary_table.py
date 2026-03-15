"""Tests for account_summary_table component — Story 7.3."""

import sys
from datetime import timedelta
from unittest.mock import MagicMock

# Mock streamlit before importing component
sys.modules["streamlit"] = MagicMock()
import streamlit as st  # noqa: E402

from dashboard.components.account_summary_table import (  # noqa: E402
    _format_timedelta,
    _phase_badge,
    render_account_summary_table,
)

_EMPTY_SUMMARY = {
    "account_id": "acc1",
    "phase": "warmup",
    "pipeline_healthy": True,
    "revenue_today": 0.0,
    "last_post_timedelta": None,
}

_SUMMARY_2 = {
    "account_id": "acc2",
    "phase": "commit",
    "pipeline_healthy": False,
    "revenue_today": 5.0,
    "last_post_timedelta": timedelta(hours=1),
}


def setup_function():
    st.reset_mock()


def test_render_account_summary_table_calls_subheader():
    render_account_summary_table([])
    st.subheader.assert_called_once_with("Portfolio Overview")


def test_render_account_summary_table_one_row_per_summary():
    render_account_summary_table([_EMPTY_SUMMARY, _SUMMARY_2])
    assert st.columns.call_count == 2


def test_phase_badge_indigo_for_commit():
    result = _phase_badge("commit")
    assert "#6366f1" in result


def test_phase_badge_indigo_for_scale():
    result = _phase_badge("scale")
    assert "#6366f1" in result


def test_phase_badge_amber_for_tournament():
    result = _phase_badge("tournament")
    assert "#f59e0b" in result


def test_phase_badge_zinc_for_warmup():
    result = _phase_badge("warmup")
    assert "#71717a" in result


def test_format_timedelta_none_returns_never():
    assert _format_timedelta(None) == "Never"


def test_format_timedelta_hours_and_minutes():
    assert _format_timedelta(timedelta(hours=3, minutes=12)) == "3h 12m ago"


def test_format_timedelta_under_one_minute():
    assert _format_timedelta(timedelta(seconds=45)) == "just now"
