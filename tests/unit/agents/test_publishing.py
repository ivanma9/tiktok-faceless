"""Tests for tiktok_faceless/agents/publishing.py — publishing_node."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.publishing import publishing_node
from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.state import AgentError, PipelineState

_MOD = "tiktok_faceless.agents.publishing"


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok_123"
    cfg.tiktok_open_id = "open_123"
    cfg.posting_window_start = 18
    cfg.posting_window_end = 22
    cfg.max_posts_per_day = 3
    cfg.tournament_posts_per_day = 5
    cfg.commit_posts_per_day = 3
    cfg.scale_posts_per_day = 10
    return cfg


def _mock_session(affiliate_link: str | None = "https://shop.tiktok.com/aff/123") -> MagicMock:
    mock_video = MagicMock()
    mock_video.affiliate_link = affiliate_link
    mock_video.lifecycle_state = "queued"
    mock_session_obj = MagicMock()
    chain = (
        mock_session_obj.query.return_value
        .filter_by.return_value
        .filter.return_value
        .order_by.return_value
    )
    chain.first.return_value = mock_video
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _state(
    assembled_video_path: str | None = "/output/acc1/videos/vid.mp4",
    last_post_timestamp: float = 0.0,
    current_script: str | None = "Great product!",
    phase: str = "warmup",
    videos_produced_today: int = 0,
) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        assembled_video_path=assembled_video_path,
        last_post_timestamp=last_post_timestamp,
        current_script=current_script,
        phase=phase,
        videos_produced_today=videos_produced_today,
    )


class TestPublishingNodeGuards:
    def test_missing_video_returns_agent_error(self) -> None:
        state = _state(assembled_video_path=None)
        result = publishing_node(state)
        assert "errors" in result
        err = result["errors"][0]
        assert isinstance(err, AgentError)
        assert err.agent == "publishing"
        assert err.error_type == "MissingVideo"

    def test_outside_window_returns_deferred(self) -> None:
        state = _state()
        with patch(
            "tiktok_faceless.agents.publishing.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.publishing.is_within_posting_window",
                return_value=False,
            ):
                result = publishing_node(state)
        assert result == {"deferred": True}

    def test_within_min_interval_returns_deferred(self) -> None:
        # last_post_timestamp close to now → interval not met
        state = _state(last_post_timestamp=9999999999.0)
        with patch(
            "tiktok_faceless.agents.publishing.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.publishing.is_within_posting_window",
                return_value=True,
            ):
                with patch("tiktok_faceless.agents.publishing.time") as mock_time:
                    mock_time.time.return_value = 9999999999.0 + 60  # 60s later < 3600
                    result = publishing_node(state)
        assert result == {"deferred": True}


class TestPublishingNodeSuccess:
    def test_returns_published_video_id(self) -> None:
        state = _state()
        mock_response = MagicMock()
        mock_response.video_id = "tiktok_vid_abc"

        with patch(
            "tiktok_faceless.agents.publishing.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.publishing.is_within_posting_window",
                return_value=True,
            ):
                with patch("tiktok_faceless.agents.publishing.time") as mock_time:
                    mock_time.time.return_value = 9999.0
                    with patch(
                        "tiktok_faceless.agents.publishing.get_session",
                        return_value=_mock_session(),
                    ):
                        with patch(
                            "tiktok_faceless.agents.publishing.TikTokAPIClient"
                        ) as mock_tk_cls:
                            mock_tk_cls.return_value.post_video.return_value = mock_response
                            result = publishing_node(state)

        assert result["published_video_id"] == "tiktok_vid_abc"
        assert "last_post_timestamp" in result
        assert "errors" not in result


class TestPublishingNodeErrors:
    def _post_with_error(self, exc: Exception) -> dict:
        state = _state()
        with patch(
            "tiktok_faceless.agents.publishing.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.publishing.is_within_posting_window",
                return_value=True,
            ):
                with patch("tiktok_faceless.agents.publishing.time") as mock_time:
                    mock_time.time.return_value = 9999.0
                    with patch(
                        "tiktok_faceless.agents.publishing.get_session",
                        return_value=_mock_session(),
                    ):
                        with patch(
                            "tiktok_faceless.agents.publishing.TikTokAPIClient"
                        ) as mock_tk_cls:
                            mock_tk_cls.return_value.post_video.side_effect = exc
                            return publishing_node(state)

    def test_tiktok_api_error(self) -> None:
        result = self._post_with_error(TikTokAPIError("500"))
        assert result["errors"][0].error_type == "TikTokAPIError"

    def test_tiktok_rate_limit_error(self) -> None:
        result = self._post_with_error(TikTokRateLimitError("429"))
        assert result["errors"][0].error_type == "TikTokRateLimitError"

    def test_tiktok_auth_error(self) -> None:
        result = self._post_with_error(TikTokAuthError("401"))
        assert result["errors"][0].error_type == "TikTokAuthError"


class TestPhaseAwareDailyLimit:
    """Tests for phase-based daily posting volume enforcement."""

    def _run_node(self, state: PipelineState) -> dict:
        """Run publishing_node with mocked window, session, and TikTok client."""
        mock_response = MagicMock()
        mock_response.video_id = "vid_xyz"
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.is_within_posting_window", return_value=True),
            patch(f"{_MOD}.get_session", return_value=_mock_session()),
            patch(f"{_MOD}.time") as mock_time,
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_time.time.return_value = 9999999.0
            mock_client = MagicMock()
            mock_client.post_video.return_value = mock_response
            mock_client_cls.return_value = mock_client
            return publishing_node(state)

    def test_tournament_defers_when_daily_limit_reached(self) -> None:
        """Defers when videos_produced_today >= tournament_posts_per_day (5)."""
        state = _state(phase="tournament", videos_produced_today=5)
        result = self._run_node(state)
        assert result == {"deferred": True}

    def test_tournament_posts_when_below_limit(self) -> None:
        """Posts when videos_produced_today < tournament_posts_per_day."""
        state = _state(phase="tournament", videos_produced_today=4)
        result = self._run_node(state)
        assert result.get("published_video_id") == "vid_xyz"

    def test_commit_defers_when_daily_limit_reached(self) -> None:
        """Defers when videos_produced_today >= commit_posts_per_day (3)."""
        state = _state(phase="commit", videos_produced_today=3)
        result = self._run_node(state)
        assert result == {"deferred": True}

    def test_scale_defers_when_daily_limit_reached(self) -> None:
        """Defers when videos_produced_today >= scale_posts_per_day (10)."""
        state = _state(phase="scale", videos_produced_today=10)
        result = self._run_node(state)
        assert result == {"deferred": True}

    def test_scale_posts_when_below_limit(self) -> None:
        """Posts when videos_produced_today < scale_posts_per_day (10)."""
        state = _state(phase="scale", videos_produced_today=9)
        result = self._run_node(state)
        assert result.get("published_video_id") == "vid_xyz"

    def test_warmup_uses_max_posts_per_day(self) -> None:
        """Warmup phase defers at max_posts_per_day (3)."""
        state = _state(phase="warmup", videos_produced_today=3)
        result = self._run_node(state)
        assert result == {"deferred": True}

    def test_successful_post_increments_videos_produced_today(self) -> None:
        """Successful post includes videos_produced_today incremented by 1."""
        state = _state(phase="tournament", videos_produced_today=2)
        result = self._run_node(state)
        assert result.get("videos_produced_today") == 3

    def test_daily_limit_deferred_not_an_error(self) -> None:
        """Daily limit hit returns deferred, not an AgentError."""
        state = _state(phase="commit", videos_produced_today=99)
        result = self._run_node(state)
        assert result == {"deferred": True}
        assert "errors" not in result
