# Story 3.2: Phase-Aware Agent Behavior

Status: ready-for-dev

## Story

As the operator,
I want all agents to automatically adapt their volume targets and behavior based on the current phase,
so that the system posts aggressively during Tournament, focuses during Commit, and scales during Scale — without any manual reconfiguration.

## Acceptance Criteria

1. **Given** `phase = "tournament"` in `PipelineState`
   **When** the Publishing Agent evaluates its daily posting target
   **Then** `max_posts_per_day` is read from `AccountConfig.tournament_posts_per_day`
   **And** `publishing_node` defers if `state.videos_produced_today >= tournament_posts_per_day`
   **And** research fans out across all `candidate_niches` (already implemented in `research_node`)

2. **Given** `phase = "commit"` in `PipelineState`
   **When** the Publishing Agent evaluates its daily posting target
   **Then** `max_posts_per_day` is read from `AccountConfig.commit_posts_per_day`
   **And** `publishing_node` defers if `state.videos_produced_today >= commit_posts_per_day`
   **And** `candidate_niches` scanning stops; only `committed_niche` is researched (already implemented in `research_node`)

3. **Given** `phase = "scale"` in `PipelineState`
   **When** the Publishing Agent evaluates its daily posting target
   **Then** `max_posts_per_day` is read from `AccountConfig.scale_posts_per_day`
   **And** `publishing_node` defers if `state.videos_produced_today >= scale_posts_per_day`

4. **Given** a successful TikTok post in any phase
   **When** `publishing_node` returns its state delta
   **Then** `videos_produced_today` is incremented by 1 in the returned delta

5. **Given** any phase value in state
   **When** any agent node runs
   **Then** `orchestrator.py` is the only file that writes `state["phase"]` — no other agent modifies phase directly

## Tasks / Subtasks

- [ ] Task 1: Add phase-specific posting limits to `AccountConfig`
  - [ ] Add `tournament_posts_per_day: int = Field(default=5, ge=1, le=15)` to `AccountConfig` in `tiktok_faceless/config.py`
  - [ ] Add `commit_posts_per_day: int = Field(default=3, ge=1, le=15)` to `AccountConfig`
  - [ ] Add `scale_posts_per_day: int = Field(default=10, ge=1, le=15)` to `AccountConfig`
  - [ ] Add after `tournament_elimination_threshold_score` (already added in Story 3.1)

- [ ] Task 2: Update `publishing_node` to enforce phase-aware daily limit
  - [ ] Add a helper `_phase_post_limit(phase: str, config: AccountConfig) -> int` (module-level private function) that maps phase → limit:
    - `"tournament"` → `config.tournament_posts_per_day`
    - `"commit"` → `config.commit_posts_per_day`
    - `"scale"` → `config.scale_posts_per_day`
    - `"warmup"` or any other → `config.max_posts_per_day`
  - [ ] In `publishing_node`, after the posting window check and before posting, add: if `state.videos_produced_today >= _phase_post_limit(state.phase, config)` → `return {"deferred": True}`
  - [ ] After successful post, add `"videos_produced_today": state.videos_produced_today + 1` to the returned state delta

- [ ] Task 3: Tests for phase-aware publishing behavior
  - [ ] Add class `TestPhaseAwareDailyLimit` in `tests/unit/agents/test_publishing.py`
  - [ ] Update `_mock_config()` helper to include `tournament_posts_per_day=5`, `commit_posts_per_day=3`, `scale_posts_per_day=10`, `max_posts_per_day=3`
  - [ ] Update `_state()` helper to accept `phase` and `videos_produced_today` parameters

## Dev Notes

### Critical Architecture Rules

- **`orchestrator.py` is the ONLY file that writes `state["phase"]`** — `publishing_node`, `research_node`, and all other agents only READ phase; they never assign to it
- **`research_node` already handles phase routing** — tournament → `candidate_niches`, commit/scale/warmup → `committed_niche`. No changes needed to `research_node`.
- **Daily limit is a soft guard** — returning `{"deferred": True}` is the correct pattern (same as posting-window deferral). Never return an `AgentError` for daily limit hit.
- **`videos_produced_today` reset** — this counter is reset by the orchestrator at the start of each day (Story 3.3+). This story only handles incrementing on successful post.
- **Agent node return pattern** — never return full `PipelineState`; always return state delta dict

### What Already Works (Do NOT Modify)

`research_node` in `tiktok_faceless/agents/research.py` already correctly:
- `phase == "tournament"` → scans `state.candidate_niches` (fan-out) ✅
- All other phases → scans only `[state.committed_niche]` ✅
- Decay detection runs in commit phase only ✅

**Do not touch `research_node`** — it is already spec-compliant for AC1 and AC2.

### `_phase_post_limit` Helper — Full Implementation

Add to `tiktok_faceless/agents/publishing.py` (module-level, before `publishing_node`):

```python
def _phase_post_limit(phase: str, config: "AccountConfig") -> int:
    """Return the daily posting limit for the given phase."""
    if phase == "tournament":
        return config.tournament_posts_per_day
    if phase == "commit":
        return config.commit_posts_per_day
    if phase == "scale":
        return config.scale_posts_per_day
    return config.max_posts_per_day  # warmup or unknown
```

Note: `AccountConfig` is imported via `load_account_config` which returns an `AccountConfig`. The type annotation can use the class directly since it is imported at the top of the file.

### `publishing_node` — Key Changes

Two additions only — do not restructure the existing function:

**1. After** the `is_within_posting_window` check (line ~43), **before** the time interval check, add the daily limit guard:

```python
limit = _phase_post_limit(state.phase, config)
if state.videos_produced_today >= limit:
    return {"deferred": True}
```

**2. In** the success return delta at the bottom of the function, add `videos_produced_today`:

```python
return {
    "published_video_id": response.video_id,
    "last_post_timestamp": time.time(),
    "videos_produced_today": state.videos_produced_today + 1,
}
```

### `AccountConfig` — New Fields Placement

In `tiktok_faceless/config.py`, add after `tournament_elimination_threshold_score` (already present from Story 3.1):

```python
tournament_posts_per_day: int = Field(default=5, ge=1, le=15)
commit_posts_per_day: int = Field(default=3, ge=1, le=15)
scale_posts_per_day: int = Field(default=10, ge=1, le=15)
```

Existing `max_posts_per_day: int = Field(default=3, ge=1, le=15)` is kept as the warmup/fallback limit. Do NOT remove it.

### Required Test Cases — `TestPhaseAwareDailyLimit`

File: `tests/unit/agents/test_publishing.py`

First, update the existing `_mock_config()` helper to include the new fields:

```python
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
```

Update `_state()` to accept `phase` and `videos_produced_today`:

```python
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
```

New test class:

```python
_MOD = "tiktok_faceless.agents.publishing"


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
        state = _state(phase="commit", videos_produced_today=3, last_post_timestamp=0.0)
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
```

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/config.py` | Add `tournament_posts_per_day`, `commit_posts_per_day`, `scale_posts_per_day` |
| `tiktok_faceless/agents/publishing.py` | Add `_phase_post_limit` helper; add daily limit guard; add `videos_produced_today` to success delta |
| `tests/unit/agents/test_publishing.py` | Update `_mock_config()` and `_state()`; add `TestPhaseAwareDailyLimit` class (8 tests) |

### Do NOT Touch

- `tiktok_faceless/agents/research.py` — already correctly phase-aware (tournament → candidate_niches, else → committed_niche)
- `tiktok_faceless/agents/orchestrator.py` — sole writer of `state["phase"]`, no changes in this story
- `tiktok_faceless/state.py` — `videos_produced_today: int = 0` already exists; no new state fields needed
- `tiktok_faceless/db/models.py` — no schema changes
- Any existing test classes in `test_publishing.py` — only ADD new class and update helpers

### Previous Story Learnings (from Stories 1.6, 2.x, 3.1)

- `_MOD = "tiktok_faceless.agents.publishing"` — use at module level in test file
- Patch `is_within_posting_window` at the module level (already done in existing tests)
- Patch `time.time` to control timestamp: `patch(f"{_MOD}.time") as mock_time; mock_time.time.return_value = 9999999.0`
- `_MIN_POST_INTERVAL_SECONDS = 3600.0` — set `last_post_timestamp=0.0` in test state so the time interval check passes
- Agent nodes return state delta dict only — never `return state`
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501)
- `MagicMock()` for config fields — not patching `AccountConfig` directly; `_mock_config()` returns a MagicMock with the needed attributes set

### Existing Test Pattern in `test_publishing.py`

The existing tests patch at `"tiktok_faceless.agents.publishing"` scope. The `_mock_session()` helper chains `.query().filter_by().filter().order_by().first()` to return a mock video. The new tests use `_run_node()` helper that patches everything (window, session, time, client) for clean isolation.

Note: `_MOD` was not previously defined at module level in this test file — add it.

### Architecture Notes

- `publishing_node` currently checks TWO guards before posting: (1) posting window, (2) min post interval. The phase-aware daily limit is a THIRD guard, added between them.
- The daily limit is per-calendar-day conceptually, but `videos_produced_today` is just an integer counter in state — it is reset externally by the orchestrator at the start of each day cycle. This story only handles the increment-on-success behavior.
- `_phase_post_limit` is a private module-level function (underscore prefix). It is not an agent node and does not return a state delta.

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 3.2 (line 676)
- Previous story: `_bmad-output/implementation-artifacts/3-1-niche-scoring-tournament-ranking.md`
- `publishing_node` current implementation: `tiktok_faceless/agents/publishing.py`
- `research_node` current implementation: `tiktok_faceless/agents/research.py` (phase-aware, no changes needed)
- `AccountConfig`: `tiktok_faceless/config.py` — add after `tournament_elimination_threshold_score`
- Existing publishing tests: `tests/unit/agents/test_publishing.py`
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "orchestrator is sole phase-writer"

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
