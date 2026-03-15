"""Tests for Story 6.6 — milestone banner render functions."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from dashboard.components.milestone_banner import (
    _FIRST_COMMISSION_SESSION_KEY,
    _MILESTONE_1K_SESSION_KEY,
    render_first_commission_banner,
    render_milestone_1k_banner,
    render_phase_transition_banner,
)
from tiktok_faceless.db.models import AgentDecision


def _make_decision(from_value="warmup", to_value="tournament", rationale="Winner detected",
                   decision_id=1):
    d = MagicMock(spec=AgentDecision)
    d.id = decision_id
    d.from_value = from_value
    d.to_value = to_value
    d.rationale = rationale
    d.decision_type = "phase_transition"
    d.account_id = "acc1"
    d.created_at = datetime.utcnow()
    return d


# --- render_first_commission_banner ---


def test_render_first_commission_banner_skipped_when_dismissed():
    with patch("dashboard.components.milestone_banner.st") as mock_st:
        mock_st.session_state = {_FIRST_COMMISSION_SESSION_KEY: True}
        render_first_commission_banner(5.00)
        mock_st.markdown.assert_not_called()


def test_render_first_commission_banner_shows_amount():
    with patch("dashboard.components.milestone_banner.st") as mock_st:
        mock_st.session_state = {}
        mock_st.button.return_value = False
        render_first_commission_banner(12.50)
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args[0][0]
        assert "$12.50" in call_args


# --- render_milestone_1k_banner ---


def test_render_milestone_1k_banner_skipped_when_dismissed():
    with patch("dashboard.components.milestone_banner.st") as mock_st:
        mock_st.session_state = {_MILESTONE_1K_SESSION_KEY: True}
        render_milestone_1k_banner()
        mock_st.markdown.assert_not_called()


# --- render_phase_transition_banner ---


def test_render_phase_transition_banner_shows_from_to_values():
    decision = _make_decision(from_value="warmup", to_value="tournament",
                              rationale="Winner detected")
    with patch("dashboard.components.milestone_banner.st") as mock_st:
        mock_st.session_state = {}
        mock_st.button.return_value = False
        render_phase_transition_banner(decision)
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args[0][0]
        assert "warmup → tournament" in call_args
