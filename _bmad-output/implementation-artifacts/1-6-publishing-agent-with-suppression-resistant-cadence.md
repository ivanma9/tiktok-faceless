# Story 1.6: Publishing Agent with Suppression-Resistant Cadence

Status: review

## Story

As the operator,
I want the Publishing Agent to post videos to TikTok within configured posting windows with randomized timing,
So that the account posts consistently without triggering bot detection.

## Acceptance Criteria

1. **Given** a `PipelineState` with `assembled_video_path` set and `product_validated=True`, **When** `publishing_node(state)` is called within a configured posting window, **Then** `TikTokAPIClient.post_video()` is called with the video file and the affiliate link embedded in the caption **And** `state["published_video_id"]` is set to the TikTok video ID returned **And** the `videos` DB row `lifecycle_state` transitions to `"posted"` and `posted_at` is set

2. **Given** a configured `posting_window_start` and `posting_window_end` (hours 0–23), **When** `publishing_node` evaluates whether to post, **Then** posts only occur within the configured window **And** if the current hour is outside the window, returns a deferred state delta (no post, no error)

3. **Given** a configured minimum post interval (`min_post_interval` seconds), **When** `publishing_node` checks timing, **Then** if `time.time() - state.last_post_timestamp < min_post_interval`, the post is deferred **And** `state["last_post_timestamp"]` is updated to `time.time()` on every successful post

4. **Given** a random offset is drawn from `utils/timing.py`, **When** `publishing_node` calculates the next post time, **Then** `get_random_posting_offset(min_minutes, max_minutes)` returns a float seconds value used as a window offset **And** this introduces human-variability in posting cadence (FR20)

5. **Given** TikTok API returns an error on `post_video()`, **When** `publishing_node` catches the exception, **Then** an `AgentError` state delta is returned with `error_type` matching the exception class name **And** the video `lifecycle_state` remains `"rendered"` — no silent failure

6. **Given** `assembled_video_path` is `None`, **When** `publishing_node(state)` is called, **Then** it returns `{"errors": [AgentError(agent="publishing", error_type="MissingVideo", ...)]}` immediately

7. **Given** all implementation is complete, **When** `uv run pytest` is run, **Then** all tests pass with zero failures **And** `uv run ruff check .` and `uv run mypy tiktok_faceless/` exit 0

## Tasks / Subtasks

- [x] Task 1: Implement `tiktok_faceless/utils/timing.py` — randomized posting offset (AC: 4)
  - [x] Define `get_random_posting_offset(min_minutes: float = 5.0, max_minutes: float = 30.0) -> float` — returns a random float in `[min_minutes*60, max_minutes*60]` seconds using `random.uniform`
  - [x] Define `is_within_posting_window(window_start: int, window_end: int) -> bool` — checks if current UTC hour is within `[window_start, window_end]` inclusive; handles wrap-around (e.g., start=22, end=2) gracefully
  - [x] Both functions are pure (no side effects) and importable

- [x] Task 2: Implement `tiktok_faceless/agents/publishing.py` — publishing_node (AC: 1, 2, 3, 5, 6)
  - [x] Import `TikTokAPIClient` from `clients.tiktok`, `TikTokAPIError`, `TikTokAuthError`, `TikTokRateLimitError` from `clients`, `AgentError` + `PipelineState` from `state`, `load_account_config` from `config`, `get_session` from `db.session`, `Video` from `db.models`, `is_within_posting_window` from `utils.timing`
  - [x] Define `publishing_node(state: PipelineState) -> dict[str, Any]` as the single public export
  - [x] Guard: if `state.assembled_video_path is None`, return `{"errors": [AgentError(agent="publishing", error_type="MissingVideo", message="assembled_video_path is None — nothing to publish")]}`
  - [x] Load `AccountConfig` via `load_account_config(state.account_id)`
  - [x] Check posting window: call `is_within_posting_window(config.posting_window_start, config.posting_window_end)` — if outside window, return `{"deferred": True}` (no error, no post)
  - [x] Check min interval: `_MIN_POST_INTERVAL_SECONDS = 3600` (1 hour default) — if `time.time() - state.last_post_timestamp < _MIN_POST_INTERVAL_SECONDS`, return `{"deferred": True}`
  - [x] Build caption: `f"{state.current_script or ''} {state.assembled_video_path or ''}".strip()` — use `current_script` as caption text; append affiliate link from DB if available
  - [x] Retrieve affiliate link from DB: query `Video` row for `account_id + lifecycle_state="queued"`, get `affiliate_link` field — append to caption as `f"\n\nShop here: {affiliate_link}"` if present
  - [x] Call `TikTokAPIClient(...).post_video(account_id=state.account_id, video_path=state.assembled_video_path, caption=caption)` inside try/except for `(TikTokRateLimitError, TikTokAuthError, TikTokAPIError)`
  - [x] On success: update `Video` row — set `lifecycle_state="posted"`, `tiktok_video_id=response.video_id`, `posted_at=datetime.utcnow()` — commit via `get_session()`
  - [x] Return `{"published_video_id": response.video_id, "last_post_timestamp": time.time()}`
  - [x] On exception: map to `error_type` string, return `{"errors": [AgentError(...)]}` — do NOT update DB lifecycle_state

- [x] Task 3: Write unit tests for `utils/timing.py` (AC: 4)
  - [x] Create `tests/unit/utils/test_timing.py`
  - [x] Test: `get_random_posting_offset()` returns a float
  - [x] Test: returned value is within `[min*60, max*60]` range
  - [x] Test: `is_within_posting_window(18, 22)` returns `True` when current hour is 20
  - [x] Test: `is_within_posting_window(18, 22)` returns `False` when current hour is 10
  - [x] Mock `datetime` or patch hour for deterministic window tests

- [x] Task 4: Write unit tests for `publishing_node` (AC: 1, 2, 3, 5, 6)
  - [x] Create `tests/unit/agents/test_publishing.py`
  - [x] Test: `assembled_video_path=None` returns `AgentError` with `error_type="MissingVideo"`
  - [x] Test: outside posting window returns `{"deferred": True}` with no errors
  - [x] Test: within min interval returns `{"deferred": True}` with no errors
  - [x] Test: successful post returns `{"published_video_id": ..., "last_post_timestamp": ...}`
  - [x] Test: `TikTokAPIError` → returns `AgentError` with correct `error_type`
  - [x] Test: `TikTokRateLimitError` → returns `AgentError`
  - [x] Mock `load_account_config`, `TikTokAPIClient`, `get_session`, `is_within_posting_window` — no real API or DB calls

- [x] Task 5: Run all validations (AC: 7)
  - [x] Run `uv run pytest` — all tests must pass
  - [x] Run `uv run ruff check .` — must exit 0
  - [x] Run `uv run mypy tiktok_faceless/` — must exit 0

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS

1. **`publishing_node` is the ONLY public export** from `agents/publishing.py`. No other functions are public.

2. **Deferred return pattern** — when outside window or interval not met, return `{"deferred": True}` (not an error — the pipeline orchestrator will retry on next cycle):
   ```python
   # Deferred — not an error
   return {"deferred": True}
   # Error — something went wrong
   return {"errors": [AgentError(...)]}
   ```

3. **DB lifecycle transition** — only update `lifecycle_state` to `"posted"` AFTER `post_video()` succeeds. If the API call fails, the row stays `"rendered"` (or `"queued"` if not yet rendered). This is the "no silent failure" guarantee from the epics.

4. **Caption construction** — TikTok captions max 2200 chars. Use `current_script` as the main text. Append affiliate link on a new line if present. Keep under 150 chars for the MVP (scripts are short).

5. **`_MIN_POST_INTERVAL_SECONDS`** — module-level constant (not in config for MVP). Set to `3600` (1 hour). This enforces FR19 — minimum interval between posts.

6. **`is_within_posting_window` edge case** — when `window_end < window_start` (overnight window, e.g., 22–2), the check must handle wrap-around:
   ```python
   def is_within_posting_window(window_start: int, window_end: int) -> bool:
       hour = datetime.utcnow().hour
       if window_start <= window_end:
           return window_start <= hour <= window_end
       # Overnight wrap: e.g., start=22, end=2
       return hour >= window_start or hour <= window_end
   ```

7. **`get_session()` context manager** — always used with `with get_session() as session:`. The context manager handles `session.commit()` on clean exit and `session.rollback()` on exception. Do NOT call `session.commit()` manually.

8. **`Video` DB query in publishing_node** — query for the specific video being published. Since Story 1.5/1.6 use the "most-recently-queued" heuristic, use the same pattern:
   ```python
   with get_session() as session:
       video = (
           session.query(Video)
           .filter_by(account_id=state.account_id)
           .filter(Video.lifecycle_state.in_(["queued", "rendered"]))
           .order_by(Video.created_at.desc())
           .first()
       )
   ```

### `publishing_node` Full Structure

```python
_MIN_POST_INTERVAL_SECONDS: float = 3600.0

def publishing_node(state: PipelineState) -> dict[str, Any]:
    if state.assembled_video_path is None:
        return {"errors": [AgentError(agent="publishing", error_type="MissingVideo", ...)]}

    config = load_account_config(state.account_id)

    # Window check
    if not is_within_posting_window(config.posting_window_start, config.posting_window_end):
        return {"deferred": True}

    # Interval check
    if time.time() - state.last_post_timestamp < _MIN_POST_INTERVAL_SECONDS:
        return {"deferred": True}

    # Build caption with affiliate link
    caption = state.current_script or ""
    with get_session() as session:
        video = session.query(Video)...first()
        if video and video.affiliate_link:
            caption = f"{caption}\n\nShop here: {video.affiliate_link}".strip()

    # Post to TikTok
    try:
        client = TikTokAPIClient(access_token=config.tiktok_access_token, open_id=config.tiktok_open_id)
        response = client.post_video(account_id=state.account_id, video_path=state.assembled_video_path, caption=caption)
    except TikTokRateLimitError as e:
        return {"errors": [AgentError(agent="publishing", error_type="TikTokRateLimitError", message=str(e))]}
    except TikTokAuthError as e:
        return {"errors": [AgentError(agent="publishing", error_type="TikTokAuthError", message=str(e))]}
    except TikTokAPIError as e:
        return {"errors": [AgentError(agent="publishing", error_type="TikTokAPIError", message=str(e))]}

    # Update DB
    with get_session() as session:
        video = session.query(Video)...first()
        if video:
            video.lifecycle_state = "posted"
            video.tiktok_video_id = response.video_id
            video.posted_at = datetime.utcnow()

    return {"published_video_id": response.video_id, "last_post_timestamp": time.time()}
```

### Testing Mocking Pattern

```python
# Patch is_within_posting_window to control window behavior
with patch("tiktok_faceless.agents.publishing.is_within_posting_window", return_value=False):
    result = publishing_node(state)
assert result == {"deferred": True}

# Patch time.time() for interval check
with patch("tiktok_faceless.agents.publishing.time") as mock_time:
    mock_time.time.return_value = 1000.0  # state.last_post_timestamp defaults to 0.0
    # 1000 - 0 = 1000 > 3600? No → within interval → deferred
```

For `get_session` mock in publishing tests (two calls: read affiliate_link, write posted state):
```python
mock_session_obj = MagicMock()
mock_video = MagicMock()
mock_video.affiliate_link = "https://shop.tiktok.com/aff/123"
mock_session_obj.query.return_value.filter_by.return_value.filter.return_value.order_by.return_value.first.return_value = mock_video
mock_ctx = MagicMock()
mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
mock_ctx.__exit__ = MagicMock(return_value=False)
```

### File Touch Map

**Implement (placeholder → full):**
- `tiktok_faceless/agents/publishing.py`
- `tiktok_faceless/utils/timing.py`

**Create new:**
- `tests/unit/agents/test_publishing.py`
- `tests/unit/utils/test_timing.py`

**Do NOT touch:**
- `tiktok_faceless/clients/tiktok.py` — `post_video()` already implemented
- `tiktok_faceless/state.py` — all required fields exist (`assembled_video_path`, `published_video_id`, `last_post_timestamp`, `current_script`)
- `tiktok_faceless/config.py` — `posting_window_start` and `posting_window_end` already in `AccountConfig`

### Previous Story Learnings

- Import sort: stdlib → third-party → local, blank lines between each group (ruff I001)
- Patch at import location: `patch("tiktok_faceless.agents.publishing.TikTokAPIClient")`
- `get_session()` context manager mock: set `__enter__` and `__exit__` on a MagicMock manually
- Catch from most-specific to least-specific: `TikTokRateLimitError` before `TikTokAuthError` before `TikTokAPIError`
- Line length: keep all lines ≤ 100 chars (ruff E501)
- `dict[str, Any]` return type annotation on all agent nodes
- `session.query(Video).filter_by(...).filter(...).order_by(Video.created_at.desc()).first()` pattern for DB reads

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Requirements to Structure Mapping" (FR17–21), pipeline flow diagram, suppression notes
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.6 (lines 412–445)
- PRD: `_bmad-output/planning-artifacts/prd.md` — FR17–21, NFR (suppression resistance)
- Previous story: `1-5-basic-script-and-affiliate-link-generation.md` — monetization_node pattern, get_session mock pattern

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- 113 tests passing (17 new: 10 timing utils + 7 publishing_node)
- ruff and mypy strict both exit 0
- Fixed Python 3.12+ deprecation: datetime.utcnow() → datetime.now(UTC)
- Deferred return pattern (no error) implemented for out-of-window and min-interval cases
- Two get_session() calls in publishing_node: once to read affiliate_link, once to update DB post-publish

### File List

- tiktok_faceless/agents/publishing.py — implemented
- tiktok_faceless/utils/timing.py — implemented
- tests/unit/agents/test_publishing.py — created
- tests/unit/utils/test_timing.py — created
