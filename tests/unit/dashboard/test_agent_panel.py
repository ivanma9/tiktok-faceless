"""Tests for Story 6.4 agent panel component."""

from unittest.mock import MagicMock, patch

from dashboard.components.agent_panel import (
    AGENT_ORDER,
    _agent_status,
    render_agent_panel,
)

# --- _agent_status ---


def test_agent_status_healthy_when_in_health_map_true():
    health_map = {"orchestrator": True}
    status_key, _ = _agent_status(health_map, "orchestrator")
    assert status_key == "healthy"


def test_agent_status_error_when_in_health_map_false():
    health_map = {"research": False}
    status_key, _ = _agent_status(health_map, "research")
    assert status_key == "error"


def test_agent_status_waiting_when_absent_from_health_map():
    health_map = {}
    status_key, _ = _agent_status(health_map, "orchestrator")
    assert status_key == "waiting"


# --- render_agent_panel ---


@patch("dashboard.components.agent_panel.get_agent_health_from_errors", return_value={})
@patch("dashboard.components.agent_panel.st")
def test_render_agent_panel_renders_six_rows(mock_st, mock_health):
    col_mock = MagicMock()
    col_mock.__enter__ = MagicMock(return_value=col_mock)
    col_mock.__exit__ = MagicMock(return_value=False)
    mock_st.columns.return_value = (col_mock, col_mock)

    session = MagicMock()
    render_agent_panel(session, "acc_test")

    # One st.columns([0.08, 0.92]) call per agent
    assert mock_st.columns.call_count == len(AGENT_ORDER)


@patch(
    "dashboard.components.agent_panel.get_agent_health_from_errors",
    side_effect=Exception("DB down"),
)
@patch("dashboard.components.agent_panel.st")
def test_render_agent_panel_handles_exception_gracefully(mock_st, mock_health):
    session = MagicMock()
    render_agent_panel(session, "acc_test")
    mock_st.error.assert_called_once()
