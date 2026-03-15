# Story 4.5: Commission Reconciliation on Schedule

Status: review

## Story

As the operator,
I want the Monetization Agent to reconcile TikTok Shop reported commissions against system-tracked click data on a configurable schedule,
so that revenue figures in the dashboard are accurate and attribution discrepancies are surfaced proactively.

## Acceptance Criteria

1. **Given** click data stored in `video_metrics` and commission data from `TikTokAPIClient.get_affiliate_orders()`
   **When** `monetization_node` runs its reconciliation cycle (configurable schedule, default daily)
   **Then** system-tracked clicks are compared against TikTok Shop reported commissions for the same period
   **And** discrepancies beyond a configurable tolerance threshold are written to the `errors` table with `error_type = "commission_discrepancy"`

2. **Given** reconciliation completes
   **When** the `video_metrics` table is queried
   **Then** each video has an up-to-date commission amount reflecting the latest TikTok Shop data
   **And** `state["affiliate_commission_week"]` is updated with the reconciled 7-day total

3. **Given** TikTok Shop API is unavailable during a reconciliation cycle
   **When** `monetization_node` catches the error
   **Then** the cycle is skipped and retried at the next scheduled interval
   **And** the last successful reconciliation timestamp is stored — no stale data presented as current

## Tasks / Subtasks

- [x] Task 1: Add config and state fields for reconciliation
  - [x] Add `reconciliation_interval_hours: int = Field(default=24, ge=1)` to `AccountConfig` in `config.py` — no env var wiring (Pydantic default only)
  - [x] Add `commission_discrepancy_tolerance: float = Field(default=0.10, ge=0.0, le=1.0)` to `AccountConfig` — no env var wiring
  - [x] Add `last_reconciliation_at: float = 0.0` to `PipelineState` in `state.py`

- [x] Task 2: Extend `monetization_node` with reconciliation logic
  - [x] Add `import time` to stdlib imports in `monetization.py`
  - [x] Add `from tiktok_faceless.db.models import Error, VideoMetric` to local imports
  - [x] After the affiliate-link generation block, add a reconciliation block:
    - Guard: only run if `time.time() - state.last_reconciliation_at >= config.reconciliation_interval_hours * 3600`
    - Call `client.get_affiliate_orders(account_id=state.account_id)` wrapped in `try/except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError)`
    - On success: compute `affiliate_commission_week` = sum of `o.commission_amount` for all orders
    - Call reconciliation helper to compare VideoMetric clicks vs orders and write `Error` rows for discrepancies
    - Update `delta["last_reconciliation_at"] = time.time()`
    - On API error: skip (preserve existing state values, do NOT update `last_reconciliation_at`)

- [x] Task 3: Add `_reconcile_commissions` helper in `monetization.py`
  - [x] Signature: `_reconcile_commissions(session, account_id, orders, tolerance) -> None`
  - [x] Aggregate comparison: sum system affiliate_clicks vs total TikTok order count for last 7 days
  - [x] Write `Error(account_id=..., agent="monetization", error_type="commission_discrepancy", message=...)` if ratio_diff > tolerance

- [x] Task 4: Add `TestCommissionReconciliation` class to `tests/unit/agents/test_monetization.py`
  - [x] Add `_mock_config()` update: include `reconciliation_interval_hours=24`, `commission_discrepancy_tolerance=0.10`
  - [x] Add `_mock_order(commission_amount=10.0)` helper returning a mock `CommissionRecord`
  - [x] Add `_run(...)` helper that patches config, session, TikTokAPIClient
  - [x] Tests (7 minimum):
    - `test_reconciliation_runs_when_interval_elapsed`
    - `test_reconciliation_skipped_when_interval_not_elapsed`
    - `test_affiliate_commission_week_updated_on_success`
    - `test_api_error_skips_cycle_preserves_timestamp`
    - `test_auth_error_skips_cycle`
    - `test_discrepancy_above_tolerance_writes_error_row`
    - `test_discrepancy_within_tolerance_no_error_row`

## Dev Notes

### Reconciliation Logic — Simplified Approach

The epics spec calls for comparing system-tracked clicks vs TikTok Shop reported commissions. Keep this SIMPLE:

**Aggregate comparison approach** (recommended — avoids complex per-video attribution):

```python
def _reconcile_commissions(
    session,
    account_id: str,
    orders: list,
    tolerance: float,
    now: datetime,
) -> None:
    """Compare aggregate system clicks vs TikTok order count for last 7 days."""
    from datetime import timedelta
    cutoff = now - timedelta(days=7)

    # Sum system-tracked clicks across all videos in last 7 days
    rows = (
        session.query(VideoMetric)
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .all()
    )
    system_clicks = sum(r.affiliate_clicks for r in rows)
    tiktok_order_count = len(orders)

    if system_clicks == 0 and tiktok_order_count == 0:
        return  # Both zero — no discrepancy

    ratio_diff = abs(system_clicks - tiktok_order_count) / max(1, system_clicks)
    if ratio_diff > tolerance:
        session.add(
            Error(
                account_id=account_id,
                agent="monetization",
                error_type="commission_discrepancy",
                message=(
                    f"Click/order discrepancy: system_clicks={system_clicks}, "
                    f"tiktok_orders={tiktok_order_count}, "
                    f"ratio_diff={ratio_diff:.3f} > tolerance={tolerance:.3f}"
                ),
            )
        )
```

### Reconciliation Guard Block in `monetization_node`

Insert AFTER the `video.affiliate_link` assignment and `session.commit()`, BEFORE the `return delta`:

```python
# Commission reconciliation — guarded by configurable interval
now_ts = time.time()
if now_ts - state.last_reconciliation_at >= config.reconciliation_interval_hours * 3600:
    try:
        orders = client.get_affiliate_orders(account_id=state.account_id)
        delta["affiliate_commission_week"] = sum(o.commission_amount for o in orders)
        now_dt = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        with get_session() as session:
            _reconcile_commissions(
                session,
                account_id=state.account_id,
                orders=orders,
                tolerance=config.commission_discrepancy_tolerance,
                now=now_dt,
            )
            session.commit()
        delta["last_reconciliation_at"] = now_ts
    except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError):
        pass  # Non-fatal: skip this cycle, preserve last_reconciliation_at
```

### Updated Import Block for `monetization.py`

```python
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import Error, Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState
```

Note: `uuid` is already imported. `AgentDecision` is NOT needed here (monetization doesn't write phase decisions).

### New `AccountConfig` Fields

Add to `tiktok_faceless/config.py` (after `archetype_min_sample_size`):

```python
reconciliation_interval_hours: int = Field(default=24, ge=1)
commission_discrepancy_tolerance: float = Field(default=0.10, ge=0.0, le=1.0)
```

### New `PipelineState` Field

Add to `tiktok_faceless/state.py` (after `affiliate_commission_week`):

```python
last_reconciliation_at: float = 0.0
```

### Key Implementation Details

**`last_reconciliation_at` in state**: Stores `time.time()` float (Unix timestamp). `0.0` means never reconciled — ensures reconciliation always runs on first invocation. Stored in PipelineState (in-memory, not DB) — acceptable since LangGraph state persists across cycles. If process restarts, reconciliation runs immediately (fine — safe to re-run).

**API error pattern**: Only `(TikTokAuthError, TikTokRateLimitError, TikTokAPIError)` caught — consistent with all other agents. Do NOT use bare `except Exception` here (the existing line 103 `except Exception` in Story 1.5 code is an accepted legacy pattern for the old commission poll, which will be replaced/subsumed by this story's implementation).

**Remove old commission poll**: The current lines 99–104 (`try: orders = client.get_affiliate_orders...`) in `monetization_node` should be REMOVED and replaced by the new guarded reconciliation block.

**Session pattern**: The affiliate-link block already uses `with get_session()`. The reconciliation uses a separate `with get_session()` for discrepancy detection. Single `session.commit()` per block.

**`CommissionRecord` structure**: From `tiktok.py`, `get_affiliate_orders()` returns `list[CommissionRecord]` with fields: `order_id`, `product_id`, `commission_amount`. The `len(orders)` gives TikTok-side order count.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/config.py` | Add `reconciliation_interval_hours`, `commission_discrepancy_tolerance` |
| `tiktok_faceless/state.py` | Add `last_reconciliation_at: float = 0.0` |
| `tiktok_faceless/agents/monetization.py` | Add `_reconcile_commissions`, update `monetization_node`, update imports |
| `tests/unit/agents/test_monetization.py` | Add `TestCommissionReconciliation` (7 tests) |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — `VideoMetric`, `Error` already have correct fields
- `tiktok_faceless/clients/tiktok.py` — `get_affiliate_orders()` works; no signature change needed
- `tiktok_faceless/db/queries.py` — no new query functions needed for this story
- Any other agent files

### Previous Story Learnings (Stories 4.1–4.4)

- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Pydantic defaults only — no env var wiring for threshold fields
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- Naive UTC datetimes: `datetime.now(tz=timezone.utc).replace(tzinfo=None)` throughout
- `TikTokAuthError` must be in every except clause catching API errors
- Non-fatal side effects: `except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError): pass`
- Single `session.commit()` at end of each `with get_session()` block
- `_MOD = "tiktok_faceless.agents.monetization"` at module level in test file
- Patch `TikTokAPIClient` at `f"{_MOD}.TikTokAPIClient"` (not at clients module)
- `session.add.call_args[0][0]` to get object passed to `session.add`
- `session.add.call_args_list` for multiple adds
- Move function-level imports to module level (quality reviewer lesson from 4.4)
- Remove `_select_hook_archetype` type patches from autouse fixtures (quality reviewer lesson from 4.4)

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 4.5
- Previous story: `_bmad-output/implementation-artifacts/4-4-hook-archetype-ab-performance-analysis.md`
- `monetization.py` current impl: `tiktok_faceless/agents/monetization.py`
- `Error` model: `tiktok_faceless/db/models.py` (has `account_id`, `agent`, `error_type`, `message`, `video_id`)
- `VideoMetric` model: `tiktok_faceless/db/models.py` (has `affiliate_clicks`)
- `CommissionRecord`: `tiktok_faceless/clients/tiktok.py` (fields: `order_id`, `product_id`, `commission_amount`)
- `AccountConfig`: `tiktok_faceless/config.py`
- `PipelineState`: `tiktok_faceless/state.py` (`affiliate_commission_week`, `last_reconciliation_at` new)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None required — implementation straightforward.

### Completion Notes List

- Replaced bare `except Exception` in old commission poll with narrowed `except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError)` per project conventions.
- Updated two existing `TestCommissionPolling` tests (`test_preserves_existing_commission_on_api_error`, `test_continues_pipeline_on_commission_polling_failure`) to use typed TikTok exceptions instead of bare `Exception`/`RuntimeError`, since the new code no longer catches generic exceptions.
- Added `all().return_value = []` to `_mock_session()` helper to support the reconciliation DB path in existing tests.
- `timedelta` import moved to module level (not inside function body) per project conventions.
- 19 monetization tests pass; 1 pre-existing failure in `test_graph.py` is unrelated.

### File List

- `tiktok_faceless/config.py`
- `tiktok_faceless/state.py`
- `tiktok_faceless/agents/monetization.py`
- `tests/unit/agents/test_monetization.py`
