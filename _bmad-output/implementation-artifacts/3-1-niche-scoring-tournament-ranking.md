# Story 3.1: Niche Scoring & Tournament Ranking

Status: review

## Story

As the operator,
I want the system to score all competing niches by affiliate CTR and commission performance during Tournament Phase,
so that the Tournament winner selection is data-driven and auditable — not arbitrary.

## Acceptance Criteria

1. **Given** `phase = "tournament"` and videos posted across multiple niches
   **When** `analytics_node` and `monetization_node` write metrics to `video_metrics`
   **Then** `db/queries.py` can compute a niche score per `account_id` as a weighted combination of avg affiliate CTR, avg 3s retention, and total affiliate orders
   **And** niche scores are returned as a ranked list `[(niche, score), ...]` in descending order

2. **Given** niche scores are computed
   **When** the Orchestrator evaluates Tournament state
   **Then** the leading niche is identifiable as the one with the highest score and ≥ `tournament_min_video_count` videos posted
   **And** niches below the elimination threshold score after ≥ 7 days are flagged as `eliminated = True` in the `products` table

3. **Given** a niche is eliminated
   **When** the Orchestrator routes the next research cycle
   **Then** `get_cached_products` excludes rows where `Product.eliminated == True`
   **And** new product research never surfaces eliminated niches

4. **Given** existing posted videos in an eliminated niche
   **When** elimination is applied
   **Then** video rows and their metrics remain unmodified (no lifecycle state change)
   **And** only future product research is blocked for that niche

## Tasks / Subtasks

- [x] Task 1: Add `eliminated` column to `Product` model + Alembic migration
  - [x] Add `eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)` to `Product` class in `tiktok_faceless/db/models.py`
  - [x] Import `Boolean` from `sqlalchemy` in `db/models.py`
  - [x] Generate new Alembic migration: `uv run alembic revision --autogenerate -m "add_eliminated_to_products"`
  - [x] Verify migration adds `eliminated BOOLEAN NOT NULL DEFAULT FALSE` to `products` table

- [x] Task 2: Add `tournament_min_video_count` and `tournament_elimination_threshold_score` to `AccountConfig`
  - [x] Add `tournament_min_video_count: int = Field(default=3, ge=1)` to `AccountConfig` in `tiktok_faceless/config.py`
  - [x] Add `tournament_elimination_threshold_score: float = Field(default=0.0, ge=0.0)` to `AccountConfig`

- [x] Task 3: Add `get_niche_scores` to `db/queries.py`
  - [x] Add function `get_niche_scores(session, account_id, days=7) -> list[tuple[str, float]]`
  - [x] Query: join `VideoMetric` → `Video` on `video_id == tiktok_video_id`, filter by `account_id` and `recorded_at >= cutoff`
  - [x] Aggregate per niche: `sum(affiliate_clicks)`, `sum(view_count)`, `avg(retention_3s)`, `sum(affiliate_orders)`, `count(distinct video_id)`
  - [x] Compute score in Python (see Dev Notes for formula)
  - [x] Filter niches with fewer than `min_video_count` (default=1) — callers pass threshold as kwarg `min_video_count=1`
  - [x] Return `[(niche, score), ...]` sorted descending by score

- [x] Task 4: Add `flag_eliminated_niches` to `db/queries.py`
  - [x] Add function `flag_eliminated_niches(session, account_id, niche_scores, threshold_score) -> list[str]`
  - [x] For each `(niche, score)` pair where `score <= threshold_score`, set `Product.eliminated = True` for all rows with that `account_id` and `niche`
  - [x] Call `session.commit()` once after all updates
  - [x] Return list of niche names that were newly eliminated

- [x] Task 5: Update `get_cached_products` to filter eliminated products
  - [x] Add `.filter(Product.eliminated == False)` clause to existing query in `get_cached_products` in `db/queries.py`

- [x] Task 6: Tests
  - [x] `tests/unit/db/test_queries.py` — new class `TestGetNicheScores`
  - [x] `tests/unit/db/test_queries.py` — new class `TestFlagEliminatedNiches`
  - [x] `tests/unit/db/test_queries.py` — new class `TestGetCachedProductsExcludesEliminated`

## Dev Notes

### Critical Architecture Rules

- **`orchestrator.py` is the only file that writes `state["phase"]`** — niche scoring in this story lives entirely in `db/queries.py`, not in any agent node
- **Scoring in Python, not SQL** — aggregate raw counts in SQL, compute weighted score in Python. This keeps the formula readable and testable.
- **`eliminated` flag is per-product row** — when a niche is eliminated, ALL Product rows for that `(account_id, niche)` pair are updated. `get_cached_products` then sees zero results for that niche, blocking future research.
- **Append-only analytics** — never update `VideoMetric` rows; the eliminated flag only touches `products`
- **Agent node return pattern** — `get_niche_scores` and `flag_eliminated_niches` are pure DB query helpers. They are not agent nodes. They return values, not state deltas.

### Niche Scoring Formula

Score is a weighted sum of three normalized metrics:

```python
def _compute_niche_score(
    aff_clicks: int,
    view_count: int,
    avg_retention_3s: float,
    total_orders: int,
    max_orders_across_niches: int,
) -> float:
    """
    Weighted niche score in range [0.0, 1.0].

    Weights:
      - 0.40: affiliate CTR (affiliate_clicks / view_count)
      - 0.30: avg 3s retention (already 0.0–1.0)
      - 0.30: normalized commission orders (total_orders / max_orders, 0.0–1.0)

    Returns 0.0 if view_count is 0.
    """
    aff_ctr = aff_clicks / max(view_count, 1)
    retention = max(0.0, min(1.0, avg_retention_3s))
    normalized_orders = total_orders / max(max_orders_across_niches, 1)
    return 0.40 * aff_ctr + 0.30 * retention + 0.30 * normalized_orders
```

The `max_orders_across_niches` is computed in Python over the query results to normalize commission contribution across all niches in the current batch.

### `get_niche_scores` — Full Implementation

Add to `tiktok_faceless/db/queries.py`:

Required additional imports (local, added at function scope like existing pattern in `get_commission_per_view`):
```python
from sqlalchemy import func
from tiktok_faceless.db.models import Video, VideoMetric
```

```python
def get_niche_scores(
    session: Session,
    account_id: str,
    days: int = 7,
    min_video_count: int = 1,
) -> list[tuple[str, float]]:
    """
    Compute a weighted tournament score per niche for the given account.

    Score formula (range 0.0–1.0):
      0.40 * affiliate_ctr + 0.30 * avg_retention_3s + 0.30 * normalized_orders

    Only niches with >= min_video_count distinct posted videos are included.
    Returns list of (niche, score) tuples sorted descending by score.
    Returns empty list if no data exists.
    """
    from sqlalchemy import func

    from tiktok_faceless.db.models import Video, VideoMetric

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

    # Filter by minimum video count
    rows = [r for r in rows if (r.video_count or 0) >= min_video_count]
    if not rows:
        return []

    max_orders = max(int(r.total_orders or 0) for r in rows)

    scored: list[tuple[str, float]] = []
    for row in rows:
        aff_ctr = int(row.total_clicks or 0) / max(int(row.total_views or 0), 1)
        retention = max(0.0, min(1.0, float(row.avg_retention_3s or 0.0)))
        norm_orders = int(row.total_orders or 0) / max(max_orders, 1)
        score = 0.40 * aff_ctr + 0.30 * retention + 0.30 * norm_orders
        scored.append((row.niche, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
```

### `flag_eliminated_niches` — Full Implementation

Add to `tiktok_faceless/db/queries.py`:

```python
def flag_eliminated_niches(
    session: Session,
    account_id: str,
    niche_scores: list[tuple[str, float]],
    threshold_score: float,
) -> list[str]:
    """
    Set Product.eliminated = True for all products in niches scoring <= threshold_score.

    Args:
        session: SQLAlchemy session
        account_id: account scope
        niche_scores: list of (niche, score) from get_niche_scores
        threshold_score: niches at or below this score are eliminated

    Returns list of niche names newly flagged as eliminated.
    """
    eliminated: list[str] = []
    for niche, score in niche_scores:
        if score <= threshold_score:
            (
                session.query(Product)
                .filter_by(account_id=account_id, niche=niche)
                .update({"eliminated": True})
            )
            eliminated.append(niche)
    if eliminated:
        session.commit()
    return eliminated
```

### `get_cached_products` — Updated Filter

Modify the existing function in `db/queries.py` to add one filter clause:

```python
# Before (line ~135 in current queries.py):
rows = (
    session.query(Product)
    .filter(
        Product.account_id == account_id,
        Product.niche == niche,
        Product.cached_at >= cutoff,
    )
    .all()
)

# After (add eliminated filter):
rows = (
    session.query(Product)
    .filter(
        Product.account_id == account_id,
        Product.niche == niche,
        Product.cached_at >= cutoff,
        Product.eliminated == False,  # noqa: E712
    )
    .all()
)
```

### `Product` Model Change — Full Updated Class

In `tiktok_faceless/db/models.py`, add `Boolean` to the sqlalchemy import and add the field:

```python
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String

class Product(Base):
    """Validated product research cache — 24h TTL enforced in application code."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    niche: Mapped[str] = mapped_column(String, nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    commission_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sales_velocity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cached_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

### Alembic Migration

After updating the model, generate the migration:
```bash
uv run alembic revision --autogenerate -m "add_eliminated_to_products"
```

Verify the generated migration file in `tiktok_faceless/db/migrations/versions/` contains:
```python
op.add_column('products', sa.Column('eliminated', sa.Boolean(), nullable=False, server_default='0'))
```

The `server_default='0'` (or `'false'` for PostgreSQL) is critical for zero-downtime on existing rows.

### `AccountConfig` Changes — Fields to Add

In `tiktok_faceless/config.py`, add after `commit_phase_min_videos`:

```python
tournament_min_video_count: int = Field(default=3, ge=1)
tournament_elimination_threshold_score: float = Field(default=0.0, ge=0.0, le=1.0)
```

These fields are not yet read in this story — they are consumed by Story 3.3 (winner detection). Adding them here avoids breaking config changes mid-epic.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/db/models.py` | Add `Boolean` import; add `eliminated` field to `Product` |
| `tiktok_faceless/db/migrations/versions/<rev>_add_eliminated_to_products.py` | New Alembic migration |
| `tiktok_faceless/config.py` | Add `tournament_min_video_count` and `tournament_elimination_threshold_score` to `AccountConfig` |
| `tiktok_faceless/db/queries.py` | Add `get_niche_scores`; add `flag_eliminated_niches`; update `get_cached_products` filter |
| `tests/unit/db/test_queries.py` | Add `TestGetNicheScores`, `TestFlagEliminatedNiches`, `TestGetCachedProductsExcludesEliminated` |

### Do NOT Touch

- `tiktok_faceless/agents/orchestrator.py` — phase transitions are Story 3.3; this story only builds the scoring infrastructure
- `tiktok_faceless/agents/research.py` — no changes needed; `get_cached_products` filter change is transparent to the caller
- `tiktok_faceless/state.py` — no new state fields needed for this story
- `tiktok_faceless/db/models.py` — only `Product` changes; `VideoMetric`, `Video`, `AgentDecision` untouched
- Any existing migration files

### Required Test Cases

#### `TestGetNicheScores` in `tests/unit/db/test_queries.py`

Use the existing in-memory SQLite session fixture (same pattern as `TestGetCommissionTotals`).

```python
class TestGetNicheScores:

    def test_returns_ranked_scores_descending(self, session: Session) -> None:
        """Higher-performing niche appears first in output."""
        now = datetime.utcnow()
        # fitness niche — high CTR
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        # beauty niche — lower CTR
        session.add(Video(
            id="v2", account_id="acc1", niche="beauty",
            lifecycle_state="posted", tiktok_video_id="tiktok-v2", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=50, retention_3s=0.8, affiliate_orders=10,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v2", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=5, retention_3s=0.3, affiliate_orders=1,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")

        assert len(result) == 2
        assert result[0][0] == "fitness"
        assert result[1][0] == "beauty"
        assert result[0][1] > result[1][1]

    def test_returns_empty_list_when_no_data(self, session: Session) -> None:
        """Returns [] when no VideoMetric rows exist for account."""
        result = get_niche_scores(session, account_id="acc1")
        assert result == []

    def test_excludes_metrics_outside_window(self, session: Session) -> None:
        """Metrics older than days= are not scored."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=10),  # outside 7-day window
            view_count=1000, affiliate_clicks=100, retention_3s=0.9, affiliate_orders=20,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")
        assert result == []

    def test_min_video_count_filters_low_sample_niches(self, session: Session) -> None:
        """Niches with fewer than min_video_count distinct videos are excluded."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=500, affiliate_clicks=10, retention_3s=0.5, affiliate_orders=2,
        ))
        session.commit()

        # Requiring 2+ videos — fitness has only 1
        result = get_niche_scores(session, account_id="acc1", min_video_count=2)
        assert result == []

    def test_scores_are_between_0_and_1(self, session: Session) -> None:
        """All returned scores are in [0.0, 1.0]."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1", created_at=now,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_clicks=200, retention_3s=0.95, affiliate_orders=15,
        ))
        session.commit()

        result = get_niche_scores(session, account_id="acc1")
        for _niche, score in result:
            assert 0.0 <= score <= 1.0
```

#### `TestFlagEliminatedNiches` in `tests/unit/db/test_queries.py`

```python
class TestFlagEliminatedNiches:

    def test_flags_low_score_niches(self, session: Session) -> None:
        """Products in niches with score <= threshold are set eliminated=True."""
        session.add(Product(
            id="p1", account_id="acc1", niche="beauty",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        niche_scores = [("beauty", 0.0), ("fitness", 0.8)]
        eliminated = flag_eliminated_niches(session, "acc1", niche_scores, threshold_score=0.1)

        assert "beauty" in eliminated
        assert "fitness" not in eliminated
        product = session.query(Product).filter_by(product_id="prod1").first()
        assert product.eliminated is True

    def test_does_not_flag_above_threshold(self, session: Session) -> None:
        """Products in niches above threshold remain eliminated=False."""
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="X", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.5,
            cached_at=datetime.utcnow(), eliminated=False,
        ))
        session.commit()

        eliminated = flag_eliminated_niches(session, "acc1", [("fitness", 0.5)], threshold_score=0.1)

        assert eliminated == []
        product = session.query(Product).filter_by(product_id="prod1").first()
        assert product.eliminated is False

    def test_returns_empty_list_when_no_eliminations(self, session: Session) -> None:
        """Returns [] when all niches are above threshold."""
        result = flag_eliminated_niches(session, "acc1", [("fitness", 0.9)], threshold_score=0.0)
        assert result == []
```

#### `TestGetCachedProductsExcludesEliminated` in `tests/unit/db/test_queries.py`

```python
class TestGetCachedProductsExcludesEliminated:

    def test_excludes_eliminated_products(self, session: Session) -> None:
        """get_cached_products does not return products where eliminated=True."""
        now = datetime.utcnow()
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="Active Wear", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.8,
            cached_at=now, eliminated=True,
        ))
        session.add(Product(
            id="p2", account_id="acc1", niche="fitness",
            product_id="prod2", product_name="Yoga Mat", product_url="https://y.com",
            commission_rate=0.12, sales_velocity_score=0.7,
            cached_at=now, eliminated=False,
        ))
        session.commit()

        result = get_cached_products(session, account_id="acc1", niche="fitness")

        assert len(result) == 1
        assert result[0].product_id == "prod2"

    def test_returns_all_when_none_eliminated(self, session: Session) -> None:
        """get_cached_products returns all non-expired products if none are eliminated."""
        now = datetime.utcnow()
        session.add(Product(
            id="p1", account_id="acc1", niche="fitness",
            product_id="prod1", product_name="Gym Gloves", product_url="https://x.com",
            commission_rate=0.1, sales_velocity_score=0.6,
            cached_at=now, eliminated=False,
        ))
        session.commit()

        result = get_cached_products(session, account_id="acc1", niche="fitness")
        assert len(result) == 1
```

### Previous Story Learnings (from Stories 2.1–2.6)

- `_MOD = "tiktok_faceless.db.queries"` pattern used at module level in query test files
- Session fixture: in-memory SQLite, created per test via `conftest.py` fixture; look for existing fixture in `tests/unit/db/conftest.py` or `tests/conftest.py`
- All models require `eliminated=False` (or True) now that it's non-nullable — add to ALL Product fixtures in new and existing test classes to avoid integrity errors
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501)
- `session.query(Product).filter_by(...)` uses keyword args for equality; `.filter(Product.eliminated == False)` uses expression syntax — both valid; prefer `.filter_by` for simple equality, expression syntax when mixing
- Alembic migrations must include `server_default` for non-nullable columns added to existing tables

### Architecture Compliance

- `get_niche_scores` and `flag_eliminated_niches` are **DB query helpers only** — no LangGraph integration, no state delta return
- `orchestrator.py` will consume these helpers in Story 3.3 to drive the phase transition decision
- The `eliminated` column is the single source of truth for niche exclusion — no parallel state field needed

### References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 3.1 (line 651)
- Current `queries.py`: `tiktok_faceless/db/queries.py` — `get_commission_totals` pattern to follow
- `Product` model: `tiktok_faceless/db/models.py` — lines 86–99
- `VideoMetric` columns: `tiktok_faceless/db/models.py` — `retention_3s`, `affiliate_clicks`, `affiliate_orders`, `view_count` all exist
- `AccountConfig`: `tiktok_faceless/config.py` — add after `commit_phase_min_videos`
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "orchestrator is sole phase-writer"; "append-only analytics"
- Alembic docs: single migration file per story following existing pattern in `db/migrations/versions/`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None.

### Completion Notes List

- Added `Boolean` import + `eliminated: Mapped[bool]` field to `Product` model
- Generated Alembic migration `c43d77205a57` — adds `eliminated` (with `server_default=sa.text('false')` for PostgreSQL) and backfills missing `product_id` from initial schema gap
- Added `tournament_min_video_count: int = Field(default=3, ge=1)` and `tournament_elimination_threshold_score: float = Field(default=0.0, ge=0.0, le=1.0)` to `AccountConfig`
- Added `get_niche_scores` to `db/queries.py` — weighted score (0.40 CTR clamped to 1.0 + 0.30 retention + 0.30 normalized orders), sorted descending, with `min_video_count` filter
- Added `flag_eliminated_niches` to `db/queries.py` — bulk-updates Product.eliminated=True for low-scoring niches; single commit; returns list of eliminated niche names
- Updated `get_cached_products` — added `Product.eliminated == False` filter; explicit `eliminated=False` in `cache_product` insert path
- 10 new tests: TestGetNicheScores (5), TestFlagEliminatedNiches (3), TestGetCachedProductsExcludesEliminated (2)
- 177 tests passing, ruff + mypy clean

### File List

- `tiktok_faceless/db/models.py` — Boolean import; eliminated field on Product
- `tiktok_faceless/db/migrations/versions/c43d77205a57_add_eliminated_to_products.py` — new migration
- `tiktok_faceless/config.py` — tournament_min_video_count, tournament_elimination_threshold_score fields
- `tiktok_faceless/db/queries.py` — get_niche_scores, flag_eliminated_niches, updated get_cached_products + cache_product
- `tests/unit/db/test_queries.py` — TestGetNicheScores (5), TestFlagEliminatedNiches (3), TestGetCachedProductsExcludesEliminated (2)

- `tiktok_faceless/db/models.py` — add `Boolean` import; add `eliminated: Mapped[bool]` to `Product`
- `tiktok_faceless/db/migrations/versions/<rev>_add_eliminated_to_products.py` — new Alembic migration
- `tiktok_faceless/config.py` — add `tournament_min_video_count` and `tournament_elimination_threshold_score` fields
- `tiktok_faceless/db/queries.py` — add `get_niche_scores`; add `flag_eliminated_niches`; update `get_cached_products`
- `tests/unit/db/test_queries.py` — add `TestGetNicheScores` (5 tests), `TestFlagEliminatedNiches` (3 tests), `TestGetCachedProductsExcludesEliminated` (2 tests)
