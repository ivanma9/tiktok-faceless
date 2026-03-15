"""Tests for Story 6.5 — dashboard/pages/decisions.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from dashboard.pages.decisions import (
    DECISION_TYPE_LABELS,
    _format_summary,
    render_decisions_page,
)
from tiktok_faceless.db.models import AgentDecision


def _make_decision(
    account_id: str = "acc_test",
    agent: str = "orchestrator",
    decision_type: str = "phase_transition",
    from_value: str | None = "warmup",
    to_value: str | None = "tournament",
    rationale: str = "CTR threshold met",
    supporting_data: str | None = None,
    created_at: datetime | None = None,
) -> AgentDecision:
    d = AgentDecision(
        account_id=account_id,
        agent=agent,
        decision_type=decision_type,
        from_value=from_value,
        to_value=to_value,
        rationale=rationale,
        supporting_data=supporting_data,
        created_at=created_at or datetime.utcnow(),
    )
    return d


# --- DECISION_TYPE_LABELS ---


def test_decision_type_labels_contains_phase_transition():
    assert DECISION_TYPE_LABELS["phase_transition"] == "Phase Transition"


# --- _format_summary ---


def test_format_summary_with_from_to_values():
    d = _make_decision(agent="orchestrator", from_value="warmup", to_value="tournament")
    assert _format_summary(d) == "orchestrator: warmup → tournament"


def test_format_summary_without_from_to_falls_back_to_rationale():
    d = _make_decision(from_value=None, to_value=None, rationale="Picked niche X based on CTR")
    assert _format_summary(d) == "Picked niche X based on CTR"


def test_format_summary_truncates_rationale_at_120_chars():
    long_rationale = "x" * 200
    d = _make_decision(from_value=None, to_value=None, rationale=long_rationale)
    assert len(_format_summary(d)) == 120


# --- render_decisions_page ---


@patch("dashboard.pages.decisions.get_agent_decisions", return_value=[])
@patch("dashboard.pages.decisions.st")
def test_render_decisions_page_shows_info_when_no_decisions(mock_st, mock_query):
    render_decisions_page(MagicMock(), "acc_test")
    mock_st.info.assert_called_once_with("No decisions recorded yet.")


@patch("dashboard.pages.decisions.get_agent_decisions", side_effect=Exception("DB error"))
@patch("dashboard.pages.decisions.st")
def test_render_decisions_page_shows_error_on_query_failure(mock_st, mock_query):
    render_decisions_page(MagicMock(), "acc_test")
    mock_st.error.assert_called_once()


@patch(
    "dashboard.pages.decisions.get_agent_decisions",
    return_value=[
        _make_decision(
            decision_type="custom_action",
            from_value=None,
            to_value=None,
            rationale="some reason",
        )
    ],
)
@patch("dashboard.pages.decisions.st")
def test_unknown_decision_type_falls_back_to_title_case(mock_st, mock_query):
    render_decisions_page(MagicMock(), "acc_test")
    calls = [str(c) for c in mock_st.markdown.call_args_list]
    assert any("Custom Action" in c for c in calls)


@patch(
    "dashboard.pages.decisions.get_agent_decisions",
    return_value=[
        _make_decision(
            decision_type="niche_commit",
            from_value=None,
            to_value=None,
            rationale="done",
            supporting_data='{"score": 0.87}',
        )
    ],
)
@patch("dashboard.pages.decisions.st")
def test_supporting_data_json_rendered_when_present(mock_st, mock_query):
    expander_mock = MagicMock()
    expander_mock.__enter__ = MagicMock(return_value=expander_mock)
    expander_mock.__exit__ = MagicMock(return_value=False)
    mock_st.expander.return_value = expander_mock

    render_decisions_page(MagicMock(), "acc_test")
    mock_st.json.assert_called_once_with({"score": 0.87})


@patch(
    "dashboard.pages.decisions.get_agent_decisions",
    return_value=[
        _make_decision(
            decision_type="niche_commit",
            from_value=None,
            to_value=None,
            rationale="done",
            supporting_data="not-json",
        )
    ],
)
@patch("dashboard.pages.decisions.st")
def test_supporting_data_fallback_to_code_on_invalid_json(mock_st, mock_query):
    expander_mock = MagicMock()
    expander_mock.__enter__ = MagicMock(return_value=expander_mock)
    expander_mock.__exit__ = MagicMock(return_value=False)
    mock_st.expander.return_value = expander_mock

    render_decisions_page(MagicMock(), "acc_test")
    mock_st.code.assert_called_once_with("not-json", language="text")
