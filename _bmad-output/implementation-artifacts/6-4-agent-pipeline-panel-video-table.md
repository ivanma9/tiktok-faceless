# Story 6.4: Agent Pipeline Panel & Video Performance Table

Status: ready-for-dev

## Story

As the operator,
I want a 50/50 bottom panel showing per-agent status on the left and a top videos performance table on the right,
So that I can check pipeline health and content performance in a single scroll.

## Acceptance Criteria

1. **Given** the dashboard is loaded
   **When** the bottom panels render
   **Then** a `st.columns(2)` layout shows Agent Pipeline Panel (left) and Video Performance Table (right)
   **And** the layout is rendered below the KPI strip (Story 6.3) and above any phase-specific panels

2. **Given** the Agent Pipeline Panel renders
   **When** I view it
   **Then** 6 agent rows display in order: Orchestrator, Research, Script, Production, Publishing, Analytics
   **And** each row shows: a colored status indicator dot, the agent name, and a plain-English status note
   **And** status color rules apply: healthy (no unresolved errors) → emerald, unhealthy (unresolved errors) → rose, absent from health map (not yet run) → zinc
   **And** the "running" indigo state is NOT used — status is derived from `get_agent_health_from_errors()` which returns only healthy/unhealthy/absent states

3. **Given** the Video Performance Table renders
   **When** I view it
   **Then** a `st.dataframe` shows up to top 20 videos by commission earned (descending) with columns: Hook Archetype, 3s Retention %, Affiliate CTR %, Commission Earned ($), Lifecycle Status
   **And** all columns are sortable by clicking the column header (native `st.dataframe` behavior)
   **And** numeric columns show formatted values: retention as percentage, CTR as percentage, commission as dollar amount

4. **Given** no video data exists (fresh account)
   **When** the Video Performance Table renders
   **Then** the table renders an empty dataframe with headers visible — no error thrown

5. **Given** `phase = "tournament"` is active for the current account
   **When** the page renders below the two-column panel
   **Then** a niche tournament table renders with columns: Rank, Niche, Video Count, Avg CTR %, Avg 3s Retention %, Total Revenue ($), Status (Leading / Trailing / Eliminated)
   **And** niches are ranked by tournament score descending (same score formula as `get_niche_scores()`)
   **And** the top-ranked niche shows "Leading", eliminated niches show "Eliminated", all others show "Trailing"

6. **Given** the phase is NOT "tournament"
   **When** the page renders
   **Then** the niche tournament table is NOT shown — no empty section, no heading

## Tasks / Subtasks

- [ ] Task 1: Add video table query function to `tiktok_faceless/db/queries.py`
  - [ ] `get_top_videos_by_commission(session, account_id: str, limit: int = 20) -> list[dict]` — see Dev Notes for exact query and returned dict schema
  - [ ] `get_tournament_niche_table(session, account_id: str, days: int = 7) -> list[dict]` — see Dev Notes for query and returned dict schema; reuses `get_niche_scores()` logic extended with status assignment

- [ ] Task 2: Implement `dashboard/components/agent_panel.py`
  - [ ] Define module-level constant `AGENT_ORDER: list[str]` = `["orchestrator", "research", "script", "production", "publishing", "analytics"]`
  - [ ] Define module-level constant `AGENT_DISPLAY_NAMES: dict[str, str]` mapping agent keys to title-case display names (e.g. `"orchestrator"` → `"Orchestrator"`)
  - [ ] Define module-level constant `STATUS_COLORS: dict[str, str]` = `{"healthy": "#10b981", "error": "#f43f5e", "waiting": "#71717a"}` (emerald / rose / zinc)
  - [ ] `_agent_status(health_map: dict[str, bool], agent: str) -> tuple[str, str]` — returns `(status_key, status_note)` where `status_key` is one of `"healthy"`, `"error"`, `"waiting"`, and `status_note` is a plain-English label; see Dev Notes for mapping rules
  - [ ] `render_agent_panel(session, account_id: str) -> None` — orchestrates the full render: calls `get_agent_health_from_errors()`, renders a labeled section header `st.subheader("Agent Pipeline")`, iterates `AGENT_ORDER`, renders each row as described in Dev Notes
  - [ ] Each agent row uses `st.columns([0.08, 0.92])` to place a colored dot (rendered via `st.markdown`) alongside the agent name + status note
  - [ ] Wrap the entire function body in `try/except Exception as e: st.error(f"Agent panel failed: {e}")` — never crash the page

- [ ] Task 3: Implement video performance table in `dashboard/components/video_table.py`
  - [ ] `render_video_table(session, account_id: str) -> None` — calls `get_top_videos_by_commission()`, builds a `pd.DataFrame`, formats numeric columns, renders `st.subheader("Top Videos by Commission")` + `st.dataframe(df, use_container_width=True)`
  - [ ] Column display names (rename from raw dict keys): `hook_archetype` → `"Hook Archetype"`, `retention_3s_pct` → `"3s Retention %"`, `affiliate_ctr_pct` → `"Affiliate CTR %"`, `commission_earned` → `"Commission ($)"`, `lifecycle_state` → `"Status"`
  - [ ] Numeric formatting before passing to dataframe: `retention_3s_pct` and `affiliate_ctr_pct` multiply by 100 and round to 1 decimal; `commission_earned` round to 2 decimal
  - [ ] If query returns empty list, render the dataframe with an empty DataFrame (columns present, zero rows) — do NOT render `st.info("No videos yet")` instead of the table
  - [ ] Wrap body in `try/except Exception as e: st.error(f"Video table failed: {e}")`

- [ ] Task 4: Implement tournament niche table in `dashboard/components/tournament_table.py`
  - [ ] `render_tournament_table(session, account_id: str) -> None` — calls `get_tournament_niche_table()`, builds a `pd.DataFrame`, renders `st.subheader("Tournament: Niche Rankings")` + `st.dataframe(df, use_container_width=True)`
  - [ ] Column display names: `rank` → `"Rank"`, `niche` → `"Niche"`, `video_count` → `"Videos"`, `avg_ctr_pct` → `"Avg CTR %"`, `avg_retention_3s_pct` → `"Avg 3s Ret %"`, `total_revenue` → `"Revenue ($)"`, `status` → `"Status"`
  - [ ] If query returns empty list, render nothing (return early without section header) — tournament is not meaningful with zero data
  - [ ] Wrap body in `try/except Exception as e: st.error(f"Tournament table failed: {e}")`

- [ ] Task 5: Integrate into `dashboard/pages/overview.py` (below KPI strip)
  - [ ] Import `render_agent_panel` from `dashboard.components.agent_panel`
  - [ ] Import `render_video_table` from `dashboard.components.video_table`
  - [ ] Import `render_tournament_table` from `dashboard.components.tournament_table`
  - [ ] Import `get_account_phase` from `tiktok_faceless.db.queries`
  - [ ] After the KPI strip block and `st.divider()`, add a `st.columns(2)` block: left column calls `render_agent_panel(session, account_id)`, right column calls `render_video_table(session, account_id)`
  - [ ] After the two-column block, add phase-gated tournament section:
    ```python
    phase = get_account_phase(session, account_id)
    if phase == "tournament":
        st.divider()
        render_tournament_table(session, account_id)
    ```
  - [ ] Each render call is independently wrapped in `try/except Exception as e: st.error(...)` to isolate failures

- [ ] Task 6: Write tests in `tests/unit/dashboard/`
  - [ ] `tests/unit/dashboard/test_queries_video_table.py`:
    - `test_get_top_videos_by_commission_returns_empty_when_no_data` — empty DB → `[]`
    - `test_get_top_videos_by_commission_orders_by_commission_desc` — insert 3 videos with different commission totals → returned list is descending by commission
    - `test_get_top_videos_by_commission_limits_to_20` — insert 25 videos → returned list has exactly 20 entries
    - `test_get_top_videos_by_commission_includes_required_keys` — returned dicts contain all required keys: `hook_archetype`, `retention_3s_pct`, `affiliate_ctr_pct`, `commission_earned`, `lifecycle_state`
    - `test_get_tournament_niche_table_returns_empty_when_no_data` — empty DB → `[]`
    - `test_get_tournament_niche_table_assigns_leading_to_top_niche` — two niches with different scores → top niche has `status="Leading"`
    - `test_get_tournament_niche_table_assigns_eliminated_status` — insert products with `eliminated=True` for a niche → that niche row has `status="Eliminated"`
    - `test_get_tournament_niche_table_assigns_trailing_to_middle_niches` — three niches → middle niche has `status="Trailing"`
    - `test_get_tournament_niche_table_includes_required_keys` — returned dicts contain all required keys: `rank`, `niche`, `video_count`, `avg_ctr_pct`, `avg_retention_3s_pct`, `total_revenue`, `status`
  - [ ] `tests/unit/dashboard/test_agent_panel.py`:
    - `test_agent_status_healthy_when_in_health_map_true` — `health_map = {"orchestrator": True}`, agent `"orchestrator"` → `status_key == "healthy"`
    - `test_agent_status_error_when_in_health_map_false` — `health_map = {"research": False}` → `status_key == "error"`
    - `test_agent_status_waiting_when_absent_from_health_map` — `health_map = {}`, any agent → `status_key == "waiting"`
    - `test_render_agent_panel_renders_six_rows` — mock `get_agent_health_from_errors` → confirm 6 agents processed (assert on `AGENT_ORDER` iteration)
    - `test_render_agent_panel_handles_exception_gracefully` — mock `get_agent_health_from_errors` raises `Exception` → `st.error` called, no re-raise

## Dev Notes

### Architecture Boundary (MUST NOT VIOLATE)

- `dashboard/` imports ONLY from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- NEVER import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, `tiktok_faceless.state`, or `tiktok_faceless.graph`
- All new query functions are read-only — no `session.add()`, `session.commit()`, or `session.delete()` calls
- `PipelineState` is NOT accessible from dashboard code — agent health is derived from the `errors` DB table only via `get_agent_health_from_errors()`

### `get_agent_health_from_errors` — Reuse Existing Function

`get_agent_health_from_errors(session, account_id)` already exists in `tiktok_faceless/db/queries.py` (line 403). It returns `dict[str, bool]` where `True` = healthy (no unresolved errors), `False` = unhealthy (has unresolved errors). Keys are only present if the agent is a known agent name.

Status mapping for agent panel:
```python
def _agent_status(health_map: dict[str, bool], agent: str) -> tuple[str, str]:
    if agent not in health_map:
        return ("waiting", "Waiting — not yet run")
    if health_map[agent]:
        return ("healthy", "Healthy — no active errors")
    return ("error", "Error — check error log")
```

The "running" (indigo) status from the epics.md AC is NOT implementable without real process monitoring (which is outside dashboard scope). This story simplifies to three states: healthy/error/waiting. The epics.md note about `state["agent_health"]` refers to the same data surfaced via `get_agent_health_from_errors()` — the DB is the source of truth.

### Agent Panel Row Render Pattern

```python
# In render_agent_panel(), for each agent in AGENT_ORDER:
status_key, status_note = _agent_status(health_map, agent)
color = STATUS_COLORS[status_key]
dot = f'<span style="color:{color}; font-size:20px;">●</span>'
col_dot, col_text = st.columns([0.08, 0.92])
with col_dot:
    st.markdown(dot, unsafe_allow_html=True)
with col_text:
    st.markdown(f"**{AGENT_DISPLAY_NAMES[agent]}** — {status_note}")
```

### `get_top_videos_by_commission` Query

```python
def get_top_videos_by_commission(
    session: Session,
    account_id: str,
    limit: int = 20,
) -> list[dict]:
    """Return top N videos by total commission earned, descending.

    Joins Video + VideoMetric + Product (optional) to compute commission.
    Returns list of dicts with keys:
      hook_archetype, retention_3s_pct, affiliate_ctr_pct, commission_earned, lifecycle_state
    """
    rows = (
        session.query(
            Video.hook_archetype,
            Video.lifecycle_state,
            func.avg(VideoMetric.retention_3s).label("avg_retention_3s"),
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
            func.sum(
                VideoMetric.affiliate_orders * Product.commission_rate
            ).label("commission_earned"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .outerjoin(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            Video.account_id == account_id,
            Video.tiktok_video_id.isnot(None),
        )
        .group_by(Video.id, Video.hook_archetype, Video.lifecycle_state)
        .order_by(func.sum(VideoMetric.affiliate_orders * Product.commission_rate).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "hook_archetype": row.hook_archetype or "—",
            "retention_3s_pct": float(row.avg_retention_3s or 0.0),
            "affiliate_ctr_pct": (
                float(row.total_clicks or 0) / max(float(row.total_views or 0), 1.0)
            ),
            "commission_earned": float(row.commission_earned or 0.0),
            "lifecycle_state": row.lifecycle_state,
        }
        for row in rows
    ]
```

If the `Product` join yields no rows (no linked products), `commission_earned` will be `None`. The `or 0.0` fallback ensures a `0.0` float is returned — never `None` in the dict.

### `get_tournament_niche_table` Query

Reuses `get_niche_scores()` logic to compute scores, then augments with extended fields and status assignment.

```python
def get_tournament_niche_table(
    session: Session,
    account_id: str,
    days: int = 7,
) -> list[dict]:
    """Return niche tournament rankings with status assignment.

    Returns list of dicts with keys:
      rank, niche, video_count, avg_ctr_pct, avg_retention_3s_pct, total_revenue, status
    Sorted by score descending. Returns [] if no data.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.niche,
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
            func.avg(VideoMetric.retention_3s).label("avg_retention_3s"),
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.count(func.distinct(VideoMetric.video_id)).label("video_count"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.niche)
        .all()
    )

    if not rows:
        return []

    max_orders = max(int(r.total_orders or 0) for r in rows)

    scored = []
    for row in rows:
        aff_ctr = int(row.total_clicks or 0) / max(int(row.total_views or 0), 1)
        retention = max(0.0, min(1.0, float(row.avg_retention_3s or 0.0)))
        norm_orders = int(row.total_orders or 0) / max(max_orders, 1)
        score = 0.40 * min(1.0, aff_ctr) + 0.30 * retention + 0.30 * norm_orders
        scored.append((row, aff_ctr, score))

    scored.sort(key=lambda x: x[2], reverse=True)

    # Determine which niches have eliminated=True products
    eliminated_niches = {
        row.niche
        for row in session.query(Product.niche)
        .filter(Product.account_id == account_id, Product.eliminated == True)  # noqa: E712
        .distinct()
        .all()
    }

    result = []
    for rank, (row, aff_ctr, score) in enumerate(scored, start=1):
        if row.niche in eliminated_niches:
            status = "Eliminated"
        elif rank == 1:
            status = "Leading"
        else:
            status = "Trailing"

        result.append({
            "rank": rank,
            "niche": row.niche,
            "video_count": int(row.video_count or 0),
            "avg_ctr_pct": aff_ctr,
            "avg_retention_3s_pct": float(row.avg_retention_3s or 0.0),
            "total_revenue": float(row.total_orders or 0),  # order count as revenue proxy
            "status": status,
        })
    return result
```

Note: `total_revenue` uses `affiliate_orders` as a unit-count proxy (same as KPI revenue fallback in Story 6.3). If products are linked, a more precise join can be added post-MVP.

### Video Table DataFrame Formatting

```python
import pandas as pd

def render_video_table(session, account_id: str) -> None:
    rows = get_top_videos_by_commission(session, account_id)
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "hook_archetype", "retention_3s_pct", "affiliate_ctr_pct",
        "commission_earned", "lifecycle_state",
    ])
    # Format numeric columns for display
    df["retention_3s_pct"] = (df["retention_3s_pct"] * 100).round(1)
    df["affiliate_ctr_pct"] = (df["affiliate_ctr_pct"] * 100).round(1)
    df["commission_earned"] = df["commission_earned"].round(2)
    # Rename columns for display
    df = df.rename(columns={
        "hook_archetype": "Hook Archetype",
        "retention_3s_pct": "3s Retention %",
        "affiliate_ctr_pct": "Affiliate CTR %",
        "commission_earned": "Commission ($)",
        "lifecycle_state": "Status",
    })
    st.subheader("Top Videos by Commission")
    st.dataframe(df, use_container_width=True)
```

### Tournament Table DataFrame Formatting

```python
def render_tournament_table(session, account_id: str) -> None:
    rows = get_tournament_niche_table(session, account_id)
    if not rows:
        return  # No header, no empty table — tournament meaningless without data
    df = pd.DataFrame(rows)
    df["avg_ctr_pct"] = (df["avg_ctr_pct"] * 100).round(1)
    df["avg_retention_3s_pct"] = (df["avg_retention_3s_pct"] * 100).round(1)
    df["total_revenue"] = df["total_revenue"].round(2)
    df = df.rename(columns={
        "rank": "Rank",
        "niche": "Niche",
        "video_count": "Videos",
        "avg_ctr_pct": "Avg CTR %",
        "avg_retention_3s_pct": "Avg 3s Ret %",
        "total_revenue": "Revenue ($)",
        "status": "Status",
    })
    st.subheader("Tournament: Niche Rankings")
    st.dataframe(df, use_container_width=True)
```

### Overview Page Integration (overview.py)

The integration point is immediately after the KPI strip block established by Story 6.3. The `get_account_phase()` function already exists in `db/queries.py`.

```python
# After KPI strip block and st.divider()

# --- Agent Pipeline Panel + Video Performance Table ---
left_col, right_col = st.columns(2)
with left_col:
    try:
        render_agent_panel(session, account_id)
    except Exception as e:
        st.error(f"Agent panel failed to load: {e}")

with right_col:
    try:
        render_video_table(session, account_id)
    except Exception as e:
        st.error(f"Video table failed to load: {e}")

# --- Tournament Niche Table (phase-gated) ---
try:
    phase = get_account_phase(session, account_id)
    if phase == "tournament":
        st.divider()
        render_tournament_table(session, account_id)
except Exception as e:
    st.error(f"Tournament table failed to load: {e}")
```

### New Files to Create

| File | Purpose |
|---|---|
| `dashboard/components/agent_panel.py` | Agent Pipeline Panel component |
| `dashboard/components/video_table.py` | Video Performance Table component |
| `dashboard/components/tournament_table.py` | Tournament Niche Table component |
| `tests/unit/dashboard/test_queries_video_table.py` | Query tests |
| `tests/unit/dashboard/test_agent_panel.py` | Agent panel unit tests |

### Existing Functions to Reuse (Do Not Duplicate)

| Function | Location | Used By |
|---|---|---|
| `get_agent_health_from_errors(session, account_id)` | `db/queries.py:403` | `agent_panel.py` |
| `get_account_phase(session, account_id)` | `db/queries.py:354` | `overview.py` |
| `get_niche_scores(session, account_id, days)` | `db/queries.py:149` | Reference pattern for `get_tournament_niche_table` |

### Project Conventions

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length <= 100 chars
- No bare `except Exception` at module top level in query functions — only in component render functions (UI resilience)
- No function-level imports — all imports at module top
- `datetime.utcnow()` for naive UTC timestamps throughout
- All query functions accept `session: Session` as first arg and `account_id: str` as second — never open a new session internally
- Run `uv run pytest tests/unit/ -q` before marking done
- Run `uv run ruff check tiktok_faceless/db/queries.py dashboard/components/ dashboard/pages/overview.py tests/unit/dashboard/` after implementation

### Dependencies

- `pandas` — transitive via streamlit; no new `pyproject.toml` entry needed
- `streamlit` — already added in Story 6.1
- Story 6.3 must be complete before integrating into `overview.py` — the KPI strip block must already be in place so this story inserts in the correct position below it
- Story 6.2 must also be complete — the top bar and alert zone must be rendering

### References

- Epic 6, Story 6.4 spec: `_bmad-output/planning-artifacts/epics.md` (lines 1120–1147)
- Architecture dashboard boundary: `_bmad-output/planning-artifacts/architecture.md` — "Dashboard Boundary"
- DB models: `tiktok_faceless/db/models.py` — `Video`, `VideoMetric`, `Product`, `Error`
- Existing queries: `tiktok_faceless/db/queries.py` — `get_agent_health_from_errors()`, `get_niche_scores()`, `get_archetype_scores()`, `get_account_phase()`
- Prior story spec: `_bmad-output/implementation-artifacts/6-3-kpi-strip-sparklines.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
