---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - _bmad-output/brainstorming/brainstorming-session-2026-03-08-001.md
date: 2026-03-08
author: Ivanma
---

# Product Brief: tiktok-faceless

## Executive Summary

tiktok-faceless is a fully autonomous multi-agent system that runs a TikTok faceless creator account end-to-end — researching trending products, producing videos, posting, optimizing, and managing affiliate revenue — with zero human intervention. The system is built by and for its creator as a personal income engine, targeting $1,000/month in TikTok Shop affiliate commissions from a single account as the initial milestone. A portfolio of 50+ accounts and a meta-product (selling the playbook) follow once the model is proven at scale.

---

## Core Vision

### Problem Statement

Earning meaningful affiliate income on TikTok requires either extraordinary manual effort — researching products, scripting, recording, editing, posting daily, analyzing results — or the budget to hire a team. Solo creators hit a hard ceiling on output, speed, and optimization depth. AI tooling exists but is fragmented, requiring constant human orchestration. No end-to-end autonomous system exists that can operate a profitable TikTok affiliate account independently.

### Problem Impact

The creator who could benefit most from this — technically capable, entrepreneurially motivated, time-constrained — is locked out of TikTok's affiliate opportunity not by lack of ideas but by the labor cost of consistent, high-volume, optimized content production. Every day without automation is lost compounding: missed trends, untested niches, unconverted traffic.

### Why Existing Solutions Fall Short

Current tools (CapCut automation, scheduling apps, AI script generators) are point solutions. They reduce friction on individual tasks but still require a human to connect the dots: decide what to make, when to post, what's working, what to kill. No existing product operates the full loop autonomously. More critically, no existing system is designed to survive TikTok's suppression risk — most AI-generated content pipelines produce high-volume, low-retention content that the algorithm correctly deprioritizes.

### Proposed Solution

A master Orchestration Agent directs a team of specialized sub-agents — Research, Script, Production, Publishing, Analytics, Engagement, Monetization — each expert at exactly one function. The system runs in phase-aware modes: Tournament (test niches), Commit (double down on winner), Scale (clone to new accounts). Data drives every decision. The agent never posts content it hasn't validated against buyer demand signals first.

The core technical bets:

**Retention-first content design.** Every video is optimized for 3-second and 15-second retention rates as primary KPIs — not view count. Hook diversity is structural: the Script Agent rotates across distinct archetypes (curiosity gap, social proof, controversy, demonstration) unpredictably to avoid algorithmic fingerprinting. The system gets measurably better at earning watch-time every week.

**Conversion as a parallel optimization track.** Affiliate CTR is tracked and A/B tested with the same rigor as retention. CTA phrasing, timing (15s vs 45s vs end-of-video), and urgency framing are iterated on independently. Buyer language mined from top-performing affiliate video comments feeds directly into script templates.

**Suppression resistance by design.** The Publishing Agent introduces human-variability patterns — randomized upload cadence, timing variance, video length variation — to avoid bot-detection triggers. High-volume posting is confined to algorithm-training phases with explicit suppression-risk monitoring.

**Continuous niche intelligence.** Niche selection from the Tournament Phase is not a one-time commitment. The Research Agent monitors commission-per-view decay signals continuously post-Commit, triggering re-tournament when a niche deteriorates.

### Key Differentiators

- **Demand-first production**: Agent validates buyer intent (TikTok Shop velocity, comment mining, cross-platform signals) before a single frame renders — zero wasted production effort
- **Dual optimization loop**: Retention earns algorithmic distribution; conversion earns revenue. Both are tracked and A/B tested independently as first-class metrics — most affiliate systems optimize for one or neither
- **Hook archetype diversity**: Script Agent rotates across structurally distinct hook types to prevent content fingerprinting and algorithmic decay
- **Suppression-resistant publishing**: Human-variability patterns built into the Publishing Agent from day 1 — not retrofitted when suppression hits
- **Niche decay detection**: Continuous market monitoring prevents single-niche commitment from becoming a revenue plateau
- **Phase-aware orchestration**: The Orchestrator knows whether it's discovering, proving, or scaling — adapting the entire agent team's behavior and risk tolerance accordingly
- **Full-funnel visibility**: Impression → view → retention → click → purchase → commission tracked per video, per product, per niche. A viral video with zero affiliate clicks is a system failure signal, not a success
- **Conversion-optimized content architecture**: Every script element — hook, problem framing, CTA phrasing — is trained on real buyer language mined from top-performing affiliate video comments

## Target Users

### Primary Users

**Ivanma — The Technical Indie Operator**

A technically fluent solo builder (Python-comfortable, system-design oriented) who wants to build and run an autonomous TikTok affiliate income engine as a personal revenue stream. Not a content creator by identity — an operator. Goals are financial: $1,000/month from account #1, scaling to $30K/month across a portfolio. Interaction with the system is primarily through a monitoring dashboard — reviewing performance data, affiliate revenue, and agent decisions — but not intervening in content production or posting. Hands-off by design. The system succeeds when it requires no daily input.

**What success looks like:** Dashboard shows $1K+ affiliate commission this month. No videos manually made. No products manually researched. No posting schedule managed. Revenue compounds week-over-week without operator involvement.

### Secondary Users

**The Technical Playbook Buyer** *(future, post $30K/month)*

Another solo developer or technical entrepreneur who wants the same outcome — autonomous affiliate income — but doesn't want to architect the system from scratch. They buy the playbook/course to compress their build time. Technically capable enough to implement with guidance. Motivated by the same financial goal. They become a secondary user of the documentation, SOPs, and system architecture that the meta-product packages.

### User Journey

**Discovery → Build → Launch → Monitor → Scale**

- **Setup (once):** Operator creates TikTok account and TikTok Shop affiliate account manually. Connects APIs (ElevenLabs, video generation, TikTok posting). Configures Orchestration Agent with initial parameters.
- **Tournament Phase (weeks 1-2):** Agent runs autonomously. Operator checks dashboard for niche tournament results — which category is generating affiliate clicks. No intervention required unless agent flags an error.
- **Commit Phase (weeks 3-4):** Orchestrator auto-commits to winning niche. Operator reviews dashboard: revenue trend, retention rates, affiliate CTR. Optionally adjusts lead magnet or monetization parameters.
- **Steady State:** Weekly dashboard review. Revenue tracked. Agent self-optimizes. Operator only re-engages when scaling to account #2 or when a niche decay signal triggers re-tournament.
- **Scale Phase:** Operator provisions account #2 manually, agent clones configuration and begins Tournament Phase independently.

## Success Metrics

### User Success Metrics

The operator (you) considers the system successful when:

- **Zero daily intervention required** — no manual content creation, product research, or posting in any given week
- **Niche winner identified by day 14** — Tournament Phase produces a data-confirmed winning category without human input
- **Full agent pipeline running end-to-end** — Research → Script → Production → Publishing → Analytics loop completes autonomously for at least 7 consecutive days
- **Dashboard is the only touchpoint** — all decisions visible and explainable through the monitoring dashboard without needing to inspect agent logs

### Business Objectives

| Milestone | Target | Timeframe |
|---|---|---|
| Proof of concept | First affiliate commission earned | Week 2 |
| MVP revenue | $1,000/month affiliate commissions | Month 3 |
| Reinvestment threshold | Account #2 launched from account #1 revenue | Month 4-5 |
| Portfolio revenue | $10,000/month across multiple accounts | Month 9-12 |
| Meta-product trigger | $30,000/month — begin packaging playbook | Month 12-18 |

### Key Performance Indicators

**Content Performance (per video)**
- 3-second retention rate: target >40%
- 15-second retention rate: target >25%
- Affiliate link CTR: target >2%
- View-to-click conversion: tracked per hook archetype

**Revenue (per account)**
- Affiliate commission per week
- Commission per video produced
- Revenue per niche (to drive rebalancing decisions)

**System Health**
- Videos produced per day (target: 3-10 depending on phase)
- Agent pipeline uptime (target: >95%)
- 48-hour kill rate: % of videos correctly auto-archived vs. promoted
- Niche decay detection lag: time from commission drop to re-tournament trigger

**Suppression Signals**
- FYP reach rate (impressions from non-followers / total views)
- Account shadowban detection: view velocity drop >70% with no content change

## MVP Scope

### Core Features (Account #1 — Must Work)

**1. Zero-Edit Production Pipeline**
Script → ElevenLabs voice → video generation → auto-captions → publish-ready vertical video. Idea to TikTok in under 10 minutes. No manual editing step exists.

**2. Orchestration Agent + Sub-Agent Wiring**
Master Orchestrator directing: Research Agent, Script Agent, Production Agent, Publishing Agent, Analytics Agent. Each independently operable. Orchestrator routes work and makes phase decisions.

**3. Niche Tournament Engine**
Posts 2-3 videos across 5-10 product categories in week 1. Analytics Agent tracks affiliate CTR and view velocity per category. Orchestrator auto-commits to winner by day 14.

**4. TikTok Shop Affiliate Integration**
Research Agent identifies validated products (minimum sales velocity threshold). Monetization Agent manages affiliate links per video. Commission tracking per video and per niche.

**5. Suppression-Resistant Publishing**
Publishing Agent with randomized cadence, timing variance, and video length variation. Phase-aware volume control (high during algorithm training, reduced in steady state).

**6. Retention-First A/B Testing**
For each product: 3 video variants with different hook archetypes. 48-hour kill switch. Winners get follow-up videos; losers archived as negative training examples. 3s/15s retention tracked as primary KPI alongside affiliate CTR.

**7. Monitoring Dashboard**
Single view: revenue by account/niche/video, retention rates, affiliate CTR, pipeline status, agent health. Read-only — operator reviews, does not intervene.

**8. Signature AI Persona**
Custom ElevenLabs voice cloned for account. Consistent name, personality, catchphrases applied across all scripts by Script Agent.

### Account Management Architecture

MVP operates a single account. Every technical decision is parameterized by `account_id` so scaling to account #2 requires provisioning (30 minutes), not rebuilding. Operator creates TikTok and TikTok Shop affiliate accounts manually; the system operates them from first post onward. Automated account creation is explicitly out of scope (TikTok ToS risk).

### Out of Scope for MVP

| Feature | Deferred To |
|---|---|
| Multi-account management (accounts 2-50) | Scale Phase |
| Omni-platform syndication (YouTube Shorts, Instagram Reels, Pinterest) | Month 4-5 |
| Email list + lead magnet pipeline | Month 3-4 (post revenue proof) |
| Engagement Agent (in-persona comment replies) | Month 2-3 |
| Cross-platform trend radar (Reddit + Google Trends) | Month 2 |
| Meta-product / playbook packaging | $30K/month milestone |
| Automated account provisioning | Scale Phase |
| TikTok SEO evergreen content strategy | Month 2-3 |

### MVP Success Criteria (Go/No-Go for Scale)

- Full agent pipeline runs end-to-end for 7 consecutive days without manual intervention
- Niche winner identified from Tournament Phase by day 14
- First affiliate commission earned by end of week 2
- $1,000/month affiliate revenue sustained for 2 consecutive months
- FYP reach rate maintained (no sustained shadowban signal)

### Future Vision

**Phase 2 — Portfolio (Months 4-12):**
50+ accounts operating as a parameterized network. Quant portfolio management allocating production budget by ROI. VC-style breakout detection fueling high-performing accounts. Omni-platform syndication generating 4x revenue per video produced.

**Phase 3 — Meta-Product (Month 12-18):**
The agent documents its own method. Performance data, SOPs, and architecture packaged into a $97-$497 "TikTok Affiliate Automation Playbook." The system that earns affiliate commissions also generates content that sells the course about building it.

**Long-Term:**
An autonomous content-to-commerce network operating at scale — the operator's role reduced to provisioning new accounts and reviewing weekly portfolio performance.
