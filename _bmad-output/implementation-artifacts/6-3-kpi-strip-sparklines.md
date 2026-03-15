# Story 6.3: KPI Strip with Sparklines

Status: ready-for-dev

## Story

As the operator,
I want a 5-column KPI strip showing Revenue, 3s Retention, 15s Retention, Affiliate CTR, and FYP Reach — each with a 7-day sparkline and freshness timestamp,
So that I can answer "is it growing?" in a single eye pass without selecting date ranges or navigating anywhere.

## Acceptance Criteria

1. **Given** the dashboard is authenticated and data is loaded
   **When** the KPI strip renders
   **Then** 5 `st.metric` cards display in a `st.columns(5)` row: Revenue (7-day total), 3s Retention (avg %), 15s Retention (avg %), Affiliate CTR (avg %), FYP Reach Rate (avg %)
   **And** each card shows: current value, delta vs prior 7-day period (↑/↓/→), and a 7-day sparkline rendered immediately below the metric

2. **Given** a KPI value is above its configured target threshold
   **When** the card renders
   **Then** the delta indicator is shown in emerald; if below threshold in amber; if critically below in rose

3. **Given** data for a KPI is older than 5 minutes
   **When** the freshness timestamp renders
   **Then** it shows in amber: "⚠ Updated Nm ago"
   **And** if older than 15 minutes, it shows in rose: "⚠ Updated Nm ago"

4. **Given** no video data exists yet (fresh account)
   **When** the KPI strip renders
   **Then** each card shows "—" with label "No data yet" — no error thrown

## Tasks / Subtasks

- [ ] Task 1: Add KPI query functions to `tiktok_faceless/db/queries.py`
  - [ ] `get_kpi_revenue(session, account_id: str, days: int = 7) -> float` — sum of `VideoMetric.affiliate_clicks * VideoMetric.affiliate_orders / max(VideoMetric.view_count, 1)` proxy; see Dev Notes for exact revenue formula
  - [ ] `get_kpi_retention_3s(session, account_id: str, days: int = 7) -> float | None` — `AVG(VideoMetric.retention_3s)` filtered to `recorded_at >= now - days`; returns `None` if no rows
  - [ ] `get_kpi_retention_15s(session, account_id: str, days: int = 7) -> float | None` — `AVG(VideoMetric.retention_15s)` filtered to `recorded_at >= now - days`; returns `None` if no rows
  - [ ] `get_kpi_affiliate_ctr(session, account_id: str, days: int = 7) -> float | None` — `SUM(affiliate_clicks) / MAX(SUM(view_count), 1)` for the window; returns `None` if no rows
  - [ ] `get_kpi_fyp_reach_rate(session, account_id: str, days: int = 7) -> float | None` — `AVG(VideoMetric.fyp_reach_pct)` filtered to `recorded_at >= now - days`; returns `None` if no rows
  - [ ] `get_kpi_sparkline(session, account_id: str, metric: str, days: int = 7) -> list[float]` — returns a list of `days` daily average values (oldest → newest). `metric` is one of `"retention_3s"`, `"retention_15s"`, `"affiliate_ctr"`, `"fyp_reach_pct"`, `"revenue"`. Each element is the day's average; missing days filled with `0.0`. See Dev Notes for implementation pattern.
  - [ ] `get_kpi_freshness(session, account_id: str) -> datetime | None` — returns `MAX(VideoMetric.recorded_at)` for the account; returns `None` if no rows exist

- [ ] Task 2: Implement `dashboard/components/sparkline.py`
  - [ ] `render_sparkline(values: list[float], color: str = "#10b981") -> None` — renders a minimal inline sparkline chart using `st.line_chart` or Altair; `color` defaults to emerald (`#10b981`), can be overridden to amber (`#f59e0b`) or rose (`#f43f5e`)
  - [ ] Chart must be compact: no axis labels, no legend, no title — pure trend line only
  - [ ] If `values` is empty or all zeros, render nothing (no error, no empty chart artifact)
  - [ ] Use Altair (`altair`) for rendering: build a `alt.Chart` from a `pd.DataFrame`, mark as `mark_line`, encode `x` as index, `y` as value, set chart height to 60px and width to fill column
  - [ ] Wrap the entire function body in `try/except Exception` — log to `st.caption("Sparkline unavailable")` on failure rather than crashing the page

- [ ] Task 3: Implement `dashboard/components/kpi_strip.py`
  - [ ] Define dataclass `KPICard` with fields: `label: str`, `value: float | None`, `delta: float | None`, `sparkline: list[float]`, `unit: str`, `threshold_ok: float`, `threshold_warn: float`
  - [ ] `build_kpi_cards(session, account_id: str) -> list[KPICard]` — calls all 5 `get_kpi_*` functions for the current 7-day window AND the prior 7-day window (days 8–14 back), computes delta as `current - prior` for each KPI, populates `KPICard` list in order: Revenue, 3s Retention, 15s Retention, Affiliate CTR, FYP Reach Rate
  - [ ] `format_kpi_value(value: float | None, unit: str) -> str` — returns `"—"` if value is `None`, `f"${value:,.2f}"` for `unit="$"`, `f"{value*100:.1f}%"` for `unit="%"`
  - [ ] `format_delta(delta: float | None, unit: str) -> str` — returns `""` (empty) if delta is `None`, `f"+${delta:,.2f}"` / `f"-${abs(delta):,.2f}"` for revenue, `f"+{delta*100:.1f}%"` / `f"-{abs(delta)*100:.1f}%"` for percentage KPIs
  - [ ] `render_freshness(last_recorded_at: datetime | None) -> None` — if `None`, renders nothing; if `< 5 min` ago, renders `st.caption("Updated just now")`; if `5–15 min` ago, renders `st.markdown(":orange[⚠ Updated Nm ago]")`; if `> 15 min` ago, renders `st.markdown(":red[⚠ Updated Nm ago]")`
  - [ ] `render_kpi_strip(session, account_id: str) -> None` — orchestrates the full render: calls `build_kpi_cards()`, calls `get_kpi_freshness()`, creates `st.columns(5)`, renders each card in its column using `st.metric()` + `render_sparkline()` + `render_freshness()`
  - [ ] Delta color override: `st.metric` native delta coloring is used — positive delta renders green (emerald), negative renders red (rose). For amber (at-threshold) override, use `st.markdown` with `:orange[delta text]` inline below the metric when `prior_value` exists and `|delta| < 0.01` (no meaningful change — neutral state)

- [ ] Task 4: Integrate KPI strip into `dashboard/pages/overview.py`
  - [ ] Import `render_kpi_strip` from `dashboard.components.kpi_strip`
  - [ ] Call `render_kpi_strip(session, account_id)` immediately after the top bar and alert zone blocks (established by Story 6.2) and before the agent pipeline panel / video table block (Story 6.4)
  - [ ] Wrap the call in `try/except Exception as e: st.error(f"KPI strip failed to load: {e}")` to prevent a single KPI failure from crashing the entire page
  - [ ] Add `st.divider()` above and below the KPI strip for visual separation

- [ ] Task 5: Write tests in `tests/unit/dashboard/`
  - [ ] `tests/unit/dashboard/test_queries_kpi.py`:
    - `test_get_kpi_revenue_returns_zero_when_no_data` — empty DB → `0.0`
    - `test_get_kpi_revenue_sums_clicks_times_orders_over_view_count` — insert 2 VideoMetric rows, assert formula result matches expected value
    - `test_get_kpi_retention_3s_returns_none_when_no_data` — empty DB → `None`
    - `test_get_kpi_retention_3s_averages_window` — two rows with `retention_3s=0.6` and `0.8` → `0.7`
    - `test_get_kpi_retention_3s_excludes_rows_outside_window` — one row within 7 days, one at day 9 → only within-window row counted
    - `test_get_kpi_retention_15s_returns_average` — mirrors 3s test
    - `test_get_kpi_affiliate_ctr_computes_ratio` — 50 clicks / 1000 views → `0.05`
    - `test_get_kpi_affiliate_ctr_returns_none_when_no_data` — empty DB → `None`
    - `test_get_kpi_fyp_reach_rate_averages_pct` — two rows at `0.4` and `0.6` → `0.5`
    - `test_get_kpi_sparkline_returns_7_elements` — insert rows spread over 7 days → returned list has exactly 7 elements
    - `test_get_kpi_sparkline_fills_missing_days_with_zero` — only 3 of 7 days have data → missing days are `0.0`
    - `test_get_kpi_freshness_returns_max_recorded_at` — two VideoMetric rows → returns the later `recorded_at`
    - `test_get_kpi_freshness_returns_none_when_empty` — empty DB → `None`
  - [ ] `tests/unit/dashboard/test_kpi_strip.py`:
    - `test_format_kpi_value_none_returns_dash` — `None` → `"—"`
    - `test_format_kpi_value_revenue` — `1234.5` with `unit="$"` → `"$1,234.50"`
    - `test_format_kpi_value_percentage` — `0.756` with `unit="%"` → `"75.6%"`
    - `test_format_delta_none_returns_empty` — `None` → `""`
    - `test_format_delta_positive_revenue` — `25.0` with `unit="$"` → `"+$25.00"`
    - `test_format_delta_negative_pct` — `-0.05` with `unit="%"` → `"-5.0%"`
    - `test_build_kpi_cards_returns_five_cards` — mock all `get_kpi_*` queries → returns list of length 5
    - `test_build_kpi_cards_computes_delta` — mock current=0.6, prior=0.5 → `KPICard.delta == 0.1`
    - `test_render_freshness_amber_at_7_minutes` — mock `datetime.utcnow`, `last_recorded_at` 7 min ago → `st.markdown` called with `:orange[...]`
    - `test_render_freshness_rose_at_20_minutes` — 20 min ago → `st.markdown` called with `:red[...]`
    - `test_render_freshness_none_renders_nothing` — `None` → no `st.markdown` / `st.caption` calls

## Dev Notes

### Architecture Boundary (MUST NOT VIOLATE)

- `dashboard/` imports ONLY from `tiktok_faceless.db.session` and `tiktok_faceless.db.queries`
- NEVER import from `tiktok_faceless.agents.*`, `tiktok_faceless.clients.*`, `tiktok_faceless.state`, or `tiktok_faceless.graph`
- All queries in Task 1 are read-only — no `session.add()`, `session.commit()`, or `session.delete()` calls
- `PipelineState` is NOT accessible from dashboard code — all KPI data comes from `video_metrics` DB table only

### VideoMetric Columns Used

| KPI | Column(s) | Aggregation |
|---|---|---|
| Revenue | `affiliate_clicks`, `affiliate_orders`, `view_count` | See revenue formula below |
| 3s Retention | `retention_3s` | `AVG` |
| 15s Retention | `retention_15s` | `AVG` |
| Affiliate CTR | `affiliate_clicks`, `view_count` | `SUM(clicks) / MAX(SUM(views), 1)` |
| FYP Reach Rate | `fyp_reach_pct` | `AVG` |
| Freshness | `recorded_at` | `MAX` |

### Revenue Formula

The `video_metrics` table does not have a `commission_per_view` column. Revenue is approximated using the available columns:

```python
# Revenue proxy: affiliate_orders treated as a commission unit
# affiliate_clicks / view_count = CTR
# affiliate_orders / affiliate_clicks = conversion rate
# Summing affiliate_orders gives total attributed conversions (each = ~$1 commission proxy at MVP)
# For a more accurate number, join Products table and multiply by commission_rate

revenue = SUM(VideoMetric.affiliate_orders)
```

A more precise revenue calculation joins `video_metrics` → `videos` → `products` to use the product's `commission_rate`:

```python
# In get_kpi_revenue():
cutoff = datetime.utcnow() - timedelta(days=days)
rows = (
    session.query(
        func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("revenue")
    )
    .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
    .join(Product, (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id))
    .filter(
        VideoMetric.account_id == account_id,
        VideoMetric.recorded_at >= cutoff,
        Video.product_id.isnot(None),
    )
    .first()
)
return float(rows.revenue or 0.0)
```

If the join yields no rows (no products linked yet), fall back to `SUM(affiliate_orders)` as a unit count and return `0.0` — never raise.

### Delta Computation Pattern

Delta for each KPI is: `current_7_day_value - prior_7_day_value`.

Prior window = days 8–14 back from now. Use `recorded_at BETWEEN (now - 14 days) AND (now - 7 days)` exclusive on the right boundary:

```python
now = datetime.utcnow()
current_cutoff = now - timedelta(days=7)
prior_cutoff   = now - timedelta(days=14)

# Current window: recorded_at >= current_cutoff
# Prior window:   recorded_at >= prior_cutoff AND recorded_at < current_cutoff
```

### Sparkline Implementation Pattern

`get_kpi_sparkline()` must return exactly `days` elements (default 7), one per calendar day, oldest first:

```python
def get_kpi_sparkline(
    session: Session,
    account_id: str,
    metric: str,
    days: int = 7,
) -> list[float]:
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # Map metric name to SQLAlchemy column expression
    col_map = {
        "retention_3s":  func.avg(VideoMetric.retention_3s),
        "retention_15s": func.avg(VideoMetric.retention_15s),
        "fyp_reach_pct": func.avg(VideoMetric.fyp_reach_pct),
        "affiliate_ctr": func.sum(VideoMetric.affiliate_clicks) / func.nullif(
            func.sum(VideoMetric.view_count), 0
        ),
        "revenue":       func.sum(VideoMetric.affiliate_orders),
    }
    agg_expr = col_map[metric]

    rows = (
        session.query(
            func.date(VideoMetric.recorded_at).label("day"),
            agg_expr.label("val"),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(func.date(VideoMetric.recorded_at))
        .order_by(func.date(VideoMetric.recorded_at))
        .all()
    )

    # Build day → value dict; fill gaps with 0.0
    day_map: dict[str, float] = {str(row.day): float(row.val or 0.0) for row in rows}
    result: list[float] = []
    for i in range(days):
        day = (cutoff + timedelta(days=i + 1)).date()
        result.append(day_map.get(str(day), 0.0))
    return result
```

### Sparkline Render (Altair)

```python
# In dashboard/components/sparkline.py
import altair as alt
import pandas as pd
import streamlit as st

def render_sparkline(values: list[float], color: str = "#10b981") -> None:
    if not values or all(v == 0.0 for v in values):
        return
    try:
        df = pd.DataFrame({"day": range(len(values)), "value": values})
        chart = (
            alt.Chart(df)
            .mark_line(color=color, strokeWidth=2)
            .encode(
                x=alt.X("day:Q", axis=None),
                y=alt.Y("value:Q", axis=None, scale=alt.Scale(zero=False)),
            )
            .properties(height=60)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.caption("Sparkline unavailable")
```

### KPI Card Thresholds

| KPI | `threshold_ok` | `threshold_warn` | Unit |
|---|---|---|---|
| Revenue | 0.0 (any positive = good) | N/A | `$` |
| 3s Retention | 0.50 (50%) | 0.30 (30%) | `%` |
| 15s Retention | 0.35 (35%) | 0.20 (20%) | `%` |
| Affiliate CTR | 0.03 (3%) | 0.01 (1%) | `%` |
| FYP Reach Rate | 0.40 (40%) | 0.25 (25%) | `%` |

Thresholds are defined as module-level constants in `dashboard/components/kpi_strip.py` — never hardcoded inline. These map to the architecture-level kill thresholds in `config.py` (source of truth for pipeline logic); the dashboard uses its own display-only copies.

Color mapping for `render_sparkline` `color` parameter:
- `current_value >= threshold_ok` → emerald `#10b981`
- `threshold_warn <= current_value < threshold_ok` → amber `#f59e0b`
- `current_value < threshold_warn` → rose `#f43f5e`
- `current_value is None` → zinc `#71717a` (no data)

### `st.metric` Usage Pattern

```python
# In render_kpi_strip(), inside each column:
with col:
    value_str = format_kpi_value(card.value, card.unit)
    delta_str = format_delta(card.delta, card.unit)

    if card.value is None:
        st.metric(label=card.label, value="—", help="No data yet")
    else:
        st.metric(
            label=card.label,
            value=value_str,
            delta=delta_str if delta_str else None,
            delta_color="normal",  # positive = green, negative = red
        )

    # Sparkline rendered immediately below the metric
    render_sparkline(card.sparkline, color=_threshold_color(card))

# Freshness is rendered once below all 5 columns (shared timestamp)
render_freshness(freshness_ts)
```

### `KPICard` Dataclass

```python
from dataclasses import dataclass, field

@dataclass
class KPICard:
    label: str
    value: float | None          # current 7-day aggregate
    prior: float | None          # prior 7-day aggregate (for delta computation)
    sparkline: list[float]       # 7 daily averages, oldest first
    unit: str                    # "$" or "%"
    threshold_ok: float          # above = emerald
    threshold_warn: float        # above = amber, below = rose

    @property
    def delta(self) -> float | None:
        if self.value is None or self.prior is None:
            return None
        return self.value - self.prior
```

### Freshness Timestamp Source

Use `get_kpi_freshness(session, account_id)` → `MAX(VideoMetric.recorded_at)`. This is a single shared timestamp for all 5 KPIs — the most recent analytics poll across any video for the account. Render it once, below all 5 columns, centered via `st.caption`:

```python
# After the st.columns(5) block
freshness_ts = get_kpi_freshness(session, account_id)
render_freshness(freshness_ts)
```

### Account ID Source

`account_id` is loaded from `st.session_state["account_id"]` (set during auth in Story 6.1). `dashboard/pages/overview.py` reads it from session state and passes it down to `render_kpi_strip(session, account_id)`. Never read `account_id` from env directly in dashboard components.

### Empty State (No Data)

When `VideoMetric` has no rows for the account, all `get_kpi_*` functions return `None` or `0.0`. `render_kpi_strip` must handle this gracefully:

```python
# KPICard with value=None renders as:
st.metric(label="3s Retention", value="—", help="No data yet")
# render_sparkline([]) → returns immediately (no chart rendered)
# render_freshness(None) → returns immediately (no timestamp rendered)
```

No `st.error()` or exceptions should propagate to the page for the no-data case.

### Dependencies

- `altair` — already available via `streamlit` transitive dependency; no new `pyproject.toml` entry needed. Verify with `uv run python -c "import altair"` before implementing.
- `pandas` — same as above; transitive via streamlit.
- `streamlit` and `streamlit-autorefresh` — added in Story 6.1.
- `dashboard/components/sparkline.py` — stub file exists from Story 6.1 (`"""Sparkline component — Story 6.3."""`). This story implements it.
- Story 6.2 must be complete before integrating into `overview.py` — the top bar and alert zone blocks must already be rendering so the KPI strip is inserted in the correct position.

### Project Conventions

- Import sort: stdlib → third-party → local (ruff enforced)
- Line length <= 100 chars
- No bare `except Exception` at module top level in query functions — only in `render_sparkline` (UI resilience)
- No function-level imports — all imports at module top
- `datetime.utcnow()` for naive UTC timestamps throughout
- All query functions accept `session: Session` as first arg and `account_id: str` as second — never open a new session internally
- Run `uv run pytest tests/unit/ -q` before marking done
- Run `uv run ruff check tiktok_faceless/db/queries.py dashboard/components/ dashboard/pages/overview.py tests/unit/dashboard/` after implementation

### References

- Epic 6, Story 6.3 spec: `_bmad-output/planning-artifacts/epics.md` (lines 1092–1118)
- Architecture dashboard boundary: `_bmad-output/planning-artifacts/architecture.md` — "Dashboard Boundary" and "Data Architecture"
- DB models: `tiktok_faceless/db/models.py` — `VideoMetric` (columns: `retention_3s`, `retention_15s`, `fyp_reach_pct`, `affiliate_clicks`, `affiliate_orders`, `view_count`, `recorded_at`), `Video` (`product_id`), `Product` (`commission_rate`)
- Query patterns: `tiktok_faceless/db/queries.py` — `get_archetype_scores()` and `get_niche_scores()` as reference for `func.avg()` / `func.sum()` join patterns
- Dependency story spec: `_bmad-output/implementation-artifacts/6-2-status-top-bar-alert-zone.md`
- Sparkline stub: `dashboard/components/sparkline.py`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
