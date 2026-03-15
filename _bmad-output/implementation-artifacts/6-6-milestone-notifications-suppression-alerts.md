# Story 6.6: Milestone Notifications & Suppression Alerts

Status: ready-for-dev

## Story

As the operator,
I want distinct visual callouts for first commission, phase transitions, and $1K/month milestone — and suppression alerts with auto-action confirmation,
So that meaningful moments are recognized and anomalies are unmissable without inducing panic.

## Acceptance Criteria

1. **Given** the first affiliate commission is recorded
   **When** the dashboard loads for the first time after this event
   **Then** a dismissible indigo banner renders: "First affiliate commission earned — $X.XX. The thesis is proven."
   **And** the banner only shows once per session via `st.session_state`

2. **Given** a phase transition occurred since the last dashboard load
   **When** the alert zone renders
   **Then** an indigo banner shows: "Phase changed: [from] → [to]. [Niche if applicable]. [View decision data]"

3. **Given** `active_suppression` is not None (suppression_detected error exists)
   **When** the alert zone renders
   **Then** a rose critical banner shows: "Suppression signal detected — FYP reach dropped [X]% in last [N]h. Publishing volume reduced automatically."
   **And** "Publishing volume reduced automatically" confirms the system already responded — no action required
   **And** the suppression banner is the highest-priority alert, shown above all other milestone banners

4. **Given** the $1,000/month commission threshold is crossed
   **When** the dashboard loads
   **Then** a milestone banner renders: "$1,000/month milestone reached. System is confirmed working."
   **And** the banner persists until dismissed (via `st.session_state.get("milestone_1k_dismissed")`)

## Tasks / Subtasks

- [ ] Task 1: Add three query functions to `tiktok_faceless/db/queries.py`
  - [ ] `get_first_commission_amount(session, account_id) -> float | None`
  - [ ] `get_latest_phase_transition(session, account_id) -> AgentDecision | None`
  - [ ] `get_monthly_revenue(session, account_id) -> float`

- [ ] Task 2: Create `dashboard/components/milestone_banner.py`
  - [ ] `render_first_commission_banner(amount: float) -> None`
  - [ ] `render_phase_transition_banner(decision: AgentDecision) -> None`
  - [ ] `render_milestone_1k_banner() -> None`
  - [ ] `render_milestone_banners(session, account_id: str) -> None` — orchestrator that calls query functions and conditionally renders each banner

- [ ] Task 3: Integrate banners into `dashboard/app.py`
  - [ ] Import `render_milestone_banners` from `dashboard.components.milestone_banner`
  - [ ] Add `get_first_commission_amount`, `get_latest_phase_transition`, `get_monthly_revenue` to the existing `with get_session() as session:` block in `app.py`
  - [ ] Call `render_milestone_banners(session, _ACCOUNT_ID)` in the alert zone, after suppression handling and before the 24h no-post warning

- [ ] Task 4: Write tests
  - [ ] `tests/unit/dashboard/test_queries_milestones.py` — 4 query tests
  - [ ] `tests/unit/dashboard/test_milestone_banner.py` — 4 banner logic tests

## Dev Notes

### Architecture Boundary (MUST NOT VIOLATE)

- `dashboard/` imports ONLY from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- NEVER import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, `tiktok_faceless.state`, or `tiktok_faceless.graph`
- All new query functions in `db/queries.py` are read-only — no `session.add()`, `session.commit()`, or `session.delete()` calls
- Banner components receive data as arguments, NOT session — they are pure display functions
- `render_milestone_banners` is the only function that accepts `session` in the component layer; it queries data and delegates to individual render functions

### Existing Infrastructure to Reuse (Do Not Duplicate)

| Item | Location | Notes |
|---|---|---|
| `get_active_suppression(session, account_id)` | `db/queries.py:428` | Already exists — returns most recent unresolved `suppression_detected` Error or None |
| `render_suppression_alert(suppression_error)` | `dashboard/components/suppression_alert.py` | Already exists from Story 6.2 — do NOT recreate |
| `get_kpi_revenue(session, account_id, days)` | `db/queries.py:463` | Joins VideoMetric + Product; use for `get_monthly_revenue` pattern reference |
| Alert zone wiring in `app.py` | `dashboard/app.py:74–86` | Existing: suppression → 24h no-post → unresolved errors → healthy |
| `_INDIGO = "#6366f1"` | Referenced in Story 6.5 decisions page | Reuse same color constant |

### Task 1: New Query Functions

All three functions go into `tiktok_faceless/db/queries.py`. Add after the existing `get_kpi_revenue` function (line 493). All imports (`func`, `Session`, `datetime`, `timedelta`, `AgentDecision`, `Product`, `Video`, `VideoMetric`) are already present at the top of the file.

#### `get_first_commission_amount`

Returns the total lifetime commission earned (sum of `affiliate_orders * commission_rate`) if greater than zero, otherwise `None`. "First commission" means the metric has ever been positive — this function is used to trigger the first-commission banner.

```python
def get_first_commission_amount(session: Session, account_id: str) -> float | None:
    """Return total lifetime commission for the account if > 0, else None.

    Used by dashboard to trigger the first-commission milestone banner.
    Returns None when no commission has ever been recorded.
    """
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("total")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    if result is None or result <= 0:
        return None
    return float(result)
```

#### `get_latest_phase_transition`

Returns the most recent `AgentDecision` with `decision_type == "phase_transition"` recorded within the last 24 hours, or `None`. The 24h window ensures the banner only surfaces for transitions that happened "recently" relative to the current dashboard session.

```python
def get_latest_phase_transition(session: Session, account_id: str) -> AgentDecision | None:
    """Return the most recent phase_transition AgentDecision within the last 24h, or None.

    Used by dashboard to trigger the phase-transition milestone banner.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        session.query(AgentDecision)
        .filter(
            AgentDecision.account_id == account_id,
            AgentDecision.decision_type == "phase_transition",
            AgentDecision.created_at >= cutoff,
        )
        .order_by(AgentDecision.created_at.desc())
        .first()
    )
```

#### `get_monthly_revenue`

Returns the sum of `affiliate_orders * commission_rate` for the current calendar month (UTC midnight of the 1st through now). Uses the same join pattern as `get_kpi_revenue`.

```python
def get_monthly_revenue(session: Session, account_id: str) -> float:
    """Return total commission revenue for the current calendar month (UTC).

    Used by dashboard to trigger the $1K/month milestone banner.
    Returns 0.0 if no revenue data exists.
    """
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("revenue")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= month_start,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    return float(result or 0.0)
```

### Task 2: `dashboard/components/milestone_banner.py`

Create this file. It contains all four functions.

```python
"""
Milestone notification banners — Story 6.6.

Renders dismissible and persistent indigo milestone banners in the dashboard alert zone.
Suppression alert rendering is delegated to suppression_alert.py (Story 6.2).
"""

import streamlit as st

from tiktok_faceless.db.models import AgentDecision
from tiktok_faceless.db.queries import (
    get_first_commission_amount,
    get_latest_phase_transition,
    get_monthly_revenue,
)

_INDIGO = "#6366f1"
_MILESTONE_1K_THRESHOLD = 1000.0

_FIRST_COMMISSION_SESSION_KEY = "first_commission_dismissed"
_PHASE_TRANSITION_SESSION_KEY = "phase_transition_shown"
_MILESTONE_1K_SESSION_KEY = "milestone_1k_dismissed"


def render_first_commission_banner(amount: float) -> None:
    """Render dismissible indigo first-commission banner.

    Only shows if not already dismissed this session.
    Sets st.session_state[_FIRST_COMMISSION_SESSION_KEY] = True on dismiss.
    """
    if st.session_state.get(_FIRST_COMMISSION_SESSION_KEY):
        return

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>First affiliate commission earned — ${amount:,.2f}. The thesis is proven.</strong>"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key="dismiss_first_commission"):
        st.session_state[_FIRST_COMMISSION_SESSION_KEY] = True
        st.rerun()


def render_phase_transition_banner(decision: AgentDecision) -> None:
    """Render indigo phase-transition banner for a recent AgentDecision.

    Does not persist — shows on every load until the 24h window expires
    (controlled by get_latest_phase_transition query).
    Uses session_state to avoid re-rendering within the same autorefresh cycle.
    """
    # Key includes decision id so a new transition clears the "seen" state
    session_key = f"{_PHASE_TRANSITION_SESSION_KEY}_{decision.id}"
    if st.session_state.get(session_key):
        return

    from_phase = decision.from_value or "unknown"
    to_phase = decision.to_value or "unknown"

    # Extract niche from rationale if present — rationale is free-text so we surface it directly
    niche_suffix = f"  \n*{decision.rationale}*" if decision.rationale else ""

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>Phase changed: {from_phase} → {to_phase}.</strong>{niche_suffix}"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key=f"dismiss_phase_{decision.id}"):
        st.session_state[session_key] = True
        st.rerun()


def render_milestone_1k_banner() -> None:
    """Render persistent $1K/month milestone banner until explicitly dismissed.

    Persists across autorefresh cycles until the operator clicks Dismiss.
    """
    if st.session_state.get(_MILESTONE_1K_SESSION_KEY):
        return

    banner_html = (
        f'<div style="border-left: 4px solid {_INDIGO}; '
        f'background: #eef2ff; padding: 12px 16px; border-radius: 4px; margin-bottom: 8px;">'
        f"<strong>$1,000/month milestone reached. System is confirmed working.</strong>"
        f"</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)
    if st.button("Dismiss", key="dismiss_milestone_1k"):
        st.session_state[_MILESTONE_1K_SESSION_KEY] = True
        st.rerun()


def render_milestone_banners(session, account_id: str) -> None:
    """Query milestone data and conditionally render all milestone banners.

    Call order (highest to lowest priority):
    1. Phase transition banner
    2. First commission banner
    3. $1K/month milestone banner

    Suppression banner is NOT rendered here — it is handled in app.py via
    render_suppression_alert() from suppression_alert.py (Story 6.2).
    """
    # Phase transition — check for recent transition
    try:
        phase_transition = get_latest_phase_transition(session, account_id)
    except Exception:
        phase_transition = None

    if phase_transition is not None:
        render_phase_transition_banner(phase_transition)

    # First commission — only if not dismissed this session
    if not st.session_state.get(_FIRST_COMMISSION_SESSION_KEY):
        try:
            commission_amount = get_first_commission_amount(session, account_id)
        except Exception:
            commission_amount = None

        if commission_amount is not None:
            render_first_commission_banner(commission_amount)

    # $1K/month milestone — only if not dismissed this session
    if not st.session_state.get(_MILESTONE_1K_SESSION_KEY):
        try:
            monthly_revenue = get_monthly_revenue(session, account_id)
        except Exception:
            monthly_revenue = 0.0

        if monthly_revenue >= _MILESTONE_1K_THRESHOLD:
            render_milestone_1k_banner()
```

Key rules:
- `_INDIGO = "#6366f1"` — matches the indigo used in Story 6.5 decisions page
- Each individual render function checks `st.session_state` before rendering — making them safe to call directly in tests without double-render risk
- The dismiss `st.button` uses a unique `key` per banner to avoid Streamlit duplicate-widget errors
- `st.rerun()` after dismiss so the banner disappears immediately without waiting for the 60s autorefresh
- `render_milestone_banners` wraps each query in `try/except` — a failing query must never crash the entire alert zone
- Phase transition banner uses `decision.id` in the session key so a new transition (new `id`) is always shown fresh even if a prior one was dismissed
- Do NOT import `get_active_suppression` here — suppression is handled upstream in `app.py`

### Task 3: Integration in `dashboard/app.py`

Modify `dashboard/app.py` to integrate milestone banners into the existing alert zone. Two changes required:

**Change 1 — Add import at module top:**

```python
from dashboard.components.milestone_banner import render_milestone_banners
```

Add this alongside the existing `from dashboard.components.suppression_alert import render_suppression_alert` import.

**Change 2 — Add queries to the existing session block:**

The existing session block (lines 37–44) fetches `phase`, `phase_started_at`, `last_post_time`, `videos_today`, `unresolved_errors`, `active_suppression`. Extend it to also fetch the three new milestone values:

```python
with get_session() as session:
    phase = get_account_phase(session, _ACCOUNT_ID)
    phase_started_at = get_phase_started_at(session, _ACCOUNT_ID)
    last_post_time = get_last_post_time(session, _ACCOUNT_ID)
    videos_today = get_videos_posted_today(session, _ACCOUNT_ID)
    unresolved_errors = get_unresolved_errors(session, _ACCOUNT_ID)
    active_suppression = get_active_suppression(session, _ACCOUNT_ID)
    # Story 6.6 — milestone data
    first_commission = get_first_commission_amount(session, _ACCOUNT_ID)
    phase_transition = get_latest_phase_transition(session, _ACCOUNT_ID)
    monthly_revenue = get_monthly_revenue(session, _ACCOUNT_ID)
```

Add `get_first_commission_amount`, `get_latest_phase_transition`, `get_monthly_revenue` to the existing import block from `tiktok_faceless.db.queries`.

**Change 3 — Extend the alert zone block:**

The existing alert zone (lines 74–86) is:

```python
# --- Alert Zone ---
_no_post_24h = last_post_time is None or (
    (datetime.utcnow() - last_post_time).total_seconds() > 86400
)

if active_suppression is not None:
    render_suppression_alert(active_suppression)
elif _no_post_24h:
    st.warning("No posts in 24h — pipeline may be stalled")
elif unresolved_errors:
    st.warning(f"{len(unresolved_errors)} unresolved error(s) — check the Errors tab")
else:
    st.success("All systems healthy · Last checked just now")
```

Replace with:

```python
# --- Alert Zone ---
_no_post_24h = last_post_time is None or (
    (datetime.utcnow() - last_post_time).total_seconds() > 86400
)

# Suppression is highest priority — shown instead of lower-level alerts
if active_suppression is not None:
    render_suppression_alert(active_suppression)
elif _no_post_24h:
    st.warning("No posts in 24h — pipeline may be stalled")
elif unresolved_errors:
    st.warning(f"{len(unresolved_errors)} unresolved error(s) — check the Errors tab")
else:
    st.success("All systems healthy · Last checked just now")

# Milestone banners render below the primary alert, independently of its state
_render_milestone_banners_inline(
    phase_transition=phase_transition,
    first_commission=first_commission,
    monthly_revenue=monthly_revenue,
)
```

Where `_render_milestone_banners_inline` is a local helper that avoids re-opening a session:

```python
def _render_milestone_banners_inline(
    phase_transition,
    first_commission: float | None,
    monthly_revenue: float,
) -> None:
    """Render milestone banners from already-fetched data (no new session needed)."""
    from dashboard.components.milestone_banner import (
        _MILESTONE_1K_THRESHOLD,
        _FIRST_COMMISSION_SESSION_KEY,
        _MILESTONE_1K_SESSION_KEY,
        render_first_commission_banner,
        render_milestone_1k_banner,
        render_phase_transition_banner,
    )

    if phase_transition is not None:
        render_phase_transition_banner(phase_transition)

    if first_commission is not None and not st.session_state.get(_FIRST_COMMISSION_SESSION_KEY):
        render_first_commission_banner(first_commission)

    if monthly_revenue >= _MILESTONE_1K_THRESHOLD and not st.session_state.get(_MILESTONE_1K_SESSION_KEY):
        render_milestone_1k_banner()
```

**Alternative (simpler) approach**: If the inline helper feels like over-engineering for a single file, `render_milestone_banners` in `milestone_banner.py` can accept the pre-fetched values directly instead of a session:

```python
def render_milestone_banners(
    phase_transition: AgentDecision | None,
    first_commission: float | None,
    monthly_revenue: float,
) -> None:
    """Render milestone banners from pre-fetched data."""
    ...
```

**Decision**: Use this signature variant — it keeps `milestone_banner.py` free of session dependencies, making it easier to test without a database. The orchestrating query calls stay in `app.py` where other queries already live. Update Task 2 above accordingly when implementing.

### Task 4: Tests

#### `tests/unit/dashboard/test_queries_milestones.py`

Use SQLite in-memory session via the same fixture pattern as other Story 6 tests (create engine with `Base.metadata.create_all`, yield a `Session`).

**4 required tests:**

```
test_get_first_commission_amount_returns_none_when_no_data
  — empty DB (no VideoMetric/Product rows) → returns None

test_get_first_commission_amount_returns_total_when_commission_exists
  — insert Video + Product (commission_rate=0.10) + VideoMetric (affiliate_orders=5)
  → returns 0.50 (5 * 0.10)
  Hint: must link tiktok_video_id on Video to video_id on VideoMetric, and product_id on both

test_get_latest_phase_transition_returns_none_when_no_recent_transition
  — insert AgentDecision with decision_type="phase_transition" but created_at = 48h ago
  → returns None (outside 24h window)

test_get_latest_phase_transition_returns_most_recent_within_24h
  — insert 2 phase_transition AgentDecisions within last 24h with different created_at
  → returns the most recently created one

test_get_monthly_revenue_returns_zero_when_no_data
  — empty DB → returns 0.0

test_get_monthly_revenue_returns_sum_for_current_month_only
  — insert VideoMetric rows: 2 in current month, 1 in prior month
  → returns sum only for current month rows; prior month row excluded

test_get_monthly_revenue_scoped_to_account_id
  — insert revenue rows for account_a and account_b
  → querying account_a returns only account_a revenue

test_get_first_commission_amount_returns_none_when_commission_is_zero
  — insert VideoMetric with affiliate_orders=0 → returns None (not > 0)
```

Note: Only 4 tests are required per the story spec. Choose the four that provide the best coverage:
1. `test_get_first_commission_amount_returns_none_when_no_data`
2. `test_get_first_commission_amount_returns_total_when_commission_exists`
3. `test_get_latest_phase_transition_returns_none_when_no_recent_transition`
4. `test_get_monthly_revenue_returns_sum_for_current_month_only`

The additional four above are strongly recommended but optional.

#### `tests/unit/dashboard/test_milestone_banner.py`

Use `unittest.mock.patch` to mock Streamlit calls. No live session needed. Mock `st.markdown`, `st.button`, `st.session_state`.

**4 required tests:**

```
test_render_first_commission_banner_skipped_when_dismissed
  — set st.session_state["first_commission_dismissed"] = True
  — call render_first_commission_banner(5.00)
  → st.markdown NOT called

test_render_first_commission_banner_shows_amount
  — st.session_state is empty (not dismissed)
  — call render_first_commission_banner(12.50)
  → st.markdown called once; call args contain "$12.50"

test_render_milestone_1k_banner_skipped_when_dismissed
  — set st.session_state["milestone_1k_dismissed"] = True
  — call render_milestone_1k_banner()
  → st.markdown NOT called

test_render_phase_transition_banner_shows_from_to_values
  — create AgentDecision(id=1, from_value="warmup", to_value="tournament", agent="orchestrator",
      rationale="Winner detected", decision_type="phase_transition", account_id="acc1",
      created_at=datetime.utcnow())
  — st.session_state is empty
  — call render_phase_transition_banner(decision)
  → st.markdown called; args contain "warmup → tournament"
```

### New Files to Create / Modify

| File | Action | Purpose |
|---|---|---|
| `tiktok_faceless/db/queries.py` | Modify — add 3 functions | `get_first_commission_amount`, `get_latest_phase_transition`, `get_monthly_revenue` |
| `dashboard/components/milestone_banner.py` | Create | Milestone banner render functions |
| `dashboard/app.py` | Modify — extend session block + alert zone | Wire milestone queries and banners |
| `tests/unit/dashboard/test_queries_milestones.py` | Create | Query unit tests (4 required) |
| `tests/unit/dashboard/test_milestone_banner.py` | Create | Banner logic unit tests (4 required) |

### Model Field Reference

**`AgentDecision`** (`agent_decisions` table) — used by `get_latest_phase_transition`:

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Auto PK — use in session key for banner deduplication |
| `account_id` | `str` | Filter key |
| `agent` | `str` | e.g. `"orchestrator"` |
| `decision_type` | `str` | Filter for `"phase_transition"` |
| `from_value` | `str \| None` | Previous phase (nullable) |
| `to_value` | `str \| None` | New phase (nullable) |
| `rationale` | `str` | Human-readable; show in banner body |
| `created_at` | `datetime` | Filter by >= 24h cutoff; order DESC |

**`VideoMetric`** — used by `get_first_commission_amount` and `get_monthly_revenue`:

| Field | Type | Notes |
|---|---|---|
| `video_id` | `str` | Join to `Video.tiktok_video_id` |
| `account_id` | `str` | Filter key |
| `recorded_at` | `datetime` | Filter for monthly window |
| `affiliate_orders` | `int` | Multiply by `Product.commission_rate` |

**`Product`** — joined by both commission queries:

| Field | Type | Notes |
|---|---|---|
| `account_id` | `str` | Join condition |
| `product_id` | `str` | Join condition via `Video.product_id` |
| `commission_rate` | `float` | Multiplier for revenue calculation |

### Session State Keys Reference

| Key | Set When | Effect |
|---|---|---|
| `"first_commission_dismissed"` | Operator clicks Dismiss on first-commission banner | Banner hidden for rest of session |
| `"phase_transition_shown_{decision.id}"` | Operator clicks Dismiss on phase-transition banner | That specific transition banner hidden |
| `"milestone_1k_dismissed"` | Operator clicks Dismiss on $1K banner | Banner hidden for rest of session |

### Banner Priority Order (in app.py alert zone)

```
1. Suppression alert (rose/critical) — render_suppression_alert() from Story 6.2
   ↓ (suppression replaces the primary alert, but milestone banners ALWAYS render below)
2. Phase transition banner (indigo) — most operationally significant positive event
3. First commission banner (indigo) — once-per-session; only if not dismissed
4. $1K/month milestone banner (indigo) — persists until dismissed
```

Suppression is gated in the `if/elif/else` block — it replaces the green healthy/yellow warning state. Milestone banners render independently below that block, so they appear alongside (not instead of) operational alerts.

### Project Conventions

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length <= 100 chars
- No bare `except` at module top level — individual render functions use session_state guards, not try/except; `render_milestone_banners` uses try/except per query only
- No function-level imports — all imports at module top (exception: the inline `_render_milestone_banners_inline` helper in `app.py` may use local imports to avoid circular issues, but prefer restructuring to avoid this)
- `datetime.utcnow()` for naive UTC timestamps throughout
- All query functions accept `session: Session` as first arg and `account_id: str` as second
- Run `uv run pytest tests/unit/ -q` before marking done
- Run `uv run ruff check tiktok_faceless/db/queries.py dashboard/components/milestone_banner.py dashboard/app.py tests/unit/dashboard/` after implementation

### Dependencies

- `streamlit` — already present (Story 6.1)
- No new `pyproject.toml` entries needed
- Story 6.2 must be complete — `dashboard/components/suppression_alert.py` must exist (confirmed: present)
- Story 6.5 must be complete — `dashboard/pages/decisions.py` and `dashboard/pages/errors.py` should exist; no direct dependency but same Epic 6 test infrastructure is reused

### References

- Epic 6, Story 6.6 spec: `_bmad-output/planning-artifacts/epics.md` (lines 1174–1204)
- DB models: `tiktok_faceless/db/models.py` — `AgentDecision` (line 108), `VideoMetric` (line 58), `Product` (line 87)
- Existing queries: `tiktok_faceless/db/queries.py` — `get_kpi_revenue()` (line 463) for join pattern reference; `get_active_suppression()` (line 428); `get_phase_started_at()` (line 360)
- Existing alert zone: `dashboard/app.py` (lines 74–86)
- Suppression component: `dashboard/components/suppression_alert.py` (Story 6.2)
- Prior story spec: `_bmad-output/implementation-artifacts/6-5-decision-audit-log-error-log.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
