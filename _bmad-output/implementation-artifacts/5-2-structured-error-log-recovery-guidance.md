# Story 5.2: Structured Error Log with Recovery Guidance

Status: review

## Story

As the operator,
I want every failure logged with structured context and a plain-English recovery suggestion,
so that when I check the dashboard I know exactly what failed, when, and what to do about it — without reading raw tracebacks.

## Acceptance Criteria

1. **Given** any agent raises a typed exception (`TikTokRateLimitError`, `ElevenLabsError`, `RenderError`, etc.)
   **When** the agent node catches it at the boundary
   **Then** an `AgentError` Pydantic model is constructed with: `agent`, `error_type`, `message`, `video_id` (if applicable), `recovery_suggestion`, `timestamp`
   **And** the `AgentError` is written to the `errors` DB table via `db/queries.py`

2. **Given** an error is written to the `errors` table
   **When** `recovery_suggestion` is inspected
   **Then** it contains a plain-English action (e.g. "ElevenLabs rate limit exceeded — reduce concurrent voice generation or upgrade plan")
   **And** recovery suggestions are defined per error type in the client wrapper — not generated at runtime

3. **Given** an error is resolved
   **When** `errors` table is updated
   **Then** `resolved_at` is set to the resume timestamp
   **And** the error no longer appears as active in dashboard queries

## Tasks / Subtasks

- [x] Task 1: Add `write_agent_errors` and `get_active_errors` to `tiktok_faceless/db/queries.py`
  - [x] Add `write_agent_errors(session, errors: list[AgentError]) -> None` — iterates errors list, constructs `Error` ORM rows, calls `session.add()` for each, then `session.commit()`
  - [x] Add `get_active_errors(session, account_id: str) -> list[Error]` — returns `Error` rows where `resolved_at IS NULL` filtered by `account_id`, ordered by `timestamp` descending
  - [x] Import `Error` from `tiktok_faceless.db.models` at module level

- [x] Task 2: Create `tiktok_faceless/utils/recovery.py` with `RECOVERY_SUGGESTIONS` dict
  - [x] Define `RECOVERY_SUGGESTIONS: dict[str, str]` mapping each `error_type` string to a plain-English action string
  - [x] Include at minimum these keys: TikTokRateLimitError, TikTokAuthError, TikTokAPIError, ElevenLabsError, RenderError, MissingProduct, MissingScript, MissingVideo, LLMError, commission_discrepancy
  - [x] Export a helper `get_recovery_suggestion(error_type: str) -> str | None` that returns `RECOVERY_SUGGESTIONS.get(error_type)`

- [x] Task 3: Update `orchestrator_node` in `orchestrator.py` to use `write_agent_errors`
  - [x] Replace the inline `session.add()` loop in the error block with a call to `write_agent_errors(session, state.errors)`
  - [x] Import `write_agent_errors` from `tiktok_faceless.db.queries` at module level
  - [x] Removed `Error` from `tiktok_faceless.db.models` import (no longer needed in orchestrator)

- [x] Task 4: Add `recovery_suggestion` to every `AgentError` construction in agent files
  - [x] `tiktok_faceless/agents/production.py`: ElevenLabsError, RenderError, MissingScript
  - [x] `tiktok_faceless/agents/publishing.py`: TikTokRateLimitError, TikTokAuthError, TikTokAPIError, MissingVideo
  - [x] `tiktok_faceless/agents/monetization.py`: commission_discrepancy (Error ORM row), MissingProduct, TikTokRateLimitError, TikTokAuthError, TikTokAPIError
  - [x] `tiktok_faceless/agents/script.py`: MissingProduct, LLMError
  - [x] Import `get_recovery_suggestion` from `tiktok_faceless.utils.recovery` at module level in each agent file

- [x] Task 5: Tests — `TestWriteAgentErrors` and `TestGetActiveErrors` in `tests/unit/db/test_queries.py`
  - [x] `test_writes_each_error_to_session` — given list of two AgentError, asserts session.add called twice
  - [x] `test_empty_errors_no_adds` — given empty list, no session.add called
  - [x] `test_recovery_suggestion_set_on_error_row` — recovery_suggestion passes through to Error ORM row
  - [x] `test_maps_all_fields` — all fields (agent, error_type, message, video_id, account_id) mapped correctly
  - [x] `test_filters_by_account_and_unresolved` — mock query returns empty list
  - [x] `test_returns_unresolved_rows_only` — in-memory SQLite: only unresolved row returned
  - [x] `test_filters_by_account_id` — in-memory SQLite: only acc1 errors returned

- [x] Task 6: Tests — recovery_suggestion assertions in agent test files
  - [x] `tests/unit/agents/test_production.py` — `TestRecoverySuggestions`: missing_script, elevenlabs_error, render_error
  - [x] `tests/unit/agents/test_publishing.py` — `TestRecoverySuggestions`: missing_video, rate_limit, auth_error
  - [x] `tests/unit/agents/test_monetization.py` — `TestRecoverySuggestions`: missing_product (with "research" check), rate_limit_error

## Dev Notes

### Current State

The `AgentError` model in `tiktok_faceless/state.py` already has a `recovery_suggestion: str | None = None` field (line 36). The `Error` DB model in `tiktok_faceless/db/models.py` already has `recovery_suggestion: Mapped[str | None]` and `resolved_at: Mapped[datetime | None]` (lines 138–140). Both models need no changes.

The `orchestrator_node` in `orchestrator.py` currently writes errors with an inline loop (lines 43–54) using direct `session.add()` calls. Story 5.2 replaces this with `write_agent_errors()` from `db/queries.py` to centralize the logic and make it testable.

All agent files currently construct `AgentError` without setting `recovery_suggestion` — it defaults to `None`. Story 5.2 adds the `recovery_suggestion` field to every `AgentError` construction site.

### `tiktok_faceless/db/queries.py` — New Functions

`db/queries.py` does not currently exist and must be created. It receives an already-open SQLAlchemy `Session` (not a context manager). The session is managed by the caller.

```python
# tiktok_faceless/db/queries.py
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Error
from tiktok_faceless.state import AgentError


def write_agent_errors(session: Session, errors: list[AgentError]) -> None:
    """Write a list of AgentError objects to the errors table and commit."""
    for err in errors:
        session.add(
            Error(
                id=str(uuid.uuid4()),
                account_id=...,  # NOTE: account_id must be passed — see design note below
                agent=err.agent,
                error_type=err.error_type,
                message=err.message,
                video_id=err.video_id,
                recovery_suggestion=err.recovery_suggestion,
            )
        )
    session.commit()


def get_active_errors(session: Session, account_id: str) -> list[Error]:
    """Return Error rows where resolved_at IS NULL for the given account, newest first."""
    return (
        session.query(Error)
        .filter_by(account_id=account_id)
        .filter(Error.resolved_at.is_(None))
        .order_by(Error.timestamp.desc())
        .all()
    )
```

**Design note on `account_id`**: `AgentError` does not carry `account_id` (it's on `PipelineState`). The function signature must therefore accept `account_id` as a separate parameter:

```python
def write_agent_errors(session: Session, account_id: str, errors: list[AgentError]) -> None:
```

And the call site in `orchestrator_node` becomes:

```python
write_agent_errors(session, state.account_id, state.errors)
```

### `tiktok_faceless/utils/recovery.py` — New File

```python
# tiktok_faceless/utils/recovery.py
"""Static recovery suggestion strings keyed by error_type."""

RECOVERY_SUGGESTIONS: dict[str, str] = {
    "TikTokRateLimitError": "TikTok rate limit hit — pipeline will retry in next cycle",
    "TikTokAuthError": "TikTok auth failed — refresh access token in AccountConfig",
    "TikTokAPIError": "TikTok API error — check credentials or TikTok service status",
    "ElevenLabsError": "ElevenLabs API error — check API key or upgrade plan",
    "RenderError": "Video render failed — check Creatomate template or API key",
    "MissingProduct": "No product selected — run research agent to populate niche products",
    "MissingScript": "No script available — run script agent before production",
    "MissingVideo": "No rendered video available — run production agent before publishing",
    "LLMError": "LLM script generation failed — check OpenAI API key or reduce prompt length",
    "commission_discrepancy": "Commission discrepancy detected — verify affiliate link and product data",
}


def get_recovery_suggestion(error_type: str) -> str | None:
    """Return the plain-English recovery suggestion for the given error_type, or None."""
    return RECOVERY_SUGGESTIONS.get(error_type)
```

### Agent File Update Pattern

All agent files follow the same pattern. Import at module level; pass into `AgentError`:

```python
from tiktok_faceless.utils.recovery import get_recovery_suggestion

# In the except block:
return {
    "errors": [
        AgentError(
            agent="production",
            error_type="ElevenLabsError",
            message=str(e),
            recovery_suggestion=get_recovery_suggestion("ElevenLabsError"),
        )
    ]
}
```

### `get_active_errors` — Dashboard Query Design

`resolved_at` is already a nullable `DateTime` column on the `Error` model (line 140 in `models.py`). The query pattern uses SQLAlchemy `.filter(Error.resolved_at.is_(None))` — do NOT use `== None` (triggers a lint warning). The dashboard marks an error resolved by setting `resolved_at = datetime.utcnow()` on the row.

### `errors` Table — ID Field

The `Error` model uses an auto-increment integer PK (`id: Mapped[int]` — line 132 in `models.py`), so no `id=str(uuid.uuid4())` is needed. Omit `id` from the `Error(...)` constructor call.

### Test Patterns

Reuse the `_mock_session()` helper from existing test files for session mocking. For `test_queries.py`, use an in-memory SQLite session (following the pattern used by other DB tests in the project) rather than mocking — this produces more reliable assertions on query behavior.

For agent test assertions on `recovery_suggestion`, use `assert result["errors"][0].recovery_suggestion is not None` plus a substring check on the human-readable text to avoid tightly coupling tests to the exact string.

### Import Order Convention

All agent files must follow: stdlib → third-party → local (ruff I001). `tiktok_faceless.utils.recovery` is a local import and goes last in the local block.

### Previous Story Learnings (Stories 4.x, 5.1)

- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- `session.add.call_args[0][0]` to get object passed to `session.add`
- `session.add.call_args_list` for multiple adds
- Do NOT use bare `except Exception` — typed exceptions only
- All module-level imports — no function-level imports
- Pydantic defaults only — no env var wiring

## References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 5.2
- Previous story: `_bmad-output/implementation-artifacts/5-1-agent-failure-isolation.md`
- `AgentError` model: `tiktok_faceless/state.py` (lines 29–37)
- `Error` DB model: `tiktok_faceless/db/models.py` (lines 127–140)
- `orchestrator_node` error block: `tiktok_faceless/agents/orchestrator.py` (lines 42–58)
- `production_node` error sites: `tiktok_faceless/agents/production.py` (lines 51–60, 77–86)
- `publishing_node` error sites: `tiktok_faceless/agents/publishing.py` (lines 88–117)
- `monetization_node` error sites: `tiktok_faceless/agents/monetization.py` (lines 72–120)
- `script_node` error sites: `tiktok_faceless/agents/script.py` (lines 98–134)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was clean on first pass.

### Completion Notes List

- `write_agent_errors` takes `account_id` as separate param since `AgentError` doesn't carry it
- `Error` model uses auto-increment int PK — no `id=uuid.uuid4()` needed in ORM constructor
- `_reconcile_commissions` in monetization.py directly constructs `Error` ORM row (not AgentError) so recovery_suggestion was added there too
- `script.py` already had an inline recovery_suggestion string for LLMError — replaced with `get_recovery_suggestion("LLMError")` for consistency
- `test_graph.py` has a pre-existing import error unrelated to this story; all 306 tests pass when it is excluded

### File List

- `tiktok_faceless/utils/recovery.py` (new)
- `tiktok_faceless/db/queries.py` (write_agent_errors, get_active_errors added; Error imported)
- `tiktok_faceless/agents/orchestrator.py` (refactored to write_agent_errors; Error import removed)
- `tiktok_faceless/agents/monetization.py` (recovery_suggestion on all AgentError sites + Error ORM row)
- `tiktok_faceless/agents/production.py` (recovery_suggestion on all AgentError sites)
- `tiktok_faceless/agents/publishing.py` (recovery_suggestion on all AgentError sites)
- `tiktok_faceless/agents/script.py` (recovery_suggestion on all AgentError sites)
- `tests/unit/db/test_queries.py` (TestWriteAgentErrors, TestGetActiveErrors added)
- `tests/unit/agents/test_monetization.py` (TestRecoverySuggestions added)
- `tests/unit/agents/test_production.py` (TestRecoverySuggestions added)
- `tests/unit/agents/test_publishing.py` (TestRecoverySuggestions added)
