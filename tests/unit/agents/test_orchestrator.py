"""Tests for tiktok_faceless/agents/orchestrator.py — orchestrator_node."""

import time
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.orchestrator import orchestrator_node
from tiktok_faceless.db.models import AgentDecision
from tiktok_faceless.state import AgentError, PipelineState

_MOD = "tiktok_faceless.agents.orchestrator"


@pytest.fixture(autouse=True)
def _patch_pause_helpers():
    """Patch pause/resume DB helpers so orchestrator tests don't hit a real DB."""
    with (
        patch(f"{_MOD}.get_paused_agents", return_value=[]),
        patch(f"{_MOD}.pause_agent_queue"),
    ):
        yield

_TOURNAMENT_START_PAST = time.time() - 15 * 86400.0  # 15 days ago (> 14 day threshold)
_TOURNAMENT_START_RECENT = time.time() - 5 * 86400.0  # 5 days ago (< 14 day threshold)


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tournament_duration_days = 14
    cfg.tournament_min_video_count = 3
    cfg.tournament_extension_days = 7
    return cfg


def _mock_session() -> MagicMock:
    mock_session_obj = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _state(
    phase: str = "warmup",
    tournament_started_at: float = 0.0,
    account_id: str = "acc1",
) -> PipelineState:
    return PipelineState(
        account_id=account_id,
        phase=phase,  # type: ignore[arg-type]
        tournament_started_at=tournament_started_at,
    )


class TestOrchestratorNodeCleanState:
    def test_clean_state_returns_empty_dict(self) -> None:
        state = PipelineState(account_id="acc1")
        with patch(f"{_MOD}.get_session", return_value=_mock_session()):
            result = orchestrator_node(state)
        assert result == {}

    def test_already_published_returns_empty_dict(self) -> None:
        state = PipelineState(account_id="acc1", published_video_id="vid_123")
        with patch(f"{_MOD}.get_session", return_value=_mock_session()):
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


class TestAgentFailureIsolation:
    """Tests for Story 5.1 — agent failure isolation via agent_health."""

    def _run_error_node(self, errors: list) -> dict:
        state = PipelineState(account_id="acc1", errors=errors)
        mock_sess = _mock_session()
        with patch(f"{_MOD}.get_session", return_value=mock_sess):
            return orchestrator_node(state)

    def test_production_error_sets_health_false(self):
        err = AgentError(agent="production", error_type="RenderError", message="render failed")
        result = self._run_error_node([err])
        assert result["agent_health"]["production"] is False

    def test_production_error_does_not_affect_other_agents(self):
        err = AgentError(agent="production", error_type="RenderError", message="render failed")
        result = self._run_error_node([err])
        assert "script" not in result["agent_health"]
        assert "monetization" not in result["agent_health"]

    def test_multiple_errors_all_logged(self):
        errors = [
            AgentError(agent="production", error_type="RenderError", message="fail"),
            AgentError(agent="script", error_type="LLMError", message="timeout"),
        ]
        result = self._run_error_node(errors)
        assert result["agent_health"]["production"] is False
        assert result["agent_health"]["script"] is False

    def test_error_block_commits_session(self):
        err = AgentError(agent="production", error_type="RenderError", message="fail")
        mock_sess = _mock_session()
        mock_session_obj = mock_sess.__enter__.return_value
        state = PipelineState(account_id="acc1", errors=[err])
        with patch(f"{_MOD}.get_session", return_value=mock_sess):
            orchestrator_node(state)
        mock_session_obj.commit.assert_called_once()

    def test_error_returns_health_delta_only(self):
        err = AgentError(agent="production", error_type="RenderError", message="fail")
        result = self._run_error_node([err])
        assert "agent_health" in result
        assert "phase" not in result
        assert "committed_niche" not in result


def _state_decay(
    committed_niche: str = "fitness",
    consecutive_decay_count: int = 2,
) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        phase="commit",
        committed_niche=committed_niche,
        niche_decay_alert=True,
        consecutive_decay_count=consecutive_decay_count,
    )


def _mock_config_with_pool() -> MagicMock:
    cfg = _mock_config()
    cfg.niche_pool = ["fitness", "tech", "gaming"]
    return cfg


class TestTournamentCompletion:
    """Tests for tournament winner detection and commit in orchestrator_node."""

    def _run_node(self, state: PipelineState, scores: list) -> dict:
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=scores),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            return orchestrator_node(state)

    def test_tournament_not_elapsed_returns_empty_delta(self) -> None:
        """Returns {} when tournament has not yet elapsed the duration."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_RECENT)
        result = self._run_node(state, scores=[("fitness", 0.8)])
        assert result == {}

    def test_tournament_elapsed_with_winner_commits(self) -> None:
        """When elapsed and winner qualifies, returns phase=commit + committed_niche."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        result = self._run_node(state, scores=[("fitness", 0.8), ("tech", 0.5)])
        assert result["phase"] == "commit"
        assert result["committed_niche"] == "fitness"

    def test_tournament_winner_writes_agent_decision(self) -> None:
        """Verifies AgentDecision of decision_type='tournament_commit' is written to DB."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=[("fitness", 0.8)]),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            orchestrator_node(state)
        added_obj = mock_sess.__enter__.return_value.add.call_args[0][0]
        assert isinstance(added_obj, AgentDecision)
        assert added_obj.decision_type == "tournament_commit"
        assert added_obj.to_value == "fitness"

    def test_tournament_elapsed_no_qualifiers_extends(self) -> None:
        """When no niche qualifies, returns tournament_started_at shifted backward."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        result = self._run_node(state, scores=[])
        assert "tournament_started_at" in result
        assert result["tournament_started_at"] > _TOURNAMENT_START_PAST

    def test_tournament_extension_writes_agent_decision(self) -> None:
        """Verifies AgentDecision of decision_type='tournament_extended' is written."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=[]),
        ):
            orchestrator_node(state)
        added_obj = mock_sess.__enter__.return_value.add.call_args[0][0]
        assert isinstance(added_obj, AgentDecision)
        assert added_obj.decision_type == "tournament_extended"

    def test_tournament_not_started_skips_detection(self) -> None:
        """When tournament_started_at=0.0, detection block is skipped."""
        state = _state(phase="tournament", tournament_started_at=0.0)
        result = self._run_node(state, scores=[("fitness", 0.8)])
        assert result == {}

    def test_non_tournament_phase_skips_detection(self) -> None:
        """Non-tournament phase does not enter tournament block."""
        state = _state(phase="commit", tournament_started_at=_TOURNAMENT_START_PAST)
        result = self._run_node(state, scores=[("fitness", 0.8)])
        assert result == {}

    def test_audit_written_before_phase_set(self) -> None:
        """Verifies session.add (audit write) is called before the phase delta is returned."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        mock_sess = _mock_session()
        call_order: list[str] = []

        inner = mock_sess.__enter__.return_value
        original_add = inner.add
        def tracking_add(obj: object) -> None:
            call_order.append("add")
            original_add(obj)
        inner.add = tracking_add

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=[("fitness", 0.8)]),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            result = orchestrator_node(state)

        # session.add must have been called (audit written)
        assert "add" in call_order
        # And the phase change is in the returned delta
        assert result.get("phase") == "commit"

    def test_tournament_commit_sends_phase_alert(self) -> None:
        """send_phase_alert called with correct args on tournament commit."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=[("fitness", 0.8)]),
            patch(f"{_MOD}.send_phase_alert") as mock_alert,
        ):
            orchestrator_node(state)
        mock_alert.assert_called_once()
        call_kwargs = mock_alert.call_args.kwargs
        assert call_kwargs["from_phase"] == "tournament"
        assert call_kwargs["to_phase"] == "commit"
        assert call_kwargs["committed_niche"] == "fitness"

    def test_tournament_extension_does_not_send_alert(self) -> None:
        """send_phase_alert NOT called in extension path (not a phase transition)."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_niche_scores", return_value=[]),
            patch(f"{_MOD}.send_phase_alert") as mock_alert,
        ):
            orchestrator_node(state)
        mock_alert.assert_not_called()

    def test_extension_shifts_started_at_by_extension_days(self) -> None:
        """Extension shifts tournament_started_at forward by tournament_extension_days * 86400."""
        state = _state(phase="tournament", tournament_started_at=_TOURNAMENT_START_PAST)
        result = self._run_node(state, scores=[])
        expected_shift = 7 * 86400.0  # tournament_extension_days=7
        shifted = result["tournament_started_at"] - _TOURNAMENT_START_PAST
        assert abs(shifted - expected_shift) < 1.0


class TestNicheDecayReTournament:
    """Tests for niche decay re-tournament detection in orchestrator_node."""

    def _run_decay_node(self, state: PipelineState, cpv: float = 0.0001) -> dict:
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config_with_pool()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_commission_per_view", return_value=cpv),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            return orchestrator_node(state)

    def test_decay_alert_in_commit_triggers_re_tournament(self) -> None:
        """Decay alert in commit phase returns phase=tournament."""
        result = self._run_decay_node(_state_decay())
        assert result["phase"] == "tournament"

    def test_re_tournament_clears_committed_niche(self) -> None:
        """Re-tournament sets committed_niche to None."""
        result = self._run_decay_node(_state_decay())
        assert result["committed_niche"] is None

    def test_re_tournament_candidate_niches_excludes_decayed(self) -> None:
        """candidate_niches includes all niche_pool entries except the decayed one."""
        result = self._run_decay_node(_state_decay(committed_niche="fitness"))
        assert "fitness" not in result["candidate_niches"]
        assert "tech" in result["candidate_niches"]
        assert "gaming" in result["candidate_niches"]

    def test_re_tournament_writes_audit_row(self) -> None:
        """AgentDecision with decision_type='niche_decay_retriggered_tournament' is written."""
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config_with_pool()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_commission_per_view", return_value=0.0001),
            patch(f"{_MOD}.get_niche_scores", return_value=[]),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            orchestrator_node(_state_decay())
        added_obj = mock_sess.__enter__.return_value.add.call_args[0][0]
        assert isinstance(added_obj, AgentDecision)
        assert added_obj.decision_type == "niche_decay_retriggered_tournament"
        assert added_obj.from_value == "commit"
        assert added_obj.to_value == "tournament"

    def test_re_tournament_resets_decay_state(self) -> None:
        """niche_decay_alert and consecutive_decay_count are reset in returned delta."""
        result = self._run_decay_node(_state_decay())
        assert result["niche_decay_alert"] is False
        assert result["consecutive_decay_count"] == 0

    def test_re_tournament_sets_tournament_started_at(self) -> None:
        """tournament_started_at is set to a positive timestamp."""
        result = self._run_decay_node(_state_decay())
        assert result["tournament_started_at"] > 0

    def test_no_decay_alert_skips_re_tournament(self) -> None:
        """niche_decay_alert=False → decay block skipped, returns {}."""
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="fitness",
            niche_decay_alert=False,
        )
        result = self._run_decay_node(state)
        assert result == {}

    def test_non_commit_phase_skips_re_tournament(self) -> None:
        """phase=tournament with niche_decay_alert=True → decay block not entered."""
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            niche_decay_alert=True,
            tournament_started_at=0.0,
        )
        result = self._run_decay_node(state)
        assert result == {}

    def test_re_tournament_sends_phase_alert(self) -> None:
        """send_phase_alert called with from_phase=commit, to_phase=tournament."""
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config_with_pool()),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_commission_per_view", return_value=0.0001),
            patch(f"{_MOD}.send_phase_alert") as mock_alert,
        ):
            orchestrator_node(_state_decay())
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["from_phase"] == "commit"
        assert mock_alert.call_args.kwargs["to_phase"] == "tournament"

    def test_re_tournament_cpv_zero_still_triggers(self) -> None:
        """cpv=0.0 (no data available) still triggers re-tournament — not blocked."""
        result = self._run_decay_node(_state_decay(), cpv=0.0)
        assert result["phase"] == "tournament"

    def test_re_tournament_empty_pool_after_exclusion(self) -> None:
        """candidate_niches is [] when niche_pool contains only the decayed niche."""
        cfg = _mock_config()
        cfg.niche_pool = ["fitness"]  # only the decayed niche
        mock_sess = _mock_session()
        with (
            patch(f"{_MOD}.load_account_config", return_value=cfg),
            patch(f"{_MOD}.get_session", return_value=mock_sess),
            patch(f"{_MOD}.get_commission_per_view", return_value=0.0),
            patch(f"{_MOD}.get_niche_scores", return_value=[]),
            patch(f"{_MOD}.send_phase_alert"),
        ):
            result = orchestrator_node(_state_decay(committed_niche="fitness"))
        assert result["candidate_niches"] == []
        assert result["phase"] == "tournament"
