# Story 4.4: Hook Archetype A/B Performance Analysis

Status: review

## Story

As the operator,
I want the Script Agent to select hook archetypes based on historical performance data,
so that higher-performing hooks are chosen more often while undersampled archetypes still get exploration opportunities.

## Acceptance Criteria

1. **Given** `VideoMetric` rows exist in the DB with `hook_archetype` data
   **When** `script_node` runs
   **Then** it calls `get_archetype_scores(session, account_id=state.account_id)` to retrieve per-archetype composite scores and sample counts
   **And** uses `_select_hook_archetype(archetypes, scores, min_sample_size)` to pick the archetype for the current video

2. **Given** all three archetypes have `video_count >= archetype_min_sample_size`
   **When** `_select_hook_archetype` selects an archetype
   **Then** it uses `random.choices` with weights proportional to composite scores
   **And** higher-scoring archetypes are selected more frequently

3. **Given** an archetype has `video_count < archetype_min_sample_size` (undersampled)
   **When** `_select_hook_archetype` selects an archetype
   **Then** undersampled archetypes receive an `EXPLORATION_BOOST = 3.0` multiplier on their weight
   **And** this ensures undersampled archetypes get disproportionate exploration

4. **Given** `get_archetype_scores` returns empty dict (no DB data yet)
   **When** `_select_hook_archetype` selects an archetype
   **Then** it falls back to uniform random selection across all archetypes

5. **Given** a selected archetype is used
   **When** `script_node` generates the current script
   **Then** `state["hook_archetype"]` is set to the selected archetype
   **And** `state["current_script"]` is the variant matching the selected archetype
   **And** `state["hook_variants"]` contains all three variants (unchanged)

## Tasks / Subtasks

- [ ] Task 1: Add `archetype_min_sample_size` to `AccountConfig`
  - [ ] Add `archetype_min_sample_size: int = Field(default=5, ge=1)` to `AccountConfig` in `config.py` after `minimum_view_threshold`
  - [ ] No env var wiring — Pydantic default only (project convention)

- [ ] Task 2: Add `get_archetype_scores` to `tiktok_faceless/db/queries.py`
  - [ ] Add `get_archetype_scores(session: Session, account_id: str, days: int = 30) -> dict[str, tuple[float, int]]`
  - [ ] Query `VideoMetric` rows where `hook_archetype IS NOT NULL` and `recorded_at >= now - timedelta(days=days)` and `account_id = account_id`
  - [ ] Group by `hook_archetype`, compute `avg_retention_3s`, `avg_retention_15s`, `avg_aff_ctr` per group
  - [ ] Composite score: `0.50 * avg_retention_3s + 0.30 * avg_retention_15s + 0.20 * avg_aff_ctr`
  - [ ] Return `{archetype: (composite_score, video_count)}` dict
  - [ ] Return `{}` if no rows match

- [ ] Task 3: Add `_select_hook_archetype` helper and update `script_node` in `tiktok_faceless/agents/script.py`
  - [ ] Add `EXPLORATION_BOOST: float = 3.0` module-level constant after `THREE_HOOK_ARCHETYPES`
  - [ ] Add `import random` to stdlib imports
  - [ ] Add `from tiktok_faceless.config import load_account_config` import (if not already present)
  - [ ] Add `from tiktok_faceless.db.session import get_session` import
  - [ ] Add `from tiktok_faceless.db.queries import get_archetype_scores` import
  - [ ] Implement `_select_hook_archetype(archetypes: list[str], scores: dict[str, tuple[float, int]], min_sample_size: int) -> str`
  - [ ] In `script_node`: open `with get_session() as session:`, call `get_archetype_scores`, call `_select_hook_archetype`, use selected archetype to pick current_script from variants

- [ ] Task 4: Add tests
  - [ ] Add `TestGetArchetypeScores` to `tests/unit/db/test_queries.py` (5 tests)
  - [ ] Add `TestArchetypeSelection` to `tests/unit/agents/test_script.py` (8 tests)

## Dev Notes

### `get_archetype_scores` Implementation

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import func

def get_archetype_scores(
    session: Session,
    account_id: str,
    days: int = 30,
) -> dict[str, tuple[float, int]]:
    """Return composite hook archetype scores from recent VideoMetric rows.

    Returns:
        Dict mapping archetype name → (composite_score, video_count).
        Empty dict if no data.
    """
    cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rows = (
        session.query(
            VideoMetric.hook_archetype,
            func.avg(VideoMetric.retention_3s).label("avg_ret3"),
            func.avg(VideoMetric.retention_15s).label("avg_ret15"),
            func.avg(VideoMetric.affiliate_clicks / func.nullif(VideoMetric.view_count, 0)).label("avg_ctr"),
            func.count(VideoMetric.id).label("cnt"),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.hook_archetype.isnot(None),
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(VideoMetric.hook_archetype)
        .all()
    )
    result: dict[str, tuple[float, int]] = {}
    for row in rows:
        avg_ret3 = row.avg_ret3 or 0.0
        avg_ret15 = row.avg_ret15 or 0.0
        avg_ctr = row.avg_ctr or 0.0
        score = 0.50 * avg_ret3 + 0.30 * avg_ret15 + 0.20 * avg_ctr
        result[row.hook_archetype] = (score, int(row.cnt))
    return result
```

**Note**: `VideoMetric` must have `hook_archetype` column. Check `db/models.py` — if missing, it must be added. Also verify `retention_15s` column exists (it does per Story 4.1). Also verify `id` column exists on `VideoMetric` for count.

### `_select_hook_archetype` Implementation

```python
EXPLORATION_BOOST: float = 3.0


def _select_hook_archetype(
    archetypes: list[str],
    scores: dict[str, tuple[float, int]],
    min_sample_size: int,
) -> str:
    """Select hook archetype using weighted random selection.

    Undersampled archetypes (video_count < min_sample_size) receive
    EXPLORATION_BOOST multiplier to ensure sufficient data collection.
    Falls back to uniform random if scores is empty.
    """
    if not scores:
        return random.choice(archetypes)

    weights: list[float] = []
    for archetype in archetypes:
        if archetype in scores:
            composite_score, video_count = scores[archetype]
            weight = max(0.01, composite_score)  # floor to avoid zero weight
            if video_count < min_sample_size:
                weight *= EXPLORATION_BOOST
        else:
            # Not in scores → definitely undersampled → boost
            weight = EXPLORATION_BOOST
        weights.append(weight)

    return random.choices(archetypes, weights=weights, k=1)[0]
```

### Updated `script_node` Logic

In `script_node`, after generating `variants`, add archetype selection before building the return dict:

```python
# Archetype performance-based selection
config = load_account_config(state.account_id)
with get_session() as session:
    archetype_scores = get_archetype_scores(session, account_id=state.account_id)

selected_archetype = _select_hook_archetype(
    THREE_HOOK_ARCHETYPES,
    archetype_scores,
    config.archetype_min_sample_size,
)

# Find the variant matching selected archetype; fallback to first variant
selected_variant = next(
    (v for v in variants if v["archetype"] == selected_archetype),
    variants[0],
)

return {
    "current_script": selected_variant["script"],
    "hook_archetype": selected_variant["archetype"],
    "hook_variants": variants,
}
```

### Import Block for `script.py`

```python
import random
from typing import Any

from tiktok_faceless.clients.openai import OpenAIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.queries import get_archetype_scores
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState
```

### `VideoMetric.hook_archetype` Column

Check `tiktok_faceless/db/models.py`. If `hook_archetype: Mapped[str | None]` does not exist on `VideoMetric`, it must be added with `mapped_column(String(64), nullable=True, default=None)`. The analytics_node currently sets `affiliate_clicks=0` and `affiliate_orders=0` in VideoMetric inserts — `hook_archetype` would similarly be populated by the script agent or publishing agent when the video is first created. For now, queries handle `NULL` via `.isnot(None)` filter.

### New `AccountConfig` Field

Add to `tiktok_faceless/config.py` after `minimum_view_threshold`:

```python
archetype_min_sample_size: int = Field(default=5, ge=1)
```

### Test Helpers for `test_queries.py`

```python
class TestGetArchetypeScores:
    def _make_session_with_rows(self, rows):
        """rows: list of (hook_archetype, avg_ret3, avg_ret15, avg_ctr, cnt)"""
        mock_sess = MagicMock()
        mock_row_objects = []
        for archetype, r3, r15, ctr, cnt in rows:
            r = MagicMock()
            r.hook_archetype = archetype
            r.avg_ret3 = r3
            r.avg_ret15 = r15
            r.avg_ctr = ctr
            r.cnt = cnt
            mock_row_objects.append(r)
        (
            mock_sess.query.return_value
            .filter.return_value
            .group_by.return_value
            .all.return_value
        ) = mock_row_objects
        return mock_sess

    def test_returns_empty_dict_when_no_rows(self): ...
    def test_single_archetype_score_computed_correctly(self): ...
    def test_all_three_archetypes_returned(self): ...
    def test_null_avg_ctr_treated_as_zero(self): ...
    def test_video_count_in_result(self): ...
```

### Test Helpers for `test_script.py`

```python
_MOD = "tiktok_faceless.agents.script"

class TestArchetypeSelection:
    def test_empty_scores_returns_random_archetype(self): ...
    def test_undersampled_archetype_gets_boost(self): ...
    def test_all_sampled_uses_score_weights(self): ...
    def test_unknown_archetype_treated_as_undersampled(self): ...
    def test_script_node_returns_selected_archetype(self): ...
    def test_script_node_fallback_to_first_variant_if_selected_missing(self): ...
    def test_script_node_calls_get_archetype_scores(self): ...
    def test_zero_score_floor_prevents_zero_weight(self): ...
```

For `script_node` tests, patch: `load_account_config`, `get_session`, `get_archetype_scores`, `_select_hook_archetype` (or `random.choices`), and `OpenAIClient`.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/config.py` | Add `archetype_min_sample_size` field |
| `tiktok_faceless/db/models.py` | Add `hook_archetype` to `VideoMetric` if missing |
| `tiktok_faceless/db/queries.py` | Add `get_archetype_scores` function |
| `tiktok_faceless/agents/script.py` | Add `_select_hook_archetype`, update `script_node` |
| `tests/unit/db/test_queries.py` | Add `TestGetArchetypeScores` (5 tests) |
| `tests/unit/agents/test_script.py` | Add `TestArchetypeSelection` (8 tests) |

### Do NOT Touch

- `tiktok_faceless/agents/analytics.py` — no changes needed
- `tiktok_faceless/state.py` — `hook_archetype` field already exists
- Any other agent files

### Previous Story Learnings (Stories 4.1–4.3)

- `_MOD = "tiktok_faceless.agents.script"` — define at module level in test file
- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- Pydantic defaults only — no env var wiring for threshold/window fields
- Agent nodes return state delta dict only — never `return state`
- `uv run pytest tests/unit/ -q` to verify no regressions
- Naive UTC datetimes: `datetime.now(tz=timezone.utc).replace(tzinfo=None)`
- Non-fatal side effects: swallow with `except Exception: pass  # noqa: BLE001`
- `session.add.call_args[0][0]` to get object passed to `session.add`

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 4.4
- Previous story: `_bmad-output/implementation-artifacts/4-3-shadowban-fyp-reach-monitoring.md`
- `script.py` current impl: `tiktok_faceless/agents/script.py`
- `queries.py` current impl: `tiktok_faceless/db/queries.py`
- `VideoMetric` model: `tiktok_faceless/db/models.py`
- `AccountConfig`: `tiktok_faceless/config.py`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
