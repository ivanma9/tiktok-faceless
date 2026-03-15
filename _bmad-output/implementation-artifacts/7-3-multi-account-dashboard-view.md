# Story 7.3: Multi-Account Dashboard View

Status: ready-for-dev

## Story

As the operator,
I want both accounts visible in the dashboard with their own phase, pipeline health, and revenue summary,
so that I can monitor the full portfolio from a single URL without switching between views.

## Acceptance Criteria

1. **Given** two or more accounts exist in the `accounts` table (phase != "archived")
   **When** the dashboard loads
   **Then** a sidebar account selector lists all provisioned accounts by `account_id`
   **And** the selected account defaults to the first account in alphabetical order

2. **Given** an account is selected in the sidebar
   **When** any dashboard component reads `st.session_state["selected_account_id"]`
   **Then** all dashboard views (top bar, KPI strip, agent panel, video table, tournament table) show only that account's data
   **And** no data from any other account is mixed in

3. **Given** the operator views the main dashboard page
   **When** the multi-account summary table renders at the top of the main view
   **Then** one summary row appears per active account with the following columns:
   - **Account ID** — string identifier
   - **Phase** — colored badge (indigo=commit/scale, amber=tournament, zinc=warmup)
   - **Status** — green dot if no unresolved errors; red dot if any unresolved errors
   - **Revenue Today** — sum of commission revenue since UTC midnight, formatted as `$0.00`
   - **Last Post** — human-readable time-ago (e.g. "3h 12m ago") or "Never"

4. **Given** account #1 is in `commit` phase and account #2 is in `warmup` phase
   **When** the summary table renders
   **Then** account #1's phase badge is indigo and account #2's is zinc
   **And** each phase badge reflects only that account's independent `phase` field in the DB

5. **Given** account #1 has unresolved errors and account #2 does not
   **When** the summary table renders
   **Then** account #1's status shows a red dot and account #2's shows a green dot

## Tasks / Subtasks

- [ ] Task 1: Add `get_account_summary_row` to `tiktok_faceless/db/queries.py`
  - [ ] Signature: `get_account_summary_row(session: Session, account_id: str) -> dict`
  - [ ] Return dict with keys: `account_id`, `phase`, `pipeline_healthy`, `revenue_today`, `last_post_timedelta`
  - [ ] `phase`: read from `Account.phase` column via `session.query(Account).filter_by(account_id=account_id).first()`; return `"unknown"` if account not found
  - [ ] `pipeline_healthy`: `True` if `get_unresolved_errors(session, account_id)` returns an empty list, else `False`
  - [ ] `revenue_today`: sum of `VideoMetric.affiliate_orders * Product.commission_rate` where `VideoMetric.recorded_at >= today_utc_midnight` and `VideoMetric.account_id == account_id`; return `0.0` if no rows
  - [ ] `last_post_timedelta`: `datetime.utcnow() - Video.posted_at` for the most recently posted video (where `Video.posted_at is not None` and `Video.account_id == account_id`); return `None` if no posted video exists

- [ ] Task 2: Update `dashboard/app.py` to support multi-account selection
  - [ ] Add `get_active_accounts` to the imports from `tiktok_faceless.db.queries`
  - [ ] Add `get_account_summary_row` to the imports from `tiktok_faceless.db.queries`
  - [ ] Add `render_account_summary_table` import from `dashboard.components.account_summary_table`
  - [ ] Remove the `_ACCOUNT_ID = os.environ.get("TIKTOK_ACCOUNT_ID", "default")` line
  - [ ] In a `with get_session() as session:` block at startup, call `get_active_accounts(session)` to build `account_ids: list[str]`; if empty, call `st.warning("No active accounts found")` and `st.stop()`
  - [ ] Add sidebar selector: `st.sidebar.selectbox("Account", account_ids, key="selected_account_id")` — Streamlit stores the value in `st.session_state["selected_account_id"]` automatically
  - [ ] If `"selected_account_id"` is not yet in `st.session_state`, initialize it to `account_ids[0]`
  - [ ] Replace all hardcoded `_ACCOUNT_ID` references in the data-fetch block with `st.session_state["selected_account_id"]`
  - [ ] Build the summary list: for each account_id in `account_ids`, call `get_account_summary_row(session, account_id)` within the existing `with get_session() as session:` block; store as `summaries: list[dict]`
  - [ ] Call `render_account_summary_table(summaries)` immediately after `st.title("TikTok Faceless Dashboard")` and before any other content

- [ ] Task 3: Create `dashboard/components/account_summary_table.py`
  - [ ] Implement `render_account_summary_table(summaries: list[dict]) -> None`
  - [ ] Import only: `from datetime import timedelta` and `import streamlit as st`; no imports from `tiktok_faceless`
  - [ ] Render a `st.subheader("Portfolio Overview")` above the table
  - [ ] For each summary dict in `summaries`, build a display row with 5 columns using `st.columns([2, 2, 1, 2, 2])`
  - [ ] Column 1 — Account ID: `st.markdown(summary["account_id"])`
  - [ ] Column 2 — Phase badge: use `_phase_badge(phase: str) -> str` helper that returns inline HTML `<span style="...">phase</span>`; render with `st.markdown(..., unsafe_allow_html=True)` — see badge colors below
  - [ ] Column 3 — Status dot: green circle if `summary["pipeline_healthy"]` else red circle using `st.markdown`
  - [ ] Column 4 — Revenue Today: `st.markdown(f"${summary['revenue_today']:,.2f}")`
  - [ ] Column 5 — Last Post: call `_format_timedelta(summary["last_post_timedelta"])` and `st.markdown(result)`
  - [ ] Implement `_phase_badge(phase: str) -> str` private helper:
    - `commit` or `scale` → indigo: `background:#6366f1; color:#fff`
    - `tournament` → amber: `background:#f59e0b; color:#000`
    - `warmup` → zinc: `background:#71717a; color:#fff`
    - all others → zinc fallback
    - Return: `f'<span style="padding:2px 8px;border-radius:4px;font-size:0.85em;background:{bg};color:{fg}">{phase}</span>'`
  - [ ] Implement `_format_timedelta(td: timedelta | None) -> str` private helper:
    - Returns `"Never"` if `td is None`
    - Computes total seconds; returns `"{h}h {m}m ago"` format where `h = int(td.total_seconds() // 3600)` and `m = int((td.total_seconds() % 3600) // 60)`
    - If under 1 minute: return `"just now"`

- [ ] Task 4: Tests in `tests/unit/db/test_queries_account_summary.py`
  - [ ] Use `pytest` with SQLAlchemy in-memory SQLite session fixture (same pattern as existing tests in `tests/unit/db/`)
  - [ ] All imports at module level — no function-level imports
  - [ ] `test_get_account_summary_row_returns_correct_phase` — seed one Account with `phase="tournament"` → `result["phase"] == "tournament"`
  - [ ] `test_get_account_summary_row_pipeline_healthy_true` — no Error rows for account → `result["pipeline_healthy"] is True`
  - [ ] `test_get_account_summary_row_pipeline_healthy_false` — seed one unresolved Error row (no `resolved_at`) → `result["pipeline_healthy"] is False`
  - [ ] `test_get_account_summary_row_revenue_today` — seed a VideoMetric row recorded today with `affiliate_orders=2` joined to a Product with `commission_rate=5.0` → `result["revenue_today"] == 10.0`
  - [ ] `test_get_account_summary_row_revenue_today_excludes_yesterday` — seed a VideoMetric row recorded yesterday → `result["revenue_today"] == 0.0`
  - [ ] `test_get_account_summary_row_last_post_timedelta_is_timedelta` — seed a Video with `posted_at` set to 2 hours ago → `isinstance(result["last_post_timedelta"], timedelta)` and `result["last_post_timedelta"].total_seconds()` is approximately 7200 (within a few seconds)
  - [ ] `test_get_account_summary_row_last_post_timedelta_none` — no Video rows → `result["last_post_timedelta"] is None`
  - [ ] `test_get_account_summary_row_unknown_account` — account_id not in DB → `result["phase"] == "unknown"` and `result["pipeline_healthy"] is True` and `result["revenue_today"] == 0.0` and `result["last_post_timedelta"] is None`

- [ ] Task 5: Tests in `tests/unit/dashboard/test_account_summary_table.py`
  - [ ] All imports at module level — no function-level imports
  - [ ] Mock `streamlit` before importing the component (use `unittest.mock.patch` or `sys.modules` stub)
  - [ ] `test_render_account_summary_table_calls_subheader` — call `render_account_summary_table([])` → assert `st.subheader` was called with `"Portfolio Overview"`
  - [ ] `test_render_account_summary_table_one_row_per_summary` — pass two summary dicts → assert `st.columns` was called twice (once per row)
  - [ ] `test_phase_badge_indigo_for_commit` — call `_phase_badge("commit")` directly → assert `"#6366f1"` in return value
  - [ ] `test_phase_badge_indigo_for_scale` — call `_phase_badge("scale")` → assert `"#6366f1"` in return value
  - [ ] `test_phase_badge_amber_for_tournament` — call `_phase_badge("tournament")` → assert `"#f59e0b"` in return value
  - [ ] `test_phase_badge_zinc_for_warmup` — call `_phase_badge("warmup")` → assert `"#71717a"` in return value
  - [ ] `test_format_timedelta_none_returns_never` — call `_format_timedelta(None)` → `== "Never"`
  - [ ] `test_format_timedelta_hours_and_minutes` — call `_format_timedelta(timedelta(hours=3, minutes=12))` → `== "3h 12m ago"`
  - [ ] `test_format_timedelta_under_one_minute` — call `_format_timedelta(timedelta(seconds=45))` → `== "just now"`

## Dev Notes

### `get_account_summary_row` Implementation Pattern

```python
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from tiktok_faceless.db.models import Account, Video, VideoMetric, Product

def get_account_summary_row(session: Session, account_id: str) -> dict:
    """Return a summary dict for one account for the dashboard portfolio table."""
    account = session.query(Account).filter_by(account_id=account_id).first()
    if account is None:
        return {
            "account_id": account_id,
            "phase": "unknown",
            "pipeline_healthy": True,
            "revenue_today": 0.0,
            "last_post_timedelta": None,
        }

    # phase
    phase = account.phase

    # pipeline_healthy — reuse existing get_unresolved_errors
    errors = get_unresolved_errors(session, account_id)
    pipeline_healthy = len(errors) == 0

    # revenue_today — UTC midnight cutoff
    now = datetime.utcnow()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    revenue_result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("rev")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= today_midnight,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    revenue_today = float(revenue_result or 0.0)

    # last_post_timedelta
    last_video = (
        session.query(Video)
        .filter(
            Video.account_id == account_id,
            Video.posted_at.isnot(None),
        )
        .order_by(Video.posted_at.desc())
        .first()
    )
    last_post_timedelta = (now - last_video.posted_at) if last_video is not None else None

    return {
        "account_id": account_id,
        "phase": phase,
        "pipeline_healthy": pipeline_healthy,
        "revenue_today": revenue_today,
        "last_post_timedelta": last_post_timedelta,
    }
```

### Sidebar Selector Pattern in `app.py`

The Streamlit `selectbox` with a `key` parameter automatically writes the selected value to `st.session_state`. The correct pattern is:

```python
with get_session() as session:
    accounts = get_active_accounts(session)
    account_ids = [a.account_id for a in accounts]
    summaries = [get_account_summary_row(session, aid) for aid in account_ids]

if not account_ids:
    st.warning("No active accounts found")
    st.stop()

if "selected_account_id" not in st.session_state:
    st.session_state["selected_account_id"] = account_ids[0]

st.sidebar.selectbox("Account", account_ids, key="selected_account_id")
selected_account_id = st.session_state["selected_account_id"]
```

All existing data-fetch calls that previously used `_ACCOUNT_ID` must use `selected_account_id` instead. The `os.environ.get("TIKTOK_ACCOUNT_ID", "default")` line is removed entirely — account selection is driven by the DB and sidebar, not by env var.

### `render_account_summary_table` Full Implementation Pattern

```python
"""Account summary table component — Story 7.3."""

from datetime import timedelta

import streamlit as st


def _phase_badge(phase: str) -> str:
    _PHASE_COLORS = {
        "commit": ("#6366f1", "#fff"),
        "scale": ("#6366f1", "#fff"),
        "tournament": ("#f59e0b", "#000"),
        "warmup": ("#71717a", "#fff"),
    }
    bg, fg = _PHASE_COLORS.get(phase, ("#71717a", "#fff"))
    return (
        f'<span style="padding:2px 8px;border-radius:4px;font-size:0.85em;'
        f'background:{bg};color:{fg}">{phase}</span>'
    )


def _format_timedelta(td: timedelta | None) -> str:
    if td is None:
        return "Never"
    total_seconds = td.total_seconds()
    if total_seconds < 60:
        return "just now"
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    return f"{h}h {m}m ago"


def render_account_summary_table(summaries: list[dict]) -> None:
    st.subheader("Portfolio Overview")
    for summary in summaries:
        cols = st.columns([2, 2, 1, 2, 2])
        with cols[0]:
            st.markdown(summary["account_id"])
        with cols[1]:
            st.markdown(_phase_badge(summary["phase"]), unsafe_allow_html=True)
        with cols[2]:
            dot = "🟢" if summary["pipeline_healthy"] else "🔴"
            st.markdown(dot)
        with cols[3]:
            st.markdown(f"${summary['revenue_today']:,.2f}")
        with cols[4]:
            st.markdown(_format_timedelta(summary["last_post_timedelta"]))
```

### Architecture Constraints

- `dashboard/` components and pages may only import from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries` — never from `tiktok_faceless.db.models` or any agent/pipeline modules
- `dashboard/components/account_summary_table.py` has **zero** imports from `tiktok_faceless` — all data arrives via the `summaries` list of plain dicts
- Dashboard components must not annotate types using ORM model types (e.g. do not use `Account` as a type hint in any dashboard file)
- All imports in test files must be at module level — no imports inside test functions or fixtures

### Test Fixture Pattern (db tests)

Follow the existing pattern from `tests/unit/db/` for the SQLite in-memory session. Seed data by instantiating ORM model objects and adding them to the session. Example:

```python
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Base, Account, Video, VideoMetric, Product, Error
from tiktok_faceless.db.queries import get_account_summary_row


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
```

### Test Pattern for Dashboard Component (Streamlit mock)

Because `streamlit` runs with a server context, mock it at import time:

```python
import sys
from unittest.mock import MagicMock, patch
from datetime import timedelta

# Mock streamlit before importing component
sys.modules["streamlit"] = MagicMock()
import streamlit as st

from dashboard.components.account_summary_table import (
    render_account_summary_table,
    _phase_badge,
    _format_timedelta,
)
```

Reset the mock between tests using `st.reset_mock()` in a `setup_method` or `autouse` fixture.

### `revenue_today` Query: Join Chain

The revenue join requires three tables:
- `VideoMetric` (has `account_id`, `video_id`, `affiliate_orders`, `recorded_at`)
- `Video` (joins `VideoMetric.video_id == Video.tiktok_video_id`; has `product_id`, `account_id`)
- `Product` (joins on `Product.account_id == Video.account_id AND Product.product_id == Video.product_id`; has `commission_rate`)

This is the same pattern used in `get_monthly_revenue`. The only difference is the time filter: today's UTC midnight rather than start of month.

### No DB Schema Changes

No Alembic migration is required. All data for `get_account_summary_row` comes from existing columns in `accounts`, `videos`, `video_metrics`, `products`, and `errors` tables.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/db/queries.py` | Add `get_account_summary_row(session, account_id) -> dict` |
| `dashboard/app.py` | Add sidebar selector; replace `_ACCOUNT_ID`; add summary table call |
| `dashboard/components/account_summary_table.py` | New — `render_account_summary_table`, `_phase_badge`, `_format_timedelta` |
| `tests/unit/db/test_queries_account_summary.py` | New — 8 tests for `get_account_summary_row` |
| `tests/unit/dashboard/test_account_summary_table.py` | New — 9 tests for component and helpers |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — no schema changes needed
- `dashboard/pages/overview.py` and other page files — they already read `st.session_state.get("account_id", "")` but should be updated to read `st.session_state.get("selected_account_id", "")` — check if the key name is already consistent before changing
- `dashboard/components/kpi_strip.py` — no changes; it already accepts `account_id` as a parameter
- Any agent or pipeline files

### Key: `account_id` vs `selected_account_id` in session_state

The existing `overview.py` reads `st.session_state.get("account_id", "")`. After this story, the canonical key is `st.session_state["selected_account_id"]`. When updating `app.py`, also verify whether `overview.py` and other pages need to be updated to read `selected_account_id` instead of `account_id`. If they do, update all dashboard page files consistently.

### Project Conventions

- Import sort: stdlib → third-party → local
- Line length <= 100 characters
- No bare `except` without specific exception type in production code
- Run `uv run pytest tests/unit/ -q` to verify no regressions after implementation

## References

- `tiktok_faceless/db/models.py` — `Account` (lines 19–33), `Video` (lines 36–56), `VideoMetric` (lines 58–84), `Product` (lines 87–105), `Error` (lines 128–141)
- `tiktok_faceless/db/queries.py` — `get_unresolved_errors`, `get_monthly_revenue` (revenue join pattern), `get_active_accounts`
- `dashboard/app.py` — existing top-bar data-fetch block and component call pattern
- `dashboard/components/kpi_strip.py` — component function signature pattern (`render_kpi_strip(session, account_id)`)
- `dashboard/pages/overview.py` — `st.session_state.get("account_id", "")` pattern (key may need updating)
- Story 7.1 spec: `_bmad-output/implementation-artifacts/7-1-isolated-multi-account-pipeline-execution.md` — `get_active_accounts` definition and return type
- Epics.md: Story 7.3 description

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
