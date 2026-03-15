"""
Unit tests for analytics_node — Stories 4.1 (Metrics), 4.2 (Kill Switch), 4.3 (Suppression).
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.analytics import analytics_node
from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.db.models import AgentDecision, Video, VideoMetric
from tiktok_faceless.models.tiktok import TikTokVideoMetrics
from tiktok_faceless.state import PipelineState

_MOD = "tiktok_faceless.agents.analytics"


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok"
    cfg.tiktok_open_id = "open"
    cfg.minimum_view_threshold = 100
    cfg.retention_kill_threshold = 0.25
    cfg.ctr_kill_threshold = 0.01
    cfg.fyp_suppression_threshold = 0.4
    cfg.suppression_window = 10
    cfg.telegram_bot_token = "tok"
    cfg.telegram_chat_id = "chat"
    return cfg


def _mock_session() -> MagicMock:
    mock_ctx = MagicMock()
    mock_sess = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_sess)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _state() -> PipelineState:
    return PipelineState(account_id="acc1")


def _state_suppression(consecutive: int = 0, alert: bool = False) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        consecutive_suppression_count=consecutive,
        suppression_alert=alert,
    )


def _posted_video(tiktok_video_id: str | None = "vid_abc") -> MagicMock:
    v = MagicMock()
    v.tiktok_video_id = tiktok_video_id
    v.lifecycle_state = "posted"
    v.posted_at = None  # No posted_at — skipped by kill switch loop
    return v


def _metrics(
    view_count: int = 1000,
    average_time_watched: float = 5.0,
    fyp_pct: float = 0.7,
) -> TikTokVideoMetrics:
    return TikTokVideoMetrics(
        video_id="vid_abc",
        view_count=view_count,
        like_count=50,
        comment_count=10,
        share_count=5,
        average_time_watched=average_time_watched,
        traffic_source_type={"FOR_YOU": fyp_pct},
    )


class TestAnalyticsNode:
    def _run(
        self,
        videos: list[Any],
        metrics: TikTokVideoMetrics | None = None,
        metrics_side_effect: Exception | None = None,
    ) -> dict:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = videos

        mock_client = MagicMock()
        if metrics_side_effect:
            mock_client.get_metrics.side_effect = metrics_side_effect
        else:
            mock_client.get_metrics.return_value = metrics or _metrics()

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=1.0),
        ):
            return analytics_node(_state())

    def _run_get_session(
        self,
        videos: list[Any],
        metrics: TikTokVideoMetrics | None = None,
        metrics_side_effect: Exception | None = None,
    ) -> tuple[dict, MagicMock]:
        """Returns (result, mock_sess) for tests that need to inspect the session."""
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = videos

        mock_client = MagicMock()
        if metrics_side_effect:
            mock_client.get_metrics.side_effect = metrics_side_effect
        else:
            mock_client.get_metrics.return_value = metrics or _metrics()

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=1.0),
        ):
            result = analytics_node(_state())

        return result, mock_sess

    def test_writes_video_metric_row_for_posted_video(self):
        _, mock_sess = self._run_get_session([_posted_video()])
        assert mock_sess.add.called
        added = mock_sess.add.call_args[0][0]
        assert isinstance(added, VideoMetric)

    def test_metric_row_is_append_only(self):
        _, mock_sess = self._run_get_session([_posted_video()])
        # Only session.add should be used — no update or merge
        assert mock_sess.add.called
        assert not mock_sess.merge.called
        # Verify no update() called on any query chain
        mock_sess.query.return_value.filter.return_value.update.assert_not_called()
        mock_sess.query.return_value.filter_by.return_value.update.assert_not_called()

    def test_retention_3s_computed_correctly(self):
        # average_time_watched=6.0 → retention_3s=1.0 (capped)
        m6 = _metrics(average_time_watched=6.0)
        _, mock_sess = self._run_get_session([_posted_video()], metrics=m6)
        added = mock_sess.add.call_args[0][0]
        assert added.retention_3s == 1.0

        # average_time_watched=1.5 → retention_3s=0.5
        m15 = _metrics(average_time_watched=1.5)
        _, mock_sess2 = self._run_get_session([_posted_video()], metrics=m15)
        added2 = mock_sess2.add.call_args[0][0]
        assert added2.retention_3s == pytest.approx(0.5)

    def test_retention_15s_computed_correctly(self):
        # average_time_watched=7.5 → retention_15s=0.5
        m75 = _metrics(average_time_watched=7.5)
        _, mock_sess = self._run_get_session([_posted_video()], metrics=m75)
        added = mock_sess.add.call_args[0][0]
        assert added.retention_15s == pytest.approx(0.5)

    def test_fyp_reach_pct_from_traffic_source(self):
        m = TikTokVideoMetrics(
            video_id="vid_abc",
            view_count=1000,
            like_count=50,
            comment_count=10,
            share_count=5,
            average_time_watched=5.0,
            traffic_source_type={"FOR_YOU": 0.65},
        )
        _, mock_sess = self._run_get_session([_posted_video()], metrics=m)
        added = mock_sess.add.call_args[0][0]
        assert added.fyp_reach_pct == pytest.approx(0.65)

    def test_fyp_reach_rate_in_state_delta(self):
        # fyp_reach_rate now comes from the rolling DB window (compute_fyp_reach_rate),
        # which is patched to 1.0 in _run; assert key is present with patched value.
        result = self._run([_posted_video()], metrics=_metrics(fyp_pct=0.7))
        assert "fyp_reach_rate" in result
        assert result["fyp_reach_rate"] == pytest.approx(1.0)

    def test_zero_metrics_stored_without_error(self):
        m = _metrics(view_count=0, average_time_watched=0.0, fyp_pct=0.0)
        _, mock_sess = self._run_get_session([_posted_video()], metrics=m)
        assert mock_sess.add.called
        added = mock_sess.add.call_args[0][0]
        assert isinstance(added, VideoMetric)
        assert added.view_count == 0
        assert added.retention_3s == 0.0
        assert added.retention_15s == 0.0

    def test_rate_limit_error_skips_video_non_fatal(self):
        # Should not raise, and no VideoMetric written
        _, mock_sess = self._run_get_session(
            [_posted_video()],
            metrics_side_effect=TikTokRateLimitError("rate limit"),
        )
        mock_sess.add.assert_not_called()

    def test_api_error_skips_video_non_fatal(self):
        # Should not raise
        _, mock_sess = self._run_get_session(
            [_posted_video()],
            metrics_side_effect=TikTokAPIError("api error"),
        )
        mock_sess.add.assert_not_called()

    def test_auth_error_skips_video_non_fatal(self):
        # Should not raise, and no VideoMetric written
        _, mock_sess = self._run_get_session(
            [_posted_video()],
            metrics_side_effect=TikTokAuthError("auth error"),
        )
        mock_sess.add.assert_not_called()

    def test_no_posted_videos_returns_empty_delta(self):
        result = self._run([])
        # Now always returns at least fyp_reach_rate from suppression detection
        assert "fyp_reach_rate" in result

    def test_video_without_tiktok_id_skipped(self):
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        no_id_video = _posted_video(tiktok_video_id=None)
        mock_sess.query.return_value.filter_by.return_value.all.return_value = [no_id_video]

        mock_client = MagicMock()

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=1.0),
        ):
            analytics_node(_state())

        mock_client.get_metrics.assert_not_called()


def _posted_video_48h(tiktok_video_id: str = "vid_old") -> MagicMock:
    v = MagicMock()
    v.tiktok_video_id = tiktok_video_id
    v.lifecycle_state = "posted"
    v.posted_at = datetime(2020, 1, 1)  # Far past 48h cutoff (naive UTC)
    return v


def _latest_metric(
    retention_3s: float = 0.1,
    view_count: int = 500,
    affiliate_clicks: int = 0,
) -> MagicMock:
    m = MagicMock()
    m.retention_3s = retention_3s
    m.view_count = view_count
    m.affiliate_clicks = affiliate_clicks
    return m


def _make_kill_switch_session(
    videos: list[Any],
    latest_metric: Any,
) -> tuple[MagicMock, MagicMock]:
    """Build mock session that dispatches Video vs VideoMetric queries correctly."""
    mock_ctx = _mock_session()
    mock_sess = mock_ctx.__enter__.return_value

    video_query = MagicMock()
    video_query.filter_by.return_value.all.return_value = videos

    metric_query = MagicMock()
    metric_query.filter_by.return_value.order_by.return_value.first.return_value = latest_metric

    def query_side_effect(model: Any) -> MagicMock:
        if model is Video:
            return video_query
        return metric_query

    mock_sess.query.side_effect = query_side_effect
    return mock_ctx, mock_sess


class TestKillSwitch:
    _SENTINEL = object()

    def _run(
        self,
        videos: list[Any],
        latest_metric: Any = _SENTINEL,
        archive_side_effect: Exception | None = None,
    ) -> tuple[dict, MagicMock, MagicMock]:
        if latest_metric is self._SENTINEL:
            latest_metric = _latest_metric()
        mock_sess_ctx, mock_sess = _make_kill_switch_session(videos, latest_metric)

        mock_client = MagicMock()
        if archive_side_effect:
            mock_client.archive_video.side_effect = archive_side_effect
        mock_client.get_metrics.return_value = _metrics()

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=mock_client),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=1.0),
        ):
            result = analytics_node(_state())
        return result, mock_sess, mock_client

    def test_video_below_threshold_is_archived(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        _, mock_sess, _ = self._run([video], metric)
        assert video.lifecycle_state == "archived"

    def test_archive_video_called_for_kill_switch(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        _, _, mock_client = self._run([video], metric)
        mock_client.archive_video.assert_called_once()

    def test_video_above_threshold_is_promoted(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.9, view_count=500, affiliate_clicks=10)
        _, mock_sess, _ = self._run([video], metric)
        assert video.lifecycle_state == "promoted"

    def test_archive_video_not_called_for_promoted(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.9, view_count=500, affiliate_clicks=10)
        _, _, mock_client = self._run([video], metric)
        mock_client.archive_video.assert_not_called()

    def test_insufficient_view_count_defers_evaluation(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=10)  # Below 100 threshold
        _, mock_sess, _ = self._run([video], metric)
        # lifecycle_state not changed — still "posted" from mock default
        assert video.lifecycle_state == "posted"

    def test_kill_switch_writes_agent_decision_kill(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        _, mock_sess, _ = self._run([video], metric)
        # Find AgentDecision add call (mock_sess.add may be called multiple times)
        add_calls = mock_sess.add.call_args_list
        decision = next(
            (a.args[0] for a in add_calls if isinstance(a.args[0], AgentDecision)), None
        )
        assert decision is not None
        assert decision.decision_type == "kill_switch"
        assert decision.to_value == "archived"
        data = json.loads(decision.supporting_data)
        assert data["video_id"] == "vid_old"
        assert "retention_3s" in data
        assert "aff_ctr" in data
        assert "view_count" in data

    def test_kill_switch_writes_agent_decision_promoted(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.9, view_count=500, affiliate_clicks=10)
        _, mock_sess, _ = self._run([video], metric)
        add_calls = mock_sess.add.call_args_list
        decision = next(
            (a.args[0] for a in add_calls if isinstance(a.args[0], AgentDecision)), None
        )
        assert decision is not None
        assert decision.decision_type == "promoted"
        assert decision.to_value == "promoted"
        data = json.loads(decision.supporting_data)
        assert data["video_id"] == "vid_old"
        assert "retention_3s" in data
        assert "aff_ctr" in data
        assert "view_count" in data

    def test_archive_api_error_non_fatal(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        # Should not raise even though archive_video raises
        result, _, _ = self._run([video], metric, archive_side_effect=TikTokAPIError("fail"))
        # lifecycle still updated
        assert video.lifecycle_state == "archived"

    def test_archive_auth_error_non_fatal(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        result, _, _ = self._run([video], metric, archive_side_effect=TikTokAuthError("fail"))
        assert video.lifecycle_state == "archived"

    def test_archive_rate_limit_error_non_fatal(self) -> None:
        video = _posted_video_48h()
        metric = _latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)
        result, _, _ = self._run([video], metric, archive_side_effect=TikTokRateLimitError("fail"))
        assert video.lifecycle_state == "archived"

    def test_video_under_48h_skipped(self) -> None:
        video = _posted_video_48h()
        # Just posted — under 48h
        video.posted_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        metric = _latest_metric(retention_3s=0.1, view_count=500)
        _, mock_sess, _ = self._run([video], metric)
        assert video.lifecycle_state == "posted"  # Not changed

    def test_no_latest_metric_defers(self) -> None:
        video = _posted_video_48h()
        _, mock_sess, _ = self._run([video], latest_metric=None)
        # No AgentDecision written, lifecycle unchanged
        add_calls = mock_sess.add.call_args_list
        decisions = [a.args[0] for a in add_calls if isinstance(a.args[0], AgentDecision)]
        assert len(decisions) == 0


class TestSuppressionDetection:
    def _run(
        self,
        fyp_rate: float = 0.8,
        consecutive: int = 0,
        alert: bool = False,
    ) -> tuple[dict, MagicMock]:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = []

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=MagicMock()),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=fyp_rate),
            patch(f"{_MOD}.send_suppression_alert"),
        ):
            result = analytics_node(_state_suppression(consecutive=consecutive, alert=alert))
        return result, mock_sess

    def test_fyp_rate_written_to_state_delta(self) -> None:
        result, _ = self._run(fyp_rate=0.75)
        assert result["fyp_reach_rate"] == pytest.approx(0.75)

    def test_first_below_threshold_increments_count(self) -> None:
        result, _ = self._run(fyp_rate=0.2, consecutive=0)
        assert result["consecutive_suppression_count"] == 1
        assert "suppression_alert" not in result

    def test_second_below_threshold_sets_alert(self) -> None:
        result, _ = self._run(fyp_rate=0.2, consecutive=1)
        assert result.get("suppression_alert") is True

    def test_alert_writes_agent_decision(self) -> None:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = []

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=MagicMock()),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=0.2),
            patch(f"{_MOD}.send_suppression_alert"),
        ):
            analytics_node(_state_suppression(consecutive=1, alert=False))
        add_calls = mock_sess.add.call_args_list
        decision = next(
            (a.args[0] for a in add_calls if isinstance(a.args[0], AgentDecision)), None
        )
        assert decision is not None
        assert decision.decision_type == "suppression_detected"
        data = json.loads(decision.supporting_data)
        assert "fyp_reach_rate" in data
        assert "threshold" in data
        assert "consecutive_suppression_count" in data

    def test_alert_sends_telegram(self) -> None:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = []

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=MagicMock()),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=0.2),
            patch(f"{_MOD}.send_suppression_alert") as mock_alert,
        ):
            analytics_node(_state_suppression(consecutive=1, alert=False))
        mock_alert.assert_called_once()

    def test_recovery_clears_alert(self) -> None:
        result, _ = self._run(fyp_rate=0.9, consecutive=3, alert=True)
        assert result.get("suppression_alert") is False
        assert result.get("consecutive_suppression_count") == 0

    def test_above_threshold_resets_count(self) -> None:
        result, _ = self._run(fyp_rate=0.9, consecutive=1)
        assert result.get("consecutive_suppression_count") == 0

    def test_no_double_alert(self) -> None:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        mock_sess.query.return_value.filter_by.return_value.all.return_value = []

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=MagicMock()),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=0.2),
            patch(f"{_MOD}.send_suppression_alert") as mock_alert,
        ):
            # Already alerted — should not fire again
            analytics_node(_state_suppression(consecutive=2, alert=True))
        mock_alert.assert_not_called()
