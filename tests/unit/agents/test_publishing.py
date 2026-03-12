"""Tests for tiktok_faceless/agents/publishing.py — publishing_node."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.publishing import publishing_node
from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.state import AgentError, PipelineState


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok_123"
    cfg.tiktok_open_id = "open_123"
    cfg.posting_window_start = 18
    cfg.posting_window_end = 22
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
) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        assembled_video_path=assembled_video_path,
        last_post_timestamp=last_post_timestamp,
        current_script=current_script,
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
