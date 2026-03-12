---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: 'complete'
completedAt: '2026-03-11'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
---

# tiktok-faceless - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for tiktok-faceless, decomposing the requirements from the PRD, Architecture, and UX Design Specification into implementable stories.

## Requirements Inventory

### Functional Requirements

**Orchestration & Pipeline Control**
FR1: The Orchestration Agent can coordinate the full pipeline sequence (Research → Script → Production → Publishing → Analytics → Monetization) autonomously per account
FR2: The Orchestration Agent can operate in three distinct phase modes (Tournament, Commit, Scale) with different agent behaviors and volume targets per phase
FR3: The Orchestration Agent can automatically detect a Tournament Phase winner and transition to Commit Phase without operator input
FR4: The Orchestration Agent can detect niche commission decay and trigger a re-tournament automatically
FR5: The Orchestration Agent can notify the operator of phase transitions and major autonomous decisions via the dashboard after execution
FR6: The system can resume pipeline execution from last known state after a VM restart or crash

**Content Research & Validation**
FR7: The Research Agent can identify and validate products based on buyer intent signals (TikTok Shop sales velocity, affiliate signal strength)
FR8: The Research Agent can mine top-performing affiliate video comments for buyer language to feed into script templates
FR9: The Research Agent can scan multiple product niches simultaneously during Tournament Phase
FR10: The Research Agent can continuously monitor commission-per-view signals for the committed niche and surface decay alerts

**Script Generation**
FR11: The Script Agent can generate video scripts for validated products using buyer language from research
FR12: The Script Agent can produce 3 distinct hook archetype variants per product (curiosity gap, social proof, controversy, demonstration)
FR13: The Script Agent can apply a consistent AI persona (name, personality, catchphrases) across all scripts for an account

**Video Production**
FR14: The Production Agent can generate a publish-ready vertical video (voiceover + visuals + auto-captions) from a script without manual editing
FR15: The Production Agent can synthesize voiceover audio using a configured ElevenLabs voice (stock or custom clone)
FR16: The Production Agent can queue render jobs and process them independently of other pipeline stages

**Publishing**
FR17: The Publishing Agent can post videos to TikTok with embedded affiliate links
FR18: The Publishing Agent can schedule posts within configurable optimal posting windows
FR19: The Publishing Agent can enforce configurable minimum time intervals between posts
FR20: The Publishing Agent can introduce randomized variability in posting cadence, timing, and video length to reduce bot-detection risk
FR21: The Publishing Agent can adjust posting volume based on current phase

**Analytics & Optimization**
FR22: The Analytics Agent can retrieve and store per-video performance data (3s retention, 15s retention, views, likes, affiliate CTR, commissions)
FR23: The Analytics Agent can evaluate videos at the 48-hour mark and trigger archive or promote decisions based on configurable retention and CTR thresholds
FR24: The Analytics Agent can track performance per niche category during Tournament Phase to determine the winner
FR25: The Analytics Agent can detect FYP reach rate drops as a shadowban signal and surface alerts
FR26: The Analytics Agent can compare hook archetype performance across A/B variants and surface winning patterns

**Monetization**
FR27: The Monetization Agent can generate and manage TikTok Shop affiliate links per product
FR28: The Monetization Agent can track affiliate commissions per video, per product, and per niche
FR29: The Monetization Agent can reconcile system-tracked click data with TikTok Shop reported commissions on a configurable schedule

**Error Handling & Recovery**
FR30: The system can detect and log failures for each agent independently without cascading failures to other agents
FR31: The system can pause a failing agent's queue while other agents continue operating
FR32: The system can surface structured error logs including failure type, timestamp, affected video/agent, and suggested recovery action
FR33: The operator can manually resume a paused agent pipeline after resolving an error
FR34: The system can automatically retry failed operations with configurable retry logic and backoff

**Operator Dashboard & Monitoring**
FR35: The operator can view current system phase and active agents in the dashboard
FR36: The operator can view revenue summary by account, niche, and video in the dashboard
FR37: The operator can view per-video performance metrics (retention, CTR, commission, status) in the dashboard
FR38: The operator can view the error log with recovery guidance in the dashboard
FR39: The operator can view the agent decision audit log (phase transitions, niche commits, kill-switch decisions with supporting data) in the dashboard
FR40: The operator can view milestone achievement notifications in the dashboard
FR41: The operator can view suppression signal alerts (FYP rate drop, shadowban indicators) in the dashboard

**Account & Configuration Management**
FR42: The system can operate multiple accounts in isolation, each parameterized by a unique `account_id`
FR43: The operator can provision a new account by supplying credentials, with the system cloning configuration from an existing account
FR44: The operator can configure per-account parameters (niche pool, posting windows, Tournament duration, phase thresholds) via configuration files

### NonFunctional Requirements

**Performance**
NFR1: Full pipeline cycle (research → script → production → scheduling) for a single video completes in under 10 minutes
NFR2: Analytics Agent retrieves and processes per-video performance data within 15 minutes of a polling interval completing
NFR3: Dashboard loads current pipeline state and revenue summary within 5 seconds
NFR4: Publishing Agent post queue evaluated and dispatched within 60 seconds of a scheduled posting window opening

**Security**
NFR5: All API credentials stored as environment variables or in a secrets manager — never hardcoded or committed to source control
NFR6: All external API communications use HTTPS/TLS
NFR7: Dashboard access restricted to operator — no unauthenticated public endpoints
NFR8: Per-account credentials and configuration isolated by `account_id` — no cross-account credential access

**Reliability**
NFR9: Pipeline uptime ≥95% measured as: scheduled posts completed / scheduled posts attempted per week
NFR10: System recovers to consistent state after VM restart without data loss or duplicate posts
NFR11: Agent failures isolated — single agent failure does not crash or corrupt other agents' state
NFR12: No video posted without confirmed affiliate link — system blocks publishing if affiliate link generation failed

**Scalability**
NFR13: All agent logic parameterized by `account_id` — adding a new account requires configuration provisioning only, no code changes
NFR14: State database schema supports arbitrary number of accounts, videos, and niches without structural changes
NFR15: System can operate up to 10 accounts concurrently on a single VM; beyond 10 requires infrastructure review

**Integration**
NFR16: TikTok API rate limit responses handled gracefully — retries queued with exponential backoff, not permanent failure
NFR17: ElevenLabs API failures cause render queue pause and structured error surface — not silent audio substitution or voiceover skip
NFR18: Video generation API failures are job-level isolated — one failed render does not block other queued renders
NFR19: TikTok Shop commission data reconciled on a configurable schedule — system does not assume real-time commission accuracy

### Additional Requirements

**From Architecture — Project Initialization & Tooling:**
- Starter: `uv init` + manual LangGraph scaffolding (no framework starter template). Initialization: `uv init tiktok-faceless` then `uv add langgraph langsmith elevenlabs httpx tenacity sqlalchemy alembic psycopg2-binary python-dotenv streamlit` and `uv add --dev pytest pytest-asyncio ruff mypy`
- Project initialization and directory scaffolding is Story 0 — the first implementation story
- Python 3.12+, managed by `uv`
- pyproject.toml as single project config source
- `.env` / `.env.example` for local secrets (never committed)
- CI/CD: GitHub Actions — ruff + mypy + pytest on push to `main`; manual deploy via SSH + git pull + systemctl restart

**From Architecture — Core Technical Decisions:**
- LangGraph v1.0 + PostgresSaver for crash-recovery state persistence
- `PipelineState` as Pydantic v2 `BaseModel` (single source of truth for all agents)
- SQLite (dev) → PostgreSQL 16 (production); SQLAlchemy ORM + Alembic migrations
- `account_id` parameterization throughout — every function, DB query, API call
- Video lifecycle state machine: `queued → rendering → rendered → scheduled → posted → analyzed → archived/promoted`
- Append-only `video_metrics` event log — no mutable row updates
- Pydantic v2 `BaseModel` for all models (state, errors, API responses, config)
- `tenacity` `@retry` on all external API calls (3 attempts, exponential backoff 4s → 16s → 30s)
- Token bucket rate limiter in client wrappers (6 req/min TikTok; plan-dependent ElevenLabs)
- All config values from `config.py` — never hardcode thresholds in agent code

**From Architecture — Infrastructure & Deployment:**
- Hetzner CX22 VPS (2 vCPU / 4GB RAM, ~$4.49/mo)
- systemd unit file with `Restart=always`, `EnvironmentFile=` for production process management
- Supabase free tier (PostgreSQL) or self-hosted on same VPS
- LangSmith for automatic graph tracing + observability
- Telegram webhook for suppression alerts, pipeline pause, 24h no-post health check
- Dashboard: Streamlit app reading PostgreSQL directly (no FastAPI intermediary); auth via `DASHBOARD_PASSWORD` env var + `st.session_state` guard; auto-refresh via `streamlit-autorefresh` at 60s interval
- Environments: Local (SQLite + `.env`) → Staging (VPS + PostgreSQL + private TikTok) → Production

**From Architecture — Implementation Sequence (dependency order):**
- TikTok API audit required for public posting — longest lead time item (sandbox = private posts, 5 users/day only); validate first before full pipeline build
- Implementation sequence: uv init → PipelineState + graph skeleton → DB models + migrations → Client wrappers → Production Agent → Publishing Agent → Analytics Agent → Research Agent → Monetization Agent → Orchestrator phase logic → Streamlit dashboard → systemd deployment + LangSmith

**From UX — Dashboard Design Requirements:**
- Dashboard implemented in Streamlit (UX spec updated to reflect this — Signal Board layout translated to Streamlit primitives).
- Signal Board layout: exception-first alert zone above the fold, 5-column KPI strip, 50/50 agent pipeline panel + video table bottom panels
- Persistent top bar (48px fixed): Phase badge · Pipeline status · Last post time-ago · Videos today · Auto-refresh indicator
- Alert zone: green "all clear" when healthy; critical/warning banners when suppression or pipeline issues detected
- 5 KPI cards: Revenue, 3s Retention, 15s Retention, Affiliate CTR, FYP Reach — each with sparkline and freshness timestamp
- Agent pipeline panel: per-agent status (Research, Script, Production, Publishing, Analytics) with running/done/waiting/error states
- Niche tournament table with ranking, video count, avg metrics, revenue, and elimination/leading status
- Dark mode default; muted slate/zinc palette; status colors (emerald/amber/rose) reserved for genuine system states only
- Responsive: desktop-first (1024px+), tablet (768px+), mobile (320px+)
- WCAG 2.1 Level AA accessibility: aria-live on auto-refresh and alerts, aria-labels on all KPI cards, color never sole differentiator
- Time-since formatting, tabular-nums for all data values, pre-configured default views (no date picker required)

### FR Coverage Map

| FR | Epic | Description |
|---|---|---|
| FR1 | Epic 1 | Basic pipeline coordination (full phase awareness added in Epic 3) |
| FR2 | Epic 3 | Tournament/Commit/Scale phase modes |
| FR3 | Epic 3 | Auto-detect tournament winner, transition to Commit |
| FR4 | Epic 3 | Niche decay detection + re-tournament |
| FR5 | Epic 3 | Phase transition notifications to dashboard |
| FR6 | Epic 1 | Pipeline resume after VM restart/crash |
| FR7 | Epic 2 | Product validation via buyer intent signals |
| FR8 | Epic 2 | Comment mining for buyer language |
| FR9 | Epic 2 | Multi-niche scanning during Tournament |
| FR10 | Epic 2 | Commission-per-view decay monitoring |
| FR11 | Epic 1/2 | Basic script in Epic 1; full buyer-language scripts in Epic 2 |
| FR12 | Epic 2 | 3 hook archetype variants per product |
| FR13 | Epic 2 | AI persona applied consistently across scripts |
| FR14 | Epic 1 | Video production from script (voiceover + render) |
| FR15 | Epic 1 | ElevenLabs voiceover synthesis |
| FR16 | Epic 1 | Independent render queue |
| FR17 | Epic 1 | Post to TikTok with affiliate link |
| FR18 | Epic 1 | Schedule within optimal posting windows |
| FR19 | Epic 1 | Configurable minimum interval between posts |
| FR20 | Epic 1 | Randomized cadence variability (suppression resistance) |
| FR21 | Epic 3 | Phase-based posting volume adjustment |
| FR22 | Epic 4 | Per-video metrics retrieval and storage |
| FR23 | Epic 4 | 48-hour kill switch (archive/promote) |
| FR24 | Epic 3 | Per-niche performance tracking for tournament |
| FR25 | Epic 4 | FYP rate drop = shadowban signal |
| FR26 | Epic 4 | Hook archetype A/B comparison |
| FR27 | Epic 1 | Affiliate link generation per product |
| FR28 | Epic 2 | Commission tracking per video/product/niche |
| FR29 | Epic 4 | Commission reconciliation on schedule |
| FR30 | Epic 5 | Independent agent failure detection (no cascade) |
| FR31 | Epic 5 | Pause failing agent queue, others continue |
| FR32 | Epic 5 | Structured error log with recovery guidance |
| FR33 | Epic 5 | Manual resume after error resolution |
| FR34 | Epic 5 | Configurable retry + exponential backoff |
| FR35 | Epic 6 | Phase + active agents view |
| FR36 | Epic 6 | Revenue summary (account/niche/video) |
| FR37 | Epic 6 | Per-video metrics view |
| FR38 | Epic 6 | Error log with recovery guidance |
| FR39 | Epic 6 | Agent decision audit log |
| FR40 | Epic 6 | Milestone notifications |
| FR41 | Epic 6 | Suppression signal alerts |
| FR42 | Epic 7 | Multi-account isolation by account_id |
| FR43 | Epic 7 | Account provisioning with config clone |
| FR44 | Epic 7 | Per-account configuration |

## Epic List

### Epic 1: Foundation & First Autonomous Post
The operator can set up the system and see the first video posted to TikTok with an affiliate link — fully autonomously. Validates the end-to-end pipeline and TikTok API access as the first milestone.
**FRs covered:** FR1 (basic), FR6, FR11 (basic), FR14, FR15, FR16, FR17, FR18, FR19, FR20, FR27

### Epic 2: Intelligent Research & Content Strategy
Every video produced is demand-validated — the system mines buyer signals, researches products, and generates 3 hook variants with a consistent persona.
**FRs covered:** FR7, FR8, FR9, FR10, FR11 (full), FR12, FR13, FR28

### Epic 3: Tournament Engine & Phase Orchestration
The operator watches the system run the Tournament Phase, auto-commit to the winning niche, and shift into Commit Phase — with no intervention required.
**FRs covered:** FR2, FR3, FR4, FR5, FR21, FR24

### Epic 4: Analytics, Kill Switch & Optimization
The operator trusts the system is self-optimizing — underperforming videos are auto-archived at 48h, hook patterns are A/B tested, suppression signals detected early.
**FRs covered:** FR22, FR23, FR25, FR26, FR29

### Epic 5: Error Resilience & Self-Healing
The operator leaves the system running for weeks knowing every failure is caught, logged with recovery guidance, and isolated — no cascades, no silent failures.
**FRs covered:** FR30, FR31, FR32, FR33, FR34

### Epic 6: Monitoring Dashboard
The operator verifies the entire system is working and making money in under 10 seconds from a single URL.
**FRs covered:** FR35, FR36, FR37, FR38, FR39, FR40, FR41

### Epic 7: Multi-Account Portfolio Scale
The operator provisions a second account in 30 minutes, sees both accounts side-by-side with isolated pipelines, and never touches account #1 during the process.
**FRs covered:** FR42, FR43, FR44

---

## Epic 1: Foundation & First Autonomous Post

The operator can set up the system and see the first video posted to TikTok with an affiliate link — fully autonomously. Validates the end-to-end pipeline and TikTok API access as the first milestone.

### Story 1.1: Project Initialization & CI/CD Foundation

As the operator,
I want the project initialized with the correct structure, dependencies, and CI pipeline,
So that I can build and test the system reliably from day one with zero environment drift.

**Acceptance Criteria:**

**Given** a fresh Linux/macOS dev environment with `uv` installed
**When** I run `uv init tiktok-faceless` and follow the setup instructions
**Then** the project structure matches the architecture spec (`agents/`, `clients/`, `db/`, `dashboard/`, `tests/`, `utils/`, `models/`)
**And** `uv run pytest` passes with zero test failures on an empty test suite
**And** `uv run ruff check .` and `uv run mypy .` exit with no errors

**Given** the project is pushed to GitHub
**When** a commit is pushed to `main`
**Then** the GitHub Actions CI workflow runs `ruff` + `mypy` + `pytest` automatically
**And** the workflow fails fast if any check fails

**Given** the project root
**When** I inspect the repo
**Then** `.env` is gitignored and `.env.example` lists all required env vars with placeholder values
**And** `pyproject.toml` is the single source of truth for all dependencies and tool config

---

### Story 1.2: Core State & Database Models

As the system,
I want `PipelineState`, `AgentError`, `AccountConfig` Pydantic models and all core SQLAlchemy DB models defined and migrated,
So that every agent has a consistent, typed contract for state and persistence from the first line of agent code.

**Acceptance Criteria:**

**Given** the project is initialized (Story 1.1 complete)
**When** I inspect `tiktok_faceless/state.py`
**Then** `PipelineState` is a Pydantic v2 `BaseModel` with all fields from the architecture spec (`account_id`, `phase`, `candidate_niches`, `committed_niche`, `selected_product`, `product_validated`, `current_script`, `hook_archetype`, `voiceover_path`, `assembled_video_path`, `published_video_id`, `videos_produced_today`, `last_post_timestamp`, `fyp_reach_rate`, `suppression_alert`, `kill_video_ids`, `affiliate_commission_week`, `agent_health`, `errors`)
**And** `AgentError` is a Pydantic v2 `BaseModel` with `agent`, `error_type`, `message`, `video_id`, `recovery_suggestion`, `timestamp` fields
**And** `VideoLifecycle` enum covers `queued → rendering → rendered → scheduled → posted → analyzed → archived/promoted`

**Given** `tiktok_faceless/config.py` exists
**When** I instantiate `AccountConfig` with valid values
**Then** all fields validate correctly (`max_posts_per_day` 1–15, `posting_window_start` 0–23, etc.)
**And** loading from environment variables works via `python-dotenv`

**Given** `tiktok_faceless/db/models.py` exists
**When** I run `alembic upgrade head`
**Then** all 6 tables are created: `accounts`, `videos`, `video_metrics`, `products`, `agent_decisions`, `errors`
**And** all columns match the architecture spec (snake_case, correct FK relationships, `account_id` FK on all tables)
**And** `ix_video_metrics_video_id_recorded_at` index exists

**Given** SQLite dev config
**When** `get_session()` is called
**Then** a working DB session is returned and queries execute without error

---

### Story 1.3: External API Client Wrappers

As the system,
I want typed client wrapper classes for TikTok, ElevenLabs, Creatomate, and the LLM API with retry logic and rate limiting,
So that agents can call external services safely without writing raw HTTP and all failures surface as typed exceptions.

**Acceptance Criteria:**

**Given** valid API credentials in `.env`
**When** any client method is called
**Then** the call goes through the typed wrapper class — never a raw `requests` or `httpx` call from agent code
**And** all responses are parsed into Pydantic models before returning to the caller

**Given** an external API returns a rate limit error (429)
**When** the client wrapper catches the response
**Then** `tenacity` retries up to 3 times with exponential backoff (4s → 16s → 30s)
**And** after 3 failures a typed exception is raised (`TikTokRateLimitError`, `ElevenLabsError`, `RenderError`, etc.)

**Given** `TikTokAPIClient` is instantiated
**When** `post_video()` is called
**Then** the token bucket enforces max 6 requests/min per OAuth token
**And** `get_metrics()` returns a `TikTokVideoMetrics` Pydantic model

**Given** `ElevenLabsClient` is instantiated
**When** `generate_voiceover(text, voice_id)` is called
**Then** audio bytes are returned on success
**And** `ElevenLabsError` is raised (not swallowed) on API failure

**Given** `CreatomateClient` is instantiated
**When** `submit_render(template_id, data)` is called
**Then** a render job ID is returned
**And** `poll_status(job_id)` returns status until complete or raises `RenderError` on failure

**Given** `LLMClient` is instantiated
**When** `generate_script(prompt)` is called
**Then** the call uses `claude-haiku-4-5` model
**And** the response is returned as a string

---

### Story 1.4: Video Production Agent

As the operator,
I want the Production Agent to generate a publish-ready vertical video from a script,
So that the system can produce content without any manual editing or intervention.

**Acceptance Criteria:**

**Given** a `PipelineState` with `current_script` populated and a valid `account_id`
**When** `production_node(state)` is called
**Then** `ElevenLabsClient.generate_voiceover()` is called with the script text and the account's configured `elevenlabs_voice_id`
**And** the resulting audio file is saved and `state["voiceover_path"]` is set

**Given** voiceover audio is generated
**When** `CreatomateClient.submit_render()` is called
**Then** a vertical video (9:16 aspect ratio) is assembled with the voiceover, stock visuals, and auto-captions
**And** `state["assembled_video_path"]` is set to the downloaded video file path

**Given** the render job is submitted
**When** the Production Agent polls for completion
**Then** polling continues until the job is `completed` or raises `RenderError`
**And** the render job runs independently — it does not block other pipeline operations

**Given** ElevenLabs returns an API error
**When** `production_node` catches the exception
**Then** it returns `{"errors": [AgentError(agent="production", error_type="ElevenLabsError", ...)]}` state delta
**And** `voiceover_path` and `assembled_video_path` remain unset (pipeline does not proceed to publishing)

**Given** a completed video
**When** `utils/video.py` post-processes the file
**Then** metadata is stripped and captions are burned in

---

### Story 1.5: Basic Script & Affiliate Link Generation

As the operator,
I want the Script Agent to generate a basic video script and the Monetization Agent to attach a valid TikTok Shop affiliate link,
So that every video produced has monetization built in before it ever reaches the Production Agent — and no video is ever posted without one.

**Acceptance Criteria:**

**Given** a `PipelineState` with `selected_product` populated
**When** `script_node(state)` is called
**Then** `LLMClient.generate_script()` is called with the product details
**And** `state["current_script"]` is set to a non-empty script string
**And** `state["hook_archetype"]` is set to one of the valid hook types

**Given** a `PipelineState` with `selected_product` populated
**When** `monetization_node(state)` is called
**Then** `TikTokAPIClient` generates an affiliate link for the product
**And** the affiliate link is stored in the `videos` DB table row for this video
**And** `state["product_validated"]` confirms the link was successfully generated

**Given** affiliate link generation fails
**When** `monetization_node` catches the error
**Then** it returns an `AgentError` state delta
**And** the video lifecycle state remains `queued` — pipeline halts before production
**And** no video proceeds to the Production Agent without a confirmed affiliate link (NFR12)

**Given** a successfully generated script and affiliate link
**When** the video DB row is inspected
**Then** `affiliate_link` is populated and `lifecycle_state` is `queued`

---

### Story 1.6: Publishing Agent with Suppression-Resistant Cadence

As the operator,
I want the Publishing Agent to post videos to TikTok within configured posting windows with randomized timing,
So that the account posts consistently without triggering bot detection.

**Acceptance Criteria:**

**Given** a `PipelineState` with `assembled_video_path` set and affiliate link confirmed
**When** `publishing_node(state)` is called within a configured posting window
**Then** `TikTokAPIClient.post_video()` is called with the video file and the affiliate link embedded in the caption
**And** `state["published_video_id"]` is set to the TikTok video ID returned
**And** the `videos` DB row lifecycle state transitions to `posted`

**Given** a configured `posting_window_start` and `posting_window_end`
**When** the Publishing Agent evaluates its queue
**Then** posts only occur within the configured window
**And** a randomized offset (drawn from `utils/timing.py`) is applied to each post time

**Given** a configured `min_post_interval` between posts
**When** the Publishing Agent attempts to post
**Then** if `time.time() - state["last_post_timestamp"] < min_post_interval` the post is deferred
**And** `state["last_post_timestamp"]` is updated on every successful post

**Given** TikTok API returns an error on `post_video()`
**When** the Publishing Agent catches the exception
**Then** an `AgentError` is returned in the state delta
**And** the video lifecycle state remains `rendered` — no silent failure

**Given** the TikTok API is in sandbox mode
**When** a video is posted
**Then** the post succeeds as a private video visible to test users — full public posting enabled after audit approval

---

### Story 1.7: Orchestrator Pipeline Wiring & Crash Recovery

As the operator,
I want the Orchestrator to wire all agents into a sequential pipeline that resumes from last known state after a VM restart,
So that the system runs the full pipeline end-to-end and achieves the first autonomous post without any manual intervention.

**Acceptance Criteria:**

**Given** a valid `AccountConfig` loaded from environment
**When** `main.py` is executed
**Then** the LangGraph graph runs: `orchestrator_node → script_node → monetization_node → production_node → publishing_node`
**And** each agent node returns a state delta dict (never full state mutation)
**And** the graph checkpointer (SqliteSaver for dev) persists state after each node

**Given** the pipeline is running mid-execution and the process is killed
**When** `main.py` is restarted
**Then** the graph resumes from the last completed node (not from the beginning)
**And** no duplicate posts occur (`published_video_id` checked before re-running publishing_node)
**And** no duplicate affiliate link generation occurs

**Given** any single agent node raises an unhandled exception
**When** the orchestrator catches it
**Then** the error is written to the `errors` DB table with `agent`, `error_type`, `timestamp`, `recovery_suggestion`
**And** the pipeline halts gracefully — no crash propagation to other agents
**And** `state["agent_health"]` reflects the failed agent as `False`

**Given** a fresh account with no prior state
**When** the full pipeline completes successfully for the first time
**Then** a video exists in the `videos` table with `lifecycle_state = "posted"`
**And** `published_video_id` is set and non-null
**And** the affiliate link is confirmed in the video row

**Given** the system is deployed on the VPS
**When** the systemd unit is configured with `Restart=always` and `EnvironmentFile=`
**Then** the pipeline process restarts automatically on crash or reboot
**And** secrets are loaded from the systemd `EnvironmentFile=` — never hardcoded

---

## Epic 2: Intelligent Research & Content Strategy

Every video produced is demand-validated — the system mines buyer signals, researches products, and generates 3 hook variants with a consistent persona.

### Story 2.1: Product Validation via Buyer Intent Signals

As the operator,
I want the Research Agent to validate products using TikTok Shop sales velocity and affiliate signal strength before any script is generated,
So that production effort is never wasted on products without proven buyer demand.

**Acceptance Criteria:**

**Given** a niche and a list of candidate products from TikTok Shop
**When** `research_node(state)` is called
**Then** `TikTokAPIClient` polls sales velocity and affiliate signal data for each product
**And** only products meeting configurable minimum thresholds (sales velocity, commission rate) are marked as validated
**And** `state["selected_product"]` is set to the highest-scoring validated product
**And** `state["product_validated"]` is set to `True`

**Given** no products in the niche meet the validation thresholds
**When** `research_node` completes
**Then** `state["product_validated"]` remains `False`
**And** the pipeline does not proceed to script generation
**And** an `AgentError` with `recovery_suggestion` is added to state

**Given** a validated product
**When** the `products` DB table is inspected
**Then** the product is cached with `cached_at` timestamp, `niche`, `sales_velocity`, `affiliate_commission_rate`
**And** subsequent research calls within 24h use the cached entry (no redundant API call)

---

### Story 2.2: Comment Mining for Buyer Language

As the operator,
I want the Research Agent to mine comments from top-performing affiliate videos for the validated product,
So that scripts use authentic buyer language that converts — not generic AI copy.

**Acceptance Criteria:**

**Given** a validated product in `state["selected_product"]`
**When** `research_node` executes comment mining
**Then** `TikTokAPIClient` fetches comments from the top N affiliate videos for that product
**And** buyer-intent phrases are extracted (e.g. "where can I get this", price objections, social proof language)
**And** the extracted buyer language is stored in `state["selected_product"]["buyer_language"]`

**Given** buyer language is extracted
**When** `script_node` is called in Story 2.4
**Then** the script prompt includes the extracted buyer phrases
**And** the generated script contains at least one buyer-language phrase from the research output

**Given** the TikTok API returns no comments for a product
**When** comment mining completes
**Then** `buyer_language` is set to an empty list (not an error)
**And** script generation proceeds with product details only — no pipeline halt

---

### Story 2.3: Multi-Niche Product Scanning

As the operator,
I want the Research Agent to scan all niches in the configured niche pool in parallel during Tournament Phase,
So that the Tournament can evaluate multiple niches simultaneously without sequential bottlenecks.

**Acceptance Criteria:**

**Given** a `PipelineState` with `phase = "tournament"` and `candidate_niches` populated from `AccountConfig`
**When** `research_node` runs in Tournament mode
**Then** LangGraph `Send` API is used to fan out research across all `candidate_niches` in parallel
**And** each niche scan runs independently — one niche failure does not block others
**And** results for all niches are merged back into state as a list of validated products per niche

**Given** parallel niche scanning completes
**When** the results are inspected
**Then** each niche has a scored product list with `sales_velocity`, `affiliate_signal`, and `commission_rate`
**And** the top product per niche is stored in the `products` table scoped by `account_id`

**Given** the system is in Commit Phase (`phase = "commit"`)
**When** `research_node` runs
**Then** only the committed niche is scanned — no multi-niche fan-out
**And** `state["candidate_niches"]` is ignored; `state["committed_niche"]` is used

---

### Story 2.4: Full Script Generation with Hook Archetypes & Persona

As the operator,
I want the Script Agent to generate 3 distinct hook archetype variants per product using buyer language, with the account persona applied consistently,
So that the system produces high-conversion scripts that A/B test hook effectiveness and maintain a recognizable account voice.

**Acceptance Criteria:**

**Given** a `PipelineState` with `selected_product` including `buyer_language`
**When** `script_node(state)` is called
**Then** `LLMClient.generate_script()` is called 3 times — once per hook archetype (curiosity gap, social proof, controversy/demonstration)
**And** each script variant incorporates buyer-language phrases from `state["selected_product"]["buyer_language"]`
**And** all 3 variants include the account persona's name, catchphrases, and tone from `AccountConfig`

**Given** 3 script variants are generated
**When** `state` is inspected
**Then** `state["current_script"]` contains the selected variant (first variant for initial run)
**And** `state["hook_archetype"]` is set to the archetype of the selected variant
**And** all 3 variants are stored in the `videos` DB row for later A/B comparison

**Given** the LLM API returns an error
**When** `script_node` catches it
**Then** an `AgentError` is added to state with `recovery_suggestion`
**And** `state["current_script"]` remains unset — pipeline halts before production

---

### Story 2.5: Commission-Per-View Decay Detection

As the operator,
I want the Research Agent to continuously monitor commission-per-view for the committed niche and surface a decay alert when it drops,
So that niche saturation is detected automatically and a re-tournament is triggered before revenue plateaus.

**Acceptance Criteria:**

**Given** `phase = "commit"` and an active `committed_niche`
**When** `research_node` runs on its polling schedule
**Then** commission-per-view is calculated as `total_niche_commissions / total_niche_views` over the last 7 days
**And** the result is compared against the configurable `decay_threshold` in `AccountConfig`

**Given** commission-per-view drops below `decay_threshold` for 2 consecutive polling intervals
**When** the decay condition is confirmed
**Then** a dedicated `niche_decay_alert` field is set in state
**And** an `agent_decisions` DB row is written with `decision_type = "niche_decay_detected"` and supporting commission-per-view data

**Given** a decay alert is raised
**When** the Orchestrator reads it on next cycle (Epic 3)
**Then** a re-tournament is triggered — `state["phase"]` is reset to `"tournament"` by the Orchestrator only
**And** the committed niche's existing videos remain live for passive affiliate earning

---

### Story 2.6: Commission Tracking per Video, Product & Niche

As the operator,
I want the Monetization Agent to track affiliate commissions at video, product, and niche granularity,
So that the system knows exactly which content earns and can attribute revenue correctly for Tournament scoring and decay detection.

**Acceptance Criteria:**

**Given** a posted video with an affiliate link
**When** `monetization_node(state)` runs on its polling schedule
**Then** `TikTokAPIClient.get_affiliate_orders()` is called scoped by `account_id`
**And** commission data is stored in `video_metrics` as an append-only row with `affiliate_clicks`, `affiliate_orders`, and commission amount

**Given** commission data is stored
**When** queried by niche
**Then** `db/queries.py` can aggregate total commission per niche, per product, and per video for the `account_id`
**And** `state["affiliate_commission_week"]` is updated with the rolling 7-day total

**Given** TikTok Shop commission data has a reporting lag
**When** `monetization_node` reconciles data
**Then** reconciliation runs on the configurable schedule from `AccountConfig` — not assumed to be real-time (NFR19)
**And** discrepancies between click data and reported commissions are logged but do not halt the pipeline

---

## Epic 3: Tournament Engine & Phase Orchestration

The operator watches the system run the Tournament Phase, auto-commit to the winning niche, and shift into Commit Phase — with no intervention required.

### Story 3.1: Niche Scoring & Tournament Ranking

As the operator,
I want the system to score all competing niches by affiliate CTR and commission performance during Tournament Phase,
So that the Tournament winner selection is data-driven and auditable — not arbitrary.

**Acceptance Criteria:**

**Given** `phase = "tournament"` and videos posted across multiple niches
**When** `analytics_node` and `monetization_node` write metrics to `video_metrics`
**Then** `db/queries.py` can compute a niche score per `account_id` as a weighted combination of avg affiliate CTR, avg 3s retention, and total commissions earned
**And** niche scores are queryable in ranked order

**Given** niche scores are computed
**When** the Orchestrator evaluates Tournament state
**Then** the leading niche is identifiable as the one with the highest score and minimum configurable video count
**And** niches below the elimination threshold after day 7 are flagged as `eliminated` in the `products` table

**Given** a niche is eliminated
**When** the Orchestrator routes the next research cycle
**Then** eliminated niches are excluded from new product research
**And** existing posted videos in eliminated niches remain live for passive earning

---

### Story 3.2: Phase-Aware Agent Behavior

As the operator,
I want all agents to automatically adapt their volume targets and behavior based on the current phase,
So that the system posts aggressively during Tournament, focuses during Commit, and scales during Scale — without any manual reconfiguration.

**Acceptance Criteria:**

**Given** `phase = "tournament"` in `PipelineState`
**When** the Publishing Agent evaluates its daily posting target
**Then** `max_posts_per_day` is read from `AccountConfig.tournament_posts_per_day`
**And** research fans out across all `candidate_niches`

**Given** `phase = "commit"` in `PipelineState`
**When** the Publishing Agent evaluates its daily posting target
**Then** `max_posts_per_day` is read from `AccountConfig.commit_posts_per_day`
**And** 80%+ of new scripts target the committed niche only
**And** `candidate_niches` scanning stops; only `committed_niche` is researched

**Given** `phase = "scale"` in `PipelineState`
**When** the Publishing Agent evaluates its daily posting target
**Then** `max_posts_per_day` is read from `AccountConfig.scale_posts_per_day`

**Given** any phase value in state
**When** any agent node runs
**Then** `orchestrator.py` is the only file that writes `state["phase"]` — no other agent modifies phase directly

---

### Story 3.3: Automatic Tournament Winner Detection & Commit

As the operator,
I want the Orchestrator to automatically detect the Tournament winner at day 14 and transition to Commit Phase without requiring any input from me,
So that the system makes the niche commitment autonomously and I only find out after the fact via the dashboard.

**Acceptance Criteria:**

**Given** `phase = "tournament"` and `tournament_duration_days` elapsed (default 14)
**When** the Orchestrator evaluates Tournament completion
**Then** the niche with the highest score is selected as `committed_niche`
**And** `state["phase"]` is set to `"commit"` — only in `orchestrator.py`
**And** `state["committed_niche"]` is set to the winning niche name

**Given** a Tournament winner is selected
**When** the `agent_decisions` DB table is inspected
**Then** a row exists with `decision_type = "tournament_commit"`, `committed_niche`, winning score, runner-up scores, and `recorded_at`
**And** the audit row is written before the phase transition completes

**Given** Tournament day 14 arrives but no niche has met the minimum video count threshold
**When** the Orchestrator evaluates winner selection
**Then** the Tournament is extended by a configurable number of days (not aborted)
**And** an `agent_decisions` row is written explaining the extension

**Given** the phase transitions to Commit
**When** new research and script cycles run
**Then** production tapers off for non-committed niches — no new scripts generated for eliminated niches
**And** existing non-committed videos remain live

---

### Story 3.4: Phase Transition Audit Log & Operator Notification

As the operator,
I want every phase transition logged with full supporting data and surfaced as a notification after the fact,
So that I can review what the system decided and why without needing to approve decisions in advance.

**Acceptance Criteria:**

**Given** any phase transition occurs
**When** `orchestrator.py` writes the transition
**Then** an `agent_decisions` row is written with: `decision_type`, `from_phase`, `to_phase`, `committed_niche` (if applicable), `supporting_data` JSON with scores and metrics, `recorded_at`
**And** the audit row is written before `state["phase"]` is updated

**Given** a phase transition is logged
**When** the operator opens the dashboard (Epic 6)
**Then** the transition appears in the decision audit log with plain-English summary and supporting data
**And** a milestone notification is shown: "Phase changed: Tournament → Commit. Winning niche: [name]."

**Given** the Orchestrator fires a post-hoc notification
**When** `utils/alerts.py` sends the Telegram webhook
**Then** a Telegram message is sent with phase change, committed niche, and timestamp
**And** Telegram send failure does not halt the pipeline

---

### Story 3.5: Niche Decay Re-Tournament

As the operator,
I want the Orchestrator to automatically reset to Tournament Phase when commission-per-view decay is confirmed,
So that niche saturation never becomes a permanent revenue plateau — the system self-corrects.

**Acceptance Criteria:**

**Given** `phase = "commit"` and `niche_decay_alert` is set in state (from Story 2.5)
**When** the Orchestrator reads state on its next cycle
**Then** `state["phase"]` is reset to `"tournament"` — written only in `orchestrator.py`
**And** `state["candidate_niches"]` is repopulated from `AccountConfig.niche_pool` excluding the decayed niche for a configurable cooldown period
**And** `state["committed_niche"]` is cleared

**Given** re-tournament is triggered
**When** the `agent_decisions` table is inspected
**Then** a row exists with `decision_type = "niche_decay_retriggered_tournament"`, decayed niche name, commission-per-view values, and `recorded_at`

**Given** re-tournament begins
**When** the Research Agent runs
**Then** existing videos from the previously committed niche remain live and continue earning passively
**And** new production focuses on the re-tournament niche pool

---

## Epic 4: Analytics, Kill Switch & Optimization

The operator trusts the system is self-optimizing — underperforming videos are auto-archived at 48h, hook patterns are A/B tested, suppression signals detected early.

### Story 4.1: Per-Video Metrics Retrieval & Storage

As the operator,
I want the Analytics Agent to poll TikTok performance data for every posted video and store it as an append-only event log,
So that the system has accurate, historical performance data to drive kill switch, A/B testing, and suppression detection decisions.

**Acceptance Criteria:**

**Given** one or more videos with `lifecycle_state = "posted"` in the `videos` table
**When** `analytics_node(state)` runs on its polling schedule (every 6 hours)
**Then** `TikTokAPIClient.get_metrics()` is called for each posted video scoped by `account_id`
**And** each result is written as a new row to `video_metrics` with `recorded_at`, `views`, `like_count`, `average_time_watched`, `fyp_pct`, `affiliate_clicks`
**And** no existing `video_metrics` rows are updated — append-only only

**Given** TikTok analytics data has a 24–48h lag
**When** the Analytics Agent retrieves metrics for a video posted under 24h ago
**Then** partial or zero metrics are stored without error
**And** the agent does not treat zero metrics as a kill signal until 48h have elapsed

**Given** metrics are stored
**When** `db/queries.py` computes 3s retention
**Then** it is derived as `average_time_watched >= 3s / view_count` from the stored data
**And** 15s retention is derived equivalently

---

### Story 4.2: 48-Hour Kill Switch

As the operator,
I want the Analytics Agent to automatically archive underperforming videos at the 48-hour mark based on configurable thresholds,
So that low-quality content stops consuming posting quota without manual review.

**Acceptance Criteria:**

**Given** a video where `posted_at` is 48+ hours ago
**When** `analytics_node` evaluates the kill switch
**Then** if 3s retention < `AccountConfig.retention_kill_threshold` AND affiliate CTR < `AccountConfig.ctr_kill_threshold`
**Then** `TikTokAPIClient` archives the video
**And** the video `lifecycle_state` is updated to `archived` in the DB
**And** an `agent_decisions` row is written with `decision_type = "kill_switch"`, video_id, metrics at decision time, and `recorded_at`

**Given** a video meets the performance thresholds at 48h
**When** `analytics_node` evaluates it
**Then** `lifecycle_state` is updated to `promoted`
**And** an `agent_decisions` row is written with `decision_type = "promoted"` and supporting metrics

**Given** TikTok analytics data lag means metrics are incomplete at 48h
**When** the kill switch evaluates
**Then** a video is only archived if `view_count >= minimum_view_threshold` — no archiving on insufficient data
**And** the evaluation is deferred to the next polling cycle if data is insufficient

---

### Story 4.3: Shadowban & FYP Reach Monitoring

As the operator,
I want the Analytics Agent to detect FYP reach rate drops as early suppression signals,
So that publishing behavior can be adjusted before a full shadowban impacts account reach.

**Acceptance Criteria:**

**Given** metrics stored in `video_metrics` with `fyp_pct` values
**When** `utils/suppression.py` computes the rolling FYP reach rate
**Then** it is calculated as the average `fyp_pct` across the last N videos (configurable window)
**And** the result is written to `state["fyp_reach_rate"]`

**Given** `fyp_reach_rate` drops below `AccountConfig.suppression_threshold` for 2 consecutive polling intervals
**When** `analytics_node` detects the condition
**Then** `state["suppression_alert"]` is set to `True`
**And** an `agent_decisions` row is written with `decision_type = "suppression_detected"` and supporting FYP rate data

**Given** `state["suppression_alert"] = True`
**When** the Orchestrator reads state
**Then** it routes to a reduced-volume subgraph (Publishing Agent posts at minimum cadence)
**And** a Telegram alert is sent via `utils/alerts.py`
**And** `state["suppression_alert"]` is cleared when FYP reach rate recovers above threshold for 2 consecutive intervals

---

### Story 4.4: Hook Archetype A/B Performance Analysis

As the operator,
I want the Analytics Agent to compare hook archetype performance across video variants and surface winning patterns,
So that the Script Agent progressively favors archetypes that drive higher retention and affiliate CTR.

**Acceptance Criteria:**

**Given** videos posted with different `hook_archetype` values stored in the `videos` table
**When** `db/queries.py` aggregates `video_metrics` by `hook_archetype` for the `account_id`
**Then** avg 3s retention, avg 15s retention, and avg affiliate CTR are computable per archetype
**And** results are queryable ranked by a composite performance score

**Given** archetype performance data is available (minimum configurable sample size per archetype)
**When** `script_node` selects which hook archetype to use for the next video
**Then** the highest-performing archetype is weighted more heavily in selection (not always selected — maintains exploration)
**And** `state["hook_archetype"]` reflects the selected archetype

**Given** an archetype has fewer than the minimum sample size
**When** archetype selection runs
**Then** undersampled archetypes are selected more frequently to build statistical confidence
**And** no archetype is permanently excluded until it has sufficient sample data

---

### Story 4.5: Commission Reconciliation on Schedule

As the operator,
I want the Monetization Agent to reconcile TikTok Shop reported commissions against system-tracked click data on a configurable schedule,
So that revenue figures in the dashboard are accurate and attribution discrepancies are surfaced proactively.

**Acceptance Criteria:**

**Given** click data stored in `video_metrics` and commission data from `TikTokAPIClient.get_affiliate_orders()`
**When** `monetization_node` runs its reconciliation cycle (configurable schedule, default daily)
**Then** system-tracked clicks are compared against TikTok Shop reported commissions for the same period
**And** discrepancies beyond a configurable tolerance threshold are written to the `errors` table with `error_type = "commission_discrepancy"`

**Given** reconciliation completes
**When** the `video_metrics` table is queried
**Then** each video has an up-to-date commission amount reflecting the latest TikTok Shop data
**And** `state["affiliate_commission_week"]` is updated with the reconciled 7-day total

**Given** TikTok Shop API is unavailable during a reconciliation cycle
**When** `monetization_node` catches the error
**Then** the cycle is skipped and retried at the next scheduled interval
**And** the last successful reconciliation timestamp is stored — no stale data presented as current

---

## Epic 5: Error Resilience & Self-Healing

The operator leaves the system running for weeks knowing every failure is caught, logged with recovery guidance, and isolated — no cascades, no silent failures.

### Story 5.1: Agent Failure Isolation

As the operator,
I want any single agent failure to be fully contained so that other agents continue operating unaffected,
So that an ElevenLabs outage doesn't stop analytics from running, and a TikTok rate limit doesn't corrupt research state.

**Acceptance Criteria:**

**Given** `production_node` raises an unhandled exception during a render
**When** the LangGraph graph catches it at the node boundary
**Then** only the Production Agent's queue is paused
**And** `analytics_node`, `monetization_node`, and `publishing_node` (for already-rendered videos) continue their cycles
**And** `state["agent_health"]["production"] = False`
**And** no other agent's state is mutated by the production failure

**Given** a failed agent node returns `{"errors": [AgentError(...)]}`
**When** the Orchestrator processes the state delta
**Then** the error is written to the `errors` DB table scoped by `account_id`
**And** the pipeline routes around the failed agent on subsequent cycles until it is manually resumed

**Given** multiple agents fail simultaneously
**When** the Orchestrator evaluates `state["agent_health"]`
**Then** each failure is isolated and logged independently
**And** the system never enters a global crash state from individual agent failures

---

### Story 5.2: Structured Error Log with Recovery Guidance

As the operator,
I want every failure logged with structured context and a plain-English recovery suggestion,
So that when I check the dashboard I know exactly what failed, when, and what to do about it — without reading raw tracebacks.

**Acceptance Criteria:**

**Given** any agent raises a typed exception (`TikTokRateLimitError`, `ElevenLabsError`, `RenderError`, etc.)
**When** the agent node catches it at the boundary
**Then** an `AgentError` Pydantic model is constructed with: `agent`, `error_type`, `message`, `video_id` (if applicable), `recovery_suggestion`, `timestamp`
**And** the `AgentError` is written to the `errors` DB table via `db/queries.py`

**Given** an error is written to the `errors` table
**When** `recovery_suggestion` is inspected
**Then** it contains a plain-English action (e.g. "ElevenLabs rate limit exceeded — reduce concurrent voice generation or upgrade plan")
**And** recovery suggestions are defined per error type in the client wrapper — not generated at runtime

**Given** an error is resolved
**When** `errors` table is updated
**Then** `resolved_at` is set to the resume timestamp
**And** the error no longer appears as active in dashboard queries

---

### Story 5.3: Agent Queue Pause & Manual Resume

As the operator,
I want a failing agent's queue to pause automatically and resume with a single action after I've resolved the underlying issue,
So that the system never retries a broken operation indefinitely or requires manual pipeline reconstruction to recover.

**Acceptance Criteria:**

**Given** an agent has exceeded its retry limit (3 attempts with backoff)
**When** the final retry fails
**Then** the agent's queue state is set to `paused` in the `accounts` table for that `account_id`
**And** no further attempts are made by that agent until manually resumed
**And** other agents continue operating normally

**Given** an agent queue is paused
**When** the operator runs the resume command (`python -m tiktok_faceless.main --resume-agent production --account-id <id>`)
**Then** the agent queue state is set back to `active`
**And** the pipeline resumes from the last unprocessed item — no reprocessing of completed items
**And** the `errors` table entry for the triggering failure has `resolved_at` set

**Given** the operator resumes the pipeline
**When** the next pipeline cycle runs
**Then** `state["agent_health"]["<agent>"]` is reset to `True`
**And** a Telegram alert is sent: "Agent [name] resumed for account [id]"

---

### Story 5.4: Configurable Retry with Exponential Backoff

As the operator,
I want all external API calls to retry automatically with exponential backoff before escalating to a logged failure,
So that transient rate limits and network blips don't produce false error log entries or unnecessary pipeline pauses.

**Acceptance Criteria:**

**Given** any external API call decorated with `@retry` from `utils/retry.py`
**When** the call returns a retryable error (429, 503, network timeout)
**Then** `tenacity` retries up to 3 times with exponential backoff: 4s → 16s → 30s
**And** each retry attempt is logged at DEBUG level with attempt number and wait time

**Given** all 3 retry attempts are exhausted
**When** the final attempt fails
**Then** a typed exception is raised to the agent node boundary (not swallowed)
**And** backoff wait times are configurable per client via `AccountConfig` — not hardcoded

**Given** a non-retryable error (401 auth failure, 400 bad request)
**When** the client wrapper receives it
**Then** the error is raised immediately without retrying
**And** the typed exception includes the HTTP status code and response body for diagnosis

**Given** `utils/retry.py` defines shared retry decorators
**When** any new client method is added
**Then** it uses the shared decorator — no per-client retry logic duplication

---

## Epic 6: Monitoring Dashboard

The operator verifies the entire system is working and making money in under 10 seconds from a single URL.

### Story 6.1: Dashboard Foundation & Auth

As the operator,
I want a Streamlit dashboard running on the VPS behind a password gate with 60-second auto-refresh,
So that I can access live system data from any device without exposing it publicly.

**Acceptance Criteria:**

**Given** the Streamlit app is deployed on the Hetzner VPS
**When** I navigate to the dashboard URL
**Then** a password prompt is shown before any data is displayed
**And** the password is validated against `DASHBOARD_PASSWORD` env var via `dashboard/auth.py`
**And** on successful auth, `st.session_state["authenticated"] = True` persists for the session

**Given** the dashboard is authenticated
**When** the page loads
**Then** `streamlit-autorefresh` triggers a data reload every 60 seconds
**And** the refresh is silent — no visible loading flash during auto-refresh
**And** the last-updated timestamp in the top bar updates on each refresh

**Given** the dashboard connects to the database
**When** `db/session.py` `get_session()` is called from `dashboard/`
**Then** it connects to PostgreSQL (production) or SQLite (dev) based on env config
**And** all queries are read-only — no dashboard code writes to the database
**And** the dashboard loads current pipeline state within 5 seconds of page load (NFR3)

---

### Story 6.2: Status Top Bar & Alert Zone

As the operator,
I want a persistent top bar showing phase, pipeline status, and last post time plus an exception-first alert zone immediately below it,
So that the two most critical questions — "what phase?" and "is anything wrong?" — are answered before I see any metric data.

**Acceptance Criteria:**

**Given** the dashboard loads
**When** I view the top bar
**Then** it shows: Phase badge (Tournament/Commit/Scale with day counter) · Pipeline status dot + label · Last post time-ago · Videos posted today · Auto-refresh timestamp
**And** the top bar is the first rendered element — always visible without scrolling

**Given** no active alerts exist
**When** the alert zone renders
**Then** a single green "All systems healthy · Last checked Ns ago" row is shown

**Given** `state["suppression_alert"] = True` or any active `errors` table entry
**When** the alert zone renders
**Then** a rose/amber banner renders with: plain-English title, detail sentence, auto-action confirmation, and time-ago stamp
**And** the banner is visible above the fold without scrolling

**Given** the pipeline has not posted in over 24 hours
**When** the top bar renders
**Then** "Last post" shows in amber with the elapsed time
**And** a warning banner appears in the alert zone: "No posts in 24h — pipeline may be stalled"

---

### Story 6.3: KPI Strip with Sparklines

As the operator,
I want a 5-column KPI strip showing Revenue, 3s Retention, 15s Retention, Affiliate CTR, and FYP Reach — each with a 7-day sparkline and freshness timestamp,
So that I can answer "is it growing?" in a single eye pass without selecting date ranges or navigating anywhere.

**Acceptance Criteria:**

**Given** the dashboard is authenticated and data is loaded
**When** the KPI strip renders
**Then** 5 `st.metric` cards display in a `st.columns(5)` row: Revenue (7-day total), 3s Retention (avg %), 15s Retention (avg %), Affiliate CTR (avg %), FYP Reach Rate (avg %)
**And** each card shows: current value, delta vs prior 7-day period (↑/↓/→), and a 7-day sparkline

**Given** a KPI value is above its configured target threshold
**When** the card renders
**Then** the delta indicator is shown in emerald; if below threshold in amber; if critically below in rose

**Given** data for a KPI is older than 5 minutes
**When** the freshness timestamp renders
**Then** it shows in amber: "⚠ Updated Nm ago"
**And** if older than 15 minutes, it shows in rose

**Given** no video data exists yet (fresh account)
**When** the KPI strip renders
**Then** each card shows "—" with label "No data yet" — no error thrown

---

### Story 6.4: Agent Pipeline Panel & Video Performance Table

As the operator,
I want a 50/50 bottom panel showing per-agent status on the left and a top videos performance table on the right,
So that I can check pipeline health and content performance in a single scroll.

**Acceptance Criteria:**

**Given** the dashboard is loaded
**When** the bottom panels render
**Then** a `st.columns(2)` layout shows Agent Pipeline Panel left and Video Performance Table right

**Given** the Agent Pipeline Panel renders
**When** I view it
**Then** 6 agent rows display (Orchestrator, Research, Script, Production, Publishing, Analytics) with: status indicator, agent name, plain-English status note
**And** status colors match: running = indigo, done = emerald, waiting = zinc, error = rose
**And** `state["agent_health"]` from the most recent pipeline run drives the values

**Given** the Video Performance Table renders
**When** I view it
**Then** a `st.dataframe` shows top 20 videos by commission with columns: hook archetype, 3s retention %, affiliate CTR %, commission earned, lifecycle status
**And** rows are sortable by any column

**Given** `phase = "tournament"` is active
**When** the page renders below the bottom panels
**Then** a niche tournament table shows all candidate niches with: rank, video count, avg CTR, avg retention, total revenue, and Leading/Trailing/Eliminated status

---

### Story 6.5: Decision Audit Log & Error Log

As the operator,
I want dedicated views for the agent decision audit log and error log,
So that I can review every autonomous decision the system made and diagnose any failures without digging through raw database queries.

**Acceptance Criteria:**

**Given** the operator navigates to the Decisions section
**When** the decision audit log renders
**Then** all `agent_decisions` rows for the `account_id` display in reverse-chronological order
**And** each row shows: decision type (plain-English label), timestamp, summary, and an expandable detail section with `supporting_data` JSON
**And** phase transitions are highlighted with indigo color

**Given** the operator navigates to the Errors section
**When** the error log renders
**Then** all unresolved `errors` rows display with: agent name, error type, plain-English message, `recovery_suggestion`, timestamp
**And** resolved errors are in a collapsed "Resolved" expander — not cluttering the active view

**Given** there are no unresolved errors
**When** the error log section renders
**Then** a green "No active errors" message is shown

---

### Story 6.6: Milestone Notifications & Suppression Alerts

As the operator,
I want distinct visual callouts for first commission, phase transitions, and $1K/month milestone — and suppression alerts with auto-action confirmation,
So that meaningful moments are recognized and anomalies are unmissable without inducing panic.

**Acceptance Criteria:**

**Given** the first affiliate commission is recorded
**When** the dashboard loads for the first time after this event
**Then** a dismissible indigo banner renders: "First affiliate commission earned — $X.XX. The thesis is proven."
**And** the banner only shows once per session via `st.session_state`

**Given** a phase transition occurred since the last dashboard load
**When** the alert zone renders
**Then** an indigo banner shows: "Phase changed: [from] → [to]. [Niche if applicable]. [View decision data]"

**Given** `state["suppression_alert"] = True`
**When** the alert zone renders
**Then** a rose critical banner shows: "Suppression signal detected — FYP reach dropped [X]% in last [N]h. Publishing volume reduced automatically."
**And** "Publishing volume reduced automatically" confirms the system already responded — no action required

**Given** the $1,000/month commission threshold is crossed
**When** the dashboard loads
**Then** a milestone banner renders: "$1,000/month milestone reached. System is confirmed working."
**And** the banner persists until dismissed

---

## Epic 7: Multi-Account Portfolio Scale

The operator provisions a second account in 30 minutes, sees both accounts side-by-side with isolated pipelines, and never touches account #1 during the process.

### Story 7.1: Isolated Multi-Account Pipeline Execution

As the operator,
I want each TikTok account to run a fully isolated pipeline with its own state, credentials, and DB scope,
So that account #2 can be provisioned and run without any risk of interfering with account #1's revenue.

**Acceptance Criteria:**

**Given** two accounts exist in the `accounts` table with distinct `account_id` values
**When** both pipelines run concurrently on the same VM
**Then** every DB query in `db/queries.py` is scoped by `account_id` — no cross-account row access
**And** every API call passes the correct `account_id` credentials — no credential mixing
**And** `PipelineState` instances are fully isolated — `account_id` is the first field and is immutable after initialization

**Given** account #1's pipeline encounters an error
**When** the error is logged and the agent pauses
**Then** account #2's pipeline continues unaffected
**And** `state["agent_health"]` and `errors` table entries are scoped independently per `account_id`

**Given** both accounts are running
**When** the systemd unit is inspected
**Then** each account runs as a parameterized invocation of `main.py --account-id <id>`
**And** VM resource usage stays within the Hetzner CX22 2 vCPU / 4GB RAM spec for up to 10 accounts (NFR15)

---

### Story 7.2: Account Provisioning with Config Clone

As the operator,
I want to provision a new account by supplying credentials and having the system clone configuration from an existing account,
So that spinning up account #2 takes 30 minutes of credential setup — not a full reconfiguration from scratch.

**Acceptance Criteria:**

**Given** account #1 is fully configured and operational
**When** I run `python -m tiktok_faceless.provision --source-account-id acc1 --new-account-id acc2`
**Then** a new row is created in the `accounts` table for `acc2`
**And** `AccountConfig` fields are cloned from `acc1` (niche pool, posting windows, tournament duration, phase thresholds)
**And** credentials (`tiktok_access_token`, `elevenlabs_voice_id`) are NOT cloned — they must be supplied explicitly

**Given** the provisioning command is run with new credentials
**When** the new account row is created
**Then** credentials are stored as references to env vars scoped by `account_id` (e.g. `TIKTOK_ACCESS_TOKEN_ACC2`)
**And** no credential value is stored in the DB — only env var key references
**And** `AccountConfig` validation runs on the new account config before provisioning completes

**Given** the new account is provisioned
**When** `main.py --account-id acc2` is started
**Then** the pipeline initializes in Tournament Phase with the cloned niche pool
**And** account #1's pipeline is undisturbed

---

### Story 7.3: Multi-Account Dashboard View

As the operator,
I want both accounts visible in the dashboard with their own phase, pipeline health, and revenue summary,
So that I can monitor the full portfolio from a single URL without switching between views.

**Acceptance Criteria:**

**Given** two or more accounts exist in the `accounts` table
**When** the dashboard loads
**Then** an account selector in the sidebar lists all provisioned accounts by `account_id`
**And** selecting an account updates all dashboard views to show that account's data only

**Given** the overview page renders with multiple accounts
**When** I view the summary section
**Then** a summary row per account shows: account ID, phase badge, pipeline status dot, revenue today, last post time-ago
**And** the operator can scan all accounts' health in a single view before drilling into a specific one

**Given** account #2 is in Tournament Phase while account #1 is in Commit Phase
**When** both are shown in the summary
**Then** each account's phase badge reflects its independent phase state
**And** no data from account #1 bleeds into account #2's metrics or vice versa
