# Story 6.2: Status Top Bar & Alert Zone

Status: ready-for-dev

## Story

As the operator,
I want a persistent top bar showing phase, pipeline status, and last post time plus an exception-first alert zone immediately below it,
so that the two most critical questions — "what phase?" and "is anything wrong?" — are answered before I see any metric data.

## Acceptance Criteria

1. **Given** the dashboard loads
   **When** I view the top bar
   **Then** it shows: Phase badge (Tournament/Commit/Scale with day counter) · Pipeline status dot + label · Last post time-ago · Videos posted today · Auto-refresh timestamp
   **And** the top bar is the first rendered element — always visible without scrolling

2. **Given** no active alerts exist
   **When** the alert zone renders
   **Then** a single green "All systems healthy · Last checked Ns ago" row is shown

3. **Given** `suppression_alert` is active (detected via `errors` table `error_type = "suppression_detected"` with `resolved_at IS NULL`) or any unresolved `errors` table entry exists
   **When** the alert zone renders
   **Then** a rose/amber banner renders with: plain-English title, detail sentence, auto-action confirmation, and time-ago stamp
   **And** the banner is visible above the fold without scrolling

4. **Given** the pipeline has not posted in over 24 hours
   **When** the top bar renders
   **Then** "Last post" shows in amber with the elapsed time
   **And** a warning banner appears in the alert zone: "No posts in 24h — pipeline may be stalled"

## Tasks / Subtasks

- [ ] Task 1: Add DB queries to `tiktok_faceless/db/queries.py`
  - [ ] `get_last_post_time(session, account_id: str) -> datetime | None` — queries `videos` table, filters `account_id` and `lifecycle_state IN ("posted", "analyzed", "archived", "promoted")`, returns `MAX(posted_at)` or `None` if no rows
  - [ ] `get_videos_posted_today(session, account_id: str) -> int` — queries `videos` table, filters `account_id`, `posted_at >= today_utc_midnight`, `lifecycle_state IN ("posted", "analyzed", "archived", "promoted")`, returns count
  - [ ] `get_account_phase(session, account_id: str) -> str` — queries `accounts` table, returns `phase` column value for `account_id`; returns `"warmup"` if account not found
  - [ ] `get_phase_started_at(session, account_id: str) -> datetime | None` — queries `agent_decisions` table, finds most recent row where `decision_type = "phase_transition"` and `to_value = current_phase`, returns `created_at`; returns `None` if no transition recorded
  - [ ] `get_unresolved_errors(session, account_id: str) -> list[Error]` — queries `errors` table, filters `account_id` and `resolved_at IS NULL`, ordered by `timestamp DESC`
  - [ ] `get_active_suppression(session, account_id: str) -> Error | None` — queries `errors` table, filters `account_id`, `error_type = "suppression_detected"`, `resolved_at IS NULL`, returns first row or `None`
  - [ ] `get_agent_health_from_errors(session, account_id: str) -> dict[str, bool]` — queries `errors` table grouped by `agent`, returns `{agent_name: False}` for any agent with unresolved errors, `True` for known agents with no unresolved errors. Known agents: `["orchestrator", "research", "script", "production", "publishing", "analytics", "monetization"]`

- [ ] Task 2: Implement `dashboard/components/phase_badge.py`
  - [ ] `render_phase_badge(phase: str, phase_started_at: datetime | None) -> None` — renders colored badge via `st.markdown` with inline HTML/CSS
  - [ ] Badge label mapping: `"warmup"` → "Warmup", `"tournament"` → "Tournament", `"commit"` → "Commit", `"scale"` → "Scale"
  - [ ] Badge color mapping: `"warmup"` → zinc, `"tournament"` → amber, `"commit"` → indigo, `"scale"` → emerald
  - [ ] Day counter: if `phase_started_at` is not `None`, compute `(datetime.utcnow() - phase_started_at).days + 1` and append "Day N" to badge label
  - [ ] Render as `st.markdown(f'<span style="...">Phase · Day N</span>', unsafe_allow_html=True)` inside a column

- [ ] Task 3: Implement `dashboard/components/suppression_alert.py`
  - [ ] `render_suppression_alert(suppression_error: Error | None) -> None` — renders suppression-specific rose banner if suppression_error is not None, no-op otherwise
  - [ ] Banner content: title "Suppression Detected", detail from `suppression_error.message`, auto-action from `suppression_error.recovery_suggestion` (or fallback "Pipeline has paused new posts automatically"), time-ago from `suppression_error.timestamp`

- [ ] Task 4: Implement top bar and alert zone in `dashboard/app.py`
  - [ ] Top bar: use `st.columns([2, 2, 2, 2, 2])` — five equal columns
    - Column 1: phase badge via `render_phase_badge(phase, phase_started_at)`
    - Column 2: pipeline status dot + label — green dot "Healthy" if no unresolved errors, red dot "Degraded" if any unresolved errors exist, determined by `get_unresolved_errors()`
    - Column 3: last post time-ago — compute `humanize_timedelta(datetime.utcnow() - last_post_time)` if `last_post_time` is not None, else "Never"; render in amber if `last_post_time` is None or elapsed > 24h
    - Column 4: videos posted today count — render as `st.metric("Posted Today", count)`
    - Column 5: auto-refresh timestamp — `st.caption(f"Refreshed {datetime.utcnow().strftime('%H:%M:%S')} UTC")`
  - [ ] Alert zone: renders immediately below top bar, above all other content
    - If `get_active_suppression()` returns a row: render rose banner via `render_suppression_alert()`
    - Else if `last_post_time` is None or `(datetime.utcnow() - last_post_time).total_seconds() > 86400`: render amber `st.warning("No posts in 24h — pipeline may be stalled")`
    - Else if `get_unresolved_errors()` returns any rows: render amber `st.warning(f"{len(errors)} unresolved error(s) — check the Errors tab")`
    - Else: render `st.success("All systems healthy · Last checked just now")`
  - [ ] Helper function `humanize_timedelta(delta: timedelta) -> str` in `app.py` or `dashboard/components/` — returns strings like "3m ago", "2h ago", "1d ago"

- [ ] Task 5: Write tests in `tests/unit/dashboard/`
  - [ ] `tests/unit/dashboard/test_queries_top_bar.py`:
    - `test_get_last_post_time_returns_none_when_no_videos` — empty DB → None
    - `test_get_last_post_time_returns_max_posted_at` — two posted videos → returns later `posted_at`
    - `test_get_last_post_time_excludes_unposted_lifecycles` — video with `lifecycle_state = "queued"` → not counted
    - `test_get_videos_posted_today_returns_zero_when_none` — no videos posted today → 0
    - `test_get_videos_posted_today_counts_only_today` — one video posted yesterday, one today → 1
    - `test_get_account_phase_returns_warmup_default` — no account row → "warmup"
    - `test_get_unresolved_errors_excludes_resolved` — one resolved + one unresolved → returns only unresolved
    - `test_get_active_suppression_returns_none_when_resolved` — suppression error with `resolved_at` set → None
    - `test_get_agent_health_from_errors_marks_agent_unhealthy` — unresolved error for "publishing" → `{"publishing": False}`
  - [ ] `tests/unit/dashboard/test_top_bar.py`:
    - `test_humanize_timedelta_minutes` — 3 minutes → "3m ago"
    - `test_humanize_timedelta_hours` — 2.5 hours → "2h ago"
    - `test_humanize_timedelta_days` — 1.5 days → "1d ago"
    - `test_render_phase_badge_tournament_with_day_counter` — mock `datetime.utcnow`, assert output contains "Tournament" and "Day"
    - `test_render_phase_badge_no_started_at` — `phase_started_at=None` → no day counter in output

## Dev Notes

### Architecture Boundary (MUST NOT VIOLATE)

- `dashboard/` imports ONLY from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- NEVER import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, `tiktok_faceless.state`, or `tiktok_faceless.graph`
- All queries are read-only — no dashboard code writes to the database
- `PipelineState` is LangGraph in-memory state and is NOT accessible from the dashboard. All top bar data comes from DB tables only.

### Key Data Sources

Each top bar element maps to a specific DB table and column:

| Top Bar Element | DB Table | Column(s) | Query Function |
|---|---|---|---|
| Phase badge label | `accounts` | `phase` | `get_account_phase()` |
| Phase day counter | `agent_decisions` | `created_at` WHERE `decision_type="phase_transition"` AND `to_value=<current_phase>` | `get_phase_started_at()` |
| Pipeline status (healthy/degraded) | `errors` | `resolved_at IS NULL` → unhealthy | `get_unresolved_errors()` |
| Last post time-ago | `videos` | `MAX(posted_at)` WHERE `lifecycle_state IN (posted, analyzed, archived, promoted)` | `get_last_post_time()` |
| Videos posted today | `videos` | `COUNT(*)` WHERE `posted_at >= today midnight UTC` AND `lifecycle_state IN (posted, ...)` | `get_videos_posted_today()` |
| Suppression alert | `errors` | `error_type = "suppression_detected"` AND `resolved_at IS NULL` | `get_active_suppression()` |
| 24h no-post warning | computed from `get_last_post_time()` result | elapsed > 86400s | inline in `app.py` |

### Agent Health Determination

Agent health is derived from the `errors` table, NOT from `PipelineState.agent_health` (which is LangGraph in-memory only). The rule:

- An agent is **unhealthy** (`False`) if any row exists in `errors` WHERE `agent = <agent_name>` AND `resolved_at IS NULL`
- An agent is **healthy** (`True`) if no such unresolved error exists
- Known agent names (for `get_agent_health_from_errors()`): `["orchestrator", "research", "script", "production", "publishing", "analytics", "monetization"]`

```python
# Correct pattern in queries.py
def get_agent_health_from_errors(session: Session, account_id: str) -> dict[str, bool]:
    known_agents = ["orchestrator", "research", "script", "production", "publishing", "analytics", "monetization"]
    unhealthy_agents = (
        session.query(Error.agent)
        .filter(Error.account_id == account_id, Error.resolved_at.is_(None))
        .distinct()
        .all()
    )
    unhealthy_set = {row.agent for row in unhealthy_agents}
    return {agent: agent not in unhealthy_set for agent in known_agents}
```

### Suppression Detection from DB

Suppression is detected by the analytics agent, which writes to the `errors` table with `error_type = "suppression_detected"`. The dashboard reads this — it does NOT read `PipelineState.suppression_alert` (in-memory, not accessible).

```python
# Correct detection pattern in queries.py
def get_active_suppression(session: Session, account_id: str) -> Error | None:
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.error_type == "suppression_detected",
            Error.resolved_at.is_(None),
        )
        .order_by(Error.timestamp.desc())
        .first()
    )
```

### Phase Day Counter

Phase transitions are logged in `agent_decisions` with `decision_type = "phase_transition"` and `to_value = <new_phase>`. To find how long the current phase has been active:

```python
def get_phase_started_at(session: Session, account_id: str) -> datetime | None:
    account_phase = get_account_phase(session, account_id)
    row = (
        session.query(AgentDecision)
        .filter(
            AgentDecision.account_id == account_id,
            AgentDecision.decision_type == "phase_transition",
            AgentDecision.to_value == account_phase,
        )
        .order_by(AgentDecision.created_at.desc())
        .first()
    )
    return row.created_at if row else None
```

If `None` (no transition recorded — e.g. initial warmup phase), the badge renders without a day counter.

### Top Bar Layout Pattern

```python
# In dashboard/app.py, after auth gate and autorefresh
col_phase, col_status, col_last_post, col_today, col_refresh = st.columns([2, 2, 2, 2, 2])

with col_phase:
    render_phase_badge(phase, phase_started_at)

with col_status:
    if unresolved_errors:
        st.markdown("🔴 **Degraded**")
    else:
        st.markdown("🟢 **Healthy**")

with col_last_post:
    if last_post_time is None:
        st.markdown(":orange[Last post: Never]")
    else:
        elapsed = datetime.utcnow() - last_post_time
        label = humanize_timedelta(elapsed)
        if elapsed.total_seconds() > 86400:
            st.markdown(f":orange[Last post: {label}]")
        else:
            st.markdown(f"Last post: {label}")

with col_today:
    st.metric("Posted Today", videos_today)

with col_refresh:
    st.caption(f"Refreshed {datetime.utcnow().strftime('%H:%M:%S')} UTC")
```

### Alert Zone Render Order (Priority)

Alert zone renders immediately after the top bar columns block, before any other content. Priority order (highest to lowest):

1. Rose: suppression detected (unresolved `error_type = "suppression_detected"`)
2. Amber: no posts in 24h (`last_post_time` None or elapsed > 86400s)
3. Amber: other unresolved errors (count + link to errors tab)
4. Green: all systems healthy (no alerts)

Only one banner renders — the highest-priority condition wins.

### `humanize_timedelta` Helper

```python
def humanize_timedelta(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    return f"{total_seconds // 86400}d ago"
```

Place in `dashboard/app.py` (or `dashboard/components/` if reused across pages).

### Streamlit Markdown Color Syntax

Use Streamlit's native color syntax for inline colored text (no raw HTML needed for simple cases):

```python
st.markdown(":orange[Last post: 26h ago]")   # amber/orange
st.markdown(":red[Pipeline degraded]")        # rose/red
st.markdown(":green[All systems healthy]")    # emerald/green
```

For badge shapes (pill/rounded), use `unsafe_allow_html=True` with a `<span>` element.

### Dependency Note

`streamlit` and `streamlit-autorefresh` are already added to `pyproject.toml` in Story 6.1. No new dependencies required for this story.

### Project Conventions

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length <= 100 chars
- No bare `except Exception` — catch typed exceptions
- No function-level imports — all imports at module level
- `datetime.utcnow()` for naive UTC timestamps
- Run `uv run pytest tests/unit/ -q` before marking done (currently 325+ passing from Story 6.1)
- Run `uv run ruff check tiktok_faceless/db/queries.py dashboard/ tests/unit/dashboard/` after implementation

### References

- Epic 6, Story 6.2 spec: `_bmad-output/planning-artifacts/epics.md`
- Architecture dashboard boundary: `_bmad-output/planning-artifacts/architecture.md` — "Dashboard Boundary"
- Architecture data model: `_bmad-output/planning-artifacts/architecture.md` — "Data Architecture"
- DB models: `tiktok_faceless/db/models.py` — `Account`, `Video`, `Error`, `AgentDecision`
- State fields (reference only, not imported by dashboard): `tiktok_faceless/state.py` — `PipelineState`
- Query patterns: `tiktok_faceless/db/queries.py` — existing `account_id`-scoped query functions
- Dependency story: `_bmad-output/implementation-artifacts/6-1-dashboard-foundation-auth.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
