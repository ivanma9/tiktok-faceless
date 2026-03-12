"""Tests for tiktok_faceless/agents/orchestrator.py — orchestrator_node."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.orchestrator import orchestrator_node
from tiktok_faceless.state import AgentError, PipelineState


def _mock_session() -> MagicMock:
    mock_session_obj = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


class TestOrchestratorNodeCleanState:
    def test_clean_state_returns_empty_dict(self) -> None:
        state = PipelineState(account_id="acc1")
        result = orchestrator_node(state)
        assert result == {}

    def test_already_published_returns_empty_dict(self) -> None:
        state = PipelineState(account_id="acc1", published_video_id="vid_123")
        result = orchestrator_node(state)
        assert result == {}


class TestOrchestratorNodeErrors:
    def test_errors_updates_agent_health(self) -> None:
        err = AgentError(agent="script", error_type="LLMError", message="timeout")
        state = PipelineState(account_id="acc1", errors=[err])

        with patch(
            "tiktok_faceless.agents.orchestrator.get_session",
            return_value=_mock_session(),
        ):
            result = orchestrator_node(state)

        assert "agent_health" in result
        assert result["agent_health"]["script"] is False

    def test_errors_persisted_to_db(self) -> None:
        err = AgentError(agent="production", error_type="RenderError", message="failed")
        state = PipelineState(account_id="acc1", errors=[err])

        mock_ctx = _mock_session()
        with patch(
            "tiktok_faceless.agents.orchestrator.get_session",
            return_value=mock_ctx,
        ):
            orchestrator_node(state)

        mock_session_obj = mock_ctx.__enter__.return_value
        assert mock_session_obj.add.called

    def test_multiple_errors_all_agents_marked_unhealthy(self) -> None:
        errors = [
            AgentError(agent="script", error_type="LLMError", message="e1"),
            AgentError(agent="monetization", error_type="TikTokAPIError", message="e2"),
        ]
        state = PipelineState(account_id="acc1", errors=errors)

        with patch(
            "tiktok_faceless.agents.orchestrator.get_session",
            return_value=_mock_session(),
        ):
            result = orchestrator_node(state)

        assert result["agent_health"]["script"] is False
        assert result["agent_health"]["monetization"] is False
