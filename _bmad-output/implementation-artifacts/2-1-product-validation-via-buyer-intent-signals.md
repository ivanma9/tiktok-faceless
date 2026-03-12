# Story 2.1: Product Validation via Buyer Intent Signals

Status: ready-for-dev

## Story

As the operator,
I want the Research Agent to validate products using TikTok Shop sales velocity and affiliate signal strength before any script is generated,
so that production effort is never wasted on products without proven buyer demand.

## Acceptance Criteria

1. **Given** a niche and a list of candidate products from TikTok Shop
   **When** `research_node(state)` is called
   **Then** `TikTokAPIClient` polls sales velocity and affiliate signal data for each product
   **And** only products meeting configurable minimum thresholds (sales velocity, commission rate) are marked as validated
   **And** `state["selected_product"]` is set to the highest-scoring validated product
   **And** `state["product_validated"]` is set to `True`

2. **Given** no products in the niche meet the validation thresholds
   **When** `research_node` completes
   **Then** `state["product_validated"]` remains `False`
   **And** the pipeline does not proceed to script generation
   **And** an `AgentError` with `recovery_suggestion` is added to state

3. **Given** a validated product
   **When** the `products` DB table is inspected
   **Then** the product is cached with `cached_at` timestamp, `niche`, `sales_velocity`, `affiliate_commission_rate`
   **And** subsequent research calls within 24h use the cached entry (no redundant API call)

## Tasks / Subtasks

- [x] Task 1: Add `get_validated_products()` to `TikTokAPIClient` (AC: #1) — **DONE** (committed `feat(2.1)`)
  - [x] Add `AffiliateProduct` import to `tiktok_faceless/clients/tiktok.py`
  - [x] Implement method with threshold filtering + descending sort
  - [x] Write 3 unit tests in `tests/unit/clients/test_tiktok.py`
- [ ] Task 2: Add `product_id` column to `Product` DB model + caching queries (AC: #3)
  - [ ] Add `product_id: Mapped[str]` column to `Product` in `tiktok_faceless/db/models.py`
  - [ ] Implement `cache_product()` in `tiktok_faceless/db/queries.py` (upsert by product_id+account_id)
  - [ ] Implement `get_cached_products()` in `tiktok_faceless/db/queries.py` (24h TTL, scoped by account_id+niche)
  - [ ] Write unit tests in `tests/unit/db/test_queries.py` (create file)
- [ ] Task 3: Implement `research_node` in `tiktok_faceless/agents/research.py` (AC: #1, #2, #3)
  - [ ] Check cache first, skip API if fresh products found
  - [ ] Call `get_validated_products()` on cache miss
  - [ ] Cache all fetched products; select highest `sales_velocity_score`
  - [ ] Return `AgentError` (with `recovery_suggestion`) when no products pass thresholds
  - [ ] Return `{"selected_product": ..., "product_validated": True}` on success
  - [ ] Write unit tests in `tests/unit/agents/test_research.py` (create file)

## Dev Notes

### Critical Architecture Rules (from `architecture.md`)

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` directly
- **Never call external APIs from agent code directly** — always through typed client wrapper class
- **All DB access through `db/queries.py`** — agents never touch SQLAlchemy sessions directly
- **`account_id` as first scope parameter** — every DB query and API call is scoped by `account_id`
- **All errors returned as `AgentError` Pydantic model** in `{"errors": [AgentError(...)]}` delta
- **No hardcoded thresholds** — `min_commission_rate` and `min_sales_velocity` come from `AccountConfig` fields (add them if not present, default 0.05 and 0.3)
- **Phase does NOT change here** — `orchestrator.py` is the ONLY file that writes `state["phase"]`

### Key Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/clients/tiktok.py` | ✅ Already modified — `get_validated_products()` added |
| `tiktok_faceless/db/models.py` | Add `product_id` column to `Product` class |
| `tiktok_faceless/db/queries.py` | Add `cache_product()` and `get_cached_products()` |
| `tiktok_faceless/agents/research.py` | Implement `research_node` (currently empty stub) |
| `tiktok_faceless/config.py` | Add `min_commission_rate` and `min_sales_velocity` to `AccountConfig` if missing |
| `tests/unit/db/test_queries.py` | Create with product caching tests |
| `tests/unit/agents/test_research.py` | Create with research_node tests |

### Do NOT Touch

- `tiktok_faceless/state.py` — `PipelineState`, `AgentError` already correct; `selected_product: dict | None` and `product_validated: bool` already present
- `tiktok_faceless/models/shop.py` — `AffiliateProduct` already has all required fields
- Any other agent files — Epic 2 Story 2.1 only touches research pipeline
- `tests/unit/clients/test_tiktok.py` — `TestGetValidatedProducts` already added

### DB Model Change — `Product` table

Current `Product` model (in `db/models.py`) is missing a `product_id` column — it only has an internal `id` UUID primary key. Story 2.1 requires caching by `product_id` for upsert logic.

**Add to `Product` class:**
```python
product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
```

Place it after the `id` primary key column. This is a schema change — for SQLite dev, `init_db()` (which does `CREATE ALL`) will include it automatically. No Alembic migration needed for SQLite dev. In production (PostgreSQL), Alembic migration would be needed, but that's deferred per architecture decision.

### `db/queries.py` — Caching Implementation Pattern

```python
"""
Typed query functions — all scoped by account_id.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Product
from tiktok_faceless.models.shop import AffiliateProduct

_PRODUCT_CACHE_TTL_HOURS = 24


def cache_product(session: Session, account_id: str, product: AffiliateProduct) -> None:
    """Upsert a product row. Key: account_id + product_id."""
    existing = (
        session.query(Product)
        .filter_by(account_id=account_id, product_id=product.product_id)
        .first()
    )
    if existing is not None:
        existing.product_name = product.product_name
        existing.product_url = product.product_url
        existing.commission_rate = product.commission_rate
        existing.sales_velocity_score = product.sales_velocity_score
        existing.cached_at = datetime.utcnow()
    else:
        session.add(
            Product(
                id=str(uuid.uuid4()),
                account_id=account_id,
                niche=product.niche,
                product_id=product.product_id,
                product_name=product.product_name,
                product_url=product.product_url,
                commission_rate=product.commission_rate,
                sales_velocity_score=product.sales_velocity_score,
                cached_at=datetime.utcnow(),
            )
        )
    session.commit()


def get_cached_products(
    session: Session,
    account_id: str,
    niche: str,
    ttl_hours: int = _PRODUCT_CACHE_TTL_HOURS,
) -> list[AffiliateProduct]:
    """Return valid cached products for account+niche within TTL window."""
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
    rows = (
        session.query(Product)
        .filter(
            Product.account_id == account_id,
            Product.niche == niche,
            Product.cached_at >= cutoff,
        )
        .all()
    )
    return [
        AffiliateProduct(
            product_id=row.product_id,
            product_name=row.product_name,
            product_url=row.product_url,
            commission_rate=row.commission_rate,
            sales_velocity_score=row.sales_velocity_score,
            niche=row.niche,
        )
        for row in rows
    ]
```

### `research_node` — Implementation Pattern

```python
"""
Research agent: product validation, comment mining, niche scanning, and decay detection.
Implementation: Story 2.1 — Product Validation via Buyer Intent Signals
"""

from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.queries import cache_product, get_cached_products
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState

_MIN_COMMISSION_RATE = 0.05   # load from AccountConfig in full implementation
_MIN_SALES_VELOCITY = 0.3


def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the committed niche via TikTok Shop buyer intent signals.
    Returns state delta — never full state.
    Cache logic: fresh products (within 24h) skip the API call.
    """
    niche = state.committed_niche
    if not niche:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message="committed_niche is not set",
                    recovery_suggestion="Set committed_niche before calling research_node.",
                )
            ]
        }

    config = load_account_config(state.account_id)

    # Cache check first
    with get_session() as session:
        cached = get_cached_products(session, account_id=state.account_id, niche=niche)
    if cached:
        best = max(cached, key=lambda p: p.sales_velocity_score)
        return {"selected_product": best.model_dump(), "product_validated": True}

    # Live API fetch
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )
    try:
        products = client.get_validated_products(
            account_id=state.account_id,
            niche=niche,
            min_commission_rate=_MIN_COMMISSION_RATE,
            min_sales_velocity=_MIN_SALES_VELOCITY,
        )
    except (TikTokRateLimitError, TikTokAPIError) as e:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type=type(e).__name__,
                    message=str(e),
                    recovery_suggestion="Check rate limits and credentials.",
                )
            ]
        }

    if not products:
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=f"No products in niche '{niche}' met validation thresholds.",
                    recovery_suggestion=f"Try a different niche or lower thresholds. Niche: {niche}.",
                )
            ],
        }

    # Cache and return
    with get_session() as session:
        for p in products:
            cache_product(session, account_id=state.account_id, product=p)

    best = products[0]  # already sorted descending by sales_velocity_score
    return {"selected_product": best.model_dump(), "product_validated": True}
```

### Unit Test Pattern — `tests/unit/agents/test_research.py`

Use `patch()` at the import location (where `research.py` imports from):
- `patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_config)`
- `patch("tiktok_faceless.agents.research.TikTokAPIClient")`
- `patch("tiktok_faceless.agents.research.get_session")` — mock context manager
- `patch("tiktok_faceless.agents.research.get_cached_products", return_value=[])`
- `patch("tiktok_faceless.agents.research.cache_product")`

`get_session()` mock pattern (from Story 1.7 learnings):
```python
mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
```

**Required test cases:**
1. `test_sets_selected_product_and_validated` — happy path, API returns products
2. `test_uses_cache_when_within_ttl` — cache hit → `get_validated_products` NOT called
3. `test_returns_agent_error_when_no_validated_products` — API returns empty list
4. `test_no_committed_niche_returns_error` — `committed_niche=None` guard

### Unit Test Pattern — `tests/unit/db/test_queries.py`

Use in-memory SQLite:
```python
@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()
```

**Required test cases:**
1. `test_cache_writes_product_row`
2. `test_cache_upserts_on_duplicate_product_id`
3. `test_returns_products_within_24h`
4. `test_excludes_products_older_than_24h` (manually expire `cached_at`)
5. `test_scoped_by_account_id`
6. `test_scoped_by_niche`

### Config — Threshold Fields

`AccountConfig` in `config.py` currently does NOT have `min_commission_rate` or `min_sales_velocity`. Add them:
```python
min_commission_rate: float = Field(default=0.05, ge=0.0, le=1.0)
min_sales_velocity: float = Field(default=0.3, ge=0.0, le=1.0)
```
Then use `config.min_commission_rate` and `config.min_sales_velocity` in `research_node` instead of the module-level constants.

### Previous Story Learnings (from Story 1.7)

- Import sort: stdlib → third-party → local (ruff I001)
- Line length ≤ 100 chars (ruff E501)
- `dict[str, Any]` return type on all agent nodes
- Patch at the import location (where the module under test imports from)
- `get_session()` mock needs `__enter__` / `__exit__` set
- `datetime.utcnow()` is deprecated in Python 3.12+ — use `datetime.now(UTC)` in new code (but existing DB model uses `default=datetime.utcnow` — keep consistent; use `utcnow()` for query cutoff calculation to match DB timestamps)

### Git Context

Last commit: `feat(2.1): add get_validated_products to TikTokAPIClient` (Task 1 done)
Test count baseline: 124 tests passing

### Project Structure Notes

- Story 2.1 is the first story in Epic 2 — no Epic 2 prior stories to reference
- `tests/unit/db/test_queries.py` does not yet exist — create it
- `tests/unit/agents/test_research.py` does not yet exist — create it
- All other test files exist and must remain passing

### References

- Architecture patterns: `_bmad-output/planning-artifacts/architecture.md` — Agent Boundary, DB Boundary, State Delta pattern, Error Contract
- Epic 2 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.1 (lines 490–520)
- Previous story learnings: `_bmad-output/implementation-artifacts/1-7-orchestrator-pipeline-wiring-and-crash-recovery.md`
- `AffiliateProduct` model: `tiktok_faceless/models/shop.py`
- `Product` DB model: `tiktok_faceless/db/models.py`
- `get_session` context manager: `tiktok_faceless/db/session.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Task 1 (get_validated_products) already committed before story file was created

### File List

- `tiktok_faceless/clients/tiktok.py` — ✅ modified (Task 1 done)
- `tests/unit/clients/test_tiktok.py` — ✅ modified (Task 1 done)
- `tiktok_faceless/db/models.py` — add `product_id` column
- `tiktok_faceless/db/queries.py` — add `cache_product`, `get_cached_products`
- `tiktok_faceless/config.py` — add `min_commission_rate`, `min_sales_velocity`
- `tiktok_faceless/agents/research.py` — implement `research_node`
- `tests/unit/db/test_queries.py` — create
- `tests/unit/agents/test_research.py` — create
