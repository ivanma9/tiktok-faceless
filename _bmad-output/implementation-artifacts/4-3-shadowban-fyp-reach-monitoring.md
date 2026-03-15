# Story 4.3: Shadowban & FYP Reach Monitoring

Status: review

## Story

As the operator,
I want the Analytics Agent to detect FYP reach rate drops as early suppression signals,
so that publishing behavior can be adjusted before a full shadowban impacts account reach.

## Acceptance Criteria

1. **Given** metrics stored in `video_metrics` with `fyp_reach_pct` values
   **When** `utils/suppression.py` computes the rolling FYP reach rate
   **Then** it is calculated as the average `fyp_reach_pct` across the last N `VideoMetric` rows for the account (N = `AccountConfig.suppression_window`, default 10)
   **And** the result is returned as a float (1.0 if no data — neutral/healthy assumption)

2. **Given** `fyp_reach_rate` drops below `AccountConfig.fyp_suppression_threshold` for 2 consecutive polling intervals
   **When** `analytics_node` detects the condition
   **Then** `state["suppression_alert"]` is set to `True` in the state delta
   **And** an `agent_decisions` row is written with `decision_type = "suppression_detected"`, `fyp_reach_rate`, `threshold`, and `consecutive_suppression_count` in `supporting_data`
   **And** a Telegram alert is sent via `utils/alerts.py` (non-fatal — never blocks pipeline)

3. **Given** `fyp_reach_rate` recovers above `AccountConfig.fyp_suppression_threshold`
   **When** `analytics_node` evaluates suppression
   **Then** `state["suppression_alert"]` is cleared to `False`
   **And** `state["consecutive_suppression_count"]` is reset to `0`

4. **Given** `state["suppression_alert"] = True`
   **When** the system operates
   **Then** `suppression_alert` in `PipelineState` is available for orchestrator/publishing agents to read and reduce posting cadence
   **Note:** Reduced-volume routing is enforced by reading `suppression_alert` in existing agents; no new orchestrator node changes required in this story

## Tasks / Subtasks

- [x] Task 1: Add `suppression_window` to `AccountConfig` and `consecutive_suppression_count` to `PipelineState`
  - [ ] Add `suppression_window: int = Field(default=10, ge=1)` to `AccountConfig` in `config.py` after `fyp_suppression_threshold`
  - [ ] Add `consecutive_suppression_count: int = 0` to `PipelineState` in `state.py` after `consecutive_decay_count`
  - [ ] No env var wiring needed for `suppression_window` — Pydantic default only (project convention)

- [x] Task 2: Create `tiktok_faceless/utils/suppression.py`
  - [ ] Implement `compute_fyp_reach_rate(session: Session, account_id: str, window: int = 10) -> float`
  - [ ] Query: last `window` `VideoMetric` rows for `account_id` ordered by `recorded_at` desc
  - [ ] Return average `fyp_reach_pct` across results; return `1.0` if no rows (healthy neutral)
  - [ ] Import: `from sqlalchemy.orm import Session` from `sqlalchemy.orm`; `VideoMetric` from `tiktok_faceless.db.models`

- [x] Task 3: Add `send_suppression_alert` to `tiktok_faceless/utils/alerts.py`
  - [ ] Implement `send_suppression_alert(bot_token: str, chat_id: str, fyp_rate: float, threshold: float, account_id: str, timestamp: float | None = None) -> None`
  - [ ] No-op guard when `bot_token` or `chat_id` is empty
  - [ ] Wrap in `try/except Exception: pass  # noqa: BLE001`
  - [ ] Message: `f"⚠️ Suppression detected for {account_id}: FYP reach {fyp_rate:.1%} below threshold {threshold:.1%}."`
  - [ ] Append timestamp line if provided (same pattern as `send_phase_alert`)
  - [ ] Use `httpx.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=5.0)`

- [x] Task 4: Extend `analytics_node` with suppression detection block
  - [ ] Add imports: `compute_fyp_reach_rate` from `tiktok_faceless.utils.suppression`; `send_suppression_alert` from `tiktok_faceless.utils.alerts`; `import time` to stdlib
  - [ ] After the existing `session.commit()` in the `with get_session()` block, open a NEW `with get_session()` block for the suppression read query
  - [ ] Call `compute_fyp_reach_rate(session, account_id=state.account_id, window=config.suppression_window)`
  - [ ] Build state delta for `fyp_reach_rate` from rolling DB value (replaces the in-memory `fyp_values` average for the final state update)
  - [ ] Suppression logic:
    - If `current_fyp_rate < config.fyp_suppression_threshold`:
      - `new_count = state.consecutive_suppression_count + 1`
      - Include `consecutive_suppression_count: new_count` in state delta
      - If `new_count >= 2` and NOT already alerted: set `suppression_alert: True`, write `AgentDecision` (in same session), send `send_suppression_alert`
    - Else (above threshold):
      - `consecutive_suppression_count: 0` and `suppression_alert: False` in state delta
  - [ ] Return combined state delta including `fyp_reach_rate` and suppression fields

- [x] Task 5: Create `tests/unit/utils/test_suppression.py`
  - [ ] Add `_MOD = "tiktok_faceless.utils.suppression"` at module level
  - [ ] Add `_mock_session()` helper (same pattern as analytics tests)
  - [ ] Tests in `TestComputeFypReachRate`:
    - `test_returns_average_of_last_n_rows` — 3 rows with fyp_pct 0.6, 0.8, 1.0 → avg 0.8
    - `test_returns_1_0_when_no_rows` — empty result → 1.0
    - `test_window_limits_query` — verify `.limit(window)` called with correct value
    - `test_single_row_returns_exact_value` — one row with 0.5 → 0.5

- [x] Task 6: Add `TestSuppressionDetection` class to `tests/unit/agents/test_analytics.py`
  - [ ] Add `_state_suppression(consecutive=0, alert=False)` helper returning `PipelineState(account_id="acc1", consecutive_suppression_count=consecutive, suppression_alert=alert)`
  - [ ] Add `_run_suppression(fyp_rate, consecutive=0, alert=False)` helper that patches `load_account_config`, `get_session`, `TikTokAPIClient`, `compute_fyp_reach_rate`, `send_suppression_alert`
  - [ ] Tests in `TestSuppressionDetection`:
    - `test_fyp_rate_written_to_state_delta` — result includes `fyp_reach_rate` equal to mocked compute value
    - `test_first_below_threshold_increments_count` — fyp=0.2 (below 0.4), consecutive=0 → delta has `consecutive_suppression_count=1`, no `suppression_alert`
    - `test_second_below_threshold_sets_alert` — fyp=0.2, consecutive=1 → delta has `suppression_alert=True`
    - `test_alert_writes_agent_decision` — second consecutive below → AgentDecision with `decision_type="suppression_detected"` written
    - `test_alert_sends_telegram` — second consecutive below → `send_suppression_alert` called
    - `test_recovery_clears_alert` — fyp=0.9 (above threshold), alert=True → `suppression_alert=False`, `consecutive_suppression_count=0`
    - `test_above_threshold_resets_count` — fyp=0.9, consecutive=1 → `consecutive_suppression_count=0`
    - `test_no_double_alert` — fyp=0.2, consecutive=2, alert=True → `send_suppression_alert` NOT called again

## Dev Notes

### `compute_fyp_reach_rate` — Full Implementation

New file `tiktok_faceless/utils/suppression.py`:

```python
"""
Suppression detection utilities — FYP reach rate computation.

Implementation: Story 4.3 — Shadowban & FYP Reach Monitoring
"""

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import VideoMetric


def compute_fyp_reach_rate(
    session: Session, account_id: str, window: int = 10
) -> float:
    """
    Compute rolling FYP reach rate as average fyp_reach_pct across last N VideoMetric rows.

    Returns 1.0 (neutral/healthy) if no data is available for the account.
    """
    rows = (
        session.query(VideoMetric.fyp_reach_pct)
        .filter_by(account_id=account_id)
        .order_by(VideoMetric.recorded_at.desc())
        .limit(window)
        .all()
    )
    if not rows:
        return 1.0
    return sum(r.fyp_reach_pct for r in rows) / len(rows)
```

### `send_suppression_alert` — Full Implementation

Add to `tiktok_faceless/utils/alerts.py` after `send_phase_alert`:

```python
def send_suppression_alert(
    bot_token: str,
    chat_id: str,
    fyp_rate: float,
    threshold: float,
    account_id: str,
    timestamp: float | None = None,
) -> None:
    """
    Send a Telegram suppression alert. Non-fatal — all errors swallowed.

    No-op if bot_token or chat_id is empty (Telegram not configured).
    """
    if not bot_token or not chat_id:
        return
    try:
        text = (
            f"\u26a0\ufe0f Suppression detected for {account_id}: "
            f"FYP reach {fyp_rate:.1%} below threshold {threshold:.1%}."
        )
        if timestamp is not None:
            import datetime
            dt = datetime.datetime.fromtimestamp(
                timestamp, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
            text += f"\nTime: {dt}"
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001
        pass  # Never block pipeline on notification failure
```

### Suppression Detection Block — Full Implementation

Updated `analytics_node` structure (after the kill-switch `session.commit()`):

```python
    # ... existing metrics + kill-switch code with session.commit() at end ...

    # Suppression detection — rolling FYP reach rate from DB
    with get_session() as session:
        current_fyp_rate = compute_fyp_reach_rate(
            session, account_id=state.account_id, window=config.suppression_window
        )

        state_delta: dict[str, Any] = {"fyp_reach_rate": current_fyp_rate}

        if current_fyp_rate < config.fyp_suppression_threshold:
            new_count = state.consecutive_suppression_count + 1
            state_delta["consecutive_suppression_count"] = new_count

            if new_count >= 2 and not state.suppression_alert:
                state_delta["suppression_alert"] = True
                session.add(
                    AgentDecision(
                        account_id=state.account_id,
                        agent="analytics",
                        decision_type="suppression_detected",
                        from_value=None,
                        to_value="suppressed",
                        rationale=(
                            f"FYP reach rate {current_fyp_rate:.3f} below "
                            f"threshold {config.fyp_suppression_threshold:.3f} "
                            f"for {new_count} consecutive intervals."
                        ),
                        supporting_data=json.dumps({
                            "fyp_reach_rate": round(current_fyp_rate, 4),
                            "threshold": config.fyp_suppression_threshold,
                            "consecutive_suppression_count": new_count,
                        }),
                    )
                )
                session.commit()
                send_suppression_alert(
                    bot_token=config.telegram_bot_token,
                    chat_id=config.telegram_chat_id,
                    fyp_rate=current_fyp_rate,
                    threshold=config.fyp_suppression_threshold,
                    account_id=state.account_id,
                    timestamp=time.time(),
                )
        else:
            # Above threshold — clear suppression state
            state_delta["consecutive_suppression_count"] = 0
            state_delta["suppression_alert"] = False

    return state_delta
```

Note: The `return state_delta` replaces the existing `if fyp_values: return {"fyp_reach_rate": ...}` at the end of analytics_node. The rolling DB computation from `compute_fyp_reach_rate` is now authoritative for `fyp_reach_rate` (more accurate than the in-memory per-poll average).

### Updated Import Block for `analytics.py`

```python
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import AgentDecision, Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState
from tiktok_faceless.utils.alerts import send_suppression_alert
from tiktok_faceless.utils.suppression import compute_fyp_reach_rate
```

### New `AccountConfig` Field

Add to `tiktok_faceless/config.py` after `fyp_suppression_threshold`:

```python
suppression_window: int = Field(default=10, ge=1)
```

No env var wiring — Pydantic default only (project convention for threshold/window fields).

### New `PipelineState` Field

Add to `tiktok_faceless/state.py` after `consecutive_decay_count`:

```python
consecutive_suppression_count: int = 0
```

### Test Helper Pattern for `TestSuppressionDetection`

```python
_SUPPRESSION_MOD = "tiktok_faceless.agents.analytics"


def _state_suppression(consecutive: int = 0, alert: bool = False) -> PipelineState:
    return PipelineState(
        account_id="acc1",
        consecutive_suppression_count=consecutive,
        suppression_alert=alert,
    )


class TestSuppressionDetection:
    def _run(
        self,
        fyp_rate: float = 0.8,
        consecutive: int = 0,
        alert: bool = False,
    ) -> dict:
        mock_sess_ctx = _mock_session()
        mock_sess = mock_sess_ctx.__enter__.return_value
        # Return empty videos list (suppression test doesn't need posted videos)
        mock_sess.query.return_value.filter_by.return_value.all.return_value = []

        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session", return_value=mock_sess_ctx),
            patch(f"{_MOD}.TikTokAPIClient", return_value=MagicMock()),
            patch(f"{_MOD}.compute_fyp_reach_rate", return_value=fyp_rate),
            patch(f"{_MOD}.send_suppression_alert") as mock_alert,
        ):
            result = analytics_node(_state_suppression(consecutive=consecutive, alert=alert))
        return result
```

Note: `_mock_config()` must include:
- `cfg.fyp_suppression_threshold = 0.4`
- `cfg.suppression_window = 10`
- `cfg.telegram_bot_token = "tok"`
- `cfg.telegram_chat_id = "chat"`

Add these to the existing `_mock_config()` helper.

### Key Implementation Details

**Two `get_session()` calls**: The kill-switch block uses one `with get_session()` for writes. The suppression detection uses a SECOND `with get_session()` for the read + optional AgentDecision write. This is intentional — they are separate logical units.

**`fyp_reach_rate` source change**: Story 4.1 returned `fyp_reach_rate` from the in-memory `fyp_values` list (average across videos polled this run). Story 4.3 replaces this with the DB-derived rolling average from `compute_fyp_reach_rate`. This is more stable (N=10 window smooths noise) and survives polling cycles where no new videos were polled.

**`suppression_alert` suppression logic**:
- Below threshold: increment `consecutive_suppression_count`; at 2 → alert fires once
- Above threshold: reset count to 0 and clear alert immediately (simple recovery, not 2-consecutive)
- "Not already alerted" guard (`not state.suppression_alert`) prevents re-triggering Telegram on every cycle

**`send_suppression_alert` call order**: Must be AFTER `session.commit()` (audit-first pattern established in Stories 3.3–3.5).

**No circular import risk**: `utils/suppression.py` imports only from `sqlalchemy.orm` and `tiktok_faceless.db.models`. `analytics.py` imports `utils/suppression` — no circular dependency.

**`tests/unit/utils/test_suppression.py`** — session mock pattern:
```python
def _mock_session_with_rows(rows: list) -> MagicMock:
    mock_sess = MagicMock()
    mock_sess.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = rows
    return mock_sess
```

Use a `MagicMock()` row with `.fyp_reach_pct` attribute for each row.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/state.py` | Add `consecutive_suppression_count: int = 0` |
| `tiktok_faceless/config.py` | Add `suppression_window: int = Field(default=10, ge=1)` |
| `tiktok_faceless/utils/suppression.py` | Create new file with `compute_fyp_reach_rate` |
| `tiktok_faceless/utils/alerts.py` | Add `send_suppression_alert` function |
| `tiktok_faceless/agents/analytics.py` | Add suppression detection block + updated imports |
| `tests/unit/utils/test_suppression.py` | Create new test file with `TestComputeFypReachRate` (4 tests) |
| `tests/unit/agents/test_analytics.py` | Add `TestSuppressionDetection` (8 tests); update `_mock_config()` |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — `VideoMetric`, `AgentDecision` already have all needed fields
- `tiktok_faceless/clients/tiktok.py` — no new API calls needed
- `tiktok_faceless/agents/orchestrator.py` — `suppression_alert` in state is already readable; routing logic is out of scope for this story
- Any other agent files

### Previous Story Learnings (Stories 4.1–4.2)

- `_MOD = "tiktok_faceless.agents.analytics"` — defined at module level in test file
- Patch `compute_fyp_reach_rate` at `f"{_MOD}.compute_fyp_reach_rate"` (not the utils module directly)
- Patch `send_suppression_alert` at `f"{_MOD}.send_suppression_alert"` (same pattern as `send_phase_alert` in orchestrator tests)
- Mock session: two-object pattern (`mock_ctx` + `mock_sess = mock_ctx.__enter__.return_value`)
- `session.add.call_args_list` to check multiple adds
- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- `noqa: BLE001` on broad `except Exception`
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- Naive UTC datetimes throughout — `datetime.now(tz=timezone.utc).replace(tzinfo=None)`
- `TikTokAuthError` must be in every except clause catching API errors
- Non-fatal side effects: Telegram alerts wrapped in `try/except Exception: pass`
- `send_phase_alert` import pattern: add to local imports alphabetically

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 4.3
- Previous story: `_bmad-output/implementation-artifacts/4-2-48-hour-kill-switch.md`
- `analytics.py` current impl: `tiktok_faceless/agents/analytics.py`
- `alerts.py` current impl: `tiktok_faceless/utils/alerts.py`
- `VideoMetric` model: `tiktok_faceless/db/models.py`
- `PipelineState`: `tiktok_faceless/state.py` (`suppression_alert`, `fyp_reach_rate` pre-exist)
- `AccountConfig`: `tiktok_faceless/config.py` (`fyp_suppression_threshold` pre-exists at 0.40)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 6 tasks complete; 264 unit tests passing, 0 failures
- New file `utils/suppression.py` with `compute_fyp_reach_rate` (rolling window DB query)
- `send_suppression_alert` added to `utils/alerts.py` with non-fatal Telegram pattern
- `consecutive_suppression_count: int = 0` added to PipelineState; `suppression_window` to AccountConfig
- Suppression block uses second `with get_session()` — unconditional `session.commit()` at end; `send_suppression_alert` called after commit (audit-first)
- "Not already alerted" guard prevents Telegram storm on consecutive suppressed intervals
- 4 tests in TestComputeFypReachRate, 8 tests in TestSuppressionDetection
- supporting_data keys (fyp_reach_rate, threshold, consecutive_suppression_count) asserted in tests
- ruff clean on all changed files

### File List

- tiktok_faceless/state.py
- tiktok_faceless/config.py
- tiktok_faceless/utils/suppression.py
- tiktok_faceless/utils/alerts.py
- tiktok_faceless/agents/analytics.py
- tests/unit/utils/test_suppression.py
- tests/unit/agents/test_analytics.py
