# Story 7.1: Isolated Multi-Account Pipeline Execution

Status: ready-for-dev

## Story

As the operator,
I want each TikTok account to run a fully isolated pipeline with its own state, credentials, and DB scope,
so that account #2 can be provisioned and run without any risk of interfering with account #1's revenue.

## Acceptance Criteria

1. **Given** two accounts exist in the `accounts` table with distinct `account_id` values
   **When** both pipelines run (serially) on the same VM invocation
   **Then** every DB query in `db/queries.py` is scoped by `account_id` — no cross-account row access
   **And** every API call passes the correct `account_id` credentials — no credential mixing
   **And** `PipelineState` instances are fully isolated — `account_id` is the first field and is immutable after initialization

2. **Given** account #1's pipeline encounters an error
   **When** the error is logged and the agent pauses
   **Then** account #2's pipeline continues unaffected
   **And** `state["agent_health"]` and `errors` table entries are scoped independently per `account_id`

3. **Given** multiple active accounts exist in the DB
   **When** `python -m tiktok_faceless.main` is run with no arguments
   **Then** `get_active_accounts(session)` loads all accounts where `phase != "archived"`
   **And** the pipeline runs for each account in sequence, one at a time
   **And** each account's graph invocation uses `thread_id = account_id` as the LangGraph checkpointer key

4. **Given** a single account's pipeline is being run
   **When** `run_pipeline_for_account(account_id, graph)` is called
   **Then** the graph is invoked with `config={"configurable": {"thread_id": account_id}}`
   **And** initial state is constructed from `load_account_config(account_id)` with `account_id` as the first field
   **And** any exception raised by the graph is caught, logged, and execution continues to the next account

5. **Given** the system has been running for multiple accounts
   **When** a VM restart occurs
   **Then** the LangGraph `MemorySaver` checkpointer keyed by `account_id` resumes each account from its last known state on the next invocation

## Tasks / Subtasks

- [ ] Task 1: Add `get_active_accounts` query to `tiktok_faceless/db/queries.py`
  - [ ] Signature: `get_active_accounts(session: Session) -> list[Account]`
  - [ ] Returns all `Account` rows where `phase != "archived"` (i.e. warmup, tournament, commit, scale)
  - [ ] Order results by `account_id` ascending for deterministic iteration order
  - [ ] No `account_id` parameter — this is the only cross-account query in the system, intentionally

- [ ] Task 2: Implement `run_pipeline_for_account` in `tiktok_faceless/main.py`
  - [ ] Signature: `run_pipeline_for_account(account_id: str, graph: CompiledStateGraph) -> None`
  - [ ] Load `AccountConfig` via `load_account_config(account_id)`
  - [ ] Construct initial `PipelineState` with `account_id=account_id` and `phase` loaded from config/DB
  - [ ] Invoke the compiled graph:
    ```python
    graph.invoke(
        initial_state.model_dump(),
        config={"configurable": {"thread_id": account_id}},
    )
    ```
  - [ ] Wrap the entire invocation in a `try/except Exception` block
  - [ ] On exception: log `logger.error("Pipeline failed for account %s: %s", account_id, e)` and return — do NOT re-raise
  - [ ] Use Python stdlib `logging` (not `print`) — logger name: `tiktok_faceless.main`

- [ ] Task 3: Implement `run_all_accounts` in `tiktok_faceless/main.py`
  - [ ] Signature: `run_all_accounts(graph: CompiledStateGraph) -> None`
  - [ ] Open a single DB session via `get_session()`
  - [ ] Call `get_active_accounts(session)` to load all active `Account` rows
  - [ ] Log `logger.info("Running pipeline for %d active accounts", len(accounts))`
  - [ ] Iterate accounts serially (no concurrency): call `run_pipeline_for_account(account.account_id, graph)` for each
  - [ ] Log `logger.info("Completed pipeline run for account %s", account.account_id)` after each
  - [ ] If `accounts` is empty, log a warning and return cleanly

- [ ] Task 4: Wire `run_all_accounts` into `_run_pipeline` in `tiktok_faceless/main.py`
  - [ ] In the existing `_run_pipeline()` stub, call `build_graph()` then `run_all_accounts(graph)`
  - [ ] Ensure the default CLI path (`python -m tiktok_faceless.main` with no args) calls `_run_pipeline()`
  - [ ] The existing `--resume-agent` / `--account-id` CLI path from Story 5.3 must remain unchanged

- [ ] Task 5: Tests in `tests/unit/`
  - [ ] `tests/unit/db/test_queries_active_accounts.py`
    - [ ] `test_get_active_accounts_returns_non_archived` — seed accounts with phases warmup/tournament/commit/scale/archived → only non-archived returned
    - [ ] `test_get_active_accounts_excludes_archived` — only archived accounts in DB → returns `[]`
    - [ ] `test_get_active_accounts_ordered_by_account_id` — multiple accounts → returned in ascending `account_id` order
    - [ ] `test_get_active_accounts_empty_db` — no accounts in DB → returns `[]`
  - [ ] `tests/unit/test_main_multi_account.py`
    - [ ] `test_run_pipeline_for_account_uses_correct_thread_id` — mock `graph.invoke` → assert called with `config={"configurable": {"thread_id": account_id}}`
    - [ ] `test_run_pipeline_for_account_isolates_state` — two calls with different account_ids → `graph.invoke` called twice with distinct thread_ids
    - [ ] `test_run_pipeline_for_account_catches_exception` — `graph.invoke` raises `RuntimeError` → function returns without re-raising, no crash
    - [ ] `test_run_all_accounts_calls_each_serially` — mock `get_active_accounts` returning 3 accounts → `run_pipeline_for_account` called 3 times in order
    - [ ] `test_run_all_accounts_empty_list` — `get_active_accounts` returns `[]` → no graph.invoke calls, no crash
    - [ ] `test_run_pipeline_default_cli_path` — simulate `sys.argv = ["main"]` (no flags) → `_run_pipeline` is called

## Dev Notes

### thread_id = account_id: The Isolation Contract

LangGraph's checkpointer uses `thread_id` (inside `config["configurable"]`) as the key for storing and resuming graph state. Every `graph.invoke(...)` or `graph.stream(...)` call that passes a distinct `thread_id` operates on a completely separate checkpoint namespace.

By setting `thread_id = account_id`, each account gets:
- Its own checkpoint history — no state bleed between accounts
- Independent crash recovery — resuming account #2 never touches account #1's checkpoint
- Isolated error state — `PipelineState.errors` and `agent_health` are per-thread

This is not a new mechanism — it uses the same `MemorySaver` already wired in `graph.py` via `build_graph()`. Story 7.1 simply enforces that every account gets its own `thread_id` at the call site.

### Invocation Pattern

```python
from langgraph.graph.state import CompiledStateGraph
from tiktok_faceless.graph import build_graph
from tiktok_faceless.state import PipelineState
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.session import get_session
from tiktok_faceless.db.queries import get_active_accounts
import logging

logger = logging.getLogger("tiktok_faceless.main")


def run_pipeline_for_account(account_id: str, graph: CompiledStateGraph) -> None:
    config = load_account_config(account_id)
    initial_state = PipelineState(account_id=account_id)
    try:
        graph.invoke(
            initial_state.model_dump(),
            config={"configurable": {"thread_id": account_id}},
        )
    except Exception as e:
        logger.error("Pipeline failed for account %s: %s", account_id, e)


def run_all_accounts(graph: CompiledStateGraph) -> None:
    with get_session() as session:
        accounts = get_active_accounts(session)
    if not accounts:
        logger.warning("No active accounts found — nothing to run")
        return
    logger.info("Running pipeline for %d active accounts", len(accounts))
    for account in accounts:
        run_pipeline_for_account(account.account_id, graph)
        logger.info("Completed pipeline run for account %s", account.account_id)


def _run_pipeline() -> None:
    graph = build_graph()
    run_all_accounts(graph)
```

### `get_active_accounts` Implementation Pattern

```python
from sqlalchemy.orm import Session
from tiktok_faceless.db.models import Account

def get_active_accounts(session: Session) -> list[Account]:
    """Return all Account rows where phase is not 'archived', ordered by account_id."""
    return (
        session.query(Account)
        .filter(Account.phase != "archived")
        .order_by(Account.account_id)
        .all()
    )
```

This is the only query in `db/queries.py` that does not take an `account_id` parameter — that is by design. Its purpose is precisely to enumerate all accounts before dispatching per-account work.

### Serial vs Parallel Execution

Accounts run **serially** in this story. This keeps the implementation simple and is sufficient for up to 10 accounts on a Hetzner CX22 given:
- Each pipeline cycle is short (~minutes per account)
- TikTok API rate limits (6 req/min) are per-OAuth-token, not system-wide
- ElevenLabs concurrency limits (5–10) are per-API-key, not per account

Parallel execution across accounts (e.g. using `asyncio` or `ThreadPoolExecutor`) is a future optimization deferred to a later story if cycle time becomes a bottleneck. Do not implement concurrency in this story.

### Error Isolation Between Accounts

The `try/except Exception` in `run_pipeline_for_account` is the sole cross-account isolation boundary. If account #2's graph raises an unhandled exception (e.g. a client misconfiguration), `run_all_accounts` catches it, logs it, and proceeds to account #3. Account #1 is never affected.

This is distinct from within-account agent failure isolation (Story 5.1 / 5.3), which handles individual agent errors within a single pipeline run. Story 7.1 handles between-account isolation at the runner level.

### PipelineState Initialization

`PipelineState` is initialized fresh for each account with `PipelineState(account_id=account_id)`. All other fields default to their Pydantic defaults (as defined in `state.py`). The LangGraph checkpointer will merge this with any existing checkpoint state for the `thread_id` — so a resumed account will recover its prior state from the checkpoint, not start fresh.

For a truly fresh start (e.g. new account), `PipelineState(account_id=account_id)` with default fields is correct. The checkpointer will have no prior state for that `thread_id`, so the defaults are used.

### `load_account_config` and Credential Isolation

`load_account_config(account_id)` (in `config.py`) loads per-account credentials from env vars scoped by `account_id` (e.g. `TIKTOK_ACCESS_TOKEN_ACC1`, `TIKTOK_ACCESS_TOKEN_ACC2`). This is the existing mechanism — Story 7.1 does not change it. Credential isolation is enforced at the config-loading layer, not in the runner.

Do not pass the `AccountConfig` object into `PipelineState` — it is not part of the state schema. Agents retrieve config via `load_account_config(state.account_id)` internally when they need credentials.

### No Changes to graph.py

`build_graph()` already uses `MemorySaver()` as the checkpointer. The `thread_id` routing is handled entirely at the call site (`graph.invoke(..., config={"configurable": {"thread_id": account_id}})`). No changes to `graph.py` are required for this story.

### No DB Schema Changes

The `accounts` table already has all required fields. `get_active_accounts` queries existing columns (`phase`, `account_id`). No Alembic migration is needed for this story.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/db/queries.py` | Add `get_active_accounts(session) -> list[Account]` |
| `tiktok_faceless/main.py` | Implement `run_pipeline_for_account`, `run_all_accounts`; fill in `_run_pipeline` stub |
| `tests/unit/db/test_queries_active_accounts.py` | New — 4 tests for `get_active_accounts` |
| `tests/unit/test_main_multi_account.py` | New — 6 tests for runner functions |

### Do NOT Touch

- `tiktok_faceless/state.py` — `PipelineState` already has `account_id` as the first field; no changes needed
- `tiktok_faceless/graph.py` — `build_graph()` and `MemorySaver` wiring already correct; no changes needed
- `tiktok_faceless/db/models.py` — `Account` model already has all required columns; no changes needed
- Any agent files — account isolation is enforced at the runner level; agents already use `state.account_id`

### Project Conventions

- Import sort: stdlib → third-party → local
- Line length <= 100 characters
- No bare `except Exception` in tests — use specific assertions on mock call counts and args
- Logger name: `"tiktok_faceless.main"` — use `logging.getLogger("tiktok_faceless.main")`
- Run `uv run pytest tests/unit/ -q` to verify no regressions after implementation

## References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 7.1 (line 1207)
- `Account` model: `tiktok_faceless/db/models.py` lines 19–33 (fields: `id`, `account_id`, `phase`, etc.)
- `PipelineState`: `tiktok_faceless/state.py` lines 40–72 (`account_id` first field)
- `build_graph()`: `tiktok_faceless/graph.py` lines 31–52 (`MemorySaver` checkpointer)
- `main.py` entrypoint (current stub): `tiktok_faceless/main.py` lines 32–51
- `db/queries.py` query patterns: `tiktok_faceless/db/queries.py` (all existing queries scoped by `account_id`)
- Story 5.3 (CLI pattern, `--resume-agent`): `_bmad-output/implementation-artifacts/5-3-agent-queue-pause-manual-resume.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
