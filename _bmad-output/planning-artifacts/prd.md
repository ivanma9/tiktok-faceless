---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
completedAt: '2026-03-10'
status: 'complete'
inputDocuments: ['_bmad-output/planning-artifacts/product-brief-tiktok-faceless-2026-03-08.md']
workflowType: 'prd'
classification:
  projectType: 'agent_orchestration_system'
  domain: 'general'
  complexity: 'medium-high'
  projectContext: 'greenfield'
---

# Product Requirements Document — tiktok-faceless

**Author:** Ivanma
**Date:** 2026-03-10
**Project Type:** Autonomous agent orchestration system (Python backend + monitoring dashboard)
**Domain:** General | **Complexity:** Medium-High | **Context:** Greenfield

---

## Executive Summary

tiktok-faceless is a fully autonomous multi-agent system that operates a TikTok faceless creator account end-to-end — researching trending products, scripting and producing short-form video, publishing, analyzing performance, and managing affiliate revenue — with zero human intervention. Built by a solo Python developer for personal use, the system targets $1,000/month in TikTok Shop affiliate commissions from a single account as its initial milestone, with a roadmap to $30K/month across a portfolio of accounts.

The operator's sole touchpoint is a monitoring dashboard. The system runs in phase-aware modes (Tournament → Commit → Scale); the dashboard exposes current phase, active agents, phase transition reasoning, revenue, and error state — hands-off doesn't mean blind.

**Target user:** Ivanma — technically fluent solo operator (Python-comfortable) who wants an autonomous affiliate income engine, not a content creation workflow. Success: dashboard shows $1K+ commissions this month with no videos manually made and no schedule managed.

### What Makes This Special

Most creator tools reduce friction on individual tasks but leave humans in the loop. tiktok-faceless closes the full loop autonomously:

- **Demand-first production** — Research Agent validates buyer intent (TikTok Shop sales velocity, comment mining) before a single frame is rendered. Zero wasted production effort.
- **Dual optimization loop** — Retention (3s/15s rates) and affiliate CTR are tracked and A/B tested as independent first-class metrics. A viral video with zero affiliate clicks is a system failure signal.
- **Suppression resistance as architecture** — Human-variability patterns (randomized cadence, timing variance, length variation, hook archetype rotation) are structural from day one, not retrofitted when suppression hits.
- **Phase-aware orchestration with operator visibility** — Orchestrator adapts agent behavior and risk tolerance per phase; current phase and active agents are surfaced in the dashboard.
- **Niche decay detection** — Continuous commission-per-view monitoring prevents single-niche commitment from becoming a revenue plateau.

**Core insight:** TikTok affiliate income is bottlenecked by the labor cost of consistent, high-volume, optimized execution — not by ideas or tools. A system that closes that loop autonomously compounds like a financial instrument.

**Competitive gap:** No existing tool combines autonomous research validation, production, suppression-resistant publishing, and dual-metric optimization in a single orchestrated system. Existing tools (CapCut automation, AI script generators, social scheduling platforms) are point solutions requiring human orchestration between steps.

---

## Success Criteria

### User Success

- Zero daily intervention required — no manual content creation, product research, or posting in any given week
- Dashboard is the sole operator touchpoint — all agent states, phase transitions, errors, and revenue visible without inspecting logs
- System errors surfaced in dashboard with context sufficient for operator to diagnose and remediate — no silent failures
- Niche winner identified by day 14 from Tournament Phase data alone, no human judgment required

### Business Success

| Milestone | Target | Timeframe |
|---|---|---|
| First autonomous action | First affiliate click generated without human input | Day 1-3 |
| First revenue | $1 affiliate commission earned | Week 1-2 |
| Early traction | $10 total commission | Week 2 |
| Proof point | $100 total commission | Week 3-4 |
| Daily recurring | $20/day affiliate revenue (7-day average) | Month 2 |
| Scaling signal | $50/day affiliate revenue (7-day average) | Month 2-3 |
| MVP revenue | $1,000/month affiliate commissions | Month 3 |
| Reinvestment threshold | $100/day — triggers account #2 provisioning | Month 4-5 |
| Portfolio revenue | $10,000/month across multiple accounts | Month 9-12 |
| Meta-product trigger | $30,000/month — begin packaging playbook | Month 12-18 |

**Engagement growth benchmarks:**
- 1,000 views on a single video (first viral signal)
- 10,000 cumulative account views
- First video hitting >40% 3s retention
- 100 likes on a single video
- 1,000 cumulative likes

**Engagement Agent early unlock:** If revenue projections are on track for 2 consecutive weeks ahead of Month 2-3 schedule, Engagement Agent activation is pulled forward.

### Technical Success

- Agent pipeline runs end-to-end for 7 consecutive days without manual intervention
- All agent failures caught, logged, and surfaced in dashboard — no silent failures
- Defined fallback and recovery paths for each failure mode (API outage, rate limit, render failure, TikTok posting error)
- FYP reach rate maintained — no sustained shadowban signal
- Pipeline uptime ≥95% (scheduled posts completed / scheduled posts attempted per week)

### Measurable Outcomes

- 48-hour kill rate: ≥80% of underperforming videos correctly auto-archived
- Niche decay detection lag: re-tournament triggered within 7 days of commission-per-view drop signal
- Video production throughput: 3-10 videos/day depending on phase
- Per-video KPIs: 3s retention >40%, 15s retention >25%, affiliate CTR >2%

---

## Product Scope

### MVP — Phase 1 (Revenue MVP)

**Philosophy:** Speed to first autonomous affiliate commission over feature completeness. Pipeline correctness first → revenue signal → dashboard UI later.

**Build sequence:** Validate TikTok API access first → build agents in sequence (Research → Script → Production → Publishing) → wire Orchestration → add Analytics + Monetization → add dashboard post-commit.

| Capability | Status | Notes |
|---|---|---|
| Orchestration Agent + sub-agent wiring | ✅ MVP | Core system |
| Research Agent (product validation) | ✅ MVP | Demand-first |
| Script Agent (hook variants) | ✅ MVP | 3 variants per product |
| Production Agent (video render) | ✅ MVP | ElevenLabs + video gen |
| Publishing Agent (suppression-resistant) | ✅ MVP | Randomized cadence |
| Analytics Agent (retention + CTR + kill switch) | ✅ MVP | 48hr kill switch |
| Monetization Agent (affiliate links) | ✅ MVP | TikTok Shop |
| Niche Tournament Engine | ✅ MVP | Auto-commit day 14 |
| State database (SQLite) | ✅ MVP | Pipeline resumable on restart |
| Error logging | ✅ MVP | Replaces dashboard for MVP launch |
| ElevenLabs voice (stock) | ✅ MVP | Custom persona added at Commit Phase |
| Monitoring dashboard (web UI) | ⏳ Phase 1b | Logs sufficient for initial launch |
| Custom AI persona voice clone | ⏳ Phase 1b | Added at Commit Phase |

### Phase 1b — Post-First Niche Win

- Custom ElevenLabs voice clone for account persona
- Basic monitoring dashboard: revenue, pipeline status, agent health, error log, current phase + active agents

### Phase 2 — Growth (Month 2-3)

- Full dashboard: audit log, milestone notifications, per-video metrics, suppression alerts
- Engagement Agent (in-persona comment replies)
- Cross-platform trend radar (Reddit + Google Trends)
- TikTok SEO evergreen content strategy

### Phase 3 — Scale (Month 4+)

- Multi-account dashboard + provisioning workflow
- Omni-platform syndication (YouTube Shorts, Instagram Reels, Pinterest)
- Email list + lead magnet pipeline
- Portfolio-level analytics and ROI allocation

### Vision (Month 12+)

- 50+ account parameterized portfolio with quant-style ROI allocation
- Meta-product: agent documents its own method — packaged as $97-$497 "TikTok Affiliate Automation Playbook"
- Operator role reduced to provisioning new accounts and reviewing weekly portfolio performance

---

## User Journeys

### Journey 1: Initial Setup & Launch

**Persona:** Ivanma — solo Python developer, operator mindset. TikTok account and TikTok Shop affiliate account created manually prior to system launch.

**Opening Scene:** Day 0. Configuration script runs, APIs connected (ElevenLabs, TikTok, video generation, TikTok Shop affiliate), Orchestration Agent initialized — niche pool (8 categories), posting cadence, Tournament duration (14 days). Dashboard loads. All agents green. Phase: Tournament.

**Rising Action:** Research Agent validates products across 8 categories — sales velocity confirmed, affiliate links generated. Script Agent produces 3 hook variants per product. Production Agent renders vertical video with stock ElevenLabs voice and auto-captions. Publishing Agent queues posts with randomized timing.

**Climax:** 6 hours after setup, first video posts autonomously. Dashboard confirms: post live, affiliate link embedded, retention tracking active.

**Resolution:** Ivanma closes his laptop. System is running.

**Requirements revealed:** API configuration workflow, agent health indicators, phase + active agent display, first autonomous action confirmation.

---

### Journey 2: Tournament Commit & Steady State

**Persona:** Ivanma, day 13. No intervention since setup.

**Opening Scene:** Dashboard notification fires automatically: "Niche committed — Home Gym Equipment. Affiliate CTR 3.2x next closest category. Production tapering off 7 other niches. [View decision data]" System has already acted.

**Rising Action:** Day 14. New scripts are 80% home gym products. Losing niche videos remain live for passive affiliate earning. Dashboard shows: Phase: Commit, commit decision log with supporting data, week 3 commission $47.

**Climax:** Ivanma reviews the automated decision after the fact. He didn't approve it. He didn't need to. The system made the right call and told him about it.

**Resolution:** Steady state. Weekly dashboard check. Revenue trending up.

**Requirements revealed:** Automatic phase transition with post-hoc dashboard notification + audit log, production taper logic, passive video tracking across all niches post-commit, per-niche revenue breakdown.

---

### Journey 3: Error Recovery

**Persona:** Ivanma, day 9. Dashboard red indicator.

**Opening Scene:** Error log: "ElevenLabs API — rate limit exceeded. Voice generation failed for 3 videos. Production pipeline paused. Publishing queue empty."

**Rising Action:** Error entry shows: timestamp, affected videos, last successful render, suggested recovery — "Reduce concurrent voice generation requests or upgrade ElevenLabs plan." System paused rather than posting broken videos.

**Climax:** Ivanma upgrades ElevenLabs plan (2 minutes). Clicks "Resume pipeline." Production picks up from failed queue. Publishing resumes with adjusted cadence.

**Resolution:** 20 minutes total. No manual video production. Failure logged — future rate limit thresholds auto-adjusted.

**Requirements revealed:** Structured error log with recovery guidance, pipeline pause-on-failure, manual resume control, automatic retry logic, agent failure isolation (no cascade).

---

### Journey 4: Scale Provisioning — Account #2

**Persona:** Ivanma, month 4. Account #1 at $110/day. TikTok account #2 and affiliate account created manually.

**Opening Scene:** Dashboard milestone notification: "$100/day threshold reached for 3 consecutive days. Account #2 provisioning available."

**Rising Action:** Scale Provisioning panel — enters account #2 credentials. System clones account #1 config by `account_id`. New ElevenLabs voice cloned for account #2 persona. Tournament Phase begins independently on account #2.

**Climax:** Both accounts appear side-by-side in dashboard — each with own phase, active agents, revenue, and metrics. Account #1 undisturbed.

**Resolution:** 30 minutes provisioning. Two autonomous income streams. One dashboard view.

**Requirements revealed:** Multi-account dashboard view, per-account config by `account_id`, provisioning workflow, config clone from existing account, isolated agent pipelines per account.

---

### Journey Requirements Summary

| Capability Area | Revealed By |
|---|---|
| API configuration & first-run setup | Journey 1 |
| Agent health + phase/active agent display | Journeys 1, 2 |
| Automatic phase transition with post-hoc notification + audit log | Journey 2 |
| Production taper logic (Tournament → Commit) | Journey 2 |
| Passive video tracking + per-niche revenue breakdown | Journey 2 |
| Structured error log with recovery guidance | Journey 3 |
| Pipeline pause-on-failure + manual resume | Journey 3 |
| Agent failure isolation (no cascade) | Journey 3 |
| Multi-account dashboard + provisioning by `account_id` | Journey 4 |
| Isolated agent pipelines per account | Journey 4 |

---

## Domain-Specific Requirements

### External Platform Constraints

- **TikTok posting limits** — TikTok enforces undisclosed rate limits; Publishing Agent must operate within safe thresholds and detect suppression signals before they escalate
- **Content policy** — All generated content must comply with TikTok Community Guidelines; AI-generated content is permitted but must avoid misleading claims and prohibited product categories
- **TikTok Shop affiliate ToS** — Affiliate links must be disclosed per policy; automated account creation is prohibited (operator provisions manually); commission attribution is a TikTok-controlled dependency
- **Bot detection risk** — High-volume uniform posting triggers suppression; Publishing Agent introduces human-variability patterns as a structural requirement

### Third-Party API Dependencies

| API | Dependency Level | Failure Impact |
|---|---|---|
| TikTok API | Critical | Posting and analytics blocked |
| ElevenLabs | Critical path | Production pipeline paused |
| Video generation API | Critical path | Render queue paused |
| TikTok Shop affiliate API | Revenue critical | Commission tracking degraded |

All external API failures are caught, logged, and surfaced in the dashboard. The system never silently skips a post or substitutes degraded output — all failures are accounted for in the pipeline audit log.

---

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. Full-Loop Autonomous Content Commerce**
No existing tool operates the complete TikTok affiliate loop autonomously — research → script → produce → publish → analyze → optimize → monetize. Existing solutions require human orchestration between steps.

**2. Demand-First Production Inversion**
Standard workflows: idea → produce → hope it converts. tiktok-faceless: validate buyer intent → produce. Research Agent confirms sales velocity and affiliate signal before a single frame renders.

**3. Dual Independent Optimization Loop**
Retention and affiliate CTR are tracked and A/B tested as independent first-class metrics. A viral video with zero affiliate clicks is a system failure signal — this framing is novel in the space.

**4. Suppression Resistance as Architecture**
Human-variability patterns are structural design constraints — not post-hoc mitigations retrofitted after suppression hits.

**5. Phase-Aware Orchestration**
Portfolio-management approach to content: niche testing as a tournament, doubling down on winners, re-testing on decay. Distinct agent behaviors and risk tolerances per phase.

### Validation Approach

- **Loop validation:** Full pipeline runs 7 consecutive days without intervention
- **Revenue validation:** First affiliate commission within week 2
- **Suppression validation:** FYP reach rate maintained through Tournament Phase (high-volume period)
- **Optimization validation:** A/B test results show measurable hook archetype performance differentiation

### Risk Mitigation

| Risk | Mitigation |
|---|---|
| TikTok API access (unvalidated — highest risk) | Validate posting capability as very first build step; evaluate browser automation fallback if restricted |
| TikTok algorithm changes | Suppression-resistance patterns are parameterized — adjustable without rebuild |
| AI content detection | Hook archetype rotation + persona consistency reduce fingerprinting; monitored via FYP rate |
| Single-platform dependency | Omni-platform syndication deferred to Phase 3 as mitigation |
| Niche saturation | Niche decay detection + re-tournament provide systematic response |
| ElevenLabs rate limits | Stock voice for MVP (low volume pressure); custom clone added at Commit Phase |

---

## Technical Architecture

### Agent Communication Pattern

- **Direct calls** — synchronous sequential steps (Orchestrator → Research → Script)
- **Message queue** — async handoffs for independent processing (Production render queue, Publishing post queue)
- Each agent is independently operable for testing or manual recovery

### Scheduling & Triggers

- **Event-based primary** — each pipeline step triggers on prior step completion
- **Time-aware publishing** — Publishing Agent holds rendered videos and dispatches at optimal posting windows with configurable minimum intervals between posts
- **Periodic polling** — Analytics Agent polls TikTok performance data on a schedule (e.g., every 6 hours) to evaluate 48-hour kill-switch decisions

### State Management

Persistent database (SQLite for MVP, migratable to Postgres) storing:
- Video lifecycle state: `queued → rendering → rendered → scheduled → posted → analyzed → archived/promoted`
- Phase state: current phase, phase history, commit decision log with supporting data
- Agent decision log: kill-switch decisions, niche scores, phase transitions
- Account configuration per `account_id`
- Error log: failure type, timestamp, affected video/agent, recovery action taken

State survives VM restarts — pipeline resumes from last known position on startup.

### Integration Architecture

Each agent calls its external APIs directly:

| Agent | External API |
|---|---|
| Research Agent | TikTok Shop API, affiliate data sources |
| Script Agent | LLM API |
| Production Agent | ElevenLabs API, video generation API |
| Publishing Agent | TikTok API |
| Analytics Agent | TikTok API (performance data) |
| Monetization Agent | TikTok Shop affiliate API |

All credentials stored as environment variables, injected per agent at runtime. No shared integration layer for MVP.

### Deployment

- Cloud VM (always-on), Linux, Python runtime
- Orchestrator as persistent process (systemd or process manager)
- Dashboard served as web app on same VM (Python-based: FastAPI + lightweight frontend or Streamlit)
- Dashboard is read-only — no content editing or agent configuration via UI; configuration is code/env
- Single-account MVP; all agent logic parameterized by `account_id` from day one

---

## Functional Requirements

### Orchestration & Pipeline Control

- **FR1:** The Orchestration Agent can coordinate the full pipeline sequence (Research → Script → Production → Publishing → Analytics → Monetization) autonomously per account
- **FR2:** The Orchestration Agent can operate in three distinct phase modes (Tournament, Commit, Scale) with different agent behaviors and volume targets per phase
- **FR3:** The Orchestration Agent can automatically detect a Tournament Phase winner and transition to Commit Phase without operator input
- **FR4:** The Orchestration Agent can detect niche commission decay and trigger a re-tournament automatically
- **FR5:** The Orchestration Agent can notify the operator of phase transitions and major autonomous decisions via the dashboard after execution
- **FR6:** The system can resume pipeline execution from last known state after a VM restart or crash

### Content Research & Validation

- **FR7:** The Research Agent can identify and validate products based on buyer intent signals (TikTok Shop sales velocity, affiliate signal strength)
- **FR8:** The Research Agent can mine top-performing affiliate video comments for buyer language to feed into script templates
- **FR9:** The Research Agent can scan multiple product niches simultaneously during Tournament Phase
- **FR10:** The Research Agent can continuously monitor commission-per-view signals for the committed niche and surface decay alerts

### Script Generation

- **FR11:** The Script Agent can generate video scripts for validated products using buyer language from research
- **FR12:** The Script Agent can produce 3 distinct hook archetype variants per product (e.g., curiosity gap, social proof, controversy, demonstration)
- **FR13:** The Script Agent can apply a consistent AI persona (name, personality, catchphrases) across all scripts for an account

### Video Production

- **FR14:** The Production Agent can generate a publish-ready vertical video (voiceover + visuals + auto-captions) from a script without manual editing
- **FR15:** The Production Agent can synthesize voiceover audio using a configured ElevenLabs voice (stock or custom clone)
- **FR16:** The Production Agent can queue render jobs and process them independently of other pipeline stages

### Publishing

- **FR17:** The Publishing Agent can post videos to TikTok with embedded affiliate links
- **FR18:** The Publishing Agent can schedule posts within configurable optimal posting windows
- **FR19:** The Publishing Agent can enforce configurable minimum time intervals between posts
- **FR20:** The Publishing Agent can introduce randomized variability in posting cadence, timing, and video length to reduce bot-detection risk
- **FR21:** The Publishing Agent can adjust posting volume based on current phase

### Analytics & Optimization

- **FR22:** The Analytics Agent can retrieve and store per-video performance data (3s retention, 15s retention, views, likes, affiliate CTR, commissions)
- **FR23:** The Analytics Agent can evaluate videos at the 48-hour mark and trigger archive or promote decisions based on configurable retention and CTR thresholds
- **FR24:** The Analytics Agent can track performance per niche category during Tournament Phase to determine the winner
- **FR25:** The Analytics Agent can detect FYP reach rate drops as a shadowban signal and surface alerts
- **FR26:** The Analytics Agent can compare hook archetype performance across A/B variants and surface winning patterns

### Monetization

- **FR27:** The Monetization Agent can generate and manage TikTok Shop affiliate links per product
- **FR28:** The Monetization Agent can track affiliate commissions per video, per product, and per niche
- **FR29:** The Monetization Agent can reconcile system-tracked click data with TikTok Shop reported commissions on a configurable schedule

### Error Handling & Recovery

- **FR30:** The system can detect and log failures for each agent independently without cascading failures to other agents
- **FR31:** The system can pause a failing agent's queue while other agents continue operating
- **FR32:** The system can surface structured error logs including failure type, timestamp, affected video/agent, and suggested recovery action
- **FR33:** The operator can manually resume a paused agent pipeline after resolving an error
- **FR34:** The system can automatically retry failed operations with configurable retry logic and backoff

### Operator Dashboard & Monitoring

- **FR35:** The operator can view current system phase and active agents in the dashboard
- **FR36:** The operator can view revenue summary by account, niche, and video in the dashboard
- **FR37:** The operator can view per-video performance metrics (retention, CTR, commission, status) in the dashboard
- **FR38:** The operator can view the error log with recovery guidance in the dashboard
- **FR39:** The operator can view the agent decision audit log (phase transitions, niche commits, kill-switch decisions with supporting data) in the dashboard
- **FR40:** The operator can view milestone achievement notifications in the dashboard
- **FR41:** The operator can view suppression signal alerts (FYP rate drop, shadowban indicators) in the dashboard

### Account & Configuration Management

- **FR42:** The system can operate multiple accounts in isolation, each parameterized by a unique `account_id`
- **FR43:** The operator can provision a new account by supplying credentials, with the system cloning configuration from an existing account
- **FR44:** The operator can configure per-account parameters (niche pool, posting windows, Tournament duration, phase thresholds) via configuration files

---

## Non-Functional Requirements

### Performance

- **NFR1:** Full pipeline cycle (research → script → production → scheduling) for a single video completes in under 10 minutes
- **NFR2:** Analytics Agent retrieves and processes per-video performance data within 15 minutes of a polling interval completing
- **NFR3:** Dashboard loads current pipeline state and revenue summary within 5 seconds
- **NFR4:** Publishing Agent post queue evaluated and dispatched within 60 seconds of a scheduled posting window opening

### Security

- **NFR5:** All API credentials stored as environment variables or in a secrets manager — never hardcoded or committed to source control
- **NFR6:** All external API communications use HTTPS/TLS
- **NFR7:** Dashboard access restricted to operator — no unauthenticated public endpoints
- **NFR8:** Per-account credentials and configuration isolated by `account_id` — no cross-account credential access

### Reliability

- **NFR9:** Pipeline uptime ≥95% measured as: scheduled posts completed / scheduled posts attempted per week
- **NFR10:** System recovers to consistent state after VM restart without data loss or duplicate posts
- **NFR11:** Agent failures isolated — single agent failure does not crash or corrupt other agents' state
- **NFR12:** No video posted without confirmed affiliate link — system blocks publishing if affiliate link generation failed

### Scalability

- **NFR13:** All agent logic parameterized by `account_id` — adding a new account requires configuration provisioning only, no code changes
- **NFR14:** State database schema supports arbitrary number of accounts, videos, and niches without structural changes
- **NFR15:** System can operate up to 10 accounts concurrently on a single VM; beyond 10 requires infrastructure review

### Integration

- **NFR16:** TikTok API rate limit responses handled gracefully — retries queued with exponential backoff, not permanent failure
- **NFR17:** ElevenLabs API failures cause render queue pause and structured error surface — not silent audio substitution or voiceover skip
- **NFR18:** Video generation API failures are job-level isolated — one failed render does not block other queued renders
- **NFR19:** TikTok Shop commission data reconciled on a configurable schedule — system does not assume real-time commission accuracy
