# Story 7.2: Account Provisioning with Config Clone

Status: ready-for-dev

## Story

As the operator,
I want to provision a new TikTok account into the system by supplying its credentials and optionally cloning non-credential configuration from an existing account,
so that spinning up account #2 takes 30 minutes of credential setup — not a full reconfiguration from scratch.

## Acceptance Criteria

1. **Given** the operator runs `python -m tiktok_faceless.main --provision-account <account_id>`
   **When** the account does not yet exist in the `accounts` table
   **Then** a new `Account` row is inserted with `phase="warmup"`, `paused_agent_queues=None`
   **And** `load_account_config(account_id)` is called to validate all required env vars exist
   **And** `logger.info("Provisioned account %s", account_id)` is emitted
   **And** the process exits cleanly with code 0

2. **Given** the provisioning command is run for an account that already exists in the DB
   **When** `provision_account(session, account_id)` is called
   **Then** no new row is inserted
   **And** `logger.warning("Account %s already exists — skipping provision", account_id)` is emitted
   **And** the process exits cleanly with code 0 (idempotent — not an error)

3. **Given** required environment variables for the account are missing (e.g. `TIKTOK_ACCESS_TOKEN` not set)
   **When** `load_account_config(account_id)` is called during provisioning
   **Then** a `KeyError` propagates and the process exits with a non-zero code
   **And** no partial `Account` row is written to the DB

4. **Given** account #1 exists and the operator provisions account #2
   **When** `python -m tiktok_faceless.main --provision-account acc2` succeeds
   **Then** `main.py` default pipeline path is unaffected — `python -m tiktok_faceless.main` (no flags) still calls `_run_pipeline()` as before
   **And** account #1's data and state are untouched

5. **Given** the new account is provisioned
   **When** `python -m tiktok_faceless.main` (no flags) is subsequently run
   **Then** `get_active_accounts(session)` returns the newly provisioned account (phase="warmup" is not "archived")
   **And** the pipeline runs for it in the normal serial loop

## Tasks / Subtasks

- [ ] Task 1: Add `provision_account` query to `tiktok_faceless/db/queries.py`
  - [ ] Signature: `provision_account(session: Session, account_id: str) -> bool`
  - [ ] Query `Account` table for an existing row with `account_id == account_id`
  - [ ] If found: log a warning and return `False` (caller interprets as "already existed")
  - [ ] If not found: insert a new `Account` row:
    - `id=str(uuid.uuid4())`
    - `account_id=account_id`
    - `tiktok_access_token=""` — placeholder; real credential lives in env var only
    - `tiktok_open_id=""` — placeholder; real credential lives in env var only
    - `phase="warmup"`
    - `paused_agent_queues=None`
    - `created_at=datetime.utcnow()`
    - `updated_at=datetime.utcnow()`
  - [ ] Call `session.add(account)` and `session.commit()`
  - [ ] Return `True` (new row created)
  - [ ] Use `logging.getLogger("tiktok_faceless.db.queries")` for the warning log inside this function

  Implementation pattern:
  ```python
  import uuid
  from datetime import datetime
  from sqlalchemy.orm import Session
  from tiktok_faceless.db.models import Account

  _queries_logger = logging.getLogger("tiktok_faceless.db.queries")

  def provision_account(session: Session, account_id: str) -> bool:
      """Insert a new Account row with phase='warmup'. Idempotent — returns False if already exists."""
      existing = session.query(Account).filter_by(account_id=account_id).first()
      if existing is not None:
          _queries_logger.warning("Account %s already exists — skipping provision", account_id)
          return False
      session.add(
          Account(
              id=str(uuid.uuid4()),
              account_id=account_id,
              tiktok_access_token="",
              tiktok_open_id="",
              phase="warmup",
              paused_agent_queues=None,
              created_at=datetime.utcnow(),
              updated_at=datetime.utcnow(),
          )
      )
      session.commit()
      return True
  ```

- [ ] Task 2: Implement `_run_provision` in `tiktok_faceless/main.py`
  - [ ] Signature: `_run_provision(account_id: str) -> None`
  - [ ] Call `load_account_config(account_id)` first — if it raises `KeyError`, let it propagate (missing env var)
  - [ ] Open a DB session via `get_session()` and call `provision_account(session, account_id)`
  - [ ] If `provision_account` returns `True`: log `logger.info("Provisioned account %s", account_id)`
  - [ ] If `provision_account` returns `False`: the warning was already logged inside the query; do nothing further
  - [ ] Do NOT catch exceptions from `load_account_config` — missing credentials must be visible to the operator

  Implementation pattern:
  ```python
  from tiktok_faceless.db.queries import provision_account  # add to existing import

  def _run_provision(account_id: str) -> None:
      load_account_config(account_id)  # raises KeyError if env vars missing
      with get_session() as session:
          created = provision_account(session, account_id)
      if created:
          logger.info("Provisioned account %s", account_id)
  ```

- [ ] Task 3: Add `--provision-account` CLI argument to `parse_args()` in `tiktok_faceless/main.py`
  - [ ] Add `parser.add_argument("--provision-account", metavar="ACCOUNT_ID")` to the existing `parse_args()` function
  - [ ] In `main()`, add a branch: if `args.provision_account` is set, call `_run_provision(args.provision_account)` and return
  - [ ] The `--provision-account` branch takes priority over the default `_run_pipeline()` path
  - [ ] The `--resume-agent` / `--account-id` mutual-dependency check is unchanged
  - [ ] `--provision-account` is independent of `--resume-agent` / `--account-id` (no cross-validation needed)

  Updated `main()` control flow:
  ```python
  def main() -> None:
      args = parse_args()
      if args.provision_account:
          _run_provision(args.provision_account)
          return
      if bool(args.resume_agent) != bool(args.account_id):
          print(
              "Error: --resume-agent and --account-id must be provided together",
              file=sys.stderr,
          )
          sys.exit(1)
      if args.resume_agent and args.account_id:
          _run_resume(args.account_id, args.resume_agent)
      else:
          _run_pipeline()
  ```

- [ ] Task 4: Add docstring header to `tiktok_faceless/main.py`
  - [ ] Add `Implementation: Story 7.2 — Account Provisioning with Config Clone` to the module docstring
  - [ ] Add `provision_account` to the import from `tiktok_faceless.db.queries`

- [ ] Task 5: Tests in `tests/unit/`
  - [ ] `tests/unit/db/test_queries_provision.py` — 4 tests
  - [ ] `tests/unit/test_main_provision.py` — 5 tests (see Dev Notes for detail)

## Dev Notes

### Why `tiktok_access_token=""` in the DB Row

The `Account` model has `tiktok_access_token` and `tiktok_open_id` as `nullable=False` columns. However, the system's credential isolation design stores actual credential values in environment variables (scoped per `account_id`), not the DB. The `Account` row is used as a registry entry (phase tracker, pause state), not as a credential store.

Setting these to `""` at provisioning time is a deliberate placeholder. The live credentials are read from env vars by `load_account_config(account_id)` at pipeline runtime. No credential value is persisted in the DB.

This matches the acceptance criteria from `epics.md` Story 7.2: "credentials are stored as references to env vars scoped by `account_id`" and "no credential value is stored in the DB."

### Environment Variable Naming Convention

The current `load_account_config` in `tiktok_faceless/config.py` reads shared (non-scoped) env vars:

```python
tiktok_access_token=os.environ["TIKTOK_ACCESS_TOKEN"],
tiktok_client_key=os.environ["TIKTOK_CLIENT_KEY"],
...
elevenlabs_api_key=os.environ["ELEVENLABS_API_KEY"],
```

There is **no per-account scoping** (e.g. `TIKTOK_ACCESS_TOKEN_ACC2`) in the current implementation. `load_account_config(account_id)` reads the same global env vars regardless of `account_id`. This is the existing behavior — Story 7.2 does **not** change `config.py`. The validation step in `_run_provision` simply calls `load_account_config(account_id)` to confirm all required env vars are present before writing the DB row.

Per-account env var scoping (e.g. `TIKTOK_ACCESS_TOKEN_{ACCOUNT_ID.upper()}`) is a future enhancement. Do not implement it in this story.

### Idempotency Contract

`provision_account` must be safe to run multiple times for the same `account_id`. On a repeated call:
- No `IntegrityError` should be raised (do not rely on the DB `UNIQUE` constraint for control flow)
- Log a warning and return `False`
- The existing `Account` row is untouched — its `phase`, `paused_agent_queues`, and other fields are preserved exactly as they were

This matters for operator workflows: running the provisioning command twice should not reset a running account back to `phase="warmup"`.

### `get_session()` Usage Pattern

Use the context manager form consistent with existing `main.py` code:

```python
with get_session() as session:
    created = provision_account(session, account_id)
```

### No DB Schema Changes

The `accounts` table already has all required columns (`id`, `account_id`, `tiktok_access_token`, `tiktok_open_id`, `phase`, `paused_agent_queues`, `created_at`, `updated_at`). No Alembic migration is needed for this story.

### Test Specifications

#### `tests/unit/db/test_queries_provision.py`

All tests use an in-memory SQLite session (same pattern as other `tests/unit/db/` tests). Import `provision_account` from `tiktok_faceless.db.queries`.

- `test_provision_account_inserts_row` — call `provision_account(session, "acc1")` on empty DB → assert `session.query(Account).filter_by(account_id="acc1").first()` is not None, `phase == "warmup"`, returns `True`
- `test_provision_account_sets_warmup_phase` — same as above, explicit check that `account.phase == "warmup"`
- `test_provision_account_idempotent` — call `provision_account` twice with same `account_id` → second call returns `False`, only one row in DB (use `session.query(Account).count() == 1`)
- `test_provision_account_does_not_overwrite_phase` — seed an `Account` row with `phase="commit"`, call `provision_account` → row still has `phase="commit"` (not reset to "warmup")

#### `tests/unit/test_main_provision.py`

Use `unittest.mock.patch` for all external dependencies. Import `_run_provision` from `tiktok_faceless.main`.

- `test_provision_account_cli_arg_calls_run_provision` — patch `tiktok_faceless.main._run_provision`, simulate `sys.argv = ["main", "--provision-account", "acc2"]`, call `main()` → assert `_run_provision` called once with `"acc2"`
- `test_run_provision_calls_load_account_config` — patch `tiktok_faceless.main.load_account_config` (returns a mock `AccountConfig`), patch `tiktok_faceless.main.provision_account` (returns `True`), patch `tiktok_faceless.main.get_session` → call `_run_provision("acc2")` → assert `load_account_config` called with `"acc2"`
- `test_run_provision_calls_provision_account` — same patches as above → assert `provision_account` called once with the session and `"acc2"`
- `test_run_provision_missing_env_var_propagates` — patch `load_account_config` to raise `KeyError("TIKTOK_ACCESS_TOKEN")` → call `_run_provision("acc2")` → assert `KeyError` propagates (do not swallow it)
- `test_run_provision_idempotent_no_error` — patch `load_account_config`, patch `provision_account` to return `False` → call `_run_provision("acc2")` → assert no exception raised (idempotent path is clean)

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/db/queries.py` | Add `provision_account(session, account_id) -> bool` |
| `tiktok_faceless/main.py` | Add `_run_provision`, `--provision-account` CLI arg, update `main()` branch, update imports + docstring |
| `tests/unit/db/test_queries_provision.py` | New — 4 tests for `provision_account` |
| `tests/unit/test_main_provision.py` | New — 5 tests for CLI and `_run_provision` |

### Do NOT Touch

- `tiktok_faceless/config.py` — `load_account_config` reads shared env vars; per-account scoping is out of scope for this story
- `tiktok_faceless/db/models.py` — `Account` model has all required columns; no changes needed
- `tiktok_faceless/db/session.py` — session management is unchanged
- `tiktok_faceless/graph.py` — no changes needed
- `tiktok_faceless/state.py` — no changes needed
- Any agent files — provisioning is purely a DB + CLI concern

### Project Conventions

- Import sort: stdlib → third-party → local
- Line length <= 100 characters
- Logger name in `main.py`: `"tiktok_faceless.main"` (existing `logger` variable — do not create a new one)
- Logger name in `queries.py`: `"tiktok_faceless.db.queries"` (module-level, add at top of file if not present)
- No bare `except Exception` in tests — use specific assertions on mock call counts and args
- Run `uv run pytest tests/unit/ -q` to verify no regressions after implementation

## References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 7.2 (line 1233)
- `Account` model: `tiktok_faceless/db/models.py` lines 19–33 (fields: `id`, `account_id`, `tiktok_access_token`, `tiktok_open_id`, `phase`, `paused_agent_queues`, `created_at`, `updated_at`)
- `load_account_config`: `tiktok_faceless/config.py` lines 65–84 (reads shared env vars; raises `KeyError` on missing vars)
- `db/queries.py` insert pattern: see `cache_product` (lines 21–51) for `session.add()` + `session.commit()` idiom
- `db/queries.py` idempotent pattern: see `pause_agent_queue` (lines 286–293) for filter-then-check pattern
- `main.py` current entrypoint: `tiktok_faceless/main.py` lines 71–86 (`parse_args`, `main()`, existing branches)
- Story 7.1 spec: `_bmad-output/implementation-artifacts/7-1-isolated-multi-account-pipeline-execution.md` (multi-account runner context)
- Story 5.3 (CLI pattern, `--resume-agent`): `_bmad-output/implementation-artifacts/5-3-agent-queue-pause-manual-resume.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
