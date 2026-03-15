# Story 3.3: Automatic Tournament Winner Detection & Commit

Status: review

## Story

As the operator,
I want the Orchestrator to automatically detect the Tournament winner at day 14 and transition to Commit Phase without requiring any input from me,
so that the system makes the niche commitment autonomously and I only find out after the fact via the dashboard.

## Acceptance Criteria

1. **Given** `phase = "tournament"` and `tournament_duration_days` elapsed (default 14)
   **When** the Orchestrator evaluates Tournament completion
   **Then** the niche with the highest score is selected as `committed_niche`
   **And** `state["phase"]` is set to `"commit"` — only in `orchestrator.py`
   **And** `state["committed_niche"]` is set to the winning niche name

2. **Given** a Tournament winner is selected
   **When** the `agent_decisions` DB table is inspected
   **Then** a row exists with `decision_type = "tournament_commit"`, the winning niche, score, runner-up scores, and `created_at`
   **And** the audit row is written before the phase transition completes

3. **Given** Tournament day 14 arrives but no niche has met the minimum video count threshold
   **When** the Orchestrator evaluates winner selection
   **Then** the Tournament is extended by `AccountConfig.tournament_extension_days` days (not aborted)
   **And** an `agent_decisions` row with `decision_type = "tournament_extended"` is written explaining the extension

4. **Given** the phase transitions to Commit
   **When** new research and script cycles run
   **Then** production automatically focuses on `committed_niche` only (already handled by `research_node` in commit phase — no code change needed)
   **And** existing non-committed videos remain live

## Tasks / Subtasks

- [x] Task 1: Extend `PipelineState` and `AccountConfig` with tournament tracking fields
  - [x] Add `tournament_started_at: float = 0.0` to `PipelineState` in `tiktok_faceless/state.py` (timestamp when tournament phase began; 0.0 = not started)
  - [x] Add `tournament_extension_days: int = Field(default=7, ge=1)` to `AccountConfig` in `tiktok_faceless/config.py` after `tournament_elimination_threshold_score`

- [x] Task 2: Update `orchestrator_node` to detect tournament completion and commit
  - [x] Add module-level helper `_tournament_elapsed_days(started_at: float) -> float` that returns `(time.time() - started_at) / 86400.0`
  - [x] Add module-level helper `_build_supporting_data(scores: list[tuple[str, float]]) -> str` that serializes `scores` to a JSON string (use `json.dumps`)
  - [x] In `orchestrator_node`, after the existing error-handling and published-video guards, add tournament completion detection block:
    - Only runs if `state.phase == "tournament"` and `state.tournament_started_at > 0`
    - Compute elapsed days via `_tournament_elapsed_days(state.tournament_started_at)`
    - If elapsed days < `config.tournament_duration_days`: skip (tournament still running), return `{}`
    - Call `get_niche_scores(session, account_id=state.account_id, days=config.tournament_duration_days, min_video_count=config.tournament_min_video_count)` to get qualifying niches
    - **Winner path** (scores not empty): write `AgentDecision(decision_type="tournament_commit")`, `session.commit()`, return `{"phase": "commit", "committed_niche": winner_niche}`
    - **Extension path** (scores empty): write `AgentDecision(decision_type="tournament_extended")`, `session.commit()`, return `{"tournament_started_at": state.tournament_started_at + config.tournament_extension_days * 86400.0}`

- [x] Task 3: Add imports to `orchestrator.py`
  - [x] Add `import json` and `import time` to stdlib imports
  - [x] Add `from tiktok_faceless.config import load_account_config` to local imports
  - [x] Add `from tiktok_faceless.db.models import AgentDecision, Error` (Error already imported; add AgentDecision)
  - [x] Add `from tiktok_faceless.db.queries import get_niche_scores` to local imports

- [x] Task 4: Tests for tournament winner detection in `tests/unit/agents/test_orchestrator.py`
  - [x] Create `tests/unit/agents/test_orchestrator.py` (new file — does not exist yet)
  - [x] Add `_MOD = "tiktok_faceless.agents.orchestrator"` at module level
  - [x] Add `_mock_config()` helper returning MagicMock with `tournament_duration_days=14`, `tournament_min_video_count=3`, `tournament_extension_days=7`
  - [x] Add `_state()` helper accepting `phase`, `tournament_started_at`, `account_id` params, returning `PipelineState`
  - [x] Add `_mock_session()` helper (context manager mock)
  - [x] Add class `TestTournamentCompletion` with 9 tests (8 spec-required + 1 bonus):
    - `test_tournament_not_elapsed_returns_empty_delta`
    - `test_tournament_elapsed_with_winner_commits`
    - `test_tournament_winner_writes_agent_decision`
    - `test_tournament_elapsed_no_qualifiers_extends`
    - `test_tournament_extension_writes_agent_decision`
    - `test_tournament_not_started_skips_detection`
    - `test_non_tournament_phase_skips_detection`
    - `test_audit_written_before_phase_set`
    - `test_extension_shifts_started_at_by_extension_days` (bonus)

## Dev Notes

### Critical Architecture Rules

- **`orchestrator.py` is the ONLY file that writes `state["phase"]`** — this is THE canonical rule of the entire system. Story 3.3 adds the first real phase write (tournament → commit). Do NOT write phase in any other file.
- **Audit-first pattern**: Write the `AgentDecision` row to DB, then commit the session, THEN return the state delta. Never return the phase change without the audit row persisted.
- **Agent nodes return state delta dict only** — never return full `PipelineState`. The LangGraph reducer handles merging.
- **`get_niche_scores` is already implemented** in `tiktok_faceless/db/queries.py` from Story 3.1 — do NOT reimplementent it. Call it directly.
- **`research_node` auto-tapers in commit phase** — AC4 is already satisfied by existing `research_node` behavior (commit phase → scans only `committed_niche`). No changes needed to `research_node`.

### Extension Logic (Critical Detail)

The extension is implemented by adjusting `tournament_started_at` backward by `tournament_extension_days * 86400.0`. This effectively postpones the next completion check without adding a new state field. The elapsed check on the next run will see: `time.time() - new_tournament_started_at < tournament_duration_days` until the extension period is exhausted.

```python
# Extension: push start back so next completion check fires tournament_extension_days later
return {"tournament_started_at": state.tournament_started_at - config.tournament_extension_days * 86400.0}
```

### `orchestrator_node` — Full Tournament Block

Insert this block at the end of `orchestrator_node`, before the final `return {}` (the no-op path):

```python
# Tournament completion detection — only orchestrator writes phase
if state.phase == "tournament" and state.tournament_started_at > 0:
    config = load_account_config(state.account_id)
    elapsed_days = _tournament_elapsed_days(state.tournament_started_at)
    if elapsed_days >= config.tournament_duration_days:
        with get_session() as session:
            scores = get_niche_scores(
                session,
                account_id=state.account_id,
                days=config.tournament_duration_days,
                min_video_count=config.tournament_min_video_count,
            )
            if scores:
                winner_niche, winner_score = scores[0]
                session.add(
                    AgentDecision(
                        account_id=state.account_id,
                        agent="orchestrator",
                        decision_type="tournament_commit",
                        from_value="tournament",
                        to_value=winner_niche,
                        rationale=(
                            f"Tournament complete after {elapsed_days:.1f} days. "
                            f"Winner: {winner_niche} score={winner_score:.4f}"
                        ),
                        supporting_data=_build_supporting_data(scores),
                    )
                )
                session.commit()
                return {"phase": "commit", "committed_niche": winner_niche}
            else:
                session.add(
                    AgentDecision(
                        account_id=state.account_id,
                        agent="orchestrator",
                        decision_type="tournament_extended",
                        from_value="tournament",
                        to_value="tournament",
                        rationale=(
                            f"Tournament extended by {config.tournament_extension_days} days — "
                            f"no niche met min_video_count={config.tournament_min_video_count}"
                        ),
                        supporting_data=None,
                    )
                )
                session.commit()
                return {
                    "tournament_started_at": (
                        state.tournament_started_at
                        - config.tournament_extension_days * 86400.0
                    )
                }
```

### Module-Level Helpers

Add before `orchestrator_node` (after imports):

```python
import json
import time


def _tournament_elapsed_days(started_at: float) -> float:
    """Return days elapsed since tournament_started_at timestamp."""
    return (time.time() - started_at) / 86400.0


def _build_supporting_data(scores: list[tuple[str, float]]) -> str:
    """Serialize niche score list to JSON string for AgentDecision.supporting_data."""
    return json.dumps([{"niche": n, "score": round(s, 6)} for n, s in scores])
```

### `PipelineState` — New Field

In `tiktok_faceless/state.py`, add after `videos_produced_today`:

```python
tournament_started_at: float = 0.0  # Unix timestamp when tournament phase began; 0.0 = not started
```

### `AccountConfig` — New Field

In `tiktok_faceless/config.py`, add after `tournament_elimination_threshold_score`:

```python
tournament_extension_days: int = Field(default=7, ge=1)
```

### `AgentDecision` Model (already exists — do NOT modify)

`tiktok_faceless/db/models.py`:
```python
class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    decision_type: Mapped[str] = mapped_column(String, nullable=False)
    from_value: Mapped[str | None] = mapped_column(String, nullable=True)
    to_value: Mapped[str | None] = mapped_column(String, nullable=True)
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    supporting_data: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
```
The `created_at` field is the `recorded_at` referenced in the AC (same concept, different name in spec).

### Test File Pattern (`test_orchestrator.py`)

Mirror the pattern from `tests/unit/agents/test_publishing.py`:

```python
from unittest.mock import MagicMock, call, patch

import pytest

from tiktok_faceless.agents.orchestrator import orchestrator_node
from tiktok_faceless.db.models import AgentDecision
from tiktok_faceless.state import PipelineState

_MOD = "tiktok_faceless.agents.orchestrator"


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tournament_duration_days = 14
    cfg.tournament_min_video_count = 3
    cfg.tournament_extension_days = 7
    return cfg


def _mock_session() -> MagicMock:
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


def _state(
    phase: str = "warmup",
    tournament_started_at: float = 0.0,
    account_id: str = "acc1",
) -> PipelineState:
    return PipelineState(
        account_id=account_id,
        phase=phase,
        tournament_started_at=tournament_started_at,
    )
```

### `get_niche_scores` Signature (from Story 3.1 — do NOT change)

```python
def get_niche_scores(
    session: Session, account_id: str, days: int = 7, min_video_count: int = 1,
) -> list[tuple[str, float]]:
```

Pass `days=config.tournament_duration_days` and `min_video_count=config.tournament_min_video_count` from the call site in `orchestrator_node`.

### What Already Works (Do NOT Modify)

- `research_node` — correctly routes to `committed_niche` in commit phase (AC4 already satisfied)
- `get_niche_scores` in `tiktok_faceless/db/queries.py` — Story 3.1 implementation, no changes
- `flag_eliminated_niches` in `tiktok_faceless/db/queries.py` — Story 3.1 implementation, no changes
- `AgentDecision` ORM model — already exists, no changes

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/state.py` | Add `tournament_started_at: float = 0.0` field |
| `tiktok_faceless/config.py` | Add `tournament_extension_days: int = Field(default=7, ge=1)` |
| `tiktok_faceless/agents/orchestrator.py` | Add helpers + tournament completion block + imports |
| `tests/unit/agents/test_orchestrator.py` | Create new test file with `TestTournamentCompletion` (8 tests) |

### Do NOT Touch

- `tiktok_faceless/agents/research.py` — AC4 already satisfied
- `tiktok_faceless/db/models.py` — `AgentDecision` already correct
- `tiktok_faceless/db/queries.py` — `get_niche_scores` already correct
- Any existing test files — only add new `test_orchestrator.py`

### Previous Story Learnings (Stories 1.7, 2.x, 3.1, 3.2)

- `_MOD = "tiktok_faceless.agents.orchestrator"` — define at module level in test file
- Patch `get_session` as context manager: `patch(f"{_MOD}.get_session", return_value=_mock_session())`
- Patch `time` at module level: `patch(f"{_MOD}.time") as mock_time; mock_time.time.return_value = <value>`
- Patch `load_account_config` at module scope: `patch(f"{_MOD}.load_account_config", return_value=_mock_config())`
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501)
- Agent nodes return state delta dict only — never `return state`
- `MagicMock()` for config — not patching `AccountConfig` class directly

### References

- Story spec in epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.3
- Previous story: `_bmad-output/implementation-artifacts/3-2-phase-aware-agent-behavior.md`
- `orchestrator_node` current impl: `tiktok_faceless/agents/orchestrator.py`
- `AgentDecision` model: `tiktok_faceless/db/models.py`
- `get_niche_scores` query: `tiktok_faceless/db/queries.py`
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "orchestrator is sole phase-writer"
- `PipelineState`: `tiktok_faceless/state.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 4 tasks complete, 208 unit tests passing (1 pre-existing unrelated failure in test_graph.py)
- Extension arithmetic uses `+ extension_days * 86400` (adds to started_at, making elapsed smaller) — spec prose was internally contradictory; implementation follows correct semantic
- `test_audit_written_before_phase_set` added to verify audit-first pattern
- ruff clean on all changed files

### File List

- tiktok_faceless/state.py
- tiktok_faceless/config.py
- tiktok_faceless/agents/orchestrator.py
- tests/unit/agents/test_orchestrator.py
