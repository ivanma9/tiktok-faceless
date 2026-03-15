"""Tests for Story 6.5 — dashboard/pages/errors.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from dashboard.pages.errors import _plain_message, render_errors_page
from tiktok_faceless.db.models import Error


def _make_error(
    account_id: str = "acc_test",
    agent: str = "production",
    error_type: str = "VideoAssemblyError",
    message: str = "Assembly failed",
    recovery_suggestion: str | None = None,
    resolved_at: datetime | None = None,
    timestamp: datetime | None = None,
) -> Error:
    e = Error(
        account_id=account_id,
        agent=agent,
        error_type=error_type,
        message=message,
        recovery_suggestion=recovery_suggestion,
        resolved_at=resolved_at,
        timestamp=timestamp or datetime.utcnow(),
    )
    return e


def _col_mock():
    col = MagicMock()
    col.__enter__ = MagicMock(return_value=col)
    col.__exit__ = MagicMock(return_value=False)
    return col


# --- _plain_message ---


def test_plain_message_returns_message_field():
    e = _make_error(message="TTS quota exceeded")
    assert _plain_message(e) == "TTS quota exceeded"


# --- render_errors_page ---


@patch("dashboard.pages.errors.get_resolved_errors", return_value=[])
@patch("dashboard.pages.errors.get_unresolved_errors", return_value=[])
@patch("dashboard.pages.errors.st")
def test_render_errors_page_shows_success_when_no_active_errors(mock_st, mock_active, mock_res):
    render_errors_page(MagicMock(), "acc_test")
    args_list = [c.args[0] for c in mock_st.success.call_args_list]
    assert any("No active errors" in a for a in args_list)


@patch("dashboard.pages.errors.get_resolved_errors", return_value=[])
@patch(
    "dashboard.pages.errors.get_unresolved_errors",
    return_value=[_make_error(), _make_error()],
)
@patch("dashboard.pages.errors.st")
def test_render_errors_page_shows_active_errors(mock_st, mock_active, mock_res):
    cols = [_col_mock(), _col_mock(), _col_mock()]
    mock_st.columns.return_value = cols
    render_errors_page(MagicMock(), "acc_test")
    assert mock_st.columns.call_count == 2


@patch(
    "dashboard.pages.errors.get_resolved_errors",
    return_value=[],
)
@patch("dashboard.pages.errors.get_unresolved_errors", return_value=[])
@patch("dashboard.pages.errors.st")
def test_render_errors_page_shows_info_when_no_resolved(mock_st, mock_active, mock_res):
    render_errors_page(MagicMock(), "acc_test")
    args_list = [c.args[0] for c in mock_st.info.call_args_list]
    assert any("No resolved errors" in a for a in args_list)


@patch(
    "dashboard.pages.errors.get_resolved_errors",
    return_value=[_make_error(), _make_error(), _make_error()],
)
@patch("dashboard.pages.errors.get_unresolved_errors", return_value=[])
@patch("dashboard.pages.errors.st")
def test_render_errors_page_shows_resolved_expander(mock_st, mock_active, mock_res):
    expander_mock = MagicMock()
    expander_mock.__enter__ = MagicMock(return_value=expander_mock)
    expander_mock.__exit__ = MagicMock(return_value=False)
    mock_st.expander.return_value = expander_mock
    cols = [_col_mock(), _col_mock(), _col_mock()]
    mock_st.columns.return_value = cols

    render_errors_page(MagicMock(), "acc_test")

    expander_calls = [str(c) for c in mock_st.expander.call_args_list]
    assert any("3" in c for c in expander_calls)


@patch("dashboard.pages.errors.get_resolved_errors", return_value=[])
@patch(
    "dashboard.pages.errors.get_unresolved_errors",
    side_effect=Exception("DB down"),
)
@patch("dashboard.pages.errors.st")
def test_render_errors_page_active_query_failure_shows_error(mock_st, mock_active, mock_res):
    render_errors_page(MagicMock(), "acc_test")
    mock_st.error.assert_called()
    # resolved section still renders
    mock_st.info.assert_called()


@patch(
    "dashboard.pages.errors.get_resolved_errors",
    side_effect=Exception("DB down"),
)
@patch("dashboard.pages.errors.get_unresolved_errors", return_value=[])
@patch("dashboard.pages.errors.st")
def test_render_errors_page_resolved_query_failure_shows_error(mock_st, mock_active, mock_res):
    render_errors_page(MagicMock(), "acc_test")
    mock_st.error.assert_called()
    mock_st.success.assert_called()  # active section rendered above


@patch("dashboard.pages.errors.get_resolved_errors", return_value=[])
@patch("dashboard.pages.errors.get_unresolved_errors", return_value=[])
@patch("dashboard.pages.errors.st")
def test_recovery_suggestion_rendered_when_present(mock_st, mock_active, mock_res):
    error = _make_error(recovery_suggestion="Check API key")
    mock_active.return_value = [error]
    cols = [_col_mock(), _col_mock(), _col_mock()]
    mock_st.columns.return_value = cols

    render_errors_page(MagicMock(), "acc_test")

    caption_calls = [str(c) for c in mock_st.caption.call_args_list]
    assert any("Check API key" in c for c in caption_calls)
