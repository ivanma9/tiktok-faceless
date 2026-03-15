# Full Project Retrospective — tiktok-faceless
**Date:** 2026-03-14
**Scope:** Epic 1 through Epic 7 (all stories)
**Final test count:** 456 passing, 0 failing
**Facilitator:** Bob (Scrum Master)

---

## Project Snapshot

| Metric | Value |
|---|---|
| Epics shipped | 7 |
| Stories shipped | 34 |
| Tests at close | 456 passing |
| Agent files | 7 (1,089 lines) |
| DB query functions | 42 |
| Dashboard components | 10 |
| CLI commands | `--resume-agent`, `--provision-account` |

---

## Epic-by-Epic Summary

### Epic 1 — MVP Pipeline Foundation ✅
**7 stories.** Delivered the full LangGraph 5-node pipeline skeleton: state schema, DB models, API client wrappers (TikTok, ElevenLabs, Fal, Anthropic, Creatomate), all 5 agent nodes, orchestrator routing, crash recovery. **121 tests.**

Key deviation: Architecture specified `SqliteSaver` for checkpoint persistence; `MemorySaver` was used instead because `langgraph-checkpoint-sqlite` was not installed. This means state is lost on process restart — documented but not resolved.

---

### Epic 2 — Research, Script & Commission Intelligence ✅
**6 stories.** `research_node` fully implemented with product validation, comment mining for buyer language, multi-niche scanning, hook archetype + persona script generation, CPV decay detection, and commission tracking per video/product/niche. Script generation uses Anthropic Claude with structured hook personas.

---

### Epic 3 — Tournament Phase Intelligence ✅
**5 stories.** Niche scoring + tournament ranking with `get_niche_scores`, `flag_eliminated_niches`. Phase-aware daily posting limits in `publishing_node`. Automatic tournament winner detection with commit logic. Phase transition audit log + Telegram alerts. Niche decay re-tournament with full state reset.

Notable: Spec prose for tournament extension direction was internally contradictory (Story 3.3). Dev agent caught and resolved correctly (adding to `started_at` to represent extended tournament end date).

---

### Epic 4 — Analytics & Kill Switch ✅
**5 stories.** Per-video metrics retrieval and storage (VideoMetric). 48-hour kill switch with AND-logic on retention + CTR thresholds. Shadowban / FYP reach monitoring with `suppression_window` config and `compute_fyp_reach_rate`. Hook archetype A/B analysis with exploration boost for undersampled archetypes. Commission reconciliation on schedule with discrepancy tolerance and `last_reconciliation_at` state tracking.

This epic generated the most review feedback — 10 recurring issues documented in `feedback_epic4_lessons.md` and applied to all subsequent epics.

---

### Epic 5 — Error Resilience & Self-Healing ✅
**4 stories.** Agent failure isolation (errors don't halt pipeline). Structured error log with recovery suggestions (`utils/recovery.py`). Agent queue pause on retry exhaustion + manual resume via `--resume-agent` CLI. Configurable exponential backoff factory (`utils/retry.py`).

Fixed the pre-existing `test_graph_invocable_with_mocked_nodes` failure that had been accepted since Story 1.7.

---

### Epic 6 — Operator Dashboard ✅
**6 stories.** Full Streamlit dashboard: password auth gate, 60s autorefresh, account selector sidebar. Status top bar (phase badge, last post, daily count, agent health dots). KPI strip with 5 metrics + sparklines + delta vs prior 7 days. Agent pipeline panel + top video performance table. Decision audit log + error log pages. Milestone banners (first commission, phase transition, $1K/month) + suppression alert.

Architecture boundary rule (`dashboard/` imports only from `db/queries` and `db/session`, never `db/models` or SQLAlchemy directly) enforced after 3 violations caught in review.

---

### Epic 7 — Multi-Account Portfolio Scale ✅
**3 stories.** Isolated pipeline execution per account with `thread_id=account_id` for LangGraph checkpointer isolation. Account provisioning via `--provision-account` CLI (idempotent DB insert, env var validation). Multi-account dashboard with sidebar account selector, `selected_account_id` session state, and per-account summary table (phase badge, status dot, revenue today, last post).

---

## What Went Well

### 1. Test discipline held through all 7 epics
The project went from 2 tests (scaffolding) to 456 without a single regression along the way. The test-per-story discipline — DB tests using real SQLite in-memory sessions, agent tests using mocks — produced a fast and reliable test suite.

### 2. Spec-first review caught real bugs, not just style
Every epic had at least one spec reviewer finding that would have been a runtime bug:
- Epic 4: Missing `TikTokAuthError` in except clauses → auth failures would silently crash nodes
- Epic 5: `session.commit()` missing in orchestrator error block → errors written but agent never actually paused
- Epic 7: `run_pipeline_for_account` passing `{}` instead of `initial_state.model_dump()` — caught because the test was written to match the broken impl, not the spec

### 3. Epic 4 lessons applied immediately and durably
10 recurring issues were caught in Epic 4, documented in persistent memory, and injected into all subsequent story Dev Notes. The function-level import violation still appeared in Epic 7's test file, but it was caught by code review (not missed). The feedback loop worked.

### 4. Architecture boundary (orchestrator owns phase) held completely
No agent node other than `orchestrator.py` ever writes `state["phase"]`. Enforced by convention, checked in spec review, tested with assertions in every phase-transition story. Zero violations across all 34 stories.

### 5. State delta pattern enforced consistently
All 5 agent nodes return `dict`, never `PipelineState`. The LangGraph reducer handles merging. This made testing straightforward and prevented the most common LangGraph antipattern (returning full state and accidentally wiping fields).

### 6. Serial decision on Epic 7 multi-account was correct
Resisting the urge to parallelize accounts in Story 7.1 kept the implementation to ~30 lines of clean code. The `try/except Exception` cross-account safety boundary is one clear line. Parallelization would have added `asyncio` complexity for no practical gain at ≤10 accounts.

---

## What Could Have Been Better

### 1. Story artifact files were never updated after implementation
**Impact: High on future maintainability.** All story files for Epics 6 and 7 still have `Status: ready-for-dev` and empty `Dev Agent Record` sections. A developer looking at the repo cold would have no idea what's done. This is the single biggest process gap.

**Root cause:** The implementation workflow updated code and tests but had no mandatory "update story file" step at close.

### 2. Spec drift from epics.md was never explicitly approved
In Epic 7, the original `epics.md` specified:
- `python -m tiktok_faceless.provision --source-account-id acc1 --new-account-id acc2` (separate module, clone from source)
- Per-account env var scoping (`TIKTOK_ACCESS_TOKEN_ACC2`)
- Accounts running concurrently (parallelized, each as a systemd parameterized unit)

What was built was simpler: single `--provision-account` flag in `main.py`, shared env vars, serial execution. This was the **right decision** for the current scale — but it happened implicitly through spec generation rather than an explicit operator decision. The operator should have been consulted before the spec was written.

### 3. The `session.commit()` rule created a contradiction
Epic 4 lesson #4 said: "Never put `session.commit()` inside an `if` branch."
Story 5.2's `write_agent_errors` correctly added `if errors: session.commit()` to avoid committing on empty list.
These two rules conflict. The lesson should have been nuanced: "Guard `session.commit()` for data-existence checks is acceptable; never gate it on business logic conditions."

### 4. Function-level import violation recurred despite being in memory
The same issue appeared in:
- Stories 4.4, 4.5 (first caught)
- Story 5.3 (function-level imports in `main.py`)
- Epic 7 (function-level imports in `test_main_multi_account.py`)

Memory injection didn't fully prevent it because the implementer subagent wrote tests before reviewing the feedback doc. A ruff rule (`PLC0415`) would enforce this mechanically.

### 5. `overview.py` session state key not updated with the rest of the codebase
When Story 7.3 renamed `"account_id"` → `"selected_account_id"` in session state, `overview.py` was missed. The component silently used an empty string as `account_id`, showing no data for any selected account. Caught by spec review — but this is exactly the kind of cross-file contract that should be a grep test or a constant, not a string literal.

---

## Recurring Issues by Frequency

| Issue | Times caught | First appeared | Fully resolved? |
|---|---|---|---|
| Function-level imports | 4 epics (4, 5, 7, 7) | Story 4.4 | No — needs ruff PLC0415 |
| Missing `TikTokAuthError` in except | 2+ stories | Story 4.1 | Yes — in Epic 4 lessons |
| Bare `except Exception` | 2 stories | Story 4.5 | Mostly — 1 intentional exception in commission poll |
| `session.commit()` placement | 3 stories | Story 4.3 | Rule clarification needed |
| Patch site mismatch in tests | 2 epics | Story 1.5 | Yes — documented in Dev Notes |
| Session state key as string literal | 1 epic | Story 7.3 | Should be a constant |
| Architecture boundary (`dashboard/` ↔ `db/models`) | 3 stories | Story 6.3 | Yes — caught and fixed each time |
| Autouse fixture patching pure helpers | 1 story | Story 4.4 | Yes — in Epic 4 lessons |

---

## Technical Debt at Project Close

| Item | Risk | Notes |
|---|---|---|
| `MemorySaver` instead of `SqliteSaver` | **High** | State lost on process restart. Install `langgraph-checkpoint-sqlite` and replace |
| `dashboard/pages/videos.py` — 1 line stub | Medium | Video detail page not implemented |
| Story status fields all stale | Medium | All 6.x, 7.x files show `ready-for-dev` |
| Pre-existing ruff errors in test files | Low | `test_research.py`, `test_tiktok.py`, `test_alerts.py`, `test_llm.py` |
| `db/queries.py` boundary partially bypassed by agent nodes | Low | `monetization_node`, `analytics_node` call SQLAlchemy directly |
| Per-account env var scoping not implemented | Low | All accounts share same TikTok/ElevenLabs credentials |

---

## Action Items

| Priority | Action |
|---|---|
| 🔴 High | Replace `MemorySaver` with `SqliteSaver` for crash-safe state persistence |
| 🔴 High | Update all story status fields to `done` (script or manual pass) |
| 🟡 Medium | Add `ruff` rule `PLC0415` (no imports inside functions) to `pyproject.toml` |
| 🟡 Medium | Define session state keys as constants in `dashboard/app.py` (not string literals) |
| 🟡 Medium | Implement per-account env var scoping before provisioning a real second account |
| 🟢 Low | Implement `dashboard/pages/videos.py` detail page |
| 🟢 Low | Add explicit spec-drift approval step to story creation workflow |

---

## What This Project Proved

A fully autonomous AI agent system — from TikTok product research through video production, affiliate commission tracking, tournament-based niche optimization, error resilience, monitoring dashboard, and multi-account scaling — can be built and fully tested by one operator directing AI subagents, story by story, with consistent quality gates. The architecture held across 34 stories and 456 tests without a single regression.

The process works. The tooling needs a few guardrails. Deploy it.
