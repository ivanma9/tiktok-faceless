# Story 3.5: Niche Decay Re-Tournament

Status: review

## Story

As the operator,
I want the Orchestrator to automatically reset to Tournament Phase when commission-per-view decay is confirmed,
so that niche saturation never becomes a permanent revenue plateau — the system self-corrects.

## Acceptance Criteria

1. **Given** `phase = "commit"` and `niche_decay_alert` is set in state (from research_node in Story 2.5)
   **When** the Orchestrator reads state on its next cycle
   **Then** `state["phase"]` is reset to `"tournament"` — written only in `orchestrator.py`
   **And** `state["candidate_niches"]` is repopulated from `AccountConfig.niche_pool` excluding the decayed niche
   **And** `state["committed_niche"]` is cleared to `None`
   **And** `state["niche_decay_alert"]` is reset to `False`
   **And** `state["consecutive_decay_count"]` is reset to `0`
   **And** `state["tournament_started_at"]` is set to `time.time()` to start the new tournament timer

2. **Given** re-tournament is triggered
   **When** the `agent_decisions` table is inspected
   **Then** a row exists with `decision_type = "niche_decay_retriggered_tournament"`, `from_value = "commit"`, `to_value = "tournament"`, the decayed niche name, commission-per-view value, and `created_at`
   **And** the audit row is written before the state delta is returned (audit-first pattern)

3. **Given** re-tournament begins
   **When** the Research Agent runs
   **Then** existing videos from the previously committed niche remain live and continue earning passively (no code required — videos in DB are never deleted)
   **And** new production focuses on the re-tournament niche pool (research_node already handles tournament phase → candidate_niches scan)

## Tasks / Subtasks

- [x] Task 1: Add `get_commission_per_view` import to `orchestrator.py`
  - [x] In `tiktok_faceless/agents/orchestrator.py`, extend the `from tiktok_faceless.db.queries import ...` line to include `get_commission_per_view`

- [x] Task 2: Add niche decay re-tournament detection block to `orchestrator_node`
  - [ ] In `tiktok_faceless/agents/orchestrator.py`, after the tournament completion detection block and before the final `return {}`, add:
    - Guard: `state.phase == "commit" and state.niche_decay_alert and state.committed_niche`
    - Load config via `load_account_config(state.account_id)` (already imported)
    - Capture `decayed_niche = state.committed_niche`
    - Open session, call `get_commission_per_view(session, account_id=state.account_id, niche=decayed_niche)`
    - Write `AgentDecision(decision_type="niche_decay_retriggered_tournament", from_value="commit", to_value="tournament", rationale=..., supporting_data=json.dumps({...}))`
    - Call `session.commit()`
    - Call `send_phase_alert(from_phase="commit", to_phase="tournament", committed_niche=None, timestamp=time.time())` (non-fatal)
    - Return state delta: `{"phase": "tournament", "committed_niche": None, "candidate_niches": [n for n in config.niche_pool if n != decayed_niche], "niche_decay_alert": False, "consecutive_decay_count": 0, "tournament_started_at": time.time()}`

- [x] Task 3: Tests for niche decay re-tournament in `tests/unit/agents/test_orchestrator.py`
  - [x] Added `_state_decay()` helper with `phase="commit"`, `niche_decay_alert=True`, `committed_niche="fitness"`, `consecutive_decay_count=2`
  - [x] Added `_mock_config_with_pool()` returning `_mock_config()` plus `niche_pool=["fitness", "tech", "gaming"]`
  - [x] Added class `TestNicheDecayReTournament` with 11 tests (9 spec-required + 2 edge cases from review):
    - `test_decay_alert_in_commit_triggers_re_tournament`
    - `test_re_tournament_clears_committed_niche`
    - `test_re_tournament_candidate_niches_excludes_decayed`
    - `test_re_tournament_writes_audit_row`
    - `test_re_tournament_resets_decay_state`
    - `test_re_tournament_sets_tournament_started_at`
    - `test_no_decay_alert_skips_re_tournament`
    - `test_non_commit_phase_skips_re_tournament`
    - `test_re_tournament_sends_phase_alert`
    - `test_re_tournament_cpv_zero_still_triggers` (edge case: cpv=0.0)
    - `test_re_tournament_empty_pool_after_exclusion` (edge case: pool exhausted)

## Dev Notes

### Critical Architecture Rules

- **`orchestrator.py` is the ONLY file that writes `state["phase"]`** — this is the third phase write added (warmup→tournament is future, tournament→commit was Story 3.3, commit→tournament is this story).
- **Audit-first pattern**: `session.add` → `session.commit` → `send_phase_alert` → `return` delta. Never return the phase change without the audit row persisted.
- **`research_node` handles the rest**: once `phase="tournament"` and `candidate_niches` is populated, the existing research_node already fans out across all candidate niches (Story 2.1/3.2 behavior). No changes to research_node needed.
- **AC3 is free**: videos in the `videos` DB table are never deleted — existing committed-niche videos stay live automatically.

### Full Re-Tournament Block

Insert after the tournament completion detection block, before the final `return {}`:

```python
# Niche decay re-tournament — commit→tournament reset on confirmed decay
if state.phase == "commit" and state.niche_decay_alert and state.committed_niche:
    config = load_account_config(state.account_id)
    decayed_niche = state.committed_niche
    with get_session() as session:
        cpv = get_commission_per_view(
            session, account_id=state.account_id, niche=decayed_niche
        )
        session.add(
            AgentDecision(
                account_id=state.account_id,
                agent="orchestrator",
                decision_type="niche_decay_retriggered_tournament",
                from_value="commit",
                to_value="tournament",
                rationale=(
                    f"Niche decay confirmed for '{decayed_niche}' "
                    f"(commission_per_view={cpv:.6f}). Re-triggering tournament."
                ),
                supporting_data=json.dumps({
                    "decayed_niche": decayed_niche,
                    "commission_per_view": round(cpv, 6),
                    "consecutive_decay_count": state.consecutive_decay_count,
                }),
            )
        )
        session.commit()
    send_phase_alert(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        from_phase="commit",
        to_phase="tournament",
        committed_niche=None,
        timestamp=time.time(),
    )
    candidate_niches = [n for n in config.niche_pool if n != decayed_niche]
    return {
        "phase": "tournament",
        "committed_niche": None,
        "candidate_niches": candidate_niches,
        "niche_decay_alert": False,
        "consecutive_decay_count": 0,
        "tournament_started_at": time.time(),
    }
```

### Import Addition

Change:
```python
from tiktok_faceless.db.queries import get_niche_scores
```
To:
```python
from tiktok_faceless.db.queries import get_commission_per_view, get_niche_scores
```

### State Fields Used (all pre-existing — do NOT add new fields)

| Field | Source | Usage |
|-------|--------|-------|
| `niche_decay_alert` | Story 2.5 research_node | Trigger condition (read-only in this block) |
| `consecutive_decay_count` | Story 2.5 research_node | Included in supporting_data; reset to 0 |
| `committed_niche` | Story 3.3 orchestrator | The decayed niche to exclude; cleared |
| `candidate_niches` | Story 1.x | Repopulated from niche_pool minus decayed |
| `tournament_started_at` | Story 3.3 | Reset to time.time() for new tournament |
| `phase` | orchestrator only | Set to "tournament" |

### `AccountConfig.niche_pool` (pre-existing)

`niche_pool: list[str] = Field(default_factory=list)` — already in `config.py`. Contains all candidate niches. NOT loaded from env in `load_account_config()` (it's config-file-driven, not env-var-driven). Use `config.niche_pool` directly.

### `get_commission_per_view` Signature (from Story 2.1 — do NOT change)

```python
def get_commission_per_view(
    session: Session, account_id: str, niche: str, days: int = 7,
) -> float:
```

Returns 0.0 if no data. Always safe to call.

### Test Helpers for `test_orchestrator.py`

The existing `_state()` helper needs extension OR add a new helper:

```python
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
```

### Test Run Helper for `TestNicheDecayReTournament`

```python
def _run_decay_node(self, state: PipelineState, cpv: float = 0.0001) -> dict:
    mock_sess = _mock_session()
    with (
        patch(f"{_MOD}.load_account_config", return_value=_mock_config_with_pool()),
        patch(f"{_MOD}.get_session", return_value=mock_sess),
        patch(f"{_MOD}.get_commission_per_view", return_value=cpv),
        patch(f"{_MOD}.get_niche_scores"),  # prevent tournament block from running
        patch(f"{_MOD}.send_phase_alert"),
    ):
        return orchestrator_node(state)
```

Note: patch `get_niche_scores` in this helper to prevent the tournament detection block from firing (since `phase="commit"` it won't run anyway, but be explicit).

### What the `_run_node` Helper in `TestTournamentCompletion` Already Does

The existing `_run_node` patches `load_account_config`, `get_session`, `get_niche_scores`, `send_phase_alert`. It does NOT patch `get_commission_per_view` — that's fine because the decay block only runs when `phase="commit"`, and `_run_node` uses `phase="tournament"`.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/agents/orchestrator.py` | Add `get_commission_per_view` import; add decay re-tournament block |
| `tests/unit/agents/test_orchestrator.py` | Add `_state_decay()`, `_mock_config_with_pool()` helpers; add `TestNicheDecayReTournament` (9 tests) |

### Do NOT Touch

- `tiktok_faceless/state.py` — all needed fields already exist
- `tiktok_faceless/config.py` — `niche_pool` already exists; no new fields needed
- `tiktok_faceless/db/models.py` — `AgentDecision` already correct
- `tiktok_faceless/agents/research.py` — AC3 already satisfied by existing code
- `tiktok_faceless/utils/alerts.py` — `send_phase_alert` already implemented in Story 3.4

### Previous Story Learnings (Stories 3.1–3.4)

- `_MOD = "tiktok_faceless.agents.orchestrator"` — already defined at module level in test file
- Patch all external dependencies in each test's context manager: `load_account_config`, `get_session`, `get_commission_per_view`, `get_niche_scores`, `send_phase_alert`
- Import sort: stdlib → third-party → local, alphabetical within groups (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- `session.add.call_args[0][0]` to get the object passed to `session.add`
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions

### References

- Story spec in epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.5
- Previous story: `_bmad-output/implementation-artifacts/3-4-phase-transition-audit-log-operator-notification.md`
- `orchestrator_node` current impl: `tiktok_faceless/agents/orchestrator.py`
- `get_commission_per_view`: `tiktok_faceless/db/queries.py` (Story 2.1)
- `niche_decay_alert` + `consecutive_decay_count`: set by `research_node` (Story 2.5)
- Architecture: "orchestrator is sole phase-writer"

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 3 tasks complete; 228 unit tests passing, 0 failures
- Added 2 edge case tests during review: `cpv=0.0` path and empty `niche_pool` after exclusion
- Updated `orchestrator_node` docstring to reflect expanded phase-transition responsibilities
- Removed spurious `get_niche_scores` patch from `_run_decay_node` (decay path never calls it)
- ruff clean on all changed files

### File List

- tiktok_faceless/agents/orchestrator.py
- tests/unit/agents/test_orchestrator.py
