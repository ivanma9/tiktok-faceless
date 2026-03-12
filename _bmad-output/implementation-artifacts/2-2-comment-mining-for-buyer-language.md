# Story 2.2: Comment Mining for Buyer Language

Status: ready-for-dev

## Story

As the operator,
I want the Research Agent to mine comments from top-performing affiliate videos for the validated product,
so that scripts use authentic buyer language that converts — not generic AI copy.

## Acceptance Criteria

1. **Given** a validated product in `state["selected_product"]`
   **When** `research_node` executes comment mining
   **Then** `TikTokAPIClient` fetches comments from the top N affiliate videos for that product
   **And** buyer-intent phrases are extracted (e.g. "where can I get this", price objections, social proof language)
   **And** the extracted buyer language is stored in `state["selected_product"]["buyer_language"]`

2. **Given** buyer language is extracted
   **When** `script_node` is called in Story 2.4
   **Then** the script prompt includes the extracted buyer phrases
   **And** the generated script contains at least one buyer-language phrase from the research output

3. **Given** the TikTok API returns no comments for a product
   **When** comment mining completes
   **Then** `buyer_language` is set to an empty list (not an error)
   **And** script generation proceeds with product details only — no pipeline halt

## Tasks / Subtasks

- [ ] Task 4: Add `get_video_comments()` to `TikTokAPIClient` (AC: #1)
  - [ ] POST `/v2/video/comment/list/` endpoint
  - [ ] Accepts `video_id: str` and `max_count: int = 20`
  - [ ] Returns `list[str]` of comment texts (not raw API objects)
  - [ ] Returns empty list when no comments — not an error, not a raise
  - [ ] Raises `TikTokRateLimitError` on 429, `TikTokAuthError` on 401/403, `TikTokAPIError` on other 4xx/5xx
  - [ ] Decorated with `@api_retry` (same as all other client methods)
  - [ ] Tests in `tests/unit/clients/test_tiktok.py` — new class `TestGetVideoComments`

- [ ] Task 5: Extend `research_node` with comment mining (AC: #1, #2, #3)
  - [ ] After computing `best` product (both cache-hit and live-fetch paths), call `get_video_comments(video_id=best["product_id"], max_count=20)`
  - [ ] Store result as `buyer_language` key in the `selected_product` dict before returning
  - [ ] Non-fatal: empty comment list → `buyer_language=[]`, pipeline continues normally
  - [ ] API error on comments → `buyer_language=[]`, pipeline continues (do NOT raise, do NOT add AgentError)
  - [ ] Tests in `tests/unit/agents/test_research.py` — extend existing test classes

## Dev Notes

### Critical Architecture Rules (from `architecture.md`)

- **Agent node returns state delta dict only** — never `return state`, never mutate `state` in place
- **Never call external APIs from agent code directly** — always through `TikTokAPIClient`
- **All DB access through `db/queries.py`** — agents never touch SQLAlchemy sessions directly
- **`account_id` as first scope parameter** — every DB query and API call is scoped by `account_id`
- **All errors returned as `AgentError` Pydantic model** in `{"errors": [AgentError(...)]}` delta — but comment API errors are non-fatal and must NOT produce AgentError entries
- **Phase does NOT change in `research_node`** — `orchestrator.py` is the ONLY file that writes `state["phase"]`
- **No hardcoded thresholds** — `min_commission_rate` and `min_sales_velocity` come from `AccountConfig`

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/clients/tiktok.py` | Add `get_video_comments()` method |
| `tiktok_faceless/agents/research.py` | Extend `research_node` to call `get_video_comments` and store `buyer_language` |
| `tests/unit/clients/test_tiktok.py` | Add `TestGetVideoComments` class |
| `tests/unit/agents/test_research.py` | Add comment mining test cases |

### Do NOT Touch

- `tiktok_faceless/state.py` — `PipelineState`, `AgentError`, `selected_product: dict | None` already correct; `buyer_language` lives inside the `selected_product` dict, not as a top-level state key
- `tiktok_faceless/db/models.py` — no schema change in Story 2.2
- `tiktok_faceless/db/queries.py` — no new queries needed
- `tiktok_faceless/config.py` — already has `min_commission_rate` and `min_sales_velocity` from Story 2.1
- Any other agent files — this story only touches the research pipeline

### `get_video_comments()` — Implementation Pattern

Add this method to `TikTokAPIClient` in `tiktok_faceless/clients/tiktok.py`, after `get_validated_products()` and before `close()`:

```python
@api_retry
def get_video_comments(self, account_id: str, video_id: str, max_count: int = 20) -> list[str]:
    """
    Fetch comment texts for a single video from TikTok Comment API.
    Returns list of comment text strings. Returns empty list when no comments — not an error.
    """
    self._bucket.consume()
    response = self._http.post(
        "/v2/video/comment/list/",
        json={"video_id": video_id, "max_count": max_count, "open_id": self._open_id},
    )
    self._handle_response(response)
    comments = response.json().get("data", {}).get("comments", [])
    return [str(c["text"]) for c in comments if c.get("text")]
```

Key points:
- `_handle_response` is called before `.json()` — same pattern as all other methods
- Empty `comments` list (API returns `[]` or missing key) → return `[]`, no exception
- Comments without `"text"` key are filtered out silently
- `account_id` parameter accepted for interface consistency even though it's not sent in the JSON body (open_id scopes the request)

### `research_node` Extension Pattern

The current `research_node` in `tiktok_faceless/agents/research.py` has two return paths that set `selected_product`:
1. Cache hit path (line ~51–55): `best = max(cached, ...)` → returns immediately
2. Live fetch path (line ~107–110): `best = products[0]` → returns immediately

Both paths must be extended to call `get_video_comments` and inject `buyer_language` into the dict before returning.

**Exact pattern to add to BOTH return paths:**

```python
# After computing `best` (AffiliateProduct) and before returning:
product_dict = best.model_dump()
try:
    comments = client.get_video_comments(
        account_id=state.account_id,
        video_id=best.product_id,
        max_count=20,
    )
except (TikTokRateLimitError, TikTokAPIError):
    comments = []
product_dict["buyer_language"] = comments
return {
    "selected_product": product_dict,
    "product_validated": True,
}
```

**Important:** The cache-hit path currently returns before creating `client`. For the cache-hit path, you must instantiate `TikTokAPIClient` before calling `get_video_comments`. The client is already instantiated in the live-fetch path — reuse it there.

**Revised cache-hit path:**

```python
if cached:
    best = max(cached, key=lambda p: p.sales_velocity_score)
    config = load_account_config(state.account_id)  # already called above
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )
    product_dict = best.model_dump()
    try:
        comments = client.get_video_comments(
            account_id=state.account_id,
            video_id=best.product_id,
            max_count=20,
        )
    except (TikTokRateLimitError, TikTokAPIError):
        comments = []
    product_dict["buyer_language"] = comments
    return {"selected_product": product_dict, "product_validated": True}
```

Note: `config = load_account_config(state.account_id)` is already called before the cache check in the current implementation — do NOT call it twice. The client instantiation moves inside the `if cached:` block.

**Revised live-fetch path (end of function):**

```python
best = products[0]  # already sorted descending
product_dict = best.model_dump()
try:
    comments = client.get_video_comments(
        account_id=state.account_id,
        video_id=best.product_id,
        max_count=20,
    )
except (TikTokRateLimitError, TikTokAPIError):
    comments = []
product_dict["buyer_language"] = comments
return {"selected_product": product_dict, "product_validated": True}
```

### Mock Pattern for `get_video_comments` in Tests

Patch at the import location — `TikTokAPIClient` is already mocked via `patch(f"{_MOD}.TikTokAPIClient")`. Add `get_video_comments` to the mock client:

```python
mock_client = MagicMock()
mock_client.get_validated_products.return_value = [_PRODUCT]
mock_client.get_video_comments.return_value = ["where can I get this", "does this work?"]
mock_client_cls.return_value = mock_client
```

For the cache-hit path test, `get_validated_products` is not called but `get_video_comments` IS called — the mock client still needs it:

```python
mock_client = MagicMock()
mock_client.get_video_comments.return_value = ["amazing product", "just bought it"]
mock_client_cls.return_value = mock_client
```

For the comment API error test, configure the mock to raise:

```python
mock_client.get_video_comments.side_effect = TikTokAPIError("500: server error")
```

Import `TikTokAPIError` in the test file:
```python
from tiktok_faceless.clients import TikTokAPIError
```

### Previous Story Learnings (from Story 2.1)

- `AccountConfig` in `config.py` now has `min_commission_rate: float` and `min_sales_velocity: float` — do not re-add them
- Mock config pattern: `_mock_config()` helper already in `test_research.py` — extend it if needed, don't duplicate
- `get_session()` mock pattern: `ctx.__enter__ = MagicMock(return_value=MagicMock()); ctx.__exit__ = MagicMock(return_value=False)`
- Patch at import location: `_MOD = "tiktok_faceless.agents.research"` constant already in test file
- Import sort: stdlib → third-party → local (ruff I001 enforced)
- Line length ≤ 100 chars (ruff E501 enforced)
- `dict[str, Any]` return type on `research_node`
- `@api_retry` decorator on all `TikTokAPIClient` methods (imported from `tiktok_faceless.utils.retry`)

### Required Test Cases — Task 4: `TestGetVideoComments`

Add to `tests/unit/clients/test_tiktok.py`:

```python
class TestGetVideoComments:
    def _make_client(self) -> TikTokAPIClient:
        return TikTokAPIClient(access_token="test_token", open_id="test_open_id")

    def test_returns_comment_texts(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "comments": [
                    {"text": "where can I get this?"},
                    {"text": "just bought it, amazing!"},
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.get_video_comments(account_id="acc1", video_id="vid_abc")
        assert result == ["where can I get this?", "just bought it, amazing!"]

    def test_returns_empty_list_when_no_comments(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"comments": []}}
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.get_video_comments(account_id="acc1", video_id="vid_abc")
        assert result == []

    def test_returns_empty_list_when_data_key_missing(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.get_video_comments(account_id="acc1", video_id="vid_abc")
        assert result == []

    def test_429_raises_rate_limit_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "rate limited"
        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(TikTokRateLimitError):
                client.get_video_comments(account_id="acc1", video_id="vid_abc")

    def test_filters_comments_missing_text_key(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "comments": [
                    {"text": "good product"},
                    {"likes": 5},  # no "text" key — should be filtered
                    {"text": ""},  # empty string — falsy, filtered
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            result = client.get_video_comments(account_id="acc1", video_id="vid_abc")
        assert result == ["good product"]
```

### Required Test Cases — Task 5: Comment Mining in `test_research.py`

Add these test cases to `tests/unit/agents/test_research.py`. Use the existing `_MOD`, `_PRODUCT`, `_STATE`, `_mock_config()`, and `_mock_session_ctx()` helpers.

```python
class TestResearchNodeCommentMining:
    def test_buyer_language_added_to_selected_product_on_live_fetch(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = [
                "where can I get this?",
                "just ordered!",
            ]
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["buyer_language"] == [
            "where can I get this?",
            "just ordered!",
        ]
        mock_client.get_video_comments.assert_called_once_with(
            account_id="acc1",
            video_id="p1",
            max_count=20,
        )

    def test_buyer_language_added_on_cache_hit(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[_PRODUCT]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_video_comments.return_value = ["amazing, just bought it"]
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result["selected_product"]["buyer_language"] == ["amazing, just bought it"]
        mock_client.get_validated_products.assert_not_called()

    def test_comment_api_error_sets_empty_buyer_language_no_pipeline_halt(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.side_effect = TikTokAPIError("500: server error")
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["buyer_language"] == []
        assert "errors" not in result  # comment failure is non-fatal

    def test_no_comments_sets_empty_buyer_language(self) -> None:
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.TikTokAPIClient") as mock_client_cls,
            patch(f"{_MOD}.get_session", return_value=_mock_session_ctx()),
            patch(f"{_MOD}.get_cached_products", return_value=[]),
            patch(f"{_MOD}.cache_product"),
        ):
            mock_client = MagicMock()
            mock_client.get_validated_products.return_value = [_PRODUCT]
            mock_client.get_video_comments.return_value = []
            mock_client_cls.return_value = mock_client

            result = research_node(_STATE)

        assert result["product_validated"] is True
        assert result["selected_product"]["buyer_language"] == []
        assert "errors" not in result
```

Also update existing tests in `TestResearchNodeSuccess` to include `get_video_comments` on the mock client (so they don't fail on AttributeError after the extension):

```python
# In test_sets_selected_product_and_validated:
mock_client.get_video_comments.return_value = []

# In test_uses_cache_when_within_ttl:
mock_client.get_video_comments.return_value = []
```

### Import Addition for Test File

Add this import to `tests/unit/agents/test_research.py` (after existing client imports):
```python
from tiktok_faceless.clients import TikTokAPIError
```

### TikTok Comment API — Endpoint Reference

- Endpoint: `POST /v2/video/comment/list/`
- Request body: `{"video_id": "<id>", "max_count": 20, "open_id": "<open_id>"}`
- Response shape: `{"data": {"comments": [{"text": "...", ...}, ...]}}`
- The `comments` key may be absent or empty — treat both as `[]`

### References

- Architecture patterns: `_bmad-output/planning-artifacts/architecture.md` — Agent Boundary, State Delta pattern, Error Contract
- Epic 2 story spec: `_bmad-output/planning-artifacts/epics.md` — Story 2.2 (lines 518–541)
- Previous story: `_bmad-output/implementation-artifacts/2-1-product-validation-via-buyer-intent-signals.md`
- `AffiliateProduct` model: `tiktok_faceless/models/shop.py`
- `TikTokAPIClient` current implementation: `tiktok_faceless/clients/tiktok.py`
- `research_node` current implementation: `tiktok_faceless/agents/research.py`
- `api_retry` decorator: `tiktok_faceless/utils/retry.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `tiktok_faceless/clients/tiktok.py` — add `get_video_comments()`
- `tiktok_faceless/agents/research.py` — extend `research_node` with comment mining
- `tests/unit/clients/test_tiktok.py` — add `TestGetVideoComments` class (5 test cases)
- `tests/unit/agents/test_research.py` — add `TestResearchNodeCommentMining` class (4 test cases) + update 2 existing tests
