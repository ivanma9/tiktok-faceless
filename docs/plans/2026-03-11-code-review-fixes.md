# Code Review Fixes — Epics 1 & 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all Critical and key Important issues found during code review of Epics 1 and 2.

**Architecture:** All fixes are surgical — minimal changes to the exact lines identified. Each task covers one bug or gap, with a failing test written first, then the fix, then a commit. No refactors beyond what's required to close the issue.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Pydantic v2, tenacity, anthropic SDK, pytest, threading

---

## Task 1: Fix TokenBucket deadlock — sleep outside the lock

**Bug:** `time.sleep()` is called while holding `self._lock` in `TokenBucket.consume()`. Under concurrency all threads serialize behind the sleeping thread.

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py:35-50`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `TestTokenBucket` class in `tests/unit/clients/test_tiktok.py`:

```python
def test_lock_not_held_during_sleep(self) -> None:
    """A second thread must be able to acquire the lock while the first is sleeping."""
    import threading

    bucket = TokenBucket(max_tokens=1, refill_period=60.0)
    bucket.consume()  # exhaust bucket

    acquired_during_sleep = threading.Event()
    original_sleep = time.sleep

    def patched_sleep(duration: float) -> None:
        # Try to acquire the lock while the first thread sleeps
        # If lock is held, this will block and the event won't be set before sleep returns
        got_it = bucket._lock.acquire(blocking=False)
        if got_it:
            acquired_during_sleep.set()
            bucket._lock.release()
        original_sleep(0)  # Don't actually sleep

    with patch("time.sleep", side_effect=patched_sleep):
        bucket.consume()

    assert acquired_during_sleep.is_set(), "Lock was held during sleep — deadlock risk"
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/ivanma/Desktop/agents/tiktok-faceless
python -m pytest tests/unit/clients/test_tiktok.py::TestTokenBucket::test_lock_not_held_during_sleep -v
```

Expected: FAIL — lock is held during sleep in current implementation.

**Step 3: Fix `TokenBucket.consume` in `tiktok_faceless/clients/tiktok.py`**

Replace lines 35-50:

```python
def consume(self) -> None:
    """Block until a token is available, then consume one."""
    wait = 0.0
    with self._lock:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._max_tokens),
            self._tokens + elapsed * (self._max_tokens / self._refill_period),
        )
        self._last_refill = now
        if self._tokens < 1:
            wait = (1 - self._tokens) * (self._refill_period / self._max_tokens)
            self._tokens = 0.0
        else:
            self._tokens -= 1.0
    # Sleep OUTSIDE the lock so other threads can proceed
    if wait > 0:
        time.sleep(wait)
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/clients/test_tiktok.py::TestTokenBucket -v
```

Expected: All TokenBucket tests PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "fix(tiktok): sleep outside lock in TokenBucket.consume to prevent deadlock"
```

---

## Task 2: Add UNIQUE constraint on Product(account_id, product_id)

**Bug:** Concurrent writes can insert two rows with the same (account_id, product_id). Read-before-write upsert is not atomic.

**Files:**
- Modify: `tiktok_faceless/db/models.py:86-100`
- Modify: `tiktok_faceless/db/queries.py:19-47` (make upsert use `niche` update too)
- Test: `tests/unit/db/test_queries.py`

**Step 1: Write the failing test**

Add to `tests/unit/db/test_queries.py`:

```python
def test_cache_product_upsert_updates_niche(session: Session) -> None:
    """Upserting a product with a new niche should update the niche field."""
    from tiktok_faceless.db.queries import cache_product
    from tiktok_faceless.models.shop import AffiliateProduct

    product_v1 = AffiliateProduct(
        product_id="p1", product_name="Widget", product_url="https://u.com",
        commission_rate=0.1, sales_velocity_score=0.5, niche="health"
    )
    product_v2 = AffiliateProduct(
        product_id="p1", product_name="Widget Updated", product_url="https://u.com",
        commission_rate=0.15, sales_velocity_score=0.7, niche="fitness"  # niche changed
    )
    cache_product(session, account_id="acc1", product=product_v1)
    cache_product(session, account_id="acc1", product=product_v2)

    from tiktok_faceless.db.models import Product
    rows = session.query(Product).filter_by(account_id="acc1", product_id="p1").all()
    assert len(rows) == 1, "Upsert must not create duplicate rows"
    assert rows[0].niche == "fitness"
    assert rows[0].product_name == "Widget Updated"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/db/test_queries.py::test_cache_product_upsert_updates_niche -v
```

Expected: FAIL — niche is not updated in current implementation.

**Step 3: Add UniqueConstraint and fix niche update**

In `tiktok_faceless/db/models.py`, replace the `Product` class `__table_args__` (add after `eliminated` field, before end of class):

```python
from sqlalchemy import UniqueConstraint

class Product(Base):
    # ... existing fields unchanged ...

    __table_args__ = (
        UniqueConstraint("account_id", "product_id", name="uq_product_account_product"),
    )
```

The full import line at top of `models.py` already has `from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String` — add `UniqueConstraint` to it.

In `tiktok_faceless/db/queries.py`, in `cache_product`, add `existing.niche = product.niche` to the update branch:

```python
if existing is not None:
    existing.product_name = product.product_name
    existing.product_url = product.product_url
    existing.niche = product.niche          # ADD THIS LINE
    existing.commission_rate = product.commission_rate
    existing.sales_velocity_score = product.sales_velocity_score
    existing.cached_at = datetime.utcnow()
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/db/test_queries.py -v
```

Expected: All DB query tests PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/db/models.py tiktok_faceless/db/queries.py tests/unit/db/test_queries.py
git commit -m "fix(db): add UNIQUE constraint on Product(account_id, product_id) and update niche on upsert"
```

---

## Task 3: Fix `get_video_comments` called with `product_id` instead of a video ID

**Bug:** `research_node` calls `client.get_video_comments(video_id=best.product_id, ...)` — a product ID is not a video ID. Comment mining silently returns empty results every run.

**Fix approach:** Add an optional `top_video_id: str | None` field to `AffiliateProduct`. When it's absent (as it currently is from the API), skip comment mining rather than call the wrong endpoint.

**Files:**
- Modify: `tiktok_faceless/models/shop.py`
- Modify: `tiktok_faceless/agents/research.py:106-110`
- Test: `tests/unit/agents/test_research.py`

**Step 1: Write the failing test**

Add to `TestCommentMining` in `tests/unit/agents/test_research.py`:

```python
def test_comment_mining_skipped_when_no_video_id(self) -> None:
    """get_video_comments must NOT be called when product has no top_video_id."""
    with (
        patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
        patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
        patch(f"{_MOD}.get_cached_products", return_value=[]),
        patch(f"{_MOD}.cache_product"),
    ):
        mock_client = MagicMock()
        mock_client.get_validated_products.return_value = [_PRODUCT]  # _PRODUCT has no top_video_id
        mock_client_cls.return_value = mock_client
        result = research_node(_STATE)

    mock_client.get_video_comments.assert_not_called()
    assert result["selected_product"]["buyer_language"] == []
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/agents/test_research.py::TestCommentMining::test_comment_mining_skipped_when_no_video_id -v
```

Expected: FAIL — `get_video_comments` is currently always called.

**Step 3: Add `top_video_id` to `AffiliateProduct` and gate the call**

In `tiktok_faceless/models/shop.py`, add the field to `AffiliateProduct`:

```python
class AffiliateProduct(BaseModel):
    product_id: str
    product_name: str
    product_url: str
    commission_rate: float
    sales_velocity_score: float = 0.0
    niche: str
    top_video_id: str | None = None   # ADD THIS
```

In `tiktok_faceless/agents/research.py`, replace lines 106-110:

```python
# Mine buyer-language comments only when a real video ID is available (non-fatal)
comments: list[str] = []
if best.top_video_id:
    try:
        comments = client.get_video_comments(video_id=best.top_video_id, max_count=20)
    except (TikTokRateLimitError, TikTokAPIError):
        comments = []
```

**Step 4: Run all research tests**

```bash
python -m pytest tests/unit/agents/test_research.py -v
```

Expected: All tests PASS (existing tests pass because `_PRODUCT` has no `top_video_id`, so `get_video_comments` is not called — existing test stubs still work).

**Step 5: Commit**

```bash
git add tiktok_faceless/models/shop.py tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "fix(research): skip comment mining when product has no top_video_id; add top_video_id field to AffiliateProduct"
```

---

## Task 4: Fix tournament live-API path uses `products[0]` instead of `max(score)`

**Bug:** In `research_node`, the live-API branch appends `products[0]` (trusting sort order) rather than `max(products, key=lambda p: p.sales_velocity_score)`. If sort order ever changes, the wrong winner is silently selected.

**Files:**
- Modify: `tiktok_faceless/agents/research.py:84-88`
- Test: `tests/unit/agents/test_research.py`

**Step 1: Write the failing test**

Add to `TestTournamentMode` in `tests/unit/agents/test_research.py`:

```python
def test_live_api_path_picks_highest_score_not_first(self) -> None:
    """When API returns unsorted products, live path must still pick highest score."""
    low = AffiliateProduct(
        product_id="p_low", product_name="Low", product_url="u",
        commission_rate=0.1, sales_velocity_score=0.2, niche="health"
    )
    high = AffiliateProduct(
        product_id="p_high", product_name="High", product_url="u",
        commission_rate=0.2, sales_velocity_score=0.9, niche="health"
    )
    state = PipelineState(
        account_id="acc1", phase="tournament", candidate_niches=["health"]
    )
    with (
        patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
        patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
        patch(f"{_MOD}.get_cached_products", return_value=[]),
        patch(f"{_MOD}.cache_product"),
    ):
        mock_client = MagicMock()
        # Return low first, high second — deliberately unsorted
        mock_client.get_validated_products.return_value = [low, high]
        mock_client_cls.return_value = mock_client
        result = research_node(state)

    assert result["selected_product"]["product_id"] == "p_high"
    assert result["selected_product"]["sales_velocity_score"] == pytest.approx(0.9)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest "tests/unit/agents/test_research.py::TestTournamentMode::test_live_api_path_picks_highest_score_not_first" -v
```

Expected: FAIL — current code appends `products[0]` which is `low`.

**Step 3: Fix line 88 in `tiktok_faceless/agents/research.py`**

Replace:
```python
            all_best.append(products[0])
```
With:
```python
            all_best.append(max(products, key=lambda p: p.sales_velocity_score))
```

**Step 4: Run all research tests**

```bash
python -m pytest tests/unit/agents/test_research.py -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "fix(research): select highest-score product in live-API tournament path instead of products[0]"
```

---

## Task 5: Fix `niche_decay_alert` never cleared on recovery

**Bug:** When `cpv >= config.decay_threshold` (recovery), `consecutive_decay_count` resets to 0 but `niche_decay_alert` stays `True` in state permanently.

**Files:**
- Modify: `tiktok_faceless/agents/research.py:125-126`
- Test: `tests/unit/agents/test_research.py`

**Step 1: Write the failing test**

Add to `TestDecayDetection` in `tests/unit/agents/test_research.py`:

```python
def test_decay_alert_cleared_on_recovery(self) -> None:
    """niche_decay_alert must be set to False when cpv recovers above threshold."""
    from tiktok_faceless.state import PipelineState
    state = PipelineState(
        account_id="acc1",
        phase="commit",
        committed_niche="health",
        consecutive_decay_count=1,
        niche_decay_alert=True,  # alert was previously fired
    )
    mock_cfg = _mock_config()
    mock_cfg.decay_threshold = 0.001
    with (
        patch("tiktok_faceless.agents.research.load_account_config", return_value=mock_cfg),
        patch("tiktok_faceless.agents.research.TikTokAPIClient") as mock_client_cls,
        patch("tiktok_faceless.agents.research.get_session", return_value=_mock_session_ctx()),
        patch("tiktok_faceless.agents.research.get_cached_products", return_value=[_PRODUCT]),
        patch("tiktok_faceless.agents.research.cache_product"),
        patch("tiktok_faceless.agents.research.get_commission_per_view", return_value=0.01),  # above threshold
    ):
        mock_client = MagicMock()
        mock_client.get_video_comments.return_value = []
        mock_client_cls.return_value = mock_client
        result = research_node(state)

    assert result.get("niche_decay_alert") is False
    assert result.get("consecutive_decay_count") == 0
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/agents/test_research.py::TestDecayDetection::test_decay_alert_cleared_on_recovery -v
```

Expected: FAIL — recovery branch does not emit `niche_decay_alert`.

**Step 3: Fix `research.py` recovery branch (lines 125-126)**

Replace:
```python
            elif cpv >= config.decay_threshold:
                decay_delta["consecutive_decay_count"] = 0
```
With:
```python
            elif cpv >= config.decay_threshold:
                decay_delta["consecutive_decay_count"] = 0
                decay_delta["niche_decay_alert"] = False
```

**Step 4: Run all decay detection tests**

```bash
python -m pytest tests/unit/agents/test_research.py::TestDecayDetection -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "fix(research): clear niche_decay_alert=False in decay recovery branch"
```

---

## Task 6: Add rate-limit error observability to tournament scanning

**Bug:** When all niches are rate-limited, `research_node` returns a generic `NoValidatedProducts` error with no indication that rate limiting was the root cause.

**Files:**
- Modify: `tiktok_faceless/agents/research.py:60-101`
- Test: `tests/unit/agents/test_research.py`

**Step 1: Write the failing test**

Add to `TestTournamentMode` in `tests/unit/agents/test_research.py`:

```python
def test_rate_limit_errors_surfaced_in_no_products_message(self) -> None:
    """When all niches are rate-limited, the error message must mention rate limiting."""
    from tiktok_faceless.clients import TikTokRateLimitError
    state = PipelineState(
        account_id="acc1", phase="tournament", candidate_niches=["health", "fitness"]
    )
    with (
        patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
        patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
        patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
        patch(f"{_MOD}.get_cached_products", return_value=[]),
    ):
        mock_client = MagicMock()
        mock_client.get_validated_products.side_effect = TikTokRateLimitError("rate limited")
        mock_client_cls.return_value = mock_client
        result = research_node(state)

    assert "errors" in result
    assert "rate" in result["errors"][0].message.lower()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest "tests/unit/agents/test_research.py::TestTournamentMode::test_rate_limit_errors_surfaced_in_no_products_message" -v
```

Expected: FAIL — current message just says "No products in niches..."

**Step 3: Fix the per-niche loop to track errors**

In `tiktok_faceless/agents/research.py`, update the niche scanning loop:

```python
    # Collect best product per niche
    all_best: list[AffiliateProduct] = []
    niche_errors: list[tuple[str, str]] = []   # ADD: (niche, reason) pairs

    for niche in niches:
        # Cache check per niche
        with get_session() as session:
            cached = get_cached_products(session, account_id=state.account_id, niche=niche)

        if cached:
            all_best.append(max(cached, key=lambda p: p.sales_velocity_score))
            continue

        # Live API fetch for this niche
        try:
            products = client.get_validated_products(
                account_id=state.account_id,
                niche=niche,
                min_commission_rate=config.min_commission_rate,
                min_sales_velocity=config.min_sales_velocity,
            )
        except TikTokRateLimitError as e:                         # CHANGE: split handlers
            niche_errors.append((niche, f"rate_limited: {e}"))   # ADD
            continue
        except TikTokAPIError as e:
            niche_errors.append((niche, f"api_error: {e}"))      # ADD
            continue

        if products:
            with get_session() as session:
                for product in products:
                    cache_product(session, account_id=state.account_id, product=product)
            all_best.append(max(products, key=lambda p: p.sales_velocity_score))

    if not all_best:
        # Build informative message including per-niche failure reasons
        error_detail = ""
        if niche_errors:
            reasons = "; ".join(f"{n}: {r}" for n, r in niche_errors)
            error_detail = f" Per-niche failures: {reasons}"
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=(
                        f"No products in niches {niches} met the validation thresholds.{error_detail}"
                    ),
                    recovery_suggestion="Try different niches or lower thresholds.",
                )
            ],
        }
```

**Step 4: Run all tests**

```bash
python -m pytest tests/unit/agents/test_research.py -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/agents/research.py tests/unit/agents/test_research.py
git commit -m "fix(research): surface per-niche rate-limit and API errors in NoValidatedProducts message"
```

---

## Task 7: Add retry to `LLMClient.generate_script` and per-archetype fallback in `script_node`

**Bug 1:** No retry on transient Anthropic errors — all 3 LLM calls fail on a single 529.
**Bug 2:** Failure on archetype 2/3 discards already-generated variants — all-or-nothing.

**Files:**
- Modify: `tiktok_faceless/clients/llm.py`
- Modify: `tiktok_faceless/utils/retry.py`
- Modify: `tiktok_faceless/agents/script.py:76-104`
- Test: `tests/unit/agents/test_script.py`
- Test: `tests/unit/clients/test_llm.py`

**Step 1: Write failing tests**

In `tests/unit/clients/test_llm.py`, add:

```python
def test_generate_script_retries_on_transient_error() -> None:
    """LLMClient.generate_script must retry on anthropic.APIStatusError with 529."""
    import anthropic
    from tiktok_faceless.clients.llm import LLMClient

    client = LLMClient(api_key="test")
    call_count = 0

    def flaky_create(**kwargs):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            # Simulate 529 overloaded
            raise anthropic.APIStatusError(
                "overloaded", response=MagicMock(status_code=529), body={}
            )
        msg = MagicMock()
        msg.content = [MagicMock(text="script text")]
        return msg

    with patch.object(client._client.messages, "create", side_effect=flaky_create):
        result = client.generate_script(prompt="test")

    assert result == "script text"
    assert call_count == 2
```

In `tests/unit/agents/test_script.py`, add:

```python
def test_partial_success_returns_completed_variants() -> None:
    """If archetype 2 fails, archetype 1's script must still be returned."""
    from tiktok_faceless.clients import LLMError

    state = PipelineState(
        account_id="acc1",
        selected_product={
            "product_id": "p1", "product_name": "Widget", "product_url": "u",
            "commission_rate": 0.1, "sales_velocity_score": 0.5, "niche": "health",
            "buyer_language": [],
        },
    )
    call_count = 0

    def flaky_generate(prompt: str, **kwargs) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise LLMError("archetype 2 failed")
        return f"script for call {call_count}"

    mock_cfg = MagicMock()
    mock_cfg.anthropic_api_key = "key"
    mock_cfg.persona_name = ""
    mock_cfg.persona_catchphrase = ""
    mock_cfg.persona_tone = "casual"

    with (
        patch("tiktok_faceless.agents.script.load_account_config", return_value=mock_cfg),
        patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
    ):
        mock_llm = MagicMock()
        mock_llm.generate_script.side_effect = flaky_generate
        mock_llm_cls.return_value = mock_llm
        result = script_node(state)

    # Should have 2 variants (1 and 3 succeeded), not an error
    assert "hook_variants" in result
    assert len(result["hook_variants"]) == 2
    assert "errors" not in result
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/clients/test_llm.py::test_generate_script_retries_on_transient_error tests/unit/agents/test_script.py::test_partial_success_returns_completed_variants -v
```

Expected: Both FAIL.

**Step 3: Add `llm_retry` to `retry.py`**

In `tiktok_faceless/utils/retry.py`, add:

```python
import anthropic

llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type((anthropic.APIStatusError, anthropic.APIConnectionError)),
    reraise=True,
)
```

**Step 4: Apply `llm_retry` to `generate_script` in `llm.py`**

```python
from tiktok_faceless.utils.retry import llm_retry

class LLMClient:
    # ...
    @llm_retry
    def generate_script(self, prompt: str, max_tokens: int = 1024) -> str:
        # ... existing implementation unchanged
```

**Step 5: Make `script_node` collect partial results**

In `tiktok_faceless/agents/script.py`, replace the `try` block (lines 76-104):

```python
    llm = LLMClient(api_key=config.anthropic_api_key)
    variants = []
    for archetype in THREE_HOOK_ARCHETYPES:
        prompt = _build_script_prompt(
            state.selected_product,
            archetype,
            buyer_language=buyer_language,
            persona_name=config.persona_name,
            persona_catchphrase=config.persona_catchphrase,
            persona_tone=config.persona_tone,
        )
        try:
            text = llm.generate_script(prompt=prompt)
            if not text or not text.strip():
                continue  # skip empty, try next archetype
            variants.append({"archetype": archetype, "script": text.strip()})
        except LLMError:
            continue  # non-fatal per archetype

    if not variants:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="LLMError",
                    message="All 3 archetypes failed — no script generated.",
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

**Step 6: Run all script and llm tests**

```bash
python -m pytest tests/unit/agents/test_script.py tests/unit/clients/test_llm.py -v
```

Expected: All PASS.

**Step 7: Commit**

```bash
git add tiktok_faceless/utils/retry.py tiktok_faceless/clients/llm.py tiktok_faceless/agents/script.py tests/unit/agents/test_script.py tests/unit/clients/test_llm.py
git commit -m "fix(script): add LLM retry on transient errors and per-archetype fallback in script_node"
```

---

## Task 8: Fix `get_affiliate_orders` — defensive `.get()` for order fields

**Bug:** `o["order_id"]` and `o["product_id"]` raise `KeyError` on malformed responses, silently swallowed by `monetization_node`.

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py:194-202`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `TestGetAffiliateOrders` in `tests/unit/clients/test_tiktok.py`:

```python
def test_skips_malformed_orders_missing_order_id(self) -> None:
    """Orders missing order_id must be skipped, not raise KeyError."""
    client = TikTokAPIClient(access_token="tok", open_id="oid")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "orders": [
                {"order_id": "ord1", "product_id": "prod1", "commission_amount": 4.50},
                {"product_id": "prod2", "commission_amount": 2.00},  # missing order_id
                {"order_id": "ord3", "commission_amount": 1.00},     # missing product_id
            ]
        }
    }
    with patch.object(client._http, "post", return_value=mock_response):
        orders = client.get_affiliate_orders(account_id="acc1")

    # Only the first complete order should be returned
    assert len(orders) == 1
    assert orders[0].order_id == "ord1"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest "tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders::test_skips_malformed_orders_missing_order_id" -v
```

Expected: FAIL with KeyError.

**Step 3: Fix `get_affiliate_orders` in `tiktok.py`**

Replace the list comprehension (lines 195-202):

```python
        records = []
        for o in orders:
            order_id = o.get("order_id")
            product_id = o.get("product_id")
            if not order_id or not product_id:
                continue  # skip malformed records
            records.append(
                CommissionRecord(
                    order_id=str(order_id),
                    product_id=str(product_id),
                    commission_amount=float(o.get("commission_amount", 0.0)),
                )
            )
        return records
```

**Step 4: Run all affiliate order tests**

```bash
python -m pytest tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "fix(tiktok): skip malformed orders missing order_id or product_id in get_affiliate_orders"
```

---

## Task 9: Fix `monetization_node` orphan Video row — scope lookup to `product_id IS NULL`

**Bug:** On restart, `monetization_node` finds an orphaned `Video` row (from a prior failed run) and overwrites its `affiliate_link` and `product_id` with the new product — corrupting the association.

**Files:**
- Modify: `tiktok_faceless/agents/monetization.py:79-94`
- Test: `tests/unit/agents/test_monetization.py`

**Step 1: Write the failing test**

Add to `tests/unit/agents/test_monetization.py`:

```python
def test_does_not_overwrite_video_with_existing_product_id(session) -> None:
    """A queued Video that already has a product_id must not be overwritten."""
    import uuid
    from tiktok_faceless.db.models import Video

    # Create an orphan video that already has a product_id
    orphan = Video(
        id=str(uuid.uuid4()),
        account_id="acc1",
        niche="health",
        lifecycle_state="queued",
        product_id="old_product",
        affiliate_link="https://old-link.com",
    )
    session.add(orphan)
    session.commit()

    # Now run monetization for a different product
    # ... setup mocks for monetization_node and run it
    # The orphan should NOT have its product_id overwritten
    from tiktok_faceless.db.models import Video as V
    rows = session.query(V).filter_by(account_id="acc1", product_id="old_product").all()
    assert len(rows) == 1, "Orphan video must not be overwritten"
```

Note: This test requires the full monetization_node test fixture. Look at existing tests in `test_monetization.py` for the mock setup pattern and replicate it.

**Step 2: Fix the Video lookup in `monetization.py` lines 79-94**

Change the filter to exclude videos that already have a `product_id`:

```python
    with get_session() as session:
        video = (
            session.query(Video)
            .filter_by(account_id=state.account_id, lifecycle_state="queued")
            .filter(Video.product_id.is_(None))     # ADD THIS FILTER
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
```

**Step 3: Run all monetization tests**

```bash
python -m pytest tests/unit/agents/test_monetization.py -v
```

Expected: All PASS.

**Step 4: Commit**

```bash
git add tiktok_faceless/agents/monetization.py tests/unit/agents/test_monetization.py
git commit -m "fix(monetization): scope queued Video lookup to product_id IS NULL to prevent orphan overwrite"
```

---

## Task 10: Fix `post_video` — actually send video bytes in upload

**Bug:** `post_video` opens the file handle but never reads it. The HTTP POST only sends JSON metadata, not the video binary.

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py:103-122`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `TestTikTokAPIClient` in `tests/unit/clients/test_tiktok.py`:

```python
def test_post_video_sends_file_bytes(self) -> None:
    """post_video must include the video file bytes in the HTTP request."""
    client = self._make_client()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {"video_id": "vid789", "share_url": None}
    }

    fake_file_content = b"fake video bytes"
    import io
    mock_file = io.BytesIO(fake_file_content)

    with (
        patch.object(client._http, "post", return_value=mock_response) as mock_post,
        patch("builtins.open", return_value=mock_file),
    ):
        client.post_video(
            account_id="acc1",
            video_path="/tmp/test.mp4",
            caption="Test caption",
        )

    # Verify the file bytes were passed to the HTTP call
    call_kwargs = mock_post.call_args
    # The file content must appear somewhere in the call (as data= or content= or files=)
    assert (
        call_kwargs.kwargs.get("content") == fake_file_content
        or call_kwargs.kwargs.get("data") == fake_file_content
        or any(fake_file_content in str(v) for v in call_kwargs.kwargs.values())
    ), "Video file bytes must be sent in the HTTP POST"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest "tests/unit/clients/test_tiktok.py::TestTikTokAPIClient::test_post_video_sends_file_bytes" -v
```

Expected: FAIL — file handle is opened but file contents not sent.

**Step 3: Fix `post_video` in `tiktok.py`**

The current TikTok Content Posting API flow requires two calls: `init` (get upload URL) then upload the bytes. For now, fix the `init` call to include the file size, and add a second call to upload the bytes to the upload URL returned:

```python
@api_retry
def post_video(
    self, account_id: str, video_path: str, caption: str
) -> TikTokPostResponse:
    """Upload and publish a video. Returns TikTokPostResponse with video_id."""
    self._bucket.consume()
    import os
    file_size = os.path.getsize(video_path)

    # Step 1: Init upload
    init_response = self._http.post(
        "/v2/post/publish/video/init/",
        json={
            "post_info": {"title": caption, "privacy_level": "SELF_ONLY"},
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
    )
    self._handle_response(init_response)
    data = init_response.json()["data"]
    upload_url = data.get("upload_url", "")
    publish_id = data.get("publish_id", "")

    # Step 2: Upload the video bytes
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_response = self._http.put(
        upload_url,
        content=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        },
    )
    self._handle_response(upload_response)

    return TikTokPostResponse(
        video_id=publish_id,
        share_url=data.get("share_url"),
    )
```

Note: `upload_url` in TikTok's API is an absolute URL, so use `httpx.Client` directly for that PUT, not `self._http` which has `base_url` set. Adjust if needed.

**Step 4: Run all post_video tests**

```bash
python -m pytest tests/unit/clients/test_tiktok.py -v
```

Expected: All PASS (update test mock if needed to match new two-step API flow).

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "fix(tiktok): post_video now sends video bytes in two-step init+upload flow"
```

---

## Task 11: Fix `get_affiliate_orders` — add 7-day date window to request

**Bug:** No date filter sent to the API. `affiliate_commission_week` accumulates all historical orders, not just the last 7 days.

**Files:**
- Modify: `tiktok_faceless/clients/tiktok.py:186-202`
- Test: `tests/unit/clients/test_tiktok.py`

**Step 1: Write the failing test**

Add to `TestGetAffiliateOrders`:

```python
def test_sends_date_window_in_request(self) -> None:
    """get_affiliate_orders must send a start_date 7 days ago in the request body."""
    from datetime import datetime, timedelta, timezone
    client = TikTokAPIClient(access_token="tok", open_id="oid")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"orders": []}}

    with patch.object(client._http, "post", return_value=mock_response) as mock_post:
        client.get_affiliate_orders(account_id="acc1")

    call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json", {})
    assert "start_date" in call_json, "start_date must be included in the request body"
    # Verify start_date is approximately 7 days ago
    start = datetime.fromisoformat(call_json["start_date"])
    expected = datetime.now(timezone.utc) - timedelta(days=7)
    assert abs((start - expected).total_seconds()) < 60, "start_date must be ~7 days ago"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest "tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders::test_sends_date_window_in_request" -v
```

Expected: FAIL.

**Step 3: Fix `get_affiliate_orders` in `tiktok.py`**

```python
@api_retry
def get_affiliate_orders(self, account_id: str) -> list[CommissionRecord]:
    """Fetch affiliate commission orders for the last 7 days."""
    from datetime import datetime, timedelta, timezone
    self._bucket.consume()
    start_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    response = self._http.post(
        "/v2/tiktok_shop/affiliate/orders/",
        json={"open_id": self._open_id, "start_date": start_date},
    )
    self._handle_response(response)
    orders = response.json().get("data", {}).get("orders", [])
    records = []
    for o in orders:
        order_id = o.get("order_id")
        product_id = o.get("product_id")
        if not order_id or not product_id:
            continue
        records.append(
            CommissionRecord(
                order_id=str(order_id),
                product_id=str(product_id),
                commission_amount=float(o.get("commission_amount", 0.0)),
            )
        )
    return records
```

**Step 4: Run all affiliate order tests**

```bash
python -m pytest tests/unit/clients/test_tiktok.py::TestGetAffiliateOrders -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add tiktok_faceless/clients/tiktok.py tests/unit/clients/test_tiktok.py
git commit -m "fix(tiktok): send 7-day start_date window in get_affiliate_orders request"
```

---

## Task 12: Run full test suite — verify all fixes pass

**Step 1: Run the complete test suite**

```bash
cd /Users/ivanma/Desktop/agents/tiktok-faceless
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: All tests PASS with no failures.

**Step 2: If any test fails, investigate and fix before proceeding.**

**Step 3: Final commit if any cleanup needed**

```bash
git add -p
git commit -m "fix: final cleanup after code review fixes"
```

---

## Summary of All Fixes

| Task | File(s) | Bug Fixed |
|------|---------|-----------|
| 1 | `clients/tiktok.py` | TokenBucket deadlock — sleep outside lock |
| 2 | `db/models.py`, `db/queries.py` | Missing UNIQUE constraint + niche not updated on upsert |
| 3 | `models/shop.py`, `agents/research.py` | Comment mining called with product_id instead of video_id |
| 4 | `agents/research.py` | Tournament live path uses `products[0]` not `max(score)` |
| 5 | `agents/research.py` | `niche_decay_alert` never cleared on recovery |
| 6 | `agents/research.py` | Rate-limit errors swallowed silently in tournament scan |
| 7 | `utils/retry.py`, `clients/llm.py`, `agents/script.py` | No LLM retry + all-or-nothing failure mode |
| 8 | `clients/tiktok.py` | KeyError on malformed orders in `get_affiliate_orders` |
| 9 | `agents/monetization.py` | Orphan Video row overwritten on restart |
| 10 | `clients/tiktok.py` | `post_video` never sends file bytes |
| 11 | `clients/tiktok.py` | No date filter in `get_affiliate_orders` — accumulates all history |
| 12 | All | Full test suite verification |
