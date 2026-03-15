# Story 4.2: 48-Hour Kill Switch

Status: review

## Story

As the operator,
I want the Analytics Agent to automatically archive underperforming videos at the 48-hour mark based on configurable thresholds,
so that low-quality content stops consuming posting quota without manual review.

## Acceptance Criteria

1. **Given** a video where `posted_at` is 48+ hours ago and `lifecycle_state = "posted"`
   **When** `analytics_node` evaluates the kill switch
   **Then** if `retention_3s < AccountConfig.retention_kill_threshold` AND `affiliate_ctr < AccountConfig.ctr_kill_threshold`
   **Then** `TikTokAPIClient.archive_video()` is called for that video
   **And** `video.lifecycle_state` is updated to `"archived"` in the DB
   **And** an `agent_decisions` row is written with `decision_type = "kill_switch"`, video_id, retention_3s, aff_ctr, view_count in `supporting_data`

2. **Given** a video meets the performance thresholds at 48h (passes retention OR CTR)
   **When** `analytics_node` evaluates it
   **Then** `video.lifecycle_state` is updated to `"promoted"`
   **And** an `agent_decisions` row is written with `decision_type = "promoted"` and supporting metrics

3. **Given** TikTok analytics data lag means metrics are incomplete at 48h
   **When** the kill switch evaluates a video
   **Then** a video is only evaluated if `view_count >= AccountConfig.minimum_view_threshold`
   **And** if `view_count < minimum_view_threshold`, evaluation is deferred to the next polling cycle (no lifecycle change, no AgentDecision)

4. **Given** `TikTokAPIClient.archive_video()` raises any API error during archiving
   **When** the kill switch processes the video
   **Then** the `video.lifecycle_state` is still updated to `"archived"` in DB (non-fatal archive call)
   **And** the next video is processed

## Tasks / Subtasks

- [x] Task 1: Add `ctr_kill_threshold` and `minimum_view_threshold` to `AccountConfig`
  - [ ] Add `ctr_kill_threshold: float = Field(default=0.01, ge=0.0, le=1.0)` to `AccountConfig` in `config.py` (after `retention_kill_threshold`)
  - [ ] Add `minimum_view_threshold: int = Field(default=100, ge=1)` to `AccountConfig` in `config.py`
  - [ ] No env var wiring needed — these are Pydantic defaults only (project convention)

- [x] Task 2: Add `archive_video` method to `TikTokAPIClient`
  - [ ] Add `@api_retry` decorated method `archive_video(self, account_id: str, video_id: str) -> None` in `tiktok_faceless/clients/tiktok.py`
  - [ ] Use `self._bucket.consume()` before the request
  - [ ] POST to `/v2/video/delete/` with `json={"video_id": video_id, "open_id": self._open_id}`
  - [ ] Call `self._handle_response(response)` — errors propagate to caller

- [x] Task 3: Extend `analytics_node` with kill switch evaluation block
  - [ ] Add `import json` to stdlib imports in `analytics.py`
  - [ ] Add `from datetime import timedelta` to the `datetime` import line
  - [ ] Add `from tiktok_faceless.db.models import AgentDecision` to local imports
  - [ ] Add kill switch block INSIDE the same `with get_session()` block, AFTER the metrics insertion loop
  - [ ] Query `posted_at <= now - timedelta(hours=48)` against the `posted_videos` list already loaded (filter in Python — do NOT issue a second DB query for videos)
  - [ ] For each 48h+ video: get latest `VideoMetric` from session, check thresholds, write `AgentDecision`, update `video.lifecycle_state`
  - [ ] Single `session.commit()` at end covers both metrics inserts AND lifecycle updates
  - [ ] API call to `client.archive_video()` for kill-switched videos — errors caught non-fatally

- [x] Task 4: Add `TestKillSwitch` class to `tests/unit/agents/test_analytics.py`
  - [ ] Add `_posted_video_48h(tiktok_video_id="vid_old")` helper returning mock Video with `posted_at = datetime(2020, 1, 1)` (well past 48h) and `lifecycle_state="posted"`
  - [ ] Add `_latest_metric(retention_3s=0.1, view_count=500, affiliate_clicks=0)` helper returning mock VideoMetric
  - [ ] Add `_run_kill_switch(videos, latest_metric, ...)` helper that patches load_account_config, get_session, TikTokAPIClient, and wires session.query chain for both Video filter and VideoMetric latest query
  - [ ] Add tests in `TestKillSwitch`:
    - `test_video_below_threshold_is_archived` — retention_3s=0.1, aff_ctr=0.0, view_count=500 → lifecycle="archived", archive_video called
    - `test_video_above_threshold_is_promoted` — retention_3s=0.9, view_count=500 → lifecycle="promoted", archive_video NOT called
    - `test_insufficient_view_count_defers_evaluation` — view_count=10 (< 100 threshold) → no lifecycle change, no AgentDecision
    - `test_kill_switch_writes_agent_decision_kill` — decision_type="kill_switch" in AgentDecision written
    - `test_kill_switch_writes_agent_decision_promoted` — decision_type="promoted" in AgentDecision written
    - `test_archive_api_error_non_fatal` — archive_video raises TikTokAPIError → lifecycle still updated to "archived", no exception propagated
    - `test_video_under_48h_skipped` — posted_at = datetime.now() → not evaluated, no AgentDecision
    - `test_no_latest_metric_defers` — session.query(VideoMetric) returns None → no lifecycle change

## Dev Notes

### Kill Switch Logic — Full Implementation Block

Add this block inside `analytics_node`, within the same `with get_session()` block, AFTER `fyp_values.append(fyp_reach_pct)` and BEFORE `session.commit()`:

```python
# Kill switch evaluation — 48h+ posted videos
cutoff_48h = now - timedelta(hours=48)

for video in posted_videos:
    if not video.tiktok_video_id:
        continue
    if video.posted_at is None or video.posted_at > cutoff_48h:
        continue  # Under 48h — defer to next cycle

    # Get latest metrics row for this video (autoflush ensures just-inserted rows are visible)
    latest = (
        session.query(VideoMetric)
        .filter_by(video_id=video.tiktok_video_id, account_id=state.account_id)
        .order_by(VideoMetric.recorded_at.desc())
        .first()
    )
    if latest is None:
        continue  # No metrics yet — defer

    if latest.view_count < config.minimum_view_threshold:
        continue  # Insufficient data — defer

    aff_ctr = latest.affiliate_clicks / max(1, latest.view_count)

    if latest.retention_3s < config.retention_kill_threshold and aff_ctr < config.ctr_kill_threshold:
        decision_type = "kill_switch"
        new_lifecycle = "archived"
        try:
            client.archive_video(account_id=state.account_id, video_id=video.tiktok_video_id)
        except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError):
            pass  # Non-fatal — DB update still proceeds
    else:
        decision_type = "promoted"
        new_lifecycle = "promoted"

    session.add(
        AgentDecision(
            account_id=state.account_id,
            agent="analytics",
            decision_type=decision_type,
            from_value="posted",
            to_value=new_lifecycle,
            rationale=(
                f"48h kill switch: retention_3s={latest.retention_3s:.3f}, "
                f"aff_ctr={aff_ctr:.4f}, view_count={latest.view_count}"
            ),
            supporting_data=json.dumps({
                "video_id": video.tiktok_video_id,
                "view_count": latest.view_count,
                "retention_3s": round(latest.retention_3s, 4),
                "aff_ctr": round(aff_ctr, 4),
            }),
        )
    )
    video.lifecycle_state = new_lifecycle

session.commit()  # Single commit: metrics inserts + lifecycle updates + audit rows
```

### Updated Import Block for `analytics.py`

```python
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import AgentDecision, Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState
```

### `archive_video` Method for `TikTokAPIClient`

Add after `get_video_comments`, before `get_affiliate_orders`:

```python
@api_retry
def archive_video(self, account_id: str, video_id: str) -> None:
    """Archive (delete) a video on TikTok. Non-recoverable — use only after kill-switch decision."""
    self._bucket.consume()
    response = self._http.post(
        "/v2/video/delete/",
        json={"video_id": video_id, "open_id": self._open_id},
    )
    self._handle_response(response)
```

### New `AccountConfig` Fields

Add to `tiktok_faceless/config.py` after `retention_kill_threshold`:

```python
ctr_kill_threshold: float = Field(default=0.01, ge=0.0, le=1.0)
minimum_view_threshold: int = Field(default=100, ge=1)
```

These use Pydantic defaults ONLY — no env var wiring needed (project convention for threshold fields).

### Key Implementation Details

**Single `session.commit()`**: The existing `session.commit()` call at the end of analytics_node must cover BOTH the metrics inserts AND the kill switch writes. Do NOT add a second `session.commit()`. Move the existing commit to be after the kill switch block.

**`cutoff_48h` uses naive UTC**: `now - timedelta(hours=48)` where `now = datetime.now(tz=timezone.utc).replace(tzinfo=None)` — consistent with all DB datetime storage in this project. `video.posted_at` is stored as naive UTC per publishing agent (Story 2.x).

**SQLAlchemy autoflush**: `session.query(VideoMetric).order_by(...).first()` will autoflush pending `session.add(VideoMetric(...))` inserts before querying — so the just-inserted metrics ARE visible within the same session without an explicit flush call.

**`aff_ctr` formula**: `affiliate_clicks / max(1, view_count)` — protects against zero views. `affiliate_clicks` is 0 in analytics_node (monetization agent fills this) so CTR will effectively be 0 until Story 4.5 populates it. This means kill switch fires primarily on retention initially — by design.

**`archive_video` errors are non-fatal**: If TikTok rejects the archive call (e.g., already deleted, auth issue), the DB lifecycle update still proceeds. The video is marked archived in our DB regardless. This prevents re-evaluation on the next cycle.

**`decision_type` values**:
- `"kill_switch"` — video archived because both retention AND CTR below threshold
- `"promoted"` — video passes at least one threshold; confirmed high-performer

**`agent_decisions` `from_value`/`to_value`**: Use `from_value="posted"`, `to_value="archived"` or `to_value="promoted"` (lifecycle state values, not phase values).

**Test session mock complexity**: The kill switch needs TWO query chains mocked:
1. `session.query(Video).filter_by(...).all()` → posted videos list
2. `session.query(VideoMetric).filter_by(...).order_by(...).first()` → latest metric

In tests, use `mock_sess.query.side_effect` to return different mocks based on the model class passed:

```python
def _make_session(videos, latest_metric):
    mock_ctx = _mock_session()
    mock_sess = mock_ctx.__enter__.return_value

    video_query = MagicMock()
    video_query.filter_by.return_value.all.return_value = videos

    metric_query = MagicMock()
    metric_query.filter_by.return_value.order_by.return_value.first.return_value = latest_metric

    def query_side_effect(model):
        if model is Video:
            return video_query
        return metric_query

    mock_sess.query.side_effect = query_side_effect
    return mock_ctx, mock_sess
```

### `_posted_video_48h` Helper

```python
def _posted_video_48h(tiktok_video_id: str = "vid_old") -> MagicMock:
    v = MagicMock()
    v.tiktok_video_id = tiktok_video_id
    v.lifecycle_state = "posted"
    v.posted_at = datetime(2020, 1, 1)  # Far past 48h cutoff (naive UTC)
    return v
```

### `_latest_metric` Helper

```python
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
```

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/config.py` | Add `ctr_kill_threshold`, `minimum_view_threshold` fields |
| `tiktok_faceless/clients/tiktok.py` | Add `archive_video` method |
| `tiktok_faceless/agents/analytics.py` | Add kill switch block + updated imports |
| `tests/unit/agents/test_analytics.py` | Add `TestKillSwitch` class (8 tests) |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — `Video`, `VideoMetric`, `AgentDecision` all have correct fields
- `tiktok_faceless/state.py` — `kill_video_ids` and `lifecycle_state` already exist
- `tiktok_faceless/clients/__init__.py` — error classes already correct
- Any other agent files

### Previous Story Learnings (Stories 4.1)

- `_MOD = "tiktok_faceless.agents.analytics"` — already defined at module level in test file
- Patch `TikTokAPIClient` at `f"{_MOD}.TikTokAPIClient"` (not clients module directly)
- Mock session pattern: two-object context manager
- `session.add.call_args[0][0]` to get the object passed to `session.add`
- `session.add.call_args_list` to check multiple adds (both VideoMetric and AgentDecision)
- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- Naive UTC datetimes: `datetime.now(tz=timezone.utc).replace(tzinfo=None)` — consistent
- `TikTokAuthError` must be in every except clause catching API errors (Story 4.1 lesson)
- Single `session.commit()` at end of all writes — never commit per-video

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 4.2
- Previous story: `_bmad-output/implementation-artifacts/4-1-per-video-metrics-retrieval-storage.md`
- `analytics.py` current impl: `tiktok_faceless/agents/analytics.py`
- `TikTokAPIClient`: `tiktok_faceless/clients/tiktok.py`
- `VideoMetric` model: `tiktok_faceless/db/models.py`
- `Video` model: `tiktok_faceless/db/models.py` (has `posted_at`, `lifecycle_state`)
- `AccountConfig`: `tiktok_faceless/config.py` (has `retention_kill_threshold` already)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 4 tasks complete; 252 unit tests passing, 0 failures
- Added `ctr_kill_threshold=0.01` and `minimum_view_threshold=100` as Pydantic defaults (no env var wiring per project convention)
- Added `archive_video()` to TikTokAPIClient with `@api_retry` and non-fatal error handling
- Extended `analytics_node` kill switch block with explicit `session.flush()` before queries, AND-logic comment
- 12 tests in TestKillSwitch (including 2 companion error type tests)
- Added `supporting_data` content assertions for both kill_switch and promoted decisions
- Refactored two duplicate-setup tests to use `_run` helper (returning 3-tuple)
- ruff clean on all changed files

### File List

- tiktok_faceless/config.py
- tiktok_faceless/clients/tiktok.py
- tiktok_faceless/agents/analytics.py
- tests/unit/agents/test_analytics.py
