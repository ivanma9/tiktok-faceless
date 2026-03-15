# Story 6.5: Decision Audit Log & Error Log

Status: ready-for-dev

## Story

As the operator,
I want dedicated views for the agent decision audit log and error log,
So that I can review every autonomous decision the system made and diagnose any failures without digging through raw database queries.

## Acceptance Criteria

1. **Given** the operator navigates to the Decisions section
   **When** the decision audit log renders
   **Then** all `agent_decisions` rows for the `account_id` display in reverse-chronological order
   **And** each row shows: decision type (plain-English label), timestamp, summary (agent + from_value → to_value or rationale), and an expandable detail section with the raw `supporting_data` JSON
   **And** phase transitions (`decision_type == "phase_transition"`) are highlighted with an indigo left-border badge

2. **Given** the operator navigates to the Errors section
   **When** the error log renders
   **Then** all unresolved `errors` rows (where `resolved_at IS NULL`) display with: agent name, error type, plain-English message, `recovery_suggestion`, and timestamp
   **And** resolved errors are rendered inside a collapsed `st.expander("Resolved errors (N)")` — not cluttering the active view

3. **Given** there are no unresolved errors
   **When** the error log section renders
   **Then** a green "No active errors" message is shown via `st.success()`

4. **Given** no `agent_decisions` rows exist for the account
   **When** the decision audit log renders
   **Then** an `st.info("No decisions recorded yet.")` message is shown — no error thrown

## Tasks / Subtasks

- [ ] Task 1: Add new query functions to `tiktok_faceless/db/queries.py`
  - [ ] `get_agent_decisions(session, account_id, limit=100) -> list[AgentDecision]`
  - [ ] `get_resolved_errors(session, account_id, limit=50) -> list[Error]`

- [ ] Task 2: Implement `dashboard/pages/decisions.py` (replace stub)
  - [ ] Define module-level `DECISION_TYPE_LABELS: dict[str, str]`
  - [ ] `_format_summary(decision: AgentDecision) -> str` helper
  - [ ] `render_decisions_page(session, account_id: str) -> None`

- [ ] Task 3: Implement `dashboard/pages/errors.py` (replace stub)
  - [ ] `render_errors_page(session, account_id: str) -> None`

- [ ] Task 4: Write tests in `tests/unit/dashboard/`
  - [ ] `tests/unit/dashboard/test_queries_decisions.py`
  - [ ] `tests/unit/dashboard/test_decisions_page.py`
  - [ ] `tests/unit/dashboard/test_errors_page.py`

## Dev Notes

### Architecture Boundary (MUST NOT VIOLATE)

- `dashboard/` imports ONLY from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- NEVER import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, `tiktok_faceless.state`, or `tiktok_faceless.graph`
- All new query functions in `db/queries.py` are read-only — no `session.add()`, `session.commit()`, or `session.delete()` calls
- Pages receive `session` and `account_id` from the caller (same pattern as `overview.py` in Story 6.4)

### Existing Functions to Reuse (Do Not Duplicate)

| Function | Location | Used By |
|---|---|---|
| `get_active_errors(session, account_id)` | `db/queries.py:270` | Already exists — returns unresolved `Error` rows |
| `get_unresolved_errors(session, account_id)` | `db/queries.py:376` | Already exists — identical semantics; prefer this one (typed return) |
| `get_phase_started_at(session, account_id)` | `db/queries.py:360` | Not used here — reference only |

Note: `get_active_errors` (line 270) and `get_unresolved_errors` (line 376) both return unresolved errors. Use `get_unresolved_errors` in `errors.py` — it has a typed return `list[Error]` and is the preferred function going forward.

### Task 1: New Query Functions

#### `get_agent_decisions`

```python
def get_agent_decisions(
    session: Session,
    account_id: str,
    limit: int = 100,
) -> list[AgentDecision]:
    """Return agent_decisions rows for the account, newest first, up to limit.

    Used by dashboard/pages/decisions.py to render the decision audit log.
    """
    return (
        session.query(AgentDecision)
        .filter(AgentDecision.account_id == account_id)
        .order_by(AgentDecision.created_at.desc())
        .limit(limit)
        .all()
    )
```

#### `get_resolved_errors`

```python
def get_resolved_errors(
    session: Session,
    account_id: str,
    limit: int = 50,
) -> list[Error]:
    """Return resolved Error rows (resolved_at IS NOT NULL) for the account, newest first.

    Used by dashboard/pages/errors.py to populate the collapsed resolved-errors expander.
    """
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.resolved_at.isnot(None),
        )
        .order_by(Error.timestamp.desc())
        .limit(limit)
        .all()
    )
```

Add both functions to `tiktok_faceless/db/queries.py` after the existing `get_unresolved_errors` function (line 386). Add `AgentDecision` and `Error` are already imported at line 16.

### Task 2: `dashboard/pages/decisions.py`

#### `DECISION_TYPE_LABELS`

Maps raw `decision_type` database values to plain-English strings. This dict must be defined at module level so tests can import and assert against it directly.

```python
DECISION_TYPE_LABELS: dict[str, str] = {
    "phase_transition": "Phase Transition",
    "niche_commit": "Niche Committed",
    "niche_decay_detected": "Niche Decay Detected",
    "retournament_triggered": "Re-tournament Triggered",
    "kill_switch": "Kill Switch Activated",
    "promoted": "Video Promoted",
    "suppression_detected": "Suppression Detected",
    "product_selected": "Product Selected",
    "product_eliminated": "Product Eliminated",
    "archetype_selected": "Hook Archetype Selected",
    "commission_discrepancy": "Commission Discrepancy",
    "pipeline_resumed": "Pipeline Resumed",
}
```

Unknown `decision_type` values not in the dict must fall back to the raw value rendered in title-case: `decision_type.replace("_", " ").title()`.

#### `_format_summary`

```python
def _format_summary(decision: AgentDecision) -> str:
    """Return a one-line human-readable summary of the decision.

    For phase transitions: "orchestrator: warmup → tournament"
    For all others: first 120 chars of rationale.
    """
    if decision.from_value and decision.to_value:
        return f"{decision.agent}: {decision.from_value} → {decision.to_value}"
    return (decision.rationale or "")[:120]
```

#### `render_decisions_page`

Full implementation pattern:

```python
import json

import streamlit as st

from tiktok_faceless.db.models import AgentDecision
from tiktok_faceless.db.queries import get_agent_decisions

DECISION_TYPE_LABELS: dict[str, str] = { ... }  # as above

_PHASE_TRANSITION_KEY = "phase_transition"
_INDIGO = "#6366f1"


def _format_summary(decision: AgentDecision) -> str:
    ...  # as above


def render_decisions_page(session, account_id: str) -> None:
    st.header("Decision Audit Log")

    try:
        decisions = get_agent_decisions(session, account_id)
    except Exception as e:
        st.error(f"Failed to load decisions: {e}")
        return

    if not decisions:
        st.info("No decisions recorded yet.")
        return

    for decision in decisions:
        label = DECISION_TYPE_LABELS.get(
            decision.decision_type,
            decision.decision_type.replace("_", " ").title(),
        )
        summary = _format_summary(decision)
        ts = decision.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")

        is_phase_transition = decision.decision_type == _PHASE_TRANSITION_KEY

        if is_phase_transition:
            # Indigo left-border highlight via markdown HTML
            header_html = (
                f'<div style="border-left: 4px solid {_INDIGO}; padding-left: 10px;">'
                f"<strong>{label}</strong> &nbsp;|&nbsp; {ts}<br/>"
                f"<span style='color:{_INDIGO};'>{summary}</span>"
                f"</div>"
            )
            st.markdown(header_html, unsafe_allow_html=True)
        else:
            st.markdown(f"**{label}** &nbsp;|&nbsp; {ts}  \n{summary}")

        if decision.supporting_data:
            with st.expander("View supporting data"):
                try:
                    parsed = json.loads(decision.supporting_data)
                    st.json(parsed)
                except (ValueError, TypeError):
                    st.code(decision.supporting_data, language="text")

        st.divider()
```

Key rules:
- Each decision is rendered as inline markdown, NOT as a `st.dataframe` row — the expandable JSON detail requires per-row `st.expander`
- Phase transitions use indigo left-border HTML rendered via `st.markdown(..., unsafe_allow_html=True)`
- `supporting_data` is stored as a JSON string in the DB (nullable). Attempt `json.loads()` and use `st.json()` for pretty rendering; fall back to `st.code()` if parsing fails
- Wrap the entire function body in `try/except` at the query level only — individual row rendering errors should propagate (they won't crash the page due to Streamlit's own exception handling)
- Import `json` from stdlib; `AgentDecision` from `tiktok_faceless.db.models`; `get_agent_decisions` from `tiktok_faceless.db.queries`

### Task 3: `dashboard/pages/errors.py`

Full implementation pattern:

```python
import streamlit as st

from tiktok_faceless.db.queries import get_resolved_errors, get_unresolved_errors

_ERROR_TYPE_LABELS: dict[str, str] = {
    "ElevenLabsError": "ElevenLabs TTS failure",
    "VideoAssemblyError": "Video assembly failure",
    "TikTokUploadError": "TikTok upload failure",
    "TikTokAuthError": "TikTok authentication error",
    "ProductResearchError": "Product research failure",
    "AnalyticsError": "Analytics fetch failure",
    "suppression_detected": "Suppression signal detected",
    "commission_discrepancy": "Commission discrepancy detected",
    "ScriptGenerationError": "Script generation failure",
    "MonetizationError": "Monetization check failure",
}

_GREEN = "#10b981"


def _plain_message(error) -> str:
    """Return the plain-English version of error.message (already human-readable from agents)."""
    return error.message or error.error_type


def _render_error_row(error, resolved: bool = False) -> None:
    """Render a single error as a compact info block."""
    label = _ERROR_TYPE_LABELS.get(error.error_type, error.error_type.replace("_", " ").title())
    ts = error.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    agent_display = error.agent.title()

    cols = st.columns([0.25, 0.25, 0.50])
    with cols[0]:
        st.markdown(f"**{agent_display}**  \n{ts}")
    with cols[1]:
        st.markdown(f"**{label}**")
    with cols[2]:
        st.markdown(_plain_message(error))
        if error.recovery_suggestion:
            st.caption(f"Suggestion: {error.recovery_suggestion}")

    if resolved and error.resolved_at:
        st.caption(f"Resolved: {error.resolved_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    st.divider()


def render_errors_page(session, account_id: str) -> None:
    st.header("Error Log")

    # --- Active errors ---
    try:
        active = get_unresolved_errors(session, account_id)
    except Exception as e:
        st.error(f"Failed to load active errors: {e}")
        active = []

    st.subheader("Active Errors")

    if not active:
        st.success("No active errors — all agents healthy.")
    else:
        for error in active:
            _render_error_row(error, resolved=False)

    # --- Resolved errors ---
    st.subheader("Resolved Errors")

    try:
        resolved = get_resolved_errors(session, account_id)
    except Exception as e:
        st.error(f"Failed to load resolved errors: {e}")
        resolved = []

    if not resolved:
        st.info("No resolved errors on record.")
    else:
        with st.expander(f"Resolved errors ({len(resolved)})"):
            for error in resolved:
                _render_error_row(error, resolved=True)
```

Key rules:
- `get_unresolved_errors` (existing, line 376) for active errors — preferred over `get_active_errors` (line 270) because it has a typed `list[Error]` return
- `get_resolved_errors` (new query added in Task 1) for collapsed resolved section
- The green "No active errors" message uses `st.success()` — not `st.info()` — to match the acceptance criteria color requirement
- `_ERROR_TYPE_LABELS` maps `error_type` DB values to plain-English strings. Unknown types fall back to `error_type.replace("_", " ").title()`
- `recovery_suggestion` is nullable — only render the caption when non-None
- `resolved_at` is rendered as a caption inside the resolved expander for traceability
- Each section (`Active Errors`, `Resolved Errors`) has its own `try/except` so a resolved-errors query failure does not hide active errors

### Task 4: Tests

#### `tests/unit/dashboard/test_queries_decisions.py`

Test cases (use SQLite in-memory session via same fixture pattern as other Story 6 tests):

- `test_get_agent_decisions_returns_empty_when_no_rows` — empty DB → `[]`
- `test_get_agent_decisions_returns_newest_first` — insert 3 `AgentDecision` rows with different `created_at` → returned list is descending by `created_at`
- `test_get_agent_decisions_scoped_to_account_id` — insert decisions for two different `account_id` values → query for account A returns only account A rows
- `test_get_agent_decisions_respects_limit` — insert 110 rows → `get_agent_decisions(session, account_id, limit=100)` returns exactly 100 rows
- `test_get_resolved_errors_returns_empty_when_none` — insert 2 active (unresolved) errors → `get_resolved_errors` returns `[]`
- `test_get_resolved_errors_returns_only_resolved` — insert 1 resolved + 1 unresolved error → returns only the resolved row
- `test_get_resolved_errors_returns_newest_first` — insert 3 resolved errors with different `timestamp` → returned list is descending by `timestamp`
- `test_get_resolved_errors_respects_limit` — insert 60 resolved errors → `get_resolved_errors(session, account_id, limit=50)` returns exactly 50 rows

#### `tests/unit/dashboard/test_decisions_page.py`

Use `unittest.mock.patch` to mock `get_agent_decisions`. No live session needed.

- `test_render_decisions_page_shows_info_when_no_decisions` — `get_agent_decisions` returns `[]` → `st.info` called with "No decisions recorded yet."
- `test_render_decisions_page_shows_error_on_query_failure` — `get_agent_decisions` raises `Exception` → `st.error` called, no re-raise
- `test_decision_type_labels_contains_phase_transition` — import `DECISION_TYPE_LABELS`; assert `"phase_transition"` key maps to `"Phase Transition"`
- `test_format_summary_with_from_to_values` — create an `AgentDecision` with `from_value="warmup"`, `to_value="tournament"`, `agent="orchestrator"` → `_format_summary` returns `"orchestrator: warmup → tournament"`
- `test_format_summary_without_from_to_falls_back_to_rationale` — create decision with `from_value=None`, `to_value=None`, `rationale="Picked niche X based on CTR"` → returns first 120 chars of rationale
- `test_unknown_decision_type_falls_back_to_title_case` — decision with `decision_type="custom_action"` → label renders as `"Custom Action"`
- `test_supporting_data_json_rendered_when_present` — decision with `supporting_data='{"score": 0.87}'` → `st.json` called (mock)
- `test_supporting_data_fallback_to_code_on_invalid_json` — decision with `supporting_data="not-json"` → `st.code` called (mock)

#### `tests/unit/dashboard/test_errors_page.py`

Use `unittest.mock.patch` to mock `get_unresolved_errors` and `get_resolved_errors`.

- `test_render_errors_page_shows_success_when_no_active_errors` — `get_unresolved_errors` returns `[]` → `st.success` called with "No active errors" text
- `test_render_errors_page_shows_active_errors` — `get_unresolved_errors` returns 2 `Error` objects → `st.columns` called twice (once per error row)
- `test_render_errors_page_shows_info_when_no_resolved` — `get_resolved_errors` returns `[]` → `st.info` called for resolved section
- `test_render_errors_page_shows_resolved_expander` — `get_resolved_errors` returns 3 errors → `st.expander` called with text containing "3"
- `test_render_errors_page_active_query_failure_shows_error` — `get_unresolved_errors` raises `Exception` → `st.error` called; resolved section still renders
- `test_render_errors_page_resolved_query_failure_shows_error` — `get_resolved_errors` raises `Exception` → `st.error` called; active section already rendered above
- `test_plain_message_returns_message_field` — `Error` with `message="TTS quota exceeded"` → `_plain_message` returns `"TTS quota exceeded"`
- `test_recovery_suggestion_rendered_when_present` — `Error` with `recovery_suggestion="Check API key"` → `st.caption` called with suggestion text

### New Files to Create / Modify

| File | Action | Purpose |
|---|---|---|
| `tiktok_faceless/db/queries.py` | Modify — add 2 functions | `get_agent_decisions`, `get_resolved_errors` |
| `dashboard/pages/decisions.py` | Replace stub | Decision audit log page |
| `dashboard/pages/errors.py` | Replace stub | Error log page |
| `tests/unit/dashboard/test_queries_decisions.py` | Create | Query unit tests |
| `tests/unit/dashboard/test_decisions_page.py` | Create | Decisions page unit tests |
| `tests/unit/dashboard/test_errors_page.py` | Create | Errors page unit tests |

### Model Field Reference

**`AgentDecision`** (`agent_decisions` table):

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Auto PK |
| `account_id` | `str` | Filter key |
| `agent` | `str` | e.g. `"orchestrator"`, `"research"` |
| `decision_type` | `str` | Key into `DECISION_TYPE_LABELS` |
| `from_value` | `str \| None` | Previous value (nullable) |
| `to_value` | `str \| None` | New value (nullable) |
| `rationale` | `str` | Always present — human-readable |
| `supporting_data` | `str \| None` | JSON string (nullable) |
| `created_at` | `datetime` | Order by this DESC |

**`Error`** (`errors` table):

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Auto PK |
| `account_id` | `str` | Filter key |
| `agent` | `str` | Agent that raised the error |
| `error_type` | `str` | Key into `_ERROR_TYPE_LABELS` |
| `message` | `str` | Human-readable, set by agents |
| `video_id` | `str \| None` | Linked video (nullable) |
| `recovery_suggestion` | `str \| None` | Operator guidance (nullable) |
| `timestamp` | `datetime` | When error occurred; order DESC |
| `resolved_at` | `datetime \| None` | NULL = active; set = resolved |

### Project Conventions

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length <= 100 chars
- No bare `except` at module top level in query functions — only in component render functions (UI resilience)
- No function-level imports — all imports at module top
- `datetime.utcnow()` for naive UTC timestamps throughout
- All query functions accept `session: Session` as first arg and `account_id: str` as second — never open a new session internally
- Run `uv run pytest tests/unit/ -q` before marking done
- Run `uv run ruff check tiktok_faceless/db/queries.py dashboard/pages/decisions.py dashboard/pages/errors.py tests/unit/dashboard/` after implementation

### Dependencies

- `streamlit` — already added in Story 6.1
- `json` — stdlib; no new dependency
- Story 6.1 must be complete — `dashboard/pages/decisions.py` and `dashboard/pages/errors.py` stubs must already exist (confirmed: both stub files present with docstring only)
- No new `pyproject.toml` entries needed

### References

- Epic 6, Story 6.5 spec: `_bmad-output/planning-artifacts/epics.md` (lines 1149–1172)
- DB models: `tiktok_faceless/db/models.py` — `AgentDecision` (line 108), `Error` (line 128)
- Existing queries: `tiktok_faceless/db/queries.py` — `get_unresolved_errors()` (line 376), `get_active_errors()` (line 270), `write_agent_errors()` (line 246), `resolve_agent_errors()` (line 306)
- Page stubs: `dashboard/pages/decisions.py`, `dashboard/pages/errors.py`
- Prior story spec: `_bmad-output/implementation-artifacts/6-4-agent-pipeline-panel-video-table.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
