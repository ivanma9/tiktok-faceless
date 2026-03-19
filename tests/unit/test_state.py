"""
Unit tests for tiktok_faceless/state.py — PipelineState, AgentError, VideoLifecycle.
"""

import time

import pytest

from tiktok_faceless.state import AgentError, PipelineState, VideoLifecycle


class TestVideoLifecycle:
    def test_all_states_exist(self) -> None:
        states = {e.value for e in VideoLifecycle}
        assert states == {
            "queued",
            "rendering",
            "rendered",
            "scheduled",
            "posted",
            "analyzed",
            "archived",
            "promoted",
        }

    def test_str_comparison(self) -> None:
        assert VideoLifecycle.queued == "queued"
        assert VideoLifecycle.posted == "posted"


class TestAgentError:
    def test_minimal_construction(self) -> None:
        err = AgentError(
            agent="research", error_type="TikTokRateLimitError", message="Rate limited"
        )
        assert err.agent == "research"
        assert err.error_type == "TikTokRateLimitError"
        assert err.message == "Rate limited"
        assert err.video_id is None
        assert err.recovery_suggestion is None
        assert err.timestamp > 0

    def test_full_construction(self) -> None:
        err = AgentError(
            agent="production",
            error_type="ElevenLabsError",
            message="Audio generation failed",
            video_id="vid_123",
            recovery_suggestion="Retry after 60s",
            timestamp=1234567890.0,
        )
        assert err.video_id == "vid_123"
        assert err.recovery_suggestion == "Retry after 60s"
        assert err.timestamp == 1234567890.0

    def test_timestamp_auto_set(self) -> None:
        before = time.time()
        err = AgentError(agent="script", error_type="LLMError", message="LLM failed")
        after = time.time()
        assert before <= err.timestamp <= after


class TestPipelineState:
    def test_minimal_construction(self) -> None:
        state = PipelineState(account_id="acc1")
        assert state.account_id == "acc1"
        assert state.phase == "warmup"
        assert state.candidate_niches == []
        assert state.committed_niche is None
        assert state.selected_product is None
        assert state.product_validated is False
        assert state.current_script is None
        assert state.hook_archetype is None
        assert state.voiceover_path is None
        assert state.assembled_video_path is None
        assert state.published_video_id is None
        assert state.videos_produced_today == 0
        assert state.last_post_timestamp == 0.0
        assert state.fyp_reach_rate == 1.0
        assert state.suppression_alert is False
        assert state.kill_video_ids == []
        assert state.affiliate_commission_week == 0.0
        assert state.agent_health == {}
        assert state.errors == []

    def test_all_phase_values_valid(self) -> None:
        for phase in ["warmup", "tournament", "commit", "scale"]:
            state = PipelineState(account_id="acc1", phase=phase)  # type: ignore[arg-type]
            assert state.phase == phase

    def test_invalid_phase_raises(self) -> None:
        with pytest.raises(Exception):
            PipelineState(account_id="acc1", phase="invalid")  # type: ignore[arg-type]

    def test_kill_video_ids_append_behavior(self) -> None:
        """Annotated[list[str], add] means lists are concatenated, not replaced."""
        state = PipelineState(account_id="acc1", kill_video_ids=["vid_1", "vid_2"])
        assert state.kill_video_ids == ["vid_1", "vid_2"]

    def test_errors_list(self) -> None:
        err = AgentError(agent="analytics", error_type="SuppressionError", message="FYP dropped")
        state = PipelineState(account_id="acc1", errors=[err])
        assert len(state.errors) == 1
        assert state.errors[0].agent == "analytics"

    def test_required_fields_present(self) -> None:
        """All 19 fields from architecture spec must be present."""
        state = PipelineState(account_id="acc1")
        required_fields = [
            "account_id",
            "phase",
            "candidate_niches",
            "committed_niche",
            "selected_product",
            "product_validated",
            "current_script",
            "hook_archetype",
            "voiceover_path",
            "assembled_video_path",
            "published_video_id",
            "videos_produced_today",
            "last_post_timestamp",
            "fyp_reach_rate",
            "suppression_alert",
            "kill_video_ids",
            "affiliate_commission_week",
            "agent_health",
            "errors",
        ]
        for field in required_fields:
            assert hasattr(state, field), f"Missing field: {field}"
