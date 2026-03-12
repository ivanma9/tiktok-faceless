# Story 2.6: Commission Tracking per Video, Product & Niche

Status: ready-for-dev

## Story

As the operator,
I want the Monetization Agent to track affiliate commissions at video, product, and niche granularity,
so that the system knows exactly which content earns and can attribute revenue correctly for Tournament scoring and decay detection.

## Acceptance Criteria

1. **Given** a posted video with an affiliate link
   **When** `monetization_node(state)` runs on its polling schedule
   **Then** `TikTokAPIClient.get_affiliate_orders(account_id)` is called
   **And** the rolling 7-day commission total is summed from the returned `list[CommissionRecord]`
   **And** `state["affiliate_commission_week"]` is updated with this total

2. **Given** commission data is stored
   **When** queried by niche
   **Then** `get_commission_totals(session, account_id, days=7) -> dict[str, dict]` aggregates `VideoMetric` rows by niche
   **And** returns `{niche: {"total_orders": int, "total_views": int}}` for all niches with data in the window

3. **Given** TikTok Shop commission data has a reporting lag
   **When** `monetization_node` calls `get_affiliate_orders` and it raises any exception
   **Then** the exception is caught in a separate try/except block
   **And** `state["affiliate_commission_week"]` is preserved from its existing value (non-fatal)
   **And** the pipeline continues — link generation result is always returned

4. **Given** `get_affiliate_orders` returns an empty list
   **When** `monetization_node` sums commission amounts
   **Then** `state["affiliate_commission_week"]` is set to `0.0`

## Tasks / Subtasks

- [ ] Task 9: Add `get_affiliate_orders` to `TikTokAPIClient`
  - [ ] Add `from tiktok_faceless.models.shop import CommissionRecord` import to `tiktok_faceless/clients/tiktok.py`
  - [ ] Implement `get_affiliate_orders(self, account_id: str) -> list[CommissionRecord]` with `@api_retry` decorator
  - [ ] POST to `/v2/tiktok_shop/affiliate/orders/`, parse response into `list[CommissionRecord]`

- [ ] Task 10: Commission aggregation query + monetization_node extension
  - [ ] Add `get_commission_totals(session, account_id, days=7) -> dict[str, dict]` to `tiktok_faceless/db/queries.py`
  - [ ] Add `from sqlalchemy import func` and `from tiktok_faceless.db.models import Video, VideoMetric` imports to `db/queries.py` (if not already present from Story 2.5)
  - [ ] Extend `monetization_node` in `tiktok_faceless/agents/monetization.py`: add commission polling try/except block at the end, after the DB write
  - [ ] Import `CommissionRecord` in `monetization.py` via `from tiktok_faceless.models.shop import CommissionRecord`
  - [ ] Tests in `tests/unit/clients/test_tiktok.py` — new class `TestGetAffiliateOrders`
  - [ ] Tests in `tests/unit/db/test_queries.py` — new class `TestGetCommissionTotals`
  - [ ] Tests in `tests/unit/agents/test_monetization.py` — new class `TestCommissionPolling`

## Dev Notes

### Critical Architecture Rules

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` in place
- **Commission polling is non-fatal** — always returns `product_validated: True` alongside any commission delta; exception in commission polling never halts the pipeline
- **Commission data has reporting lag** — TikTok controls the order window returned; do not attempt client-side 7-day filtering on `CommissionRecord.recorded_at`
- **`affiliate_commission_week` is approximate** — it is the sum of all `CommissionRecord.commission_amount` in the current orders response, not filtered by date
- **Separate try/except block** — commission polling must be a completely independent `try/except` at the END of `monetization_node`, after the `return {"product_validated": True}` — the return must be restructured to collect the delta first

### `get_affiliate_orders` — Full Implementation

Add to `tiktok_faceless/clients/tiktok.py`:

New import (add alongside existing `AffiliateProduct` import):

```python
from tiktok_faceless.models.shop import AffiliateProduct, CommissionRecord
```

New method on `TikTokAPIClient`:

```python
@api_retry
def get_affiliate_orders(self, account_id: str) -> list[CommissionRecord]:
    """
    Fetch recent TikTok Shop affiliate orders for the account.

    Returns a list of CommissionRecord parsed from the API response.
    TikTok controls the time window returned — do not assume real-time data.
    Returns empty list if no orders are found.
    """
    self._bucket.consume()
    response = self._http.post(
        "/v2/tiktok_shop/affiliate/orders/",
        json={"open_id": self._open_id},
    )
    self._handle_response(response)
    raw_orders = response.json().get("data", {}).get("orders", [])
    results: list[CommissionRecord] = []
    for o in raw_orders:
        results.append(
            CommissionRecord(
                order_id=str(o["order_id"]),
                product_id=str(o["product_id"]),
                commission_amount=float(o.get("commission_amount", 0.0)),
            )
        )
    return results
```

### `get_commission_totals` — Full Implementation

Add to `tiktok_faceless/db/queries.py`:

Required imports (check if already present after Story 2.5 — add only what is missing):

```python
from sqlalchemy import func
from tiktok_faceless.db.models import Product, Video, VideoMetric
```

New function:

```python
def get_commission_totals(
    session: Session,
    account_id: str,
    days: int = 7,
) -> dict[str, dict]:
    """
    Aggregate VideoMetric data by niche over the last `days` days.

    Joins VideoMetric on VideoMetric.video_id == Video.tiktok_video_id,
    groups by Video.niche. Returns a dict keyed by niche with
    {"total_orders": int, "total_views": int} per niche.

    Returns empty dict if no matching rows exist.
    """
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

### `monetization_node` Extension — Full Updated Function

The current `monetization_node` ends with `return {"product_validated": True}`. This must be restructured so the commission polling block can append to the delta before returning. The commission block is a separate `try/except` at the very end.

```python
def monetization_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate a TikTok Shop affiliate link for state.selected_product and persist to DB.
    Then poll affiliate orders and update affiliate_commission_week (non-fatal).

    Returns state delta dict with product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.
    """
    if state.selected_product is None:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="MissingProduct",
                    message="selected_product is None — no product to generate affiliate link",
                )
            ]
        }

    config = load_account_config(state.account_id)
    product_id: str = state.selected_product["product_id"]

    try:
        client = TikTokAPIClient(
            access_token=config.tiktok_access_token,
            open_id=config.tiktok_open_id,
        )
        affiliate_link = client.generate_affiliate_link(
            account_id=state.account_id,
            product_id=product_id,
        )
    except TikTokRateLimitError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokRateLimitError",
                    message=str(e),
                )
            ]
        }
    except TikTokAuthError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokAuthError",
                    message=str(e),
                )
            ]
        }
    except TikTokAPIError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokAPIError",
                    message=str(e),
                )
            ]
        }

    with get_session() as session:
        video = (
            session.query(Video)
            .filter_by(account_id=state.account_id, lifecycle_state="queued")
            .order_by(Video.created_at.desc())
            .first()
        )
        if video is None:
            video = Video(
                id=str(uuid.uuid4()),
                account_id=state.account_id,
                niche=state.committed_niche or "unknown",
            )
            session.add(video)
        video.affiliate_link = affiliate_link
        video.product_id = product_id

    delta: dict[str, Any] = {"product_validated": True}

    # --- Commission polling (non-fatal) ---
    try:
        orders = client.get_affiliate_orders(account_id=state.account_id)
        delta["affiliate_commission_week"] = sum(o.commission_amount for o in orders)
    except Exception:
        # Commission data has reporting lag and is non-critical.
        # Preserve existing affiliate_commission_week; do not halt the pipeline.
        pass

    return delta
```

Updated imports for `monetization.py` — add `CommissionRecord` is not needed directly (it comes back as typed objects from `get_affiliate_orders`). The return type of `get_affiliate_orders` is `list[CommissionRecord]` but `monetization.py` only reads `.commission_amount`, so no explicit import of `CommissionRecord` is required in this file. The `client` variable is already in scope from the link generation block.

### State Field: `affiliate_commission_week`

Check `tiktok_faceless/state.py` — if `affiliate_commission_week` does not already exist, add it:

```python
affiliate_commission_week: float = 0.0
```

This field is overwritten wholesale on each successful poll (plain replacement, no LangGraph `add` reducer).

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/clients/tiktok.py` | Add `CommissionRecord` to shop import; add `get_affiliate_orders` method |
| `tiktok_faceless/db/queries.py` | Add `get_commission_totals`; ensure `func`, `Video`, `VideoMetric` imports present |
| `tiktok_faceless/agents/monetization.py` | Restructure return + add commission polling try/except at end |
| `tiktok_faceless/state.py` | Add `affiliate_commission_week: float = 0.0` if missing |
| `tests/unit/clients/test_tiktok.py` | Add `TestGetAffiliateOrders` class |
| `tests/unit/db/test_queries.py` | Add `TestGetCommissionTotals` class |
| `tests/unit/agents/test_monetization.py` | Add `TestCommissionPolling` class |

### Do NOT Touch

- `tiktok_faceless/db/models.py` — no schema changes; `VideoMetric` already has `affiliate_orders` and `affiliate_clicks`
- `tiktok_faceless/agents/research.py` — decay detection already in place from Story 2.5
- `tiktok_faceless/orchestrator.py` — phase logic is Epic 3

### Required Test Cases

#### `TestGetAffiliateOrders` in `tests/unit/clients/test_tiktok.py`

```python
_MOD = "tiktok_faceless.clients.tiktok"


class TestGetAffiliateOrders:

    def _make_client(self) -> TikTokAPIClient:
        return TikTokAPIClient(access_token="tok", open_id="oid")

    def test_returns_list_of_commission_records(self, respx_mock: Any) -> None:
        """Parses orders array into list[CommissionRecord] correctly."""
        respx_mock.post("https://open.tiktokapis.com/v2/tiktok_shop/affiliate/orders/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "orders": [
                            {
                                "order_id": "ord1",
                                "product_id": "prod1",
                                "commission_amount": 4.50,
                            },
                            {
                                "order_id": "ord2",
                                "product_id": "prod2",
                                "commission_amount": 2.00,
                            },
                        ]
                    }
                },
            )
        )
        client = self._make_client()
        result = client.get_affiliate_orders(account_id="acc1")

        assert len(result) == 2
        assert result[0].order_id == "ord1"
        assert result[0].product_id == "prod1"
        assert result[0].commission_amount == pytest.approx(4.50)
        assert result[1].order_id == "ord2"
        assert result[1].commission_amount == pytest.approx(2.00)

    def test_returns_empty_list_when_no_orders(self, respx_mock: Any) -> None:
        """Returns [] when data.orders is absent or empty."""
        respx_mock.post("https://open.tiktokapis.com/v2/tiktok_shop/affiliate/orders/").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        client = self._make_client()
        result = client.get_affiliate_orders(account_id="acc1")

        assert result == []
```

#### `TestGetCommissionTotals` in `tests/unit/db/test_queries.py`

Use in-memory SQLite via the existing session fixture pattern.

```python
class TestGetCommissionTotals:

    def test_aggregates_by_niche_correctly(self, session: Session) -> None:
        """Returns total_orders and total_views per niche."""
        now = datetime.utcnow()
        # Two videos in different niches
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1",
            created_at=now,
        ))
        session.add(Video(
            id="v2", account_id="acc1", niche="beauty",
            lifecycle_state="posted", tiktok_video_id="tiktok-v2",
            created_at=now,
        ))
        # Metrics within 7 days
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=1),
            view_count=1000, affiliate_orders=3,
        ))
        session.add(VideoMetric(
            video_id="tiktok-v2", account_id="acc1",
            recorded_at=now - timedelta(days=2),
            view_count=500, affiliate_orders=1,
        ))
        session.commit()

        result = get_commission_totals(session, account_id="acc1")

        assert result["fitness"]["total_orders"] == 3
        assert result["fitness"]["total_views"] == 1000
        assert result["beauty"]["total_orders"] == 1
        assert result["beauty"]["total_views"] == 500

    def test_returns_empty_dict_when_no_data(self, session: Session) -> None:
        """Returns {} when no VideoMetric rows match account_id in the window."""
        result = get_commission_totals(session, account_id="acc1")
        assert result == {}

    def test_excludes_metrics_outside_window(self, session: Session) -> None:
        """Metrics older than days= are not included in aggregation."""
        now = datetime.utcnow()
        session.add(Video(
            id="v1", account_id="acc1", niche="fitness",
            lifecycle_state="posted", tiktok_video_id="tiktok-v1",
            created_at=now,
        ))
        # Old metric — outside 7-day window
        session.add(VideoMetric(
            video_id="tiktok-v1", account_id="acc1",
            recorded_at=now - timedelta(days=10),
            view_count=9999, affiliate_orders=99,
        ))
        session.commit()

        result = get_commission_totals(session, account_id="acc1")

        assert result == {}
```

#### `TestCommissionPolling` in `tests/unit/agents/test_monetization.py`

```python
_MOD = "tiktok_faceless.agents.monetization"

_BASE_STATE = PipelineState(
    account_id="acc1",
    selected_product={
        "product_id": "prod1",
        "product_name": "Widget",
        "product_url": "https://example.com/widget",
        "commission_rate": 0.10,
        "sales_velocity_score": 0.8,
        "niche": "fitness",
    },
    affiliate_commission_week=0.0,
)


def _make_orders(amounts: list[float]) -> list[CommissionRecord]:
    return [
        CommissionRecord(order_id=f"ord{i}", product_id="prod1", commission_amount=a)
        for i, a in enumerate(amounts)
    ]


class TestCommissionPolling:

    def _run(
        self,
        state: PipelineState,
        orders: list[CommissionRecord] | Exception,
    ) -> dict[str, Any]:
        """Helper: run monetization_node with mocked affiliate link + orders response."""
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session"),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.generate_affiliate_link.return_value = "https://affiliate.link/x"
            if isinstance(orders, Exception):
                mock_client.get_affiliate_orders.side_effect = orders
            else:
                mock_client.get_affiliate_orders.return_value = orders
            mock_client_cls.return_value = mock_client
            return monetization_node(state)

    def test_updates_affiliate_commission_week_when_orders_returned(self) -> None:
        """affiliate_commission_week is set to sum of commission_amount from orders."""
        orders = _make_orders([4.50, 2.00])
        result = self._run(_BASE_STATE, orders)

        assert result["product_validated"] is True
        assert result["affiliate_commission_week"] == pytest.approx(6.50)

    def test_sets_zero_when_no_orders(self) -> None:
        """affiliate_commission_week is 0.0 when orders list is empty."""
        result = self._run(_BASE_STATE, [])

        assert result["affiliate_commission_week"] == pytest.approx(0.0)

    def test_preserves_existing_commission_on_api_error(self) -> None:
        """When get_affiliate_orders raises, affiliate_commission_week is absent from delta."""
        state = PipelineState(
            account_id="acc1",
            selected_product=_BASE_STATE.selected_product,
            affiliate_commission_week=12.34,
        )
        result = self._run(state, Exception("network error"))

        # Key absent from delta — LangGraph preserves existing state value
        assert "affiliate_commission_week" not in result
        assert result["product_validated"] is True

    def test_continues_pipeline_on_commission_polling_failure(self) -> None:
        """monetization_node always returns product_validated=True even if commission polling fails."""
        result = self._run(_BASE_STATE, RuntimeError("TikTok Shop down"))

        assert result["product_validated"] is True
        assert "errors" not in result

    def test_commission_polling_does_not_interfere_with_link_generation(self) -> None:
        """product_validated is True and affiliate_commission_week is present on happy path."""
        orders = _make_orders([1.00])
        result = self._run(_BASE_STATE, orders)

        assert result["product_validated"] is True
        assert result["affiliate_commission_week"] == pytest.approx(1.00)

    def test_missing_product_returns_error_without_polling(self) -> None:
        """MissingProduct error is returned immediately — commission polling never runs."""
        state = PipelineState(account_id="acc1", selected_product=None)
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            result = monetization_node(state)

        mock_client.get_affiliate_orders.assert_not_called()
        assert "errors" in result
        assert result["errors"][0].error_type == "MissingProduct"
```

### Key Design Decisions

1. **`get_affiliate_orders` endpoint** — POST `/v2/tiktok_shop/affiliate/orders/` with `{"open_id": self._open_id}`. TikTok controls the order window; the response is treated as the "current rolling window." No client-side date filtering is applied.

2. **`affiliate_commission_week` is a sum approximation** — The value is `sum(o.commission_amount for o in orders)`. It is called "week" because TikTok's API window approximates 7 days, but we do not filter by `CommissionRecord.recorded_at` — that field tracks local ingestion time, not TikTok's settlement window.

3. **Commission polling block placement** — The block is added AFTER the DB write and AFTER link generation succeeds. It uses the same `client` instance already constructed in the link generation block. The `delta` dict is built first (`{"product_validated": True}`) and the commission key is conditionally added before returning.

4. **Non-fatal semantics** — If `get_affiliate_orders` raises any exception (including `TikTokAPIError`, `TikTokRateLimitError`, network errors), the bare `except Exception` swallows it. `affiliate_commission_week` is NOT written to `delta`, so LangGraph preserves the previous state value. No `AgentError` is appended — discrepancies are silently tolerated at MVP per NFR19.

5. **`get_commission_totals` join** — Same join as `get_commission_per_view` (Story 2.5): `VideoMetric.video_id == Video.tiktok_video_id`. Groups by `Video.niche`. The result is a plain Python dict — not stored in state; used by analytics consumers (Epic 3 tournament scoring).

6. **No new DB schema** — `VideoMetric` already has `affiliate_orders`, `affiliate_clicks`, and all required columns. `CommissionRecord` in `models/shop.py` is a Pydantic model only (no ORM table).

7. **`CommissionRecord` import in `tiktok.py`** — Change the existing line:
   ```python
   from tiktok_faceless.models.shop import AffiliateProduct
   ```
   to:
   ```python
   from tiktok_faceless.models.shop import AffiliateProduct, CommissionRecord
   ```

### Previous Story Learnings (from Stories 2.1–2.5)

- `_MOD = "tiktok_faceless.agents.monetization"` — use at module level in test file
- Patch `get_session` at the monetization module level
- `AgentError` and `PipelineState` imported from `tiktok_faceless.state`
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501 enforced)
- `dict[str, Any]` return type on `monetization_node`
- `get_session()` used as context manager (`with get_session() as session:`)
- `@api_retry` decorator required on all `TikTokAPIClient` methods that make HTTP calls
- `self._bucket.consume()` must be the first call inside each `@api_retry` method

### References

- Epic 2.6 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.6 (line 622)
- Previous story: `_bmad-output/implementation-artifacts/2-5-commission-per-view-decay-detection.md`
- `monetization_node` current implementation: `tiktok_faceless/agents/monetization.py`
- `TikTokAPIClient` current state: `tiktok_faceless/clients/tiktok.py`
- `CommissionRecord` model: `tiktok_faceless/models/shop.py`
- `VideoMetric`, `Video` ORM models: `tiktok_faceless/db/models.py`
- Existing DB queries: `tiktok_faceless/db/queries.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `tiktok_faceless/clients/tiktok.py` — add `CommissionRecord` to shop import; add `get_affiliate_orders` method
- `tiktok_faceless/db/queries.py` — add `get_commission_totals`; ensure `func`, `Video`, `VideoMetric` imports present
- `tiktok_faceless/agents/monetization.py` — restructure final return into `delta` dict; add commission polling try/except block
- `tiktok_faceless/state.py` — add `affiliate_commission_week: float = 0.0` if missing
- `tests/unit/clients/test_tiktok.py` — add `TestGetAffiliateOrders` class (2 test cases)
- `tests/unit/db/test_queries.py` — add `TestGetCommissionTotals` class (3 test cases)
- `tests/unit/agents/test_monetization.py` — add `TestCommissionPolling` class (6 test cases)
