# Story 1.2: Core State & Database Models

Status: review

## Story

As the system,
I want `PipelineState`, `AgentError`, `AccountConfig` Pydantic models and all core SQLAlchemy DB models defined and migrated,
So that every agent has a consistent, typed contract for state and persistence from the first line of agent code.

## Acceptance Criteria

1. **Given** the project is initialized (Story 1.1 complete), **When** I inspect `tiktok_faceless/state.py`, **Then** `PipelineState` is a Pydantic v2 `BaseModel` with all required fields: `account_id`, `phase`, `candidate_niches`, `committed_niche`, `selected_product`, `product_validated`, `current_script`, `hook_archetype`, `voiceover_path`, `assembled_video_path`, `published_video_id`, `videos_produced_today`, `last_post_timestamp`, `fyp_reach_rate`, `suppression_alert`, `kill_video_ids`, `affiliate_commission_week`, `agent_health`, `errors` **And** `AgentError` is a Pydantic v2 `BaseModel` with `agent`, `error_type`, `message`, `video_id`, `recovery_suggestion`, `timestamp` fields **And** `VideoLifecycle` enum covers all states: `queued → rendering → rendered → scheduled → posted → analyzed → archived/promoted`

2. **Given** `tiktok_faceless/config.py` exists, **When** I instantiate `AccountConfig` with valid values, **Then** all fields validate correctly (`max_posts_per_day` 1–15, `posting_window_start` 0–23, etc.) **And** loading from environment variables works via `python-dotenv`

3. **Given** `tiktok_faceless/db/models.py` exists, **When** I run `alembic upgrade head`, **Then** all 6 tables are created: `accounts`, `videos`, `video_metrics`, `products`, `agent_decisions`, `errors` **And** all columns match the architecture spec (snake_case, correct FK relationships, `account_id` FK on all tables) **And** `ix_video_metrics_video_id_recorded_at` index exists

4. **Given** SQLite dev config, **When** `get_session()` is called, **Then** a working DB session is returned and queries execute without error

5. **Given** all models are defined, **When** `uv run pytest` is run, **Then** all unit tests pass with zero failures **And** `uv run mypy tiktok_faceless/` exits 0

## Tasks / Subtasks

- [x] Task 1: Implement `tiktok_faceless/state.py` — PipelineState, AgentError, VideoLifecycle (AC: 1)
  - [x] Import `pydantic`, `typing`, `operator`, `enum`, `time` — no other project imports (zero-dependency module)
  - [x] Define `VideoLifecycle(str, Enum)` with values: `queued`, `rendering`, `rendered`, `scheduled`, `posted`, `analyzed`, `archived`, `promoted`
  - [x] Define `AgentError(BaseModel)` with fields: `agent: str`, `error_type: str`, `message: str`, `video_id: str | None = None`, `recovery_suggestion: str | None = None`, `timestamp: float = Field(default_factory=time.time)`
  - [x] Define `PipelineState(BaseModel)` with ALL fields from architecture spec (exact types and Annotated reducers as shown in Dev Notes)
  - [x] Use `Annotated[list[str], add]` for `kill_video_ids` and `Annotated[list[AgentError], add]` for `errors`
  - [x] Use `Literal["warmup", "tournament", "commit", "scale"]` for `phase`
  - [x] Write unit test `tests/unit/test_state.py` covering: instantiation with defaults, AgentError creation, VideoLifecycle values, kill_video_ids append behavior

- [x] Task 2: Implement `tiktok_faceless/config.py` — AccountConfig + env loading (AC: 2)
  - [x] Import `pydantic`, `pydantic_settings` or `python-dotenv` + `os`
  - [x] Define `AccountConfig(BaseModel)` with all fields and `Field(...)` validators as specified in architecture
  - [x] Add `load_account_config(account_id: str) -> AccountConfig` function that loads from env vars (prefix: `TIKTOK_`, `ELEVENLABS_`, etc.)
  - [x] Add `load_env()` helper that calls `python-dotenv` `load_dotenv()` — call at module level only in `main.py`, not inside agents
  - [x] Write unit test `tests/unit/test_config.py` covering: valid instantiation, field validation (max_posts_per_day out-of-range raises), env var loading with monkeypatch

- [x] Task 3: Implement `tiktok_faceless/db/models.py` — SQLAlchemy ORM models (AC: 3)
  - [x] Use SQLAlchemy 2.0 `DeclarativeBase` + `Mapped` / `mapped_column` syntax — NOT legacy `Column()`
  - [x] Define `Base = DeclarativeBase()`
  - [x] Define `Account` model: `id: Mapped[str]` (PK), `account_id: Mapped[str]` (unique), `tiktok_access_token: Mapped[str]`, `tiktok_open_id: Mapped[str]`, `phase: Mapped[str]` (default "warmup"), `created_at: Mapped[datetime]`, `updated_at: Mapped[datetime]`
  - [x] Define `Video` model: `id: Mapped[str]` (PK, UUID), `account_id: Mapped[str]` (FK→accounts.account_id), `niche: Mapped[str]`, `hook_archetype: Mapped[str | None]`, `lifecycle_state: Mapped[str]` (default "queued"), `script_text: Mapped[str | None]`, `voiceover_path: Mapped[str | None]`, `assembled_video_path: Mapped[str | None]`, `tiktok_video_id: Mapped[str | None]`, `affiliate_link: Mapped[str | None]`, `product_id: Mapped[str | None]`, `created_at: Mapped[datetime]`, `posted_at: Mapped[datetime | None]`
  - [x] Define `VideoMetric` model (append-only): `id: Mapped[int]` (PK autoincrement), `video_id: Mapped[str]` (FK→videos.id), `account_id: Mapped[str]`, `recorded_at: Mapped[datetime]`, `view_count: Mapped[int]`, `like_count: Mapped[int]`, `comment_count: Mapped[int]`, `share_count: Mapped[int]`, `average_time_watched: Mapped[float]`, `retention_3s: Mapped[float]`, `retention_15s: Mapped[float]`, `fyp_reach_pct: Mapped[float]`, `affiliate_clicks: Mapped[int]`, `affiliate_orders: Mapped[int]`
  - [x] Add composite index `ix_video_metrics_video_id_recorded_at` on (video_id, recorded_at)
  - [x] Define `Product` model: `id: Mapped[str]` (PK), `account_id: Mapped[str]`, `niche: Mapped[str]`, `product_name: Mapped[str]`, `product_url: Mapped[str]`, `commission_rate: Mapped[float]`, `sales_velocity_score: Mapped[float]`, `cached_at: Mapped[datetime]`
  - [x] Define `AgentDecision` model (audit log): `id: Mapped[int]` (PK autoincrement), `account_id: Mapped[str]`, `agent: Mapped[str]`, `decision_type: Mapped[str]`, `from_value: Mapped[str | None]`, `to_value: Mapped[str | None]`, `rationale: Mapped[str]`, `supporting_data: Mapped[str | None]` (JSON string), `created_at: Mapped[datetime]`
  - [x] Define `Error` model: `id: Mapped[int]` (PK autoincrement), `account_id: Mapped[str]`, `agent: Mapped[str]`, `error_type: Mapped[str]`, `message: Mapped[str]`, `video_id: Mapped[str | None]`, `recovery_suggestion: Mapped[str | None]`, `timestamp: Mapped[datetime]`, `resolved_at: Mapped[datetime | None]`
  - [x] Write unit test `tests/unit/db/test_models.py` covering: table name assertions, index assertion, column presence for each model

- [x] Task 4: Implement `tiktok_faceless/db/session.py` — engine + session (AC: 4)
  - [x] Create `get_engine(database_url: str | None = None) -> Engine` — defaults to `DATABASE_URL` env var, falls back to `sqlite:///./tiktok_faceless_dev.db`
  - [x] Create `get_session(engine: Engine | None = None) -> Generator[Session, None, None]` as a context manager using `contextlib.contextmanager`
  - [x] Create `init_db(engine: Engine) -> None` that calls `Base.metadata.create_all(bind=engine)` — for SQLite dev use only
  - [x] Write unit test `tests/unit/db/test_session.py` covering: SQLite in-memory session returns valid session, tables created after init_db

- [x] Task 5: Initialize Alembic and create first migration (AC: 3)
  - [x] Run `uv run alembic init tiktok_faceless/db/migrations` (or update the existing placeholder `env.py`)
  - [x] Configure `alembic.ini` to use `DATABASE_URL` env var: `sqlalchemy.url = %(DATABASE_URL)s`
  - [x] Update `env.py` to import `Base` from `tiktok_faceless.db.models` and set `target_metadata = Base.metadata`
  - [x] Run `uv run alembic revision --autogenerate -m "initial_schema"` to create first migration
  - [x] Run `uv run alembic upgrade head` and confirm all 6 tables and the composite index are created
  - [x] Verify migration script is saved in `db/migrations/versions/`

- [x] Task 6: Verify all checks pass (AC: 5)
  - [x] Run `uv run pytest` — all tests must pass
  - [x] Run `uv run ruff check .` — must exit 0
  - [x] Run `uv run mypy tiktok_faceless/` — must exit 0 (strict mode — annotate everything)
  - [x] Update placeholder files that are now implemented to remove old placeholder docstrings

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS — READ FIRST

**DO NOT DEVIATE. These are enforced project-wide.**

1. **Pydantic v2 ONLY** — `BaseModel`, `ConfigDict`, `Field`, `field_validator`. NEVER use `class Config:` (v1 pattern). NEVER import from `pydantic.v1`.

2. **`state.py` has ZERO imports from the rest of the project** — no imports from `config.py`, `db/`, `agents/`, `clients/`. This prevents circular dependencies. Only stdlib + pydantic imports allowed.

3. **SQLAlchemy 2.0 style ONLY** — use `Mapped[T]` and `mapped_column()` syntax. NEVER use legacy `Column(Integer, ...)` syntax. Example:
   ```python
   # CORRECT (2.0 style)
   id: Mapped[str] = mapped_column(String, primary_key=True)
   
   # WRONG (1.x legacy)
   id = Column(String, primary_key=True)
   ```

4. **`account_id` as first parameter** — every DB query function, every agent function, every client method takes `account_id` as the first meaningful param (after `self`).

5. **All timestamps in DB as `datetime`** — use `Mapped[datetime]` with `default=datetime.utcnow` for auto timestamps. In `PipelineState`, use `float` (Unix time) for `last_post_timestamp`.

6. **`VideoLifecycle` as `str, Enum`** — using `str` mixin allows direct comparison with string DB values without `.value` calls.

### Exact `PipelineState` Implementation

From architecture spec — implement EXACTLY as shown:

```python
from pydantic import BaseModel, Field
from typing import Literal, Annotated
from operator import add
import time

class PipelineState(BaseModel):
    account_id: str
    phase: Literal["warmup", "tournament", "commit", "scale"] = "warmup"
    candidate_niches: list[str] = []
    committed_niche: str | None = None
    selected_product: dict | None = None
    product_validated: bool = False
    current_script: str | None = None
    hook_archetype: str | None = None
    voiceover_path: str | None = None
    assembled_video_path: str | None = None
    published_video_id: str | None = None
    videos_produced_today: int = 0
    last_post_timestamp: float = 0.0
    fyp_reach_rate: float = 1.0
    suppression_alert: bool = False
    kill_video_ids: Annotated[list[str], add] = []
    affiliate_commission_week: float = 0.0
    agent_health: dict[str, bool] = {}
    errors: Annotated[list["AgentError"], add] = []
```

**Note on `Annotated[list[X], add]`:** LangGraph uses these reducers to merge state deltas — `add` means list items are appended, not replaced. This is critical for `kill_video_ids` and `errors` to accumulate across agent nodes.

### Exact `AccountConfig` Implementation

```python
from pydantic import BaseModel, Field

class AccountConfig(BaseModel):
    account_id: str
    tiktok_access_token: str
    tiktok_client_key: str
    tiktok_client_secret: str
    tiktok_open_id: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    anthropic_api_key: str
    niche_pool: list[str] = []
    max_posts_per_day: int = Field(default=3, ge=1, le=15)
    posting_window_start: int = Field(default=18, ge=0, le=23)
    posting_window_end: int = Field(default=22, ge=0, le=23)
    tournament_duration_days: int = Field(default=14, ge=7)
    retention_kill_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    fyp_suppression_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    commit_phase_min_videos: int = Field(default=5, ge=1)
```

### SQLAlchemy 2.0 Model Pattern

Use this exact pattern for all models:

```python
from sqlalchemy import String, Float, Integer, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Video(Base):
    __tablename__ = "videos"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # ... other fields
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

**The composite index must be declared explicitly:**
```python
class VideoMetric(Base):
    __tablename__ = "video_metrics"
    __table_args__ = (
        Index("ix_video_metrics_video_id_recorded_at", "video_id", "recorded_at"),
    )
```

### Alembic Configuration for env var URL

In `alembic.ini`, replace the default `sqlalchemy.url` with:
```ini
sqlalchemy.url = 
```
(leave blank — URL will come from env.py)

In `env.py`, add:
```python
import os
from dotenv import load_dotenv
load_dotenv()

config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
```

### File Touch Map for This Story

**Create/Replace (placeholder → implementation):**
- `tiktok_faceless/state.py` — replace docstring placeholder with full implementation
- `tiktok_faceless/config.py` — replace docstring placeholder with full implementation
- `tiktok_faceless/db/models.py` — replace docstring placeholder with full implementation
- `tiktok_faceless/db/session.py` — replace docstring placeholder with full implementation
- `tiktok_faceless/db/migrations/env.py` — replace placeholder with Alembic config
- `tiktok_faceless/db/migrations/alembic.ini` — replace placeholder with real alembic.ini

**Create new:**
- `tests/unit/test_state.py`
- `tests/unit/test_config.py`
- `tests/unit/db/__init__.py`
- `tests/unit/db/test_models.py`
- `tests/unit/db/test_session.py`
- `tiktok_faceless/db/migrations/versions/<hash>_initial_schema.py` (auto-generated by alembic)

**Do NOT touch:**
- `tiktok_faceless/agents/*.py` — still placeholders, will be implemented in later stories
- `tiktok_faceless/clients/*.py` — still placeholders
- `tiktok_faceless/graph.py` — still placeholder
- `tiktok_faceless/main.py` — still placeholder

### Testing Requirements

- All tests use `pytest` + `pytest-asyncio` (no async needed for this story but setup must work)
- Use `pytest` fixtures in `conftest.py` for reusable SQLite in-memory engine
- For `AccountConfig` env var tests, use `monkeypatch.setenv()` — do NOT write to `.env` file
- For DB tests, use `sqlite:///:memory:` — never use the dev `.db` file in tests
- Test `VideoLifecycle` enum values exhaustively — every state transition matters downstream

### mypy Strict Mode Requirements

With `strict = true` in `pyproject.toml`, ALL of these must pass:

```python
# Must have return type annotations
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]: ...

# Must NOT use bare dict/list where types are known
def get_engine(database_url: str | None = None) -> Engine: ...

# Pydantic models are naturally typed — no issues expected
# SQLAlchemy 2.0 Mapped[] is also naturally typed
```

The `ignore_missing_imports = true` setting handles SQLAlchemy/Pydantic stub gaps.

### Previous Story Learnings (Story 1.1)

- The `Write` tool fails for new files without a prior `Read` — use `Bash` with heredoc for new file creation if needed
- `ruff` must exclude pre-existing non-package files (`tools/`, `tiktok_upload.py`) — this is already configured in `pyproject.toml`
- All placeholder files currently have docstring-only content — they will pass mypy as-is
- `uv sync` is already done; all dependencies are installed in `.venv/`

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Core Architectural Decisions > Data Architecture", "Implementation Patterns > Type Safety — Pydantic v2 Throughout", "Project Structure & Boundaries"
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.2 (lines 275–303)
- Architecture PipelineState spec: architecture.md section "Pydantic v2 Throughout" (exact field list + types)
- Architecture DB tables: architecture.md section "Core Tables" (column specs)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 6 tasks completed. 38 tests pass (11 state, 8 config, 12 models, 5 session, 2 smoke).
- `state.py`: `VideoLifecycle(str, Enum)`, `AgentError(BaseModel)`, `PipelineState(BaseModel)` with `Annotated[list, add]` reducers for LangGraph fan-out merging. Zero project imports — no circular dep risk.
- `config.py`: `AccountConfig` with Pydantic `Field(ge=..., le=...)` validators + `load_account_config()` from env vars.
- `db/models.py`: SQLAlchemy 2.0 `Mapped[]` syntax. `Video.account_id` has explicit FK to `accounts.account_id`. Composite index `ix_video_metrics_video_id_recorded_at` on VideoMetric confirmed. Video `__table_args__` redundant index removed (implicit from `index=True` on `mapped_column`).
- `db/session.py`: `get_engine()`, `init_db()`, `get_session()` context manager with rollback on exception.
- Alembic: `script.py.mako` template created manually (not present in placeholder). Migration `4c34fe0b3891_initial_schema.py` auto-generated and `alembic upgrade head` confirmed all 6 tables + indexes.
- All checks pass: `pytest` (38/38), `ruff check .` (0 errors), `mypy tiktok_faceless/` (0 issues in 35 files).

### File List

**Implemented (placeholder → full implementation):**
- `tiktok_faceless/state.py`
- `tiktok_faceless/config.py`
- `tiktok_faceless/db/models.py`
- `tiktok_faceless/db/session.py`
- `tiktok_faceless/db/migrations/env.py`
- `tiktok_faceless/db/migrations/alembic.ini`

**Created new:**
- `tiktok_faceless/db/migrations/script.py.mako`
- `tiktok_faceless/db/migrations/versions/4c34fe0b3891_initial_schema.py`
- `tests/unit/test_state.py`
- `tests/unit/test_config.py`
- `tests/unit/db/__init__.py`
- `tests/unit/db/test_models.py`
- `tests/unit/db/test_session.py`
- `tiktok_faceless_dev.db` (SQLite dev DB — gitignored)
