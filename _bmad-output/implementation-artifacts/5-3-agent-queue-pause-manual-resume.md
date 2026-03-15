# Story 5.3: Agent Queue Pause & Manual Resume

Status: review

## Story

As the operator,
I want a failing agent's queue to pause automatically and resume with a single action after I've resolved the underlying issue,
so that the system never retries a broken operation indefinitely or requires manual pipeline reconstruction to recover.

## Acceptance Criteria

1. **Given** an agent has exceeded its retry limit (3 attempts with backoff)
   **When** the final retry fails
   **Then** the agent's queue state is set to `paused` in the `accounts` table for that `account_id`
   **And** no further attempts are made by that agent until manually resumed
   **And** other agents continue operating normally

2. **Given** an agent queue is paused
   **When** the operator runs the resume command (`python -m tiktok_faceless.main --resume-agent production --account-id <id>`)
   **Then** the agent queue state is set back to `active`
   **And** the pipeline resumes from the last unprocessed item — no reprocessing of completed items
   **And** the `errors` table entry for the triggering failure has `resolved_at` set

3. **Given** the operator resumes the pipeline
   **When** the next pipeline cycle runs
   **Then** `state["agent_health"]["<agent>"]` is reset to `True`
   **And** a Telegram alert is sent: "Agent [name] resumed for account [id]"

## Tasks / Subtasks

- [ ] Task 1: Add `paused_agent_queues` column to `Account` DB model in `tiktok_faceless/db/models.py`
  - [ ] Add `paused_agent_queues: Mapped[str | None] = mapped_column(String, nullable=True)` to `Account`
  - [ ] Field stores a JSON-encoded list of agent name strings (e.g. `'["production", "script"]'`)
  - [ ] Default is `None` (empty — no agents paused)
  - [ ] Write Alembic migration or inline `Base.metadata.create_all` note for the new column

- [ ] Task 2: Add DB query helpers in `tiktok_faceless/db/queries.py`
  - [ ] Add `pause_agent_queue(session, account_id: str, agent: str) -> None`
    - Reads current `paused_agent_queues` JSON, appends agent name if not already present, writes back
  - [ ] Add `resume_agent_queue(session, account_id: str, agent: str) -> None`
    - Reads current `paused_agent_queues` JSON, removes agent name, writes back
  - [ ] Add `resolve_agent_errors(session, account_id: str, agent: str) -> None`
    - Updates all `errors` rows where `account_id` matches, `agent` matches, and `resolved_at` is NULL
    - Sets `resolved_at = datetime.utcnow()`
  - [ ] Add `get_paused_agents(session, account_id: str) -> list[str]`
    - Returns parsed list from `paused_agent_queues` (empty list if None)

- [ ] Task 3: Wire auto-pause into orchestrator after retry exhaustion in `tiktok_faceless/agents/orchestrator.py`
  - [ ] When `orchestrator_node` receives errors and marks `agent_health[agent] = False`, also call `pause_agent_queue(session, account_id, agent)` for each failed agent
  - [ ] On subsequent pipeline starts, read `get_paused_agents(session, account_id)` and inject into `agent_health` as `False` entries so Story 5.1 routing skips them — do this in orchestrator at graph entry
  - [ ] NOTE: `agent_health` in `PipelineState` is the runtime gate; `paused_agent_queues` in `accounts` is the persistence layer so paused state survives process restarts

- [ ] Task 4: Add CLI resume command to `tiktok_faceless/main.py`
  - [ ] Parse `--resume-agent <agent_name>` and `--account-id <id>` args with `argparse`
  - [ ] On resume:
    1. Call `load_env()`
    2. Open DB session
    3. Call `resume_agent_queue(session, account_id, agent)` — removes from `paused_agent_queues`
    4. Call `resolve_agent_errors(session, account_id, agent)` — stamps `resolved_at`
    5. Call `send_resume_alert(account_id, agent, config)` — Telegram notification
  - [ ] Resume command must NOT reinvoke the graph or touch LangGraph checkpointer state directly — `agent_health` will reset naturally on next cycle in Task 3
  - [ ] If `--resume-agent` / `--account-id` not provided together, print usage and exit with code 1

- [ ] Task 5: Add `send_resume_alert` to `tiktok_faceless/utils/alerts.py`
  - [ ] Signature: `send_resume_alert(account_id: str, agent: str, config: AccountConfig) -> None`
  - [ ] Message text: `"Agent {agent} resumed for account {account_id}"`
  - [ ] Reuse existing Telegram send logic (same pattern as other alert functions in the file)
  - [ ] No-op (log only) if `config.telegram_bot_token` or `config.telegram_chat_id` is empty

- [ ] Task 6: Tests in `tests/unit/`
  - [ ] `tests/unit/db/test_queries_pause_resume.py`
    - [ ] `test_pause_agent_queue_adds_to_list` — empty account → pause "production" → `["production"]`
    - [ ] `test_pause_agent_queue_idempotent` — already paused agent → no duplicate in list
    - [ ] `test_resume_agent_queue_removes_from_list` — `["production", "script"]` → resume "production" → `["script"]`
    - [ ] `test_resolve_agent_errors_stamps_resolved_at` — open Error rows → `resolved_at` set
    - [ ] `test_resolve_agent_errors_ignores_already_resolved` — already-resolved rows unchanged
    - [ ] `test_get_paused_agents_returns_empty_for_null` — `None` column → returns `[]`
  - [ ] `tests/unit/test_main_resume.py`
    - [ ] `test_resume_cli_parses_args` — `sys.argv` with `--resume-agent` and `--account-id` → correct args parsed
    - [ ] `test_resume_cli_calls_resume_queue_and_resolve_errors` — mocked session → both DB functions called
    - [ ] `test_resume_cli_sends_telegram_alert` — `send_resume_alert` called with correct args
    - [ ] `test_resume_cli_missing_args_exits_nonzero` — missing `--account-id` → `SystemExit(1)`
  - [ ] `tests/unit/utils/test_alerts_resume.py`
    - [ ] `test_send_resume_alert_posts_correct_message` — mock HTTP call → message contains agent name and account id
    - [ ] `test_send_resume_alert_noop_when_token_empty` — no token → no HTTP call made

## Dev Notes

### State Persistence Design — `agent_health` vs `paused_agent_queues`

`PipelineState.agent_health` (in `state.py`) is an in-memory runtime flag managed by LangGraph's
MemorySaver. It does NOT survive process restarts — a redeployed worker would start with a clean
`agent_health = {}`, silently re-enabling a paused agent.

To provide durable pause state, `paused_agent_queues` is added to the `accounts` DB row as a
JSON-encoded list. This is the source of truth across restarts:

- **Auto-pause path**: orchestrator error block → `pause_agent_queue(session, ...)` writes to DB +
  sets `agent_health[agent] = False` in returned state delta
- **Startup/cycle path**: orchestrator reads `get_paused_agents(session, account_id)` at the top of
  each cycle and merges into `agent_health` before routing decisions — this re-applies durable pause
  state to fresh in-memory state
- **Resume path**: CLI command removes agent from `paused_agent_queues` in DB; next cycle orchestrator
  reads clean list → `agent_health` starts without `False` for that agent → Story 5.1 routing allows it

This avoids any need to reach into LangGraph checkpointer internals from the CLI.

### `Account` Model Change

Add to `tiktok_faceless/db/models.py` — `Account` class only, no other models touched:

```python
paused_agent_queues: Mapped[str | None] = mapped_column(String, nullable=True)
```

Stored value examples:
- `None` — no agents paused (default)
- `'[]'` — empty list (after all agents resumed)
- `'["production"]'` — production agent paused
- `'["production", "script"]'` — two agents paused

Parse/serialize with `json.loads` / `json.dumps`. Always guard against `None` before parsing.

### `pause_agent_queue` / `resume_agent_queue` Implementation Pattern

```python
import json
from sqlalchemy.orm import Session
from tiktok_faceless.db.models import Account

def pause_agent_queue(session: Session, account_id: str, agent: str) -> None:
    account = session.query(Account).filter_by(account_id=account_id).one()
    paused: list[str] = json.loads(account.paused_agent_queues or "[]")
    if agent not in paused:
        paused.append(agent)
    account.paused_agent_queues = json.dumps(paused)
    session.commit()
```

`resume_agent_queue` follows the same pattern but uses `paused.remove(agent)` (guarded with
`if agent in paused`).

### `resolve_agent_errors` Implementation Pattern

```python
from datetime import datetime
from sqlalchemy.orm import Session
from tiktok_faceless.db.models import Error

def resolve_agent_errors(session: Session, account_id: str, agent: str) -> None:
    rows = (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.agent == agent,
            Error.resolved_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.resolved_at = datetime.utcnow()
    session.commit()
```

### CLI Entrypoint Pattern

`tiktok_faceless/main.py` may not exist yet or may only be a stub. Structure it so that:

1. `argparse.ArgumentParser` is defined at module level or in a `parse_args()` function
2. The `if __name__ == "__main__"` block (or `main()` entrypoint function) dispatches on args
3. Normal pipeline invocation remains the default when no resume flags are present

```python
import argparse
import sys

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tiktok_faceless.main")
    parser.add_argument("--resume-agent", metavar="AGENT")
    parser.add_argument("--account-id", metavar="ACCOUNT_ID")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if bool(args.resume_agent) != bool(args.account_id):
        print("Error: --resume-agent and --account-id must be provided together", file=sys.stderr)
        sys.exit(1)
    if args.resume_agent and args.account_id:
        _run_resume(args.account_id, args.resume_agent)
    else:
        _run_pipeline()
```

### Orchestrator Cycle-Start Merge Pattern

At the top of `orchestrator_node`, before any routing or error handling:

```python
with get_session() as session:
    paused = get_paused_agents(session, state.account_id)

merged_health = {**state.agent_health}
for agent in paused:
    merged_health[agent] = False
# Use merged_health for all decisions in this cycle; return it in state delta if changed
```

This ensures durable pause state always wins over any stale in-memory `True` from checkpointer.

### `send_resume_alert` Pattern

Reuse the same HTTP POST pattern used by other alert functions in `utils/alerts.py`:

```python
def send_resume_alert(account_id: str, agent: str, config: AccountConfig) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return
    message = f"Agent {agent} resumed for account {account_id}"
    # POST to Telegram sendMessage API — same pattern as existing alerts
```

### DB Migration Note

This story adds a nullable column to `accounts`. Since the project uses `Base.metadata.create_all`
for local dev, new installs will pick it up automatically. Existing deployments need a migration:

```sql
ALTER TABLE accounts ADD COLUMN paused_agent_queues TEXT;
```

Document this in the PR description. A formal Alembic migration file is optional but preferred if
the project already has an `alembic/` directory.

### Agent Health Semantics (from Story 5.1)

- `agent_health` default is `{}` — absence of a key means HEALTHY
- `agent_health.get("production") is False` — explicit `is False` check, not just falsy
- Setting `agent_health["production"] = True` on resume signals recovery to routing functions
- Story 5.1 routing in `graph.py` already skips unhealthy agents — Story 5.3 only needs to ensure
  `agent_health` is correctly populated at cycle start and cleared on resume

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/db/models.py` | Add `paused_agent_queues` column to `Account` |
| `tiktok_faceless/db/queries.py` | Add `pause_agent_queue`, `resume_agent_queue`, `resolve_agent_errors`, `get_paused_agents` |
| `tiktok_faceless/agents/orchestrator.py` | Call `pause_agent_queue` in error block; merge paused agents at cycle start |
| `tiktok_faceless/main.py` | Add `--resume-agent` / `--account-id` CLI args and `_run_resume` handler |
| `tiktok_faceless/utils/alerts.py` | Add `send_resume_alert` |
| `tests/unit/db/test_queries_pause_resume.py` | New — 6 tests for query helpers |
| `tests/unit/test_main_resume.py` | New — 4 tests for CLI resume command |
| `tests/unit/utils/test_alerts_resume.py` | New — 2 tests for resume alert |

### Do NOT Touch

- `tiktok_faceless/state.py` — `agent_health: dict[str, bool]` already correct; no changes needed
- `tiktok_faceless/graph.py` — Story 5.1 handles all routing around unhealthy agents; no changes needed
- `tiktok_faceless/db/models.py` `Error` model — `resolved_at` column already exists

### Project Conventions

- Import sort: stdlib → third-party → local
- Line length <= 100 characters
- No bare `except Exception` — catch typed exceptions only (`sqlalchemy.exc.NoResultFound`, etc.)
- Run `uv run pytest tests/unit/ -q` to verify no regressions

## References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 5.3
- Previous story: `_bmad-output/implementation-artifacts/5-1-agent-failure-isolation.md`
- `PipelineState.agent_health`: `tiktok_faceless/state.py` line 71
- `Account` model: `tiktok_faceless/db/models.py` lines 19–32
- `Error` model (has `resolved_at`): `tiktok_faceless/db/models.py` lines 127–140
- `AccountConfig` (Telegram fields): `tiktok_faceless/config.py` lines 53–54
- Graph routing (Story 5.1 patterns): `tiktok_faceless/graph.py`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
