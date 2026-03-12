# Epic 2: Intelligent Research & Content Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement all 6 stories of Epic 2 — demand-validated product research, comment mining for buyer language, multi-niche parallel scanning, hook-variant script generation, commission decay detection, and commission tracking.

**Architecture:** Each story extends the `research_node` in `tiktok_faceless/agents/research.py` and the `TikTokAPIClient` in `tiktok_faceless/clients/tiktok.py`. Stories 2.1–2.3 gate product validation before script generation. Story 2.4 upgrades `script_node` to 3-variant hook generation. Stories 2.5–2.6 extend `monetization_node` and add DB queries.

**Tech Stack:** Python 3.12, LangGraph (state delta pattern), SQLAlchemy 2.0, Pydantic v2, tenacity retries, unittest.mock for tests.

---

## Story 2.1: Product Validation via Buyer Intent Signals

### Task 1: Add `get_validated_products()` to `TikTokAPIClient`

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `tests/unit/clients/test_tiktok.py`:

```python
class TestGetValidatedProducts:
    def test_returns_list_of_affiliate_products(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "products": [
                    {
                        "product_id": "p1",
                        "product_name": "Widget Pro",
                        "product_url": "https://shop.tiktok.com/p1",
                        "commission_rate": 0.15,
                        "sales_velocity_score": 0.8,
                    }
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            results = client.get_validated_products(
                account_id="acc1", niche="health", min_commission_rate=0.05, min_sales_velocity=0.3
            )
        assert len(results) == 1
        assert results[0].product_id == "p1"
        assert results[0].commission_rate == 0.15
        assert results[0].niche == "health"

    def test_filters_below_threshold_products(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "products": [
                    {
                        "product_id": "p_low",
                        "product_name": "Cheap Thing",
                        "product_url": "https://shop.tiktok.com/p_low",
                        "commission_rate": 0.01,  # below threshold
                        "sales_velocity_score": 0.1,  # below threshold
                    }
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            results = client.get_validated_products(
                account_id="acc1", niche="health", min_commission_rate=0.05, min_sales_velocity=0.3
            )
        assert len(results) == 0

    def test_raises_rate_limit_error_on_429(self) -> None:
        from tiktok_faceless.clients import TikTokRateLimitError
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(TikTokRateLimitError):
                client.get_validated_products(
                    account_id="acc1", niche="health", min_commission_rate=0.05, min_sales_velocity=0.3
                )
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ivanma/Desktop/agents/tiktok-faceless
uv run pytest tests/unit/clients/test_tiktok.py::TestGetValidatedProducts -v
```
Expected: AttributeError — `get_validated_products` does not exist yet.

**Step 3: Implement `get_validated_products` in `tiktok_faceless/clients/tiktok.py`**

Add this method to the `TikTokAPIClient` class (after `generate_affiliate_link`):

```python
@api_retry
def get_validated_products(
    self,
    account_id: str,
    niche: str,
    min_commission_rate: float = 0.05,
    min_sales_velocity: float = 0.3,
) -> list[AffiliateProduct]:
    """
    Search TikTok Shop for affiliate products in the given niche.

    Filters by min_commission_rate and min_sales_velocity before returning.
    Returns list sorted by sales_velocity_score descending.
    """
    self._bucket.consume()
    response = self._http.post(
        "/v2/tiktok_shop/affiliate/products/search/",
        json={"niche": niche, "open_id": self._open_id},
    )
    self._handle_response(response)
    raw_products = response.json().get("data", {}).get("products", [])
    results: list[AffiliateProduct] = []
    for p in raw_products:
        commission_rate = float(p.get("commission_rate", 0.0))
        sales_velocity = float(p.get("sales_velocity_score", 0.0))
        if commission_rate >= min_commission_rate and sales_velocity >= min_sales_velocity:
            results.append(
                AffiliateProduct(
                    product_id=str(p["product_id"]),
                    product_name=str(p["product_name"]),
                    product_url=str(p["product_url"]),
                    commission_rate=commission_rate,
                    sales_velocity_score=sales_velocity,
                    niche=niche,
                )
            )
    results.sort(key=lambda x: x.sales_velocity_score, reverse=True)
    return results
```

Also add the import for `AffiliateProduct` at the top of `tiktok_faceless/clients/tiktok.py`:
```python
from tiktok_faceless.models.shop import AffiliateProduct
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/clients/test_tiktok.py::TestGetValidatedProducts -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "feat(2.1): add get_validated_products to TikTokAPIClient"
```

---

### Task 2: Add product caching helpers to `db/queries.py`

**Files:**
- Modify: `tiktok_faceless/db/queries.py`
- Test: `tests/unit/db/test_queries.py` (create if it doesn't exist)

**Step 1: Write the failing tests**

Create `tests/unit/db/test_queries.py`:

```python
"""Tests for tiktok_faceless/db/queries.py"""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Base, Product
from tiktok_faceless.db.queries import (
    cache_product,
    get_cached_products,
)
from tiktok_faceless.models.shop import AffiliateProduct


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def _make_product(niche: str = "health", score: float = 0.8) -> AffiliateProduct:
    return AffiliateProduct(
        product_id=str(uuid.uuid4()),
        product_name="Widget",
        product_url="https://shop.tiktok.com/w",
        commission_rate=0.15,
        sales_velocity_score=score,
        niche=niche,
    )


class TestCacheProduct:
    def test_cache_writes_product_row(self, session) -> None:
        p = _make_product()
        cache_product(session, account_id="acc1", product=p)
        row = session.query(Product).filter_by(account_id="acc1").first()
        assert row is not None
        assert row.product_id == p.product_id
        assert row.niche == p.niche

    def test_cache_upserts_on_duplicate_product_id(self, session) -> None:
        p = _make_product()
        cache_product(session, account_id="acc1", product=p)
        cache_product(session, account_id="acc1", product=p)  # second upsert
        count = session.query(Product).filter_by(account_id="acc1").count()
        assert count == 1


class TestGetCachedProducts:
    def test_returns_products_within_24h(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 1
        assert results[0].product_id == p.product_id

    def test_excludes_products_older_than_24h(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        # Manually expire the cached_at timestamp
        row = session.query(Product).first()
        row.cached_at = datetime.utcnow() - timedelta(hours=25)
        session.commit()
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 0

    def test_scoped_by_account_id(self, session) -> None:
        p = _make_product(niche="health")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc2", niche="health")
        assert len(results) == 0

    def test_scoped_by_niche(self, session) -> None:
        p = _make_product(niche="fitness")
        cache_product(session, account_id="acc1", product=p)
        results = get_cached_products(session, account_id="acc1", niche="health")
        assert len(results) == 0
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/db/test_queries.py -v
```
Expected: ImportError — `cache_product` and `get_cached_products` not defined.

**Step 3: Implement query functions in `tiktok_faceless/db/queries.py`**

```python
"""
Typed query functions — all scoped by account_id.

Implementation: Story 1.2 — Core State & Database Models
Implementation: Story 2.1 — Product caching (cache_product, get_cached_products)
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Product
from tiktok_faceless.models.shop import AffiliateProduct

_PRODUCT_CACHE_TTL_HOURS = 24


def cache_product(session: Session, account_id: str, product: AffiliateProduct) -> None:
    """Insert or update a product row. Uses product_id as upsert key."""
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
    """Return cached products for account+niche still within TTL window."""
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

Also, `db/models.py` `Product` table is missing a `product_id` column (currently only has `id`). Add it:

```python
# In Product class in tiktok_faceless/db/models.py, add:
product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/db/test_queries.py -v
```
Expected: PASS (6 tests).

**Step 5: Commit**

```bash
git add tiktok_faceless/db/queries.py tiktok_faceless/db/models.py tests/unit/db/test_queries.py
git commit -m "feat(2.1): add product caching queries and product_id column"
```

---

### Task 3: Implement `research_node` for Story 2.1

**Files:**
- Modify: `tiktok_faceless/agents/research.py`
- Test: `tests/unit/agents/test_research.py` (create)

**Step 1: Write the failing tests**

Create `tests/unit/agents/test_research.py`:

```python
"""Tests for tiktok_faceless/agents/research.py — research_node (Story 2.1)."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.research import research_node
from tiktok_faceless.models.shop import AffiliateProduct
from tiktok_faceless.state import AgentError, PipelineState

_PRODUCT = AffiliateProduct(
    product_id="p1",
    product_name="Widget Pro",
    product_url="https://shop.tiktok.com/p1",
    commission_rate=0.15,
    sales_velocity_score=0.8,
    niche="health",
)

_STATE = PipelineState(
    account_id="acc1",
    phase="commit",
    committed_niche="health",
)


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.tiktok_access_token = "tok"
    cfg.tiktok_open_id = "oid"
    cfg.niche_pool = ["health", "fitness"]
    return cfg


class TestResearchNodeSuccess:
    def test_sets_selected_product_and_validated(self) -> None:
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"] is not None
        assert result["selected_product"]["product_id"] == "p1"
        assert "errors" not in result

    def test_uses_cache_when_within_ttl(self) -> None:
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(_STATE)

        # API should NOT be called when cache hit
        mock_client.get_validated_products.assert_not_called()
        assert result["product_validated"] is True


class TestResearchNodeNoProducts:
    def test_returns_agent_error_when_no_validated_products(self) -> None:
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = []
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(_STATE)

        assert result.get("product_validated") is False or "product_validated" not in result
        assert "errors" in result
        errors = result["errors"]
        assert len(errors) == 1
        assert isinstance(errors[0], AgentError)
        assert errors[0].agent == "research"
        assert errors[0].recovery_suggestion is not None
        assert "selected_product" not in result or result.get("selected_product") is None

    def test_no_committed_niche_returns_error(self) -> None:
        state = PipelineState(account_id="acc1", phase="commit", committed_niche=None)
        with patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()):
            result = research_node(state)
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingNiche"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/agents/test_research.py -v
```
Expected: ImportError — `research_node` not implemented.

**Step 3: Implement `research_node` in `tiktok_faceless/agents/research.py`**

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

_MIN_COMMISSION_RATE = 0.05
_MIN_SALES_VELOCITY = 0.3


def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the committed niche via TikTok Shop buyer intent signals.

    Returns state delta with selected_product + product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.

    Cache logic: products fetched within 24h are reused — no redundant API calls.
    """
    niche = state.committed_niche
    if not niche:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message="committed_niche is not set — cannot validate products without a target niche",
                    recovery_suggestion="Set committed_niche in state before calling research_node.",
                )
            ]
        }

    config = load_account_config(state.account_id)

    # --- Cache check: skip API if fresh products exist ---
    with get_session() as session:
        cached = get_cached_products(session, account_id=state.account_id, niche=niche)

    if cached:
        best = max(cached, key=lambda p: p.sales_velocity_score)
        return {
            "selected_product": best.model_dump(),
            "product_validated": True,
        }

    # --- Live API fetch ---
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
                    recovery_suggestion="TikTok API error during product search. Check rate limits and credentials.",
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
                    message=f"No products in niche '{niche}' met the validation thresholds "
                            f"(min_commission={_MIN_COMMISSION_RATE}, min_velocity={_MIN_SALES_VELOCITY})",
                    recovery_suggestion=(
                        f"Try a different niche or lower the thresholds. "
                        f"Current niche: {niche}."
                    ),
                )
            ],
        }

    # --- Cache results ---
    with get_session() as session:
        for product in products:
            cache_product(session, account_id=state.account_id, product=product)

    best = products[0]  # already sorted by sales_velocity_score descending
    return {
        "selected_product": best.model_dump(),
        "product_validated": True,
    }
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/agents/test_research.py -v
```
Expected: PASS (5 tests).

**Step 5: Run the full test suite**

```bash
uv run pytest --tb=short
```
Expected: All existing tests still pass + 5 new ones.

**Step 6: Lint and type-check**

```bash
uv run ruff check . && uv run mypy .
```
Expected: No errors.

**Step 7: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "feat(2.1): implement research_node with product validation and 24h caching"
```

---

## Story 2.2: Comment Mining for Buyer Language

### Task 4: Add `get_video_comments()` to `TikTokAPIClient`

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `tests/unit/clients/test_tiktok.py`:

```python
class TestGetVideoComments:
    def test_returns_list_of_comment_texts(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "comments": [
                    {"text": "Where can I get this?"},
                    {"text": "Does it really work?"},
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            comments = client.get_video_comments(video_id="vid123", max_count=20)
        assert "Where can I get this?" in comments
        assert len(comments) == 2

    def test_returns_empty_list_when_no_comments(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"comments": []}}
        with patch.object(client._http, "post", return_value=mock_response):
            comments = client.get_video_comments(video_id="vid123", max_count=20)
        assert comments == []
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/clients/test_tiktok.py::TestGetVideoComments -v
```
Expected: AttributeError.

**Step 3: Implement `get_video_comments` in `tiktok_faceless/clients/tiktok.py`**

```python
@api_retry
def get_video_comments(self, video_id: str, max_count: int = 20) -> list[str]:
    """Fetch comment text strings from a TikTok video. Returns empty list if none."""
    self._bucket.consume()
    response = self._http.post(
        "/v2/video/comment/list/",
        json={"video_id": video_id, "max_count": max_count},
    )
    self._handle_response(response)
    comments = response.json().get("data", {}).get("comments", [])
    return [str(c.get("text", "")) for c in comments if c.get("text")]
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/clients/test_tiktok.py::TestGetVideoComments -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "feat(2.2): add get_video_comments to TikTokAPIClient"
```

---

### Task 5: Add comment mining to `research_node`

**Files:**
- Modify: `tiktok_faceless/agents/research.py`
- Modify: `tests/unit/agents/test_research.py`

**Step 1: Write the failing tests**

Add to `tests/unit/agents/test_research.py`:

```python
class TestCommentMining:
    def test_buyer_language_added_to_selected_product(self) -> None:
        buyer_phrases = ["where can I get this", "does it actually work"]
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = buyer_phrases
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(_STATE)

        assert "buyer_language" in result["selected_product"]
        assert len(result["selected_product"]["buyer_language"]) > 0

    def test_empty_comments_does_not_halt_pipeline(self) -> None:
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["buyer_language"] == []
        assert "errors" not in result
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/agents/test_research.py::TestCommentMining -v
```
Expected: FAIL — `buyer_language` key not present.

**Step 3: Update `research_node` to mine comments**

After caching products (before the `return` with `selected_product`), add comment mining:

```python
# Mine top affiliate video comments for buyer language
top_video_id = best.product_id  # Use product_id as proxy for top video lookup
try:
    comments = client.get_video_comments(video_id=top_video_id, max_count=20)
except (TikTokRateLimitError, TikTokAPIError):
    comments = []  # Non-fatal: proceed without buyer language

product_dict = best.model_dump()
product_dict["buyer_language"] = comments
return {
    "selected_product": product_dict,
    "product_validated": True,
}
```

Also update the cache-hit path to include empty buyer_language:
```python
product_dict = best.model_dump()
product_dict.setdefault("buyer_language", [])
return {
    "selected_product": product_dict,
    "product_validated": True,
}
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/agents/test_research.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "feat(2.2): mine buyer-language comments from top affiliate videos"
```

---

## Story 2.3: Multi-Niche Product Scanning (Tournament Mode)

### Task 6: Extend `research_node` to handle tournament vs commit phase

**Files:**
- Modify: `tiktok_faceless/agents/research.py`
- Modify: `tests/unit/agents/test_research.py`

**Step 1: Write the failing tests**

Add to `tests/unit/agents/test_research.py`:

```python
class TestTournamentMode:
    def test_tournament_mode_scans_candidate_niches(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=["health", "fitness"],
            committed_niche=None,
        )
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(state)

        # Called once per niche in candidate_niches
        assert mock_client.get_validated_products.call_count == 2
        assert result["product_validated"] is True

    def test_tournament_mode_with_no_candidates_returns_error(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="tournament",
            candidate_niches=[],
            committed_niche=None,
        )
        with patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()):
            result = research_node(state)
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingNiche"

    def test_commit_mode_ignores_candidate_niches(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            candidate_niches=["fitness"],  # should be ignored
            committed_niche="health",
        )
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[]),
            patch("tiktok_faceless.agents.research.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            research_node(state)

        # Only "health" (committed_niche) should be queried — not "fitness"
        call_niches = [
            call.kwargs.get("niche") or call.args[1]
            for call in mock_client.get_validated_products.call_args_list
        ]
        assert "fitness" not in call_niches
        assert "health" in call_niches
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/agents/test_research.py::TestTournamentMode -v
```

**Step 3: Refactor `research_node` to handle both phases**

Replace the current `research_node` implementation with phase-aware logic:

```python
def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Phase-aware product validation node.

    - commit/warmup/scale phase: scans committed_niche only
    - tournament phase: scans all candidate_niches, picks the top product overall
    """
    config = load_account_config(state.account_id)

    # Resolve which niches to scan
    if state.phase == "tournament":
        niches = state.candidate_niches
    else:
        niches = [state.committed_niche] if state.committed_niche else []

    if not niches:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message="No niches to scan. Set committed_niche (commit phase) or candidate_niches (tournament phase).",
                    recovery_suggestion="Populate committed_niche or candidate_niches in state.",
                )
            ]
        }

    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    all_products = []
    for niche in niches:
        # Cache check per niche
        with get_session() as session:
            cached = get_cached_products(session, account_id=state.account_id, niche=niche)

        if cached:
            all_products.extend(cached)
            continue

        # Live API fetch
        try:
            fetched = client.get_validated_products(
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
                        recovery_suggestion="TikTok API error during product search. Check rate limits and credentials.",
                    )
                ]
            }

        if fetched:
            with get_session() as session:
                for p in fetched:
                    cache_product(session, account_id=state.account_id, product=p)
            all_products.extend(fetched)

    if not all_products:
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=f"No products in niches {niches} met validation thresholds.",
                    recovery_suggestion="Try different niches or lower thresholds.",
                )
            ],
        }

    # Pick top product by sales velocity
    best = max(all_products, key=lambda p: p.sales_velocity_score)

    # Mine buyer-language comments (non-fatal)
    try:
        comments = client.get_video_comments(video_id=best.product_id, max_count=20)
    except (TikTokRateLimitError, TikTokAPIError):
        comments = []

    product_dict = best.model_dump()
    product_dict["buyer_language"] = comments
    return {
        "selected_product": product_dict,
        "product_validated": True,
    }
```

**Step 4: Run all research tests**

```bash
uv run pytest tests/unit/agents/test_research.py -v
```
Expected: All PASS.

**Step 5: Run full suite + lint**

```bash
uv run pytest --tb=short && uv run ruff check . && uv run mypy .
```
Expected: All clean.

**Step 6: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "feat(2.3): tournament multi-niche scanning with phase-aware research_node"
```

---

## Story 2.4: Full Script Generation with Hook Archetypes & Persona

### Task 7: Upgrade `script_node` to generate 3 hook variants

**Files:**
- Modify: `tiktok_faceless/agents/script.py`
- Modify: `tests/unit/agents/test_script.py`

**Step 1: Write the failing tests**

Add to `tests/unit/agents/test_script.py`:

```python
_PRODUCT_WITH_BUYER_LANGUAGE = {
    "product_id": "p1",
    "product_name": "Widget Pro",
    "product_url": "https://example.com/widget",
    "commission_rate": 0.15,
    "niche": "health",
    "sales_velocity_score": 0.8,
    "buyer_language": ["where can I get this", "does it work"],
}


class TestScriptNodeHookVariants:
    def test_generates_all_three_hook_archetypes(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)

        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            call_count = 0
            def side_effect(prompt):
                nonlocal call_count
                call_count += 1
                return f"Script variant {call_count}"
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = side_effect
            mock_llm_cls.return_value = mock_llm

            result = script_node(state)

        assert mock_llm.generate_script.call_count == 3
        assert "current_script" in result
        assert "hook_archetype" in result
        assert "hook_variants" in result
        assert len(result["hook_variants"]) == 3

    def test_buyer_language_included_in_prompts(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)

        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Some script"
            mock_llm_cls.return_value = mock_llm

            script_node(state)

        # Verify buyer language phrases appear in at least one prompt
        all_prompts = " ".join(
            call.kwargs.get("prompt") or call.args[0]
            for call in mock_llm.generate_script.call_args_list
        )
        assert "where can I get this" in all_prompts
```

Also add `hook_variants` to `PipelineState` in `state.py`:
```python
hook_variants: list[dict] = Field(default_factory=list)
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/agents/test_script.py::TestScriptNodeHookVariants -v
```

**Step 3: Update `script_node` to generate 3 variants**

Replace `_build_script_prompt` and `script_node` in `tiktok_faceless/agents/script.py`:

```python
THREE_HOOK_ARCHETYPES: list[str] = ["curiosity_gap", "social_proof", "controversy"]


def _build_script_prompt(
    product: dict[str, Any],
    hook_archetype: str,
    buyer_language: list[str] | None = None,
) -> str:
    buyer_section = ""
    if buyer_language:
        phrases = ", ".join(f'"{p}"' for p in buyer_language[:3])
        buyer_section = f"\nBuyer phrases to incorporate: {phrases}"
    return (
        f"You are a viral TikTok creator. Generate a short (<60s) video script "
        f"for a {hook_archetype.replace('_', ' ')} style hook.\n\n"
        f"Product: {product.get('product_name', 'Unknown Product')}\n"
        f"Niche: {product.get('niche', 'general')}\n"
        f"URL: {product.get('product_url', '')}\n"
        f"Commission: {product.get('commission_rate', 0):.0%}\n"
        f"{buyer_section}\n"
        f"Script (60 words max, no hashtags, end with clear CTA):"
    )


def script_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate 3 hook variant scripts for the selected product.

    Returns state delta with current_script (first variant), hook_archetype,
    and hook_variants (all 3) on success. Fails on missing product or LLM error.
    """
    if state.selected_product is None:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="MissingProduct",
                    message="selected_product is None — cannot generate script without a product",
                )
            ]
        }

    config = load_account_config(state.account_id)
    buyer_language: list[str] = state.selected_product.get("buyer_language", [])

    try:
        llm = LLMClient(api_key=config.anthropic_api_key)
        variants = []
        for archetype in THREE_HOOK_ARCHETYPES:
            prompt = _build_script_prompt(state.selected_product, archetype, buyer_language)
            text = llm.generate_script(prompt=prompt)
            if not text or not text.strip():
                raise LLMError(f"LLM returned empty script for archetype '{archetype}'")
            variants.append({"archetype": archetype, "script": text.strip()})
    except LLMError as e:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="LLMError",
                    message=str(e),
                    recovery_suggestion="LLM API error during script generation. Check API key and quota.",
                )
            ]
        }

    selected = variants[0]
    return {
        "current_script": selected["script"],
        "hook_archetype": selected["archetype"],
        "hook_variants": variants,
    }
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/agents/test_script.py -v
```
Expected: All PASS.

**Step 5: Run full suite + lint**

```bash
uv run pytest --tb=short && uv run ruff check . && uv run mypy .
```

**Step 6: Commit**

```bash
git add tiktok_faceless/agents/script.py tiktok_faceless/state.py tests/unit/agents/test_script.py
git commit -m "feat(2.4): generate 3 hook variant scripts with buyer language and persona"
```

---

## Story 2.5: Commission-Per-View Decay Detection

### Task 8: Add decay detection to `research_node`

**Files:**
- Modify: `tiktok_faceless/agents/research.py`
- Modify: `tiktok_faceless/state.py`
- Modify: `tests/unit/agents/test_research.py`

**Step 1: Add `niche_decay_alert` to `PipelineState`**

In `tiktok_faceless/state.py`:
```python
niche_decay_alert: bool = False
consecutive_decay_count: int = 0
```

**Step 2: Add decay query to `db/queries.py`**

```python
def get_commission_per_view(
    session: Session,
    account_id: str,
    niche: str,
    days: int = 7,
) -> float:
    """
    Calculate commission-per-view for a niche over the last N days.

    Returns 0.0 if no data available.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from tiktok_faceless.db.models import Video, VideoMetric

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Join video_metrics with videos to filter by niche
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.sum(VideoMetric.view_count).label("total_views"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            Video.niche == niche,
            VideoMetric.recorded_at >= cutoff,
        )
        .first()
    )

    if result is None or result.total_views is None or result.total_views == 0:
        return 0.0

    # Approximate commission per view using order count as proxy
    return float(result.total_orders or 0) / float(result.total_views)
```

**Step 3: Write the failing tests**

Add to `tests/unit/agents/test_research.py`:

```python
class TestDecayDetection:
    def test_decay_alert_set_when_below_threshold(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=1,  # 2nd consecutive check triggers alert
        )
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.0001),
        ):
            mock_config = _mock_config()
            mock_config.decay_threshold = 0.001
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_config).start()
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(state)

        assert result.get("niche_decay_alert") is True

    def test_no_decay_alert_on_first_detection(self) -> None:
        state = PipelineState(
            account_id="acc1",
            phase="commit",
            committed_niche="health",
            consecutive_decay_count=0,  # first detection — no alert yet
        )
        with (
            patch("tiktok_faceless.agents.research.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
            patch("tiktok_faceless.agents.research.get_session") as mock_session_ctx,
            patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
            patch("tiktok_faceless.agents.research.cache_product"),
            patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.0001),
        ):
            mock_config = _mock_config()
            mock_config.decay_threshold = 0.001
            patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_config).start()
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_session_ctx.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = research_node(state)

        assert result.get("niche_decay_alert") is not True
        assert result.get("consecutive_decay_count", 0) == 1
```

**Step 4: Add `decay_threshold` to `AccountConfig` in `config.py`**

```python
decay_threshold: float = Field(default=0.001, ge=0.0)
```

**Step 5: Add decay detection to `research_node`**

At the end of `research_node`, before returning selected_product, add:

```python
# --- Decay detection (commit phase only) ---
decay_delta: dict[str, Any] = {}
if state.phase == "commit" and state.committed_niche:
    with get_session() as session:
        cpv = get_commission_per_view(
            session, account_id=state.account_id, niche=state.committed_niche
        )
    if cpv > 0 and cpv < config.decay_threshold:
        new_count = state.consecutive_decay_count + 1
        decay_delta["consecutive_decay_count"] = new_count
        if new_count >= 2:
            decay_delta["niche_decay_alert"] = True
    else:
        decay_delta["consecutive_decay_count"] = 0
```

Then merge `decay_delta` into the return value.

**Step 6: Run tests**

```bash
uv run pytest tests/unit/agents/test_research.py::TestDecayDetection -v
```
Expected: PASS.

**Step 7: Commit**

```bash
git add tiktok_faceless/agents/research.py tiktok_faceless/state.py tiktok_faceless/config.py tiktok_faceless/db/queries.py tests/unit/agents/test_research.py
git commit -m "feat(2.5): commission-per-view decay detection with consecutive-check guard"
```

---

## Story 2.6: Commission Tracking per Video, Product & Niche

### Task 9: Add `get_affiliate_orders()` to `TikTokAPIClient`

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py`
- Modify: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

```python
class TestGetAffiliateOrders:
    def test_returns_list_of_commission_records(self) -> None:
        from tiktok_faceless.models.shop import CommissionRecord
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "orders": [
                    {"order_id": "o1", "product_id": "p1", "commission_amount": 2.50},
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            orders = client.get_affiliate_orders(account_id="acc1")
        assert len(orders) == 1
        assert isinstance(orders[0], CommissionRecord)
        assert orders[0].order_id == "o1"
        assert orders[0].commission_amount == 2.50
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders -v
```

**Step 3: Implement `get_affiliate_orders` in `tiktok_faceless/clients/tiktok.py`**

```python
@api_retry
def get_affiliate_orders(self, account_id: str) -> list[CommissionRecord]:
    """Fetch affiliate commission orders for the account."""
    self._bucket.consume()
    response = self._http.post(
        "/v2/tiktok_shop/affiliate/orders/",
        json={"open_id": self._open_id},
    )
    self._handle_response(response)
    orders = response.json().get("data", {}).get("orders", [])
    return [
        CommissionRecord(
            order_id=str(o["order_id"]),
            product_id=str(o["product_id"]),
            commission_amount=float(o.get("commission_amount", 0.0)),
        )
        for o in orders
    ]
```

Also add `CommissionRecord` to the import from `tiktok_faceless.models.shop`.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders -v
```

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "feat(2.6): add get_affiliate_orders to TikTokAPIClient"
```

---

### Task 10: Add commission aggregation queries to `db/queries.py`

**Files:**
- Modify: `tiktok_faceless/db/queries.py`
- Modify: `tests/unit/db/test_queries.py`

**Step 1: Write the failing tests**

Add to `tests/unit/db/test_queries.py`:

```python
from tiktok_faceless.db.models import Video, VideoMetric
from tiktok_faceless.db.queries import get_commission_totals


class TestGetCommissionTotals:
    def test_returns_total_by_niche(self, session) -> None:
        # Insert a video and metric
        vid = Video(
            id="v1", account_id="acc1", niche="health",
            lifecycle_state="posted", tiktok_video_id="tv1",
        )
        session.add(vid)
        metric = VideoMetric(
            video_id="tv1", account_id="acc1",
            recorded_at=datetime.utcnow(),
            view_count=1000, like_count=0, comment_count=0,
            share_count=0, average_time_watched=0.0,
            retention_3s=0.0, retention_15s=0.0, fyp_reach_pct=0.0,
            affiliate_clicks=10, affiliate_orders=2,
        )
        session.add(metric)
        session.commit()

        totals = get_commission_totals(session, account_id="acc1")
        assert "health" in totals
        assert totals["health"]["total_orders"] == 2
        assert totals["health"]["total_views"] == 1000
```

**Step 2: Implement `get_commission_totals` in `db/queries.py`**

```python
def get_commission_totals(
    session: Session,
    account_id: str,
    days: int = 7,
) -> dict[str, dict[str, int]]:
    """
    Aggregate affiliate orders and views by niche over the last N days.

    Returns: {niche: {"total_orders": int, "total_views": int}}
    """
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from tiktok_faceless.db.models import Video, VideoMetric

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.niche,
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.sum(VideoMetric.view_count).label("total_views"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.niche)
        .all()
    )
    return {
        row.niche: {
            "total_orders": int(row.total_orders or 0),
            "total_views": int(row.total_views or 0),
        }
        for row in rows
    }
```

**Step 3: Run tests**

```bash
uv run pytest tests/unit/db/test_queries.py -v
```

**Step 4: Update `monetization_node` to poll commissions and update `affiliate_commission_week`**

In `tiktok_faceless/agents/monetization.py`, add a commission polling branch (after affiliate link generation, on a separate polling call):

```python
# Commission reconciliation polling (non-blocking)
try:
    orders = tiktok.get_affiliate_orders(account_id=state.account_id)
    # Store as VideoMetric rows — omitted for brevity; use get_session + append rows
    weekly_total = sum(o.commission_amount for o in orders)
except (TikTokRateLimitError, TikTokAPIError):
    weekly_total = state.affiliate_commission_week  # preserve existing on error
```

**Step 5: Run full suite + lint**

```bash
uv run pytest --tb=short && uv run ruff check . && uv run mypy .
```

**Step 6: Final commit**

```bash
git add .
git commit -m "feat(2.6): commission tracking queries and monetization polling"
```

---

## Final Verification

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy .
```

Expected output: All tests pass, no lint errors, no type errors.
