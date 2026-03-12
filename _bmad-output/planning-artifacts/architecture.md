---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-03-10'
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-tiktok-faceless-2026-03-08.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - _bmad-output/planning-artifacts/research/technical-tiktok-faceless-architecture-research-2026-03-09.md
workflowType: 'architecture'
project_name: 'tiktok-faceless'
user_name: 'Ivanma'
date: '2026-03-10'
---

# Architecture Decision Document: tiktok-faceless

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

---

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
44 FRs across 8 capability areas: Orchestration & Pipeline Control (FR1–6), Content Research & Validation (FR7–10), Script Generation (FR11–13), Video Production (FR14–16), Publishing (FR17–21), Analytics & Optimization (FR22–26), Monetization (FR27–29), Error Handling & Recovery (FR30–34), Dashboard & Monitoring (FR35–41), Account & Configuration Management (FR42–44).

**Non-Functional Requirements:**
- Performance: Full pipeline cycle <10 min per video; dashboard load <5s; analytics retrieved within 15 min of polling interval
- Security: Env-var credentials only; HTTPS; per-account credential isolation by `account_id`; dashboard auth-gated
- Reliability: ≥95% pipeline uptime; crash recovery to consistent state without duplicate posts; agent failure isolation (no cascade)
- Scalability: `account_id` parameterization throughout; supports 10 accounts on single VM; schema supports arbitrary accounts/videos/niches
- Integration: Graceful TikTok/ElevenLabs/video API rate limit handling; job-level render failure isolation; configurable commission reconciliation schedule

**Scale & Complexity:**
- Primary domain: Python agent orchestration system + web dashboard
- Complexity level: Medium-High (greenfield, multi-agent, 6 external API dependencies)
- Estimated architectural components: 9 (Orchestrator + 6 agents + DB + Dashboard)

### Technical Constraints & Dependencies

- TikTok API audit required for public posting — longest lead time item; sandbox = private posts, 5 users/day only
- TikTok API hard limits: 15 posts/day/account, 6 req/min per OAuth token
- TikTok analytics data has 24-48h lag — affects 48-hour kill-switch timing accuracy
- ElevenLabs concurrent request limits: 5 (Creator plan), 10 (Pro)
- Video generation API throughput is tier-gated (Runway Tier 1: 200 generations/day; Kling via fal.ai: queue-based)
- State must survive VM restarts — SQLite for MVP, PostgreSQL for LangGraph checkpointing in production
- Single Python process on Linux VM (systemd-managed), 2 vCPU / 4GB RAM target

---

## Starter Template Evaluation

### Primary Technology Domain

Python backend agent orchestration system with web monitoring dashboard. No framework starter equivalent — project bootstrapped via `uv init` with manual module scaffolding.

### Starter Options Considered

**Option A: `uv init` + manual LangGraph scaffolding (SELECTED)**
Clean Python project with full control over structure. Aligns with solo-dev VPS deployment model (systemd-managed). No unwanted cloud infrastructure overhead.

**Option B: `langgraph new` (LangGraph CLI)**
Opinionated starter targeting LangGraph Platform cloud deployment. Adds Docker + `langgraph.json` config unnecessary for a bare VPS + systemd approach. Rejected: too cloud-platform-specific.

### Selected Starter: `uv init`

**Rationale for Selection:**
- Project runs as a persistent systemd process on a Linux VPS — not a LangGraph Platform deployment
- `uv` is the current Python packaging standard (2025–2026), replacing pip + venv for solo devs
- Manual scaffolding gives precise control over module boundaries, essential for the 6-agent architecture

**Initialization Commands:**

```bash
uv init tiktok-faceless
cd tiktok-faceless
uv add langgraph langsmith elevenlabs httpx tenacity \
       sqlalchemy alembic psycopg2-binary python-dotenv streamlit
uv add --dev pytest pytest-asyncio ruff mypy
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:** Python 3.12+, managed by uv

**Project Structure:**
```
tiktok_faceless/
├── agents/          # orchestrator.py, research.py, script.py, production.py,
│                    # publishing.py, analytics.py, monetization.py
├── clients/         # tiktok.py, elevenlabs.py, creatomate.py, fal.py
├── state.py         # PipelineState TypedDict
├── graph.py         # LangGraph graph assembly
├── main.py          # Entry point + graph runner
├── config.py        # Env var loading, account config
├── db/              # SQLAlchemy models + Alembic migrations
├── dashboard/       # Streamlit app
└── tests/           # unit/ and integration/
```

**Build Tooling:** uv for dependency management and virtualenv

**Testing Framework:** pytest + pytest-asyncio

**Code Quality:** ruff (lint + format), mypy (type checking)

**Development Experience:**
- `.env` / `.env.example` for local secrets (never committed)
- `pyproject.toml` as single project config source
- `systemd` unit file for production process management

**Note:** Project initialization and directory scaffolding is Story 0 — the first implementation story.

---

### Cross-Cutting Concerns Identified

- **State persistence:** Every agent reads/writes shared `PipelineState` — crash recovery is a system-wide concern, not per-agent
- **`account_id` isolation:** Every DB query, API call, credential lookup, and agent invocation must be scoped by `account_id`
- **Structured error logging:** All 6 agents must emit consistent structured failure events to a central error log with recovery guidance surfaced in dashboard
- **Rate limit handling:** TikTok API, ElevenLabs, and video generation APIs each have distinct rate profiles — all require circuit breaker + retry with exponential backoff
- **Suppression monitoring:** FYP reach rate monitoring spans Publishing (posting behavior) and Analytics (signal detection) — requires coordinated state
- **Phase awareness:** Orchestrator phase state is a global concern — all agents adapt volume and behavior based on current phase

---

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Orchestration: LangGraph v1.0 + PostgresSaver for crash recovery
- State: Shared `PipelineState` TypedDict — single source of truth for all agents
- DB: SQLite (MVP/dev) → PostgreSQL (production); SQLAlchemy ORM + Alembic migrations
- `account_id` parameterization throughout — every function, DB query, API call
- Video lifecycle state machine: `queued → rendering → rendered → scheduled → posted → analyzed → archived/promoted`

**Important Decisions (Shape Architecture):**
- Analytics storage: Append-only event log (never mutable row updates)
- Dashboard: Streamlit reading PostgreSQL directly (no FastAPI intermediary)
- Dashboard auth: Single password via env var + `st.session_state` guard
- Secrets: `python-dotenv` local; systemd `EnvironmentFile=` production
- Error contract: All client methods raise typed exceptions; agent nodes return `{"errors": [...]}` state deltas

**Deferred Decisions (Post-MVP):**
- Redis/caching layer — application-level 24h TTL in PostgreSQL is sufficient at MVP
- FastAPI backend — Streamlit direct DB access is sufficient for a single read-only dashboard
- Container orchestration — systemd is sufficient for single-account MVP; revisit at 10+ accounts

### Data Architecture

**Database:**
- Development: SQLite (zero infrastructure, `SqliteSaver` for LangGraph)
- Production: PostgreSQL 16 (`PostgresSaver` for LangGraph + SQLAlchemy ORM)
- Migrations: Alembic — all schema changes tracked in version control

**Core Tables:**
- `accounts` — per-account config, credentials ref, phase state
- `videos` — video lifecycle state machine, niche, hook archetype, file paths, affiliate link
- `video_metrics` — append-only event log (recorded_at, views, likes, 3s_retention, 15s_retention, fyp_pct, affiliate_clicks, affiliate_orders)
- `products` — validated products cache (cached_at, niche, sales_velocity, affiliate_commission_rate)
- `agent_decisions` — audit log: phase transitions, niche commits, kill-switch decisions with supporting data
- `errors` — structured error log: agent, video_id, error_type, timestamp, recovery_suggestion, resolved_at

**Analytics pattern:** Append-only. All per-video metrics written as new rows with `recorded_at`. Aggregations computed at query time. Supports sparkline trends, A/B test history without write conflicts.

**Caching:** Product research results cached in `products` table with `cached_at`. 24h TTL enforced in application code. No Redis at MVP.

### Authentication & Security

- Dashboard auth: `DASHBOARD_PASSWORD` env var checked on session init via `st.session_state["authenticated"]`
- Secrets: `.env` for local dev; systemd `EnvironmentFile=` for production; never committed to VCS
- Per-account credential isolation: `account_id` FK on all credential lookups; no cross-account access by design
- TikTok OAuth tokens: Stored encrypted in `accounts` table; refreshed proactively 5 min before expiry
- Dashboard: No public endpoints; served on VPS; firewall-restricted to operator IP

### API & Communication Patterns

- **Agent communication:** LangGraph `PipelineState` TypedDict only — no direct agent-to-agent calls
- **State updates:** Each agent node returns a state delta dict; LangGraph merges via annotated reducers
- **External API pattern:** All calls through typed client wrapper classes — agents never call external APIs directly
- **Error contract:** Client methods raise typed exceptions; agent nodes catch at boundary and return `{"errors": [StructuredError(...)]}` — graph never crashes
- **Rate limiting:** Token bucket enforced in client wrappers (6 req/min TikTok; plan-dependent ElevenLabs)
- **Dashboard data:** Streamlit reads PostgreSQL via SQLAlchemy directly
- **Dashboard refresh:** `streamlit-autorefresh` at 60s interval

### Infrastructure & Deployment

- **Hosting:** Hetzner CX22 VPS (2 vCPU / 4GB RAM, ~$4.49/mo)
- **Process management:** systemd unit file with `Restart=always`, `EnvironmentFile=`
- **Database:** Supabase free tier (PostgreSQL, auto-backup) or self-hosted on same VPS
- **Observability:** LangSmith (automatic graph tracing) + Python `logging` → JSON → systemd journal
- **Alerting:** Telegram webhook for suppression alerts, pipeline pause, 24h no-post health check
- **CI/CD:** GitHub Actions — ruff + mypy + pytest on push to `main`; manual deploy (SSH + git pull + systemctl restart)
- **Environments:** Local (SQLite + `.env`) → Staging (VPS + PostgreSQL + private TikTok) → Production

### Decision Impact Analysis

**Implementation Sequence (dependency order):**
1. `uv init` + project structure + `pyproject.toml`
2. `PipelineState` TypedDict + LangGraph graph skeleton (stub nodes)
3. SQLAlchemy models + Alembic initial migration
4. Client wrappers (TikTok, ElevenLabs, Creatomate) with typed exceptions
5. Production Agent (ElevenLabs + Creatomate) — highest integration risk, validate first
6. Publishing Agent (TikTok Content Posting API)
7. Analytics Agent (TikTok Analytics API + suppression monitor)
8. Research Agent (TikTok Shop product polling)
9. Monetization Agent (affiliate link generation)
10. Orchestrator phase logic (Tournament → Commit → Scale)
11. Streamlit dashboard
12. systemd deployment + LangSmith wiring

**Cross-Component Dependencies:**
- All agents depend on `PipelineState` schema being finalized before implementation
- Publishing Agent depends on TikTok API audit approval for public posts
- Analytics Agent 48h kill switch must account for TikTok analytics 24-48h data lag
- Dashboard depends on `video_metrics` append-only schema being stable

---

## Implementation Patterns & Consistency Rules

**Critical Conflict Points Identified:** 7 areas where AI agents could make different choices without explicit rules.

### Naming Patterns

**Python code — all `snake_case`:**
- Functions: `get_validated_products()`, `post_video()`, `check_suppression()`
- Variables/state fields: `account_id`, `video_id`, `fyp_reach_rate`, `hook_archetype`
- Files: `research_agent.py`, `tiktok_client.py`, `pipeline_state.py`
- Modules: `tiktok_faceless/agents/`, `tiktok_faceless/clients/`

**Database — `snake_case`, plural table names:**
- Tables: `accounts`, `videos`, `video_metrics`, `products`, `agent_decisions`, `errors`
- Columns: `account_id`, `video_id`, `recorded_at`, `hook_archetype`, `fyp_pct`
- Foreign keys: `account_id` (never `fk_account`, never `accountId`)
- Indexes: `ix_{table}_{column}` — e.g. `ix_video_metrics_video_id_recorded_at`

**Environment variables — `UPPER_SNAKE_CASE`:**
`TIKTOK_ACCESS_TOKEN`, `ELEVENLABS_API_KEY`, `DASHBOARD_PASSWORD`, `LANGCHAIN_API_KEY`

**Typed exceptions — `PascalCase` + domain prefix:**
`TikTokRateLimitError`, `TikTokAuthError`, `ElevenLabsError`, `RenderError`, `SuppressionDetectedError`

### Structure Patterns

**One agent = one file in `agents/`, exports one public function:**
```python
# agents/research.py
def research_node(state: PipelineState) -> dict: ...  # only public export
```

**One external service = one client class in `clients/`:**
- `clients/tiktok.py` → `TikTokAPIClient`
- `clients/elevenlabs.py` → `ElevenLabsClient`
- `clients/creatomate.py` → `CreatomateClient`
- `clients/fal.py` → `FalClient`

**Tests mirror source structure:**
- `tests/unit/agents/test_research.py` mirrors `tiktok_faceless/agents/research.py`
- `tests/integration/` — real API call tests only (excluded from default CI run)

**DB models in `db/models.py` only; migrations in `db/migrations/`:**
Never define models inline in agent files; never write raw SQL in agents.

### Type Safety — Pydantic v2 Throughout

**`PipelineState` as Pydantic `BaseModel`** (LangGraph supports natively):
```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Annotated
from operator import add

class PipelineState(BaseModel):
    account_id: str
    phase: Literal["warmup", "tournament", "commit", "scale"]
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

**`AgentError` as Pydantic `BaseModel`** (replaces dataclass):
```python
class AgentError(BaseModel):
    agent: str
    error_type: str
    message: str
    video_id: str | None = None
    recovery_suggestion: str | None = None
    timestamp: float = Field(default_factory=time.time)
```

**External API responses parsed through Pydantic models:**
```python
class TikTokVideoMetrics(BaseModel):
    video_id: str
    view_count: int
    like_count: int
    average_time_watched: float
    traffic_source_type: dict[str, float]
```

**`AccountConfig` as Pydantic `BaseModel` with validators:**
```python
class AccountConfig(BaseModel):
    account_id: str
    tiktok_access_token: str
    elevenlabs_voice_id: str
    niche_pool: list[str]
    max_posts_per_day: int = Field(default=3, ge=1, le=15)
    posting_window_start: int = Field(default=18, ge=0, le=23)
    tournament_duration_days: int = Field(default=14, ge=7)
    retention_kill_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
```

**SQLAlchemy ORM for DB models only** (not Pydantic) — separate concern.

### Format Patterns

**Agent node return — state delta dict only (never full state):**
```python
# CORRECT
def research_node(state: PipelineState) -> dict:
    return {"selected_product": product, "product_validated": True}

# WRONG — never return or mutate full state
state["selected_product"] = product  # ❌
return state  # ❌
```

**Timestamps — Unix float (`time.time()`) in state; ISO 8601 in DB `recorded_at` columns.**

**Booleans — `True/False` only** — never `1/0` or `"yes"/"no"`.

### Communication Patterns

**Phase transitions — `orchestrator.py` only:**
No other agent writes `state["phase"]`. Phase change must write an `agent_decisions` DB row with supporting data before transitioning.

**Suppression signal flow:**
Analytics writes `state["suppression_alert"] = True` → Orchestrator reads on next cycle and routes to pause subgraph → Publishing does NOT read suppression state directly.

**LangGraph `Send` for Tournament fan-out:**
Use LangGraph's `Send` API for parallel niche research — never `asyncio.gather` across agent nodes.

### Process Patterns

**`tenacity` `@retry` on all external API calls (mandatory):**
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=30))
def call_elevenlabs(self, text: str) -> bytes: ...
```
3 attempts, exponential backoff 4s → 16s → 30s. After 3 failures: raise typed exception.

**`account_id` as first parameter — always:**
Every client method, every DB query function, every agent node reads `account_id` from state first.

**No hardcoded config — all values from `config.py`:**
Never hardcode `3` posts/day, `14` days for tournament, `0.40` retention threshold in agent code.

### Enforcement Guidelines

**All AI agents implementing this codebase MUST:**
1. Return state delta dicts (not full state) from node functions
2. Use Pydantic `BaseModel` for state, errors, API responses, config — never bare `dict` or `TypedDict`
3. Scope every DB query and API call by `account_id`
4. Use typed client wrapper classes — never call external APIs directly from agent functions
5. Use `AgentError` Pydantic model for all error reporting
6. Never write `state["phase"]` outside `orchestrator.py`
7. Apply `tenacity` `@retry` on all external API calls
8. Load all config values from `config.py` — never hardcode

**Anti-patterns (explicitly forbidden):**
- `state["phase"] = "commit"` in any file other than `orchestrator.py`
- `requests.post("https://api.elevenlabs.io/...")` directly in an agent function
- Bare `dict` for structured data that has a Pydantic model
- Raw SQL strings in agent files
- `time.sleep()` for rate limiting — use token bucket in client wrappers

---

## Project Structure & Boundaries

### Complete Project Directory Structure

```
tiktok-faceless/
├── pyproject.toml                    # uv project config, all dependencies
├── .env                              # secrets (gitignored)
├── .env.example                      # template with all required env vars
├── .gitignore
├── README.md
├── systemd/
│   └── tiktok-faceless.service       # systemd unit file for VPS deployment
├── .github/
│   └── workflows/
│       └── ci.yml                    # ruff + mypy + pytest on push to main
│
├── tiktok_faceless/
│   ├── state.py                      # PipelineState BaseModel (Pydantic v2)
│   │                                 # AgentError BaseModel, VideoLifecycle enum
│   ├── config.py                     # AccountConfig BaseModel + env var loading
│   │                                 # all tunable constants (thresholds, cadence, etc.)
│   ├── graph.py                      # LangGraph graph assembly, node registration,
│   │                                 # conditional edges, checkpointer setup
│   ├── main.py                       # entry point: load config, build graph, run loop
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # FR1–6: phase routing, transitions, health checks
│   │   │                             # ONLY file that writes state["phase"]
│   │   ├── research.py               # FR7–10: product validation, comment mining, niche scan
│   │   ├── script.py                 # FR11–13: hook variants, persona application
│   │   ├── production.py             # FR14–16: ElevenLabs TTS + Creatomate assembly
│   │   ├── publishing.py             # FR17–21: TikTok posting, cadence randomization
│   │   ├── analytics.py              # FR22–26: metrics pull, kill switch, suppression monitor
│   │   └── monetization.py           # FR27–29: affiliate link gen, commission tracking
│   │
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── tiktok.py                 # TikTokAPIClient: post_video, get_metrics,
│   │   │                             # get_affiliate_orders, OAuth token refresh,
│   │   │                             # token bucket rate limiter (6 req/min)
│   │   ├── elevenlabs.py             # ElevenLabsClient: generate_voiceover, clone_voice
│   │   ├── creatomate.py             # CreatomateClient: submit_render, poll_status, download
│   │   ├── fal.py                    # FalClient: kling_generate (optional generative video)
│   │   └── llm.py                    # LLMClient: script generation (claude-haiku-4-5)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                 # SQLAlchemy ORM: Account, Video, VideoMetric,
│   │   │                             # Product, AgentDecision, Error
│   │   ├── session.py                # engine setup, get_session() context manager
│   │   ├── queries.py                # typed query functions (all scoped by account_id)
│   │   └── migrations/
│   │       ├── env.py                # Alembic env config
│   │       ├── alembic.ini
│   │       └── versions/             # versioned migration scripts
│   │
│   ├── models/                       # Pydantic response/request models (not DB)
│   │   ├── __init__.py
│   │   ├── tiktok.py                 # TikTokVideoMetrics, TikTokPostResponse
│   │   ├── elevenlabs.py             # ElevenLabsVoiceConfig
│   │   └── shop.py                   # AffiliateProduct, CommissionRecord
│   │
│   └── utils/
│       ├── __init__.py
│       ├── retry.py                  # shared tenacity retry decorators
│       ├── timing.py                 # randomized posting window logic
│       ├── suppression.py            # FYP rate calculation, shadowban detection
│       ├── alerts.py                 # Telegram webhook sender
│       └── video.py                  # ffmpeg helpers: metadata strip, caption burn
│
├── dashboard/
│   ├── app.py                        # Streamlit entry point (FR35–41)
│   ├── auth.py                       # password gate via st.session_state
│   ├── pages/
│   │   ├── overview.py               # phase indicator, pipeline health, revenue summary
│   │   ├── videos.py                 # per-video metrics table with sparklines
│   │   ├── decisions.py              # agent decision audit log
│   │   └── errors.py                 # error log with recovery guidance
│   └── components/
│       ├── phase_badge.py            # Tournament/Commit/Scale visual indicator
│       ├── suppression_alert.py      # FYP rate alert banner
│       └── sparkline.py              # retention/CTR trend charts
│
└── tests/
    ├── conftest.py                   # shared fixtures, mock factories
    ├── unit/
    │   ├── agents/
    │   │   ├── test_orchestrator.py  # phase routing logic, transition conditions
    │   │   ├── test_research.py      # product validation logic, niche scoring
    │   │   ├── test_script.py        # hook archetype selection, persona application
    │   │   ├── test_production.py    # video assembly pipeline logic
    │   │   ├── test_publishing.py    # cadence randomization, timing windows
    │   │   ├── test_analytics.py     # 48h kill switch, suppression detection
    │   │   └── test_monetization.py  # affiliate link management
    │   ├── clients/
    │   │   ├── test_tiktok.py        # rate limiter, token refresh, error mapping
    │   │   └── test_elevenlabs.py    # retry logic, error handling
    │   └── utils/
    │       ├── test_timing.py
    │       └── test_suppression.py
    └── integration/
        ├── test_tiktok_api.py        # real API calls (private account, skipped in CI)
        ├── test_elevenlabs_api.py
        └── test_full_pipeline.py     # end-to-end graph with SqliteSaver
```

### Architectural Boundaries

**Agent Boundary:** Each agent has one public function `*_node(state) -> dict`. Agents import from `clients/` and `db/queries.py` — never from other `agents/` files.

**Client Boundary:** Client classes own all HTTP, rate limiting, auth, and retry. Agents receive typed return values or typed exceptions — never raw HTTP responses.

**DB Boundary:** `db/queries.py` owns all DB interactions. Agents never access SQLAlchemy sessions directly. All queries scoped by `account_id`.

**Dashboard Boundary:** `dashboard/` imports `db/session.py` and `db/queries.py` only. Never imports from `agents/` or `clients/`.

**State Boundary:** `state.py` has zero imports from the rest of the project — no circular dependencies possible.

### Requirements to Structure Mapping

| FR Group | Primary Files |
|---|---|
| FR1–6 Orchestration | `agents/orchestrator.py`, `graph.py`, `state.py` |
| FR7–10 Research | `agents/research.py`, `clients/tiktok.py`, `models/shop.py` |
| FR11–13 Script | `agents/script.py`, `clients/llm.py` |
| FR14–16 Production | `agents/production.py`, `clients/elevenlabs.py`, `clients/creatomate.py` |
| FR17–21 Publishing | `agents/publishing.py`, `clients/tiktok.py`, `utils/timing.py` |
| FR22–26 Analytics | `agents/analytics.py`, `clients/tiktok.py`, `utils/suppression.py` |
| FR27–29 Monetization | `agents/monetization.py`, `clients/tiktok.py`, `models/shop.py` |
| FR30–34 Error Handling | `state.py` (AgentError), `db/models.py` (Error table), `utils/alerts.py` |
| FR35–41 Dashboard | `dashboard/` (all files) |
| FR42–44 Account Mgmt | `config.py`, `db/models.py` (Account), `db/queries.py` |

**Cross-cutting → `utils/`:**
Suppression monitoring → `utils/suppression.py` | Posting timing → `utils/timing.py` | Retry decorators → `utils/retry.py` | Alerting → `utils/alerts.py` | Video metadata → `utils/video.py`

### Data Flow

```
main.py → graph.py (LangGraph runner)
  └── orchestrator_node (reads phase, routes via conditional edges)
        ├── research_node → clients/tiktok.py → models/shop.py → db/queries.py
        ├── script_node  → clients/llm.py
        ├── production_node → clients/elevenlabs.py + clients/creatomate.py
        │                     writes: voiceover_path, assembled_video_path to state
        ├── publishing_node → clients/tiktok.py
        │                     writes: Video row to DB, published_video_id to state
        ├── analytics_node → clients/tiktok.py
        │                     writes: VideoMetric rows (append-only) to DB
        │                     sets: suppression_alert in state if FYP drops
        └── monetization_node → clients/tiktok.py
                                writes: CommissionRecord to DB

dashboard/app.py → db/session.py + db/queries.py (read-only PostgreSQL)
  └── renders: overview, video table, decision log, error log
```
