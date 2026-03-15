# Story 4.1: Per-Video Metrics Retrieval & Storage

Status: review

## Story

As the operator,
I want the Analytics Agent to poll TikTok performance data for every posted video and store it as an append-only event log,
so that the system has accurate, historical performance data to drive kill switch, A/B testing, and suppression detection decisions.

## Acceptance Criteria

1. **Given** one or more videos with `lifecycle_state = "posted"` in the `videos` table
   **When** `analytics_node(state)` runs
   **Then** `TikTokAPIClient.get_metrics()` is called for each posted video scoped by `account_id`
   **And** each result is written as a **new** row to `video_metrics` with `recorded_at`, `view_count`, `like_count`, `average_time_watched`, `retention_3s`, `retention_15s`, `fyp_reach_pct`, `affiliate_clicks`
   **And** no existing `video_metrics` rows are updated — append-only strictly enforced

2. **Given** TikTok analytics data has a 24–48h lag
   **When** the Analytics Agent retrieves metrics for a video posted under 24h ago
   **Then** partial or zero metrics are stored without error (zero is a valid value)
   **And** `TikTokRateLimitError` and `TikTokAPIError` per video are handled non-fatally — log to errors list and continue to next video

3. **Given** metrics are stored
   **When** `analytics_node` computes retention
   **Then** `retention_3s = min(1.0, average_time_watched / 3.0)` (proxy: avg watch / 3s threshold)
   **And** `retention_15s = min(1.0, average_time_watched / 15.0)`
   **And** `fyp_reach_pct = traffic_source_type.get("FOR_YOU", 0.0)` from `TikTokVideoMetrics`
   **And** these computed values are stored directly in the `VideoMetric` row

## Tasks / Subtasks

- [x] Task 1: Implement `analytics_node` in `tiktok_faceless/agents/analytics.py`
  - [x] Replace the stub with a full implementation:
    - Accept `state: PipelineState`, return `dict[str, Any]`
    - Load config via `load_account_config(state.account_id)`, build `TikTokAPIClient`
    - Query DB: `session.query(Video).filter_by(account_id=state.account_id, lifecycle_state="posted").all()`
    - For each video with a non-null `tiktok_video_id`:
      - Call `client.get_metrics(account_id=state.account_id, video_id=video.tiktok_video_id)`
      - On `TikTokRateLimitError` or `TikTokAPIError`: append to `api_errors` list, `continue`
      - Compute: `retention_3s = min(1.0, metrics.average_time_watched / 3.0)`
      - Compute: `retention_15s = min(1.0, metrics.average_time_watched / 15.0)`
      - Compute: `fyp_reach_pct = metrics.traffic_source_type.get("FOR_YOU", 0.0)`
      - Write new `VideoMetric` row (never update existing rows)
      - Collect `fyp_reach_pct` values for state update
    - `session.commit()` once after all inserts (single transaction)
    - Compute `avg_fyp = sum(fyp_values) / len(fyp_values)` if any collected, else keep existing `state.fyp_reach_rate`
    - Return `{"fyp_reach_rate": avg_fyp}` if FYP data collected, else `{}`

- [x] Task 2: Add required imports to `analytics.py`
  - [ ] `import` stdlib: `from datetime import datetime, timezone`; `from typing import Any`
  - [ ] Local imports: `TikTokAPIClient`, `TikTokRateLimitError`, `TikTokAPIError` from `tiktok_faceless.clients`
  - [ ] Local: `load_account_config` from `tiktok_faceless.config`
  - [ ] Local: `Video`, `VideoMetric` from `tiktok_faceless.db.models`
  - [ ] Local: `get_session` from `tiktok_faceless.db.session`
  - [ ] Local: `PipelineState` from `tiktok_faceless.state`

- [x] Task 3: Create `tests/unit/agents/test_analytics.py`
  - [ ] Add `_MOD = "tiktok_faceless.agents.analytics"` at module level
  - [ ] Add `_mock_config()` helper with `tiktok_access_token="tok"`, `tiktok_open_id="open"`
  - [ ] Add `_mock_session()` helper (context manager returning inner session mock)
  - [ ] Add `_state()` helper returning minimal `PipelineState(account_id="acc1")`
  - [ ] Add `_posted_video(tiktok_video_id="vid_abc")` helper returning mock `Video` with `lifecycle_state="posted"` and given `tiktok_video_id`
  - [ ] Add `_metrics(view_count=1000, average_time_watched=5.0, fyp_pct=0.7)` helper returning `TikTokVideoMetrics`
  - [ ] Add class `TestAnalyticsNode` with tests:
    - `test_writes_video_metric_row_for_posted_video` — verifies `session.add` called with a `VideoMetric` instance
    - `test_metric_row_is_append_only` — session never calls `.update()` or `.merge()`; only `.add()` used
    - `test_retention_3s_computed_correctly` — `average_time_watched=6.0` → `retention_3s=1.0` (capped); `average_time_watched=1.5` → `retention_3s=0.5`
    - `test_retention_15s_computed_correctly` — `average_time_watched=7.5` → `retention_15s=0.5`
    - `test_fyp_reach_pct_from_traffic_source` — `traffic_source_type={"FOR_YOU": 0.65}` → `fyp_reach_pct=0.65` in VideoMetric
    - `test_fyp_reach_rate_in_state_delta` — `traffic_source_type={"FOR_YOU": 0.7}` → result includes `fyp_reach_rate=0.7`
    - `test_zero_metrics_stored_without_error` — `view_count=0, average_time_watched=0.0` → no exception, VideoMetric still written
    - `test_rate_limit_error_skips_video_non_fatal` — `get_metrics` raises `TikTokRateLimitError` → no exception propagated, no VideoMetric written for that video
    - `test_api_error_skips_video_non_fatal` — `get_metrics` raises `TikTokAPIError` → no exception propagated
    - `test_no_posted_videos_returns_empty_delta` — empty video list → result == `{}`
    - `test_video_without_tiktok_id_skipped` — `tiktok_video_id=None` → `get_metrics` never called

## Dev Notes

### `analytics_node` — Full Implementation

```python
"""
Analytics agent: metrics retrieval, 48h kill switch, and suppression monitoring.

Implementation: Story 4.1 — Per-Video Metrics Retrieval & Storage
"""

from datetime import datetime, timezone
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState


def analytics_node(state: PipelineState) -> dict[str, Any]:
    """
    Poll TikTok metrics for all posted videos and store as append-only event log.

    Returns state delta with updated fyp_reach_rate if FYP data was collected.
    Never returns full PipelineState — only a state delta dict.
    """
    config = load_account_config(state.account_id)
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    with get_session() as session:
        posted_videos = (
            session.query(Video)
            .filter_by(account_id=state.account_id, lifecycle_state="posted")
            .all()
        )

        fyp_values: list[float] = []
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)  # store as naive UTC

        for video in posted_videos:
            if not video.tiktok_video_id:
                continue
            try:
                metrics = client.get_metrics(
                    account_id=state.account_id,
                    video_id=video.tiktok_video_id,
                )
            except (TikTokRateLimitError, TikTokAPIError):
                continue  # Non-fatal: skip this video, try next

            retention_3s = min(1.0, metrics.average_time_watched / 3.0)
            retention_15s = min(1.0, metrics.average_time_watched / 15.0)
            fyp_reach_pct = metrics.traffic_source_type.get("FOR_YOU", 0.0)

            session.add(
                VideoMetric(
                    video_id=video.tiktok_video_id,
                    account_id=state.account_id,
                    recorded_at=now,
                    view_count=metrics.view_count,
                    like_count=metrics.like_count,
                    comment_count=metrics.comment_count,
                    share_count=metrics.share_count,
                    average_time_watched=metrics.average_time_watched,
                    retention_3s=retention_3s,
                    retention_15s=retention_15s,
                    fyp_reach_pct=fyp_reach_pct,
                    affiliate_clicks=0,   # populated by monetization agent
                    affiliate_orders=0,   # populated by monetization agent
                )
            )
            fyp_values.append(fyp_reach_pct)

        session.commit()

    if fyp_values:
        avg_fyp = sum(fyp_values) / len(fyp_values)
        return {"fyp_reach_rate": avg_fyp}
    return {}
```

### Key Implementation Details

**Append-only enforcement**: NEVER call `session.query(VideoMetric).filter(...).update(...)`. Always `session.add(new_row)`.

**Single transaction**: One `session.commit()` at the end covers all inserts — do NOT commit per-video.

**Retention proxy formula** (AC3):
- `retention_3s = min(1.0, average_time_watched / 3.0)` — if avg watch time ≥ 3s, proxy is 1.0
- `retention_15s = min(1.0, average_time_watched / 15.0)` — same for 15s threshold
- Zero `average_time_watched` → both retentions = 0.0 (safe, no division)

**FYP source key**: `traffic_source_type.get("FOR_YOU", 0.0)` — TikTok uses "FOR_YOU" for FYP feed traffic. Missing key → 0.0 (safe default).

**`affiliate_clicks` and `affiliate_orders`**: Set to 0 in analytics_node — these are populated by the monetization agent (Story 4.5). Do not attempt to fetch them here.

**`recorded_at` timezone**: Store as naive UTC (`datetime.now(tz=timezone.utc).replace(tzinfo=None)`) — consistent with all other DB writes in this project.

**Error handling**: `TikTokRateLimitError` and `TikTokAPIError` are both silently skipped per video. The rate limiter in `TikTokAPIClient` already enforces 6 req/min — analytics_node does NOT need its own rate limiting logic.

### `TikTokVideoMetrics` Fields (do NOT modify)

```python
class TikTokVideoMetrics(BaseModel):
    video_id: str
    view_count: int
    like_count: int
    comment_count: int
    share_count: int
    average_time_watched: float
    traffic_source_type: dict[str, float]  # e.g. {"FOR_YOU": 0.65, "FOLLOWING": 0.35}
```

### `VideoMetric` Model Fields (do NOT modify)

All fields exist — no new columns needed:
`id`, `video_id`, `account_id`, `recorded_at`, `view_count`, `like_count`, `comment_count`, `share_count`, `average_time_watched`, `retention_3s`, `retention_15s`, `fyp_reach_pct`, `affiliate_clicks`, `affiliate_orders`

### Test Pattern for `test_analytics.py`

```python
_MOD = "tiktok_faceless.agents.analytics"

from unittest.mock import MagicMock, patch
from tiktok_faceless.agents.analytics import analytics_node
from tiktok_faceless.db.models import VideoMetric
from tiktok_faceless.models.tiktok import TikTokVideoMetrics
from tiktok_faceless.state import PipelineState


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok"
    cfg.tiktok_open_id = "open"
    return cfg


def _mock_session() -> MagicMock:
    mock_ctx = MagicMock()
    mock_sess = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_sess)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _state() -> PipelineState:
    return PipelineState(account_id="acc1")


def _posted_video(tiktok_video_id: str | None = "vid_abc") -> MagicMock:
    v = MagicMock()
    v.tiktok_video_id = tiktok_video_id
    v.lifecycle_state = "posted"
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
        videos: list,
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
        ):
            return analytics_node(_state())
```

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/agents/analytics.py` | Implement `analytics_node` (replace stub) |
| `tests/unit/agents/test_analytics.py` | Create new test file with `TestAnalyticsNode` (11 tests) |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — `VideoMetric` already has all needed fields
- `tiktok_faceless/models/tiktok.py` — `TikTokVideoMetrics` already correct
- `tiktok_faceless/clients/tiktok.py` — `get_metrics()` already implemented
- `tiktok_faceless/state.py` — `fyp_reach_rate` already exists
- Any other agent files

### Previous Story Learnings (Stories 3.1–3.5, 4.x pattern)

- `_MOD = "tiktok_faceless.agents.analytics"` — define at module level in test file
- Patch `TikTokAPIClient` at `f"{_MOD}.TikTokAPIClient"` — not the clients module directly
- Mock session pattern: two-object (`mock_ctx` + `mock_sess = mock_ctx.__enter__.return_value`)
- Mock `session.query(...).filter_by(...).all()` chain for posted videos
- `session.add.call_args[0][0]` to get the `VideoMetric` object passed to add
- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 4.1
- Previous story: `_bmad-output/implementation-artifacts/3-5-niche-decay-re-tournament.md`
- `analytics.py` stub: `tiktok_faceless/agents/analytics.py`
- `TikTokVideoMetrics`: `tiktok_faceless/models/tiktok.py`
- `TikTokAPIClient.get_metrics()`: `tiktok_faceless/clients/tiktok.py`
- `VideoMetric` model: `tiktok_faceless/db/models.py`
- Architecture: append-only analytics pattern, 24–48h TikTok data lag

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 3 tasks complete; 240 unit tests passing, 0 failures
- Added `TikTokAuthError` to except clause during quality review (auth failures now non-fatal)
- Added `test_auth_error_skips_video_non_fatal` (12 tests total in TestAnalyticsNode)
- Added snapshot-time comment on `now` timestamp; fixed module docstring scope
- Fixed minor typing: `list[Any]` params, `_run_get_session` return annotation
- ruff clean on all changed files

### File List

- tiktok_faceless/agents/analytics.py
- tests/unit/agents/test_analytics.py
