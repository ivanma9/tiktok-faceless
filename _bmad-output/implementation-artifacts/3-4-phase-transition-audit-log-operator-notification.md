# Story 3.4: Phase Transition Audit Log & Operator Notification

Status: review

## Story

As the operator,
I want every phase transition logged with full supporting data and surfaced as a notification after the fact,
so that I can review what the system decided and why without needing to approve decisions in advance.

## Acceptance Criteria

1. **Given** any phase transition occurs
   **When** `orchestrator.py` writes the transition
   **Then** an `agent_decisions` row is written with `decision_type`, `from_value` (old phase), `to_value` (new phase or committed niche), `supporting_data` JSON (scores + metrics + committed_niche if applicable), and `created_at`
   **And** the audit row is written before `state["phase"]` is updated (audit-first pattern)
   **Note:** Story 3.3 already satisfies this for the `tournament_commit` transition. This story adds supporting_data enrichment and coverage for any future transitions.

2. **Given** a phase transition is logged (Epic 6 dashboard — deferred)
   **When** the operator opens the dashboard
   **Then** the transition appears in the decision audit log with plain-English summary
   **Note:** This AC is tracked here for completeness but belongs to Epic 6. No code required in this story.

3. **Given** the Orchestrator fires a post-hoc notification
   **When** `utils/alerts.py` sends the Telegram webhook
   **Then** a Telegram message is sent to the configured chat with phase change, committed niche, and timestamp
   **And** Telegram send failure does NOT halt the pipeline (non-fatal, silent swallow)

## Tasks / Subtasks

- [x] Task 1: Add Telegram config fields to `AccountConfig`
  - [ ] Add `telegram_bot_token: str = ""` to `AccountConfig` in `tiktok_faceless/config.py`
  - [ ] Add `telegram_chat_id: str = ""` to `AccountConfig` in `tiktok_faceless/config.py`
  - [ ] Add both to `load_account_config()` via `os.environ.get("TELEGRAM_BOT_TOKEN", "")` and `os.environ.get("TELEGRAM_CHAT_ID", "")`

- [x] Task 2: Implement `send_phase_alert` in `tiktok_faceless/utils/alerts.py`
  - [x] Implement `send_phase_alert(bot_token: str, chat_id: str, from_phase: str, to_phase: str, committed_niche: str | None = None, timestamp: float | None = None) -> None`
  - [x] Build message text with phase names, optional niche, optional timestamp line
  - [x] Use `httpx.post(...)` with `timeout=5.0`
  - [x] No-op guard when `bot_token` or `chat_id` is empty
  - [x] Wrap in `try/except Exception` with `# noqa: BLE001`
  - [x] Fixed deprecated `datetime.utcfromtimestamp` → `datetime.fromtimestamp(..., tz=datetime.timezone.utc)`

- [x] Task 3: Call `send_phase_alert` from `orchestrator_node` after tournament commit
  - [x] Added after `session.commit()`, before `return {"phase": "commit", ...}` in winner path
  - [x] Import added: `from tiktok_faceless.utils.alerts import send_phase_alert`
  - [x] Extension path has NO alert call

- [x] Task 4: Tests for `send_phase_alert` in `tests/unit/utils/test_alerts.py`
  - [x] `tests/unit/utils/__init__.py` created
  - [x] `tests/unit/utils/test_alerts.py` created with 6 tests in `TestSendPhaseAlert`
  - [x] All 6 required tests passing

- [x] Task 5: Update `test_orchestrator.py` to verify alert is called on tournament commit
  - [x] `_run_node` helper patched with `send_phase_alert`
  - [x] `test_tournament_winner_writes_agent_decision` patched with `send_phase_alert`
  - [x] `test_audit_written_before_phase_set` patched with `send_phase_alert`
  - [x] `test_tournament_commit_sends_phase_alert` added
  - [x] `test_tournament_extension_does_not_send_alert` added

## Dev Notes

### Critical Architecture Rules

- **Non-fatal alerts**: `send_phase_alert` MUST never raise. Wrap in `try/except Exception: pass`. Pipeline continuity > notification delivery.
- **Audit-first remains**: Story 3.3 established the audit-first pattern (`session.add` → `session.commit` → alert → `return`). The alert comes AFTER the DB commit, BEFORE the return.
- **`orchestrator.py` is sole phase writer** — no changes to this rule.
- **Agent nodes return state delta only** — alert is a side effect, not state.

### Call Order in `orchestrator_node` Winner Path

```
session.add(AgentDecision(...))       # 1. audit log
session.commit()                       # 2. flush to DB
send_phase_alert(...)                  # 3. notify (non-fatal)
return {"phase": "commit", ...}        # 4. state delta
```

### `send_phase_alert` — Full Implementation

```python
"""
Telegram webhook sender for suppression alerts, pipeline pause, and health checks.

Implementation: Story 3.4 — Phase Transition Audit Log & Operator Notification
"""

import httpx


def send_phase_alert(
    bot_token: str,
    chat_id: str,
    from_phase: str,
    to_phase: str,
    committed_niche: str | None = None,
    timestamp: float | None = None,
) -> None:
    """
    Send a Telegram message for a phase transition. Non-fatal — all errors swallowed.

    No-op if bot_token or chat_id is empty (Telegram not configured).
    """
    if not bot_token or not chat_id:
        return
    try:
        text = f"Phase changed: {from_phase.title()} → {to_phase.title()}."
        if committed_niche:
            text += f" Winning niche: {committed_niche}."
        if timestamp is not None:
            import datetime
            dt = datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC")
            text += f"\nTime: {dt}"
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001
        pass  # Never block pipeline on notification failure
```

### `AccountConfig` — New Fields

Add to `tiktok_faceless/config.py` after `persona_tone`:

```python
telegram_bot_token: str = ""
telegram_chat_id: str = ""
```

Add to `load_account_config()`:

```python
telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
```

### Import in `orchestrator.py`

Add to local imports (after existing imports, alphabetical):

```python
from tiktok_faceless.utils.alerts import send_phase_alert
```

### Test Pattern for `test_alerts.py`

```python
_MOD = "tiktok_faceless.utils.alerts"


class TestSendPhaseAlert:
    def test_sends_telegram_message_on_transition(self) -> None:
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("tok", "chat123", "tournament", "commit", "fitness")
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        assert "Tournament" in call_kwargs.kwargs["json"]["text"]
        assert "Commit" in call_kwargs.kwargs["json"]["text"]
```

Patch `httpx` at module level (`tiktok_faceless.utils.alerts.httpx`) — not `httpx.post` directly.

### What Story 3.3 Already Satisfies

- AC1 (audit row written before phase delta) — `AgentDecision(decision_type="tournament_commit")` written and committed in Story 3.3 before `return {"phase": "commit", ...}`
- `from_value="tournament"`, `to_value=winner_niche` — covers from_phase and committed_niche
- `supporting_data` = JSON of all niche scores

AC1 is fully satisfied. This story adds only the Telegram notification (AC3). AC2 is deferred to Epic 6.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/config.py` | Add `telegram_bot_token`, `telegram_chat_id` fields + `load_account_config()` reads |
| `tiktok_faceless/utils/alerts.py` | Implement `send_phase_alert` (currently a stub) |
| `tiktok_faceless/agents/orchestrator.py` | Add `send_phase_alert` call in winner path + import |
| `tests/unit/utils/__init__.py` | Create if not exists (empty) |
| `tests/unit/utils/test_alerts.py` | Create with `TestSendPhaseAlert` (6 tests) |
| `tests/unit/agents/test_orchestrator.py` | Add 2 alert-related tests + patch alert in `_run_node` |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — `AgentDecision` already correct
- `tiktok_faceless/agents/research.py` — no changes
- Any other agent files

### Previous Story Learnings (Stories 3.1–3.3)

- `_MOD` at module level in every test file
- Patch at module level: `patch(f"{_MOD}.httpx")` not `patch("httpx.post")`
- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- `noqa: BLE001` on broad `except Exception` — ruff requires this for blind exception suppression
- Existing `test_orchestrator.py` has `TestTournamentCompletion._run_node` helper — update it to also patch `send_phase_alert` so existing tests don't fail when alert call is added
- `uv run pytest tests/unit/ -q` to verify no regressions

### References

- Story spec in epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.4
- Previous story: `_bmad-output/implementation-artifacts/3-3-automatic-tournament-winner-detection-commit.md`
- `orchestrator_node` impl: `tiktok_faceless/agents/orchestrator.py`
- `alerts.py` stub: `tiktok_faceless/utils/alerts.py`
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Telegram webhook for suppression alerts, pipeline pause, 24h no-post health check"
- httpx already in `pyproject.toml` dependencies — do NOT add it again

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 5 tasks complete; 217 unit tests passing, 0 failures
- Fixed deprecated `datetime.utcfromtimestamp` → `datetime.fromtimestamp(..., tz=datetime.timezone.utc)` during review
- Fixed test isolation: `send_phase_alert` patched in `test_tournament_winner_writes_agent_decision` and `test_audit_written_before_phase_set` to prevent real HTTP calls in CI
- ruff clean on all changed files

### File List

- tiktok_faceless/config.py
- tiktok_faceless/utils/alerts.py
- tiktok_faceless/agents/orchestrator.py
- tests/unit/utils/__init__.py
- tests/unit/utils/test_alerts.py
- tests/unit/agents/test_orchestrator.py
