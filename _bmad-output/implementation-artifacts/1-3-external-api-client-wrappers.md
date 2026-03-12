# Story 1.3: External API Client Wrappers

Status: review

## Story

As the system,
I want typed client wrapper classes for TikTok, ElevenLabs, Creatomate, fal.ai, and the LLM API with retry logic and rate limiting,
So that agents can call external services safely without writing raw HTTP and all failures surface as typed exceptions.

## Acceptance Criteria

1. **Given** any client method is called, **When** the external API responds, **Then** the call goes through the typed wrapper class — never a raw `requests` or `httpx` call from agent code **And** all responses are parsed into Pydantic models before returning to the caller

2. **Given** an external API returns a rate limit error (429) or transient failure, **When** the client wrapper catches the response, **Then** `tenacity` retries up to 3 times with exponential backoff (4s → 16s → 30s) **And** after 3 failures a typed exception is raised (`TikTokRateLimitError`, `ElevenLabsError`, `RenderError`, etc.)

3. **Given** `TikTokAPIClient` is instantiated, **When** `post_video()` is called, **Then** the token bucket enforces max 6 requests/min per OAuth token **And** `get_metrics()` returns a `TikTokVideoMetrics` Pydantic model

4. **Given** `ElevenLabsClient` is instantiated, **When** `generate_voiceover(text, voice_id)` is called, **Then** audio bytes are returned on success **And** `ElevenLabsError` is raised (not swallowed) on API failure

5. **Given** `CreatomateClient` is instantiated, **When** `submit_render(template_id, data)` is called, **Then** a render job ID is returned **And** `poll_status(job_id)` returns status until complete or raises `RenderError` on failure

6. **Given** `LLMClient` is instantiated, **When** `generate_script(prompt)` is called, **Then** the call uses `claude-haiku-4-5-20251001` model **And** the response is returned as a string

7. **Given** all clients are implemented, **When** `uv run pytest` is run, **Then** all unit tests pass with zero failures **And** `uv run ruff check .` and `uv run mypy tiktok_faceless/` exit 0

## Tasks / Subtasks

- [x] Task 1: Define typed exceptions in `tiktok_faceless/clients/__init__.py` (AC: 2)
  - [x] Define `TikTokRateLimitError(Exception)` — raised after 3 rate-limit retries
  - [x] Define `TikTokAuthError(Exception)` — raised on 401/403 responses
  - [x] Define `TikTokAPIError(Exception)` — generic TikTok API error
  - [x] Define `ElevenLabsError(Exception)` — raised on any ElevenLabs API failure
  - [x] Define `RenderError(Exception)` — raised on Creatomate render failure or timeout
  - [x] Define `FalError(Exception)` — raised on fal.ai API failure
  - [x] Define `LLMError(Exception)` — raised on LLM API failure
  - [x] Write unit test `tests/unit/clients/test_exceptions.py` confirming all exceptions are importable and are subclasses of `Exception`

- [x] Task 2: Define Pydantic response models in `tiktok_faceless/models/` (AC: 1, 3)
  - [x] In `models/tiktok.py`: define `TikTokVideoMetrics(BaseModel)` with fields: `video_id: str`, `view_count: int`, `like_count: int`, `comment_count: int`, `share_count: int`, `average_time_watched: float`, `traffic_source_type: dict[str, float]`
  - [x] In `models/tiktok.py`: define `TikTokPostResponse(BaseModel)` with fields: `video_id: str`, `share_url: str | None = None`
  - [x] In `models/elevenlabs.py`: define `ElevenLabsVoiceConfig(BaseModel)` with fields: `voice_id: str`, `stability: float = 0.5`, `similarity_boost: float = 0.75`, `style: float = 0.0`
  - [x] In `models/shop.py`: define `AffiliateProduct(BaseModel)` with fields: `product_id: str`, `product_name: str`, `product_url: str`, `commission_rate: float`, `sales_velocity_score: float = 0.0`, `niche: str`
  - [x] In `models/shop.py`: define `CommissionRecord(BaseModel)` with fields: `order_id: str`, `product_id: str`, `commission_amount: float`, `recorded_at: float = Field(default_factory=time.time)`
  - [x] Write unit test `tests/unit/clients/test_models.py` covering instantiation and field defaults for all models

- [x] Task 3: Implement shared retry decorator in `tiktok_faceless/utils/retry.py` (AC: 2)
  - [x] Import `tenacity`: `retry`, `stop_after_attempt`, `wait_exponential`, `retry_if_exception_type`
  - [x] Define `api_retry` decorator: 3 attempts, `wait_exponential(multiplier=1, min=4, max=30)`, retries on `httpx.HTTPStatusError` and `httpx.TransportError`
  - [x] Define `render_retry` decorator: 5 attempts, `wait_exponential(multiplier=2, min=5, max=60)` — longer waits for render polling
  - [x] Export both from `utils/retry.py`
  - [x] Write unit test `tests/unit/utils/test_retry.py` verifying retry counts and that non-retryable exceptions propagate immediately

- [x] Task 4: Implement `tiktok_faceless/clients/tiktok.py` — TikTokAPIClient (AC: 3)
  - [x] Implement `TokenBucket` class: `max_tokens: int = 6`, `refill_period: float = 60.0`, `consume()` blocks until a token is available using `time.sleep()`
  - [x] Implement `TikTokAPIClient` with `__init__(self, access_token: str, open_id: str)` — stores credentials, instantiates `TokenBucket` and `httpx.Client`
  - [x] Implement `post_video(self, account_id: str, video_path: str, caption: str) -> TikTokPostResponse` — calls token bucket before each request, applies `@api_retry`, raises `TikTokRateLimitError` / `TikTokAuthError` on mapped HTTP errors
  - [x] Implement `get_metrics(self, account_id: str, video_id: str) -> TikTokVideoMetrics` — applies `@api_retry`, returns parsed Pydantic model
  - [x] Implement `generate_affiliate_link(self, account_id: str, product_id: str) -> str` — returns affiliate URL string
  - [x] Use `httpx.Client` (sync) with `base_url="https://open.tiktokapis.com"` and `Authorization: Bearer {token}` header
  - [x] Write unit tests `tests/unit/clients/test_tiktok.py` using `httpx.MockTransport` or `unittest.mock.patch` — test: token bucket allows 6 calls/min, 7th call is delayed; 429 response triggers retry; 401 raises `TikTokAuthError` without retry; successful response returns `TikTokVideoMetrics`

- [x] Task 5: Implement `tiktok_faceless/clients/elevenlabs.py` — ElevenLabsClient (AC: 4)
  - [x] Implement `ElevenLabsClient` with `__init__(self, api_key: str)` — stores key, instantiates `httpx.Client`
  - [x] Implement `generate_voiceover(self, text: str, voice_id: str, config: ElevenLabsVoiceConfig | None = None) -> bytes` — POSTs to `/v1/text-to-speech/{voice_id}`, applies `@api_retry`, returns raw audio bytes on success, raises `ElevenLabsError` on failure
  - [x] Use `base_url="https://api.elevenlabs.io"` and `xi-api-key: {api_key}` header
  - [x] Write unit tests `tests/unit/clients/test_elevenlabs.py` — test: successful call returns bytes; non-200 response raises `ElevenLabsError`; retry fires on 500

- [x] Task 6: Implement `tiktok_faceless/clients/creatomate.py` — CreatomateClient (AC: 5)
  - [x] Implement `CreatomateClient` with `__init__(self, api_key: str)` — stores key, instantiates `httpx.Client`
  - [x] Implement `submit_render(self, template_id: str, data: dict[str, str]) -> str` — POSTs to `/v1/renders`, returns render job `id` string, applies `@api_retry`, raises `RenderError` on failure
  - [x] Implement `poll_status(self, job_id: str, timeout_seconds: int = 600) -> str` — GETs `/v1/renders/{job_id}`, polls until status is `"succeeded"` or `"failed"`, raises `RenderError` on failure or timeout, uses `render_retry`
  - [x] Implement `download_render(self, output_url: str, dest_path: str) -> str` — downloads rendered file to `dest_path`, returns path
  - [x] Use `base_url="https://api.creatomate.com"` and `Authorization: Bearer {api_key}` header
  - [x] Write unit tests `tests/unit/clients/test_creatomate.py` — test: submit returns job ID; poll succeeds on status=succeeded; poll raises `RenderError` on status=failed; poll raises `RenderError` on timeout

- [x] Task 7: Implement `tiktok_faceless/clients/llm.py` — LLMClient (AC: 6)
  - [x] Implement `LLMClient` with `__init__(self, api_key: str)` — instantiates `anthropic.Anthropic(api_key=api_key)`
  - [x] Implement `generate_script(self, prompt: str, max_tokens: int = 1024) -> str` — calls `client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])`, returns `response.content[0].text`, applies `@api_retry`, raises `LLMError` on failure
  - [x] Write unit tests `tests/unit/clients/test_llm.py` — test: successful call returns string; API exception raises `LLMError`; correct model `claude-haiku-4-5-20251001` is used

- [x] Task 8: Implement `tiktok_faceless/clients/fal.py` — FalClient (AC: 1)
  - [x] Implement `FalClient` with `__init__(self, api_key: str)` — stores key
  - [x] Implement `generate_video(self, prompt: str, image_url: str | None = None) -> str` — submits Kling video generation job via fal.ai Python SDK (`fal_client.submit`), returns output video URL, raises `FalError` on failure
  - [x] Write unit test `tests/unit/clients/test_fal.py` — test: fal_client.submit called with correct arguments; `FalError` raised on exception

- [x] Task 9: Run all validations (AC: 7)
  - [x] Run `uv run pytest` — all tests must pass
  - [x] Run `uv run ruff check .` — must exit 0
  - [x] Run `uv run mypy tiktok_faceless/` — must exit 0

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS

1. **Agents NEVER call external APIs directly** — all HTTP calls go through client classes in `clients/`. This is a hard boundary.

2. **`httpx` not `requests`** — `requests` is not installed. Use `httpx.Client` (sync) for all HTTP. Import pattern: `import httpx`.

3. **`@api_retry` on all external calls** — every method that makes an HTTP call must have the retry decorator from `utils/retry.py`. No exceptions.

4. **Token bucket in `TikTokAPIClient` only** — rate limiting is the client's responsibility, not the agent's. The token bucket must block (not raise) when the bucket is empty.

5. **Pydantic v2 response models** — all API responses are parsed through Pydantic models before returning to callers. Agents receive typed objects, never raw dicts.

6. **Typed exceptions from `clients/__init__.py`** — agent nodes catch these at their boundary and convert to `AgentError` state deltas. Clients raise, agents catch.

### Retry Decorator Implementation

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    reraise=True,
)
```

**Important:** `reraise=True` ensures the original exception type is preserved after retries exhausted. Without this, tenacity raises its own `RetryError`.

### Token Bucket Implementation

```python
import time
import threading

class TokenBucket:
    def __init__(self, max_tokens: int = 6, refill_period: float = 60.0) -> None:
        self._max_tokens = max_tokens
        self._tokens = float(max_tokens)
        self._refill_period = refill_period
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                float(self._max_tokens),
                self._tokens + elapsed * (self._max_tokens / self._refill_period)
            )
            self._last_refill = now
            if self._tokens < 1:
                wait = (1 - self._tokens) * (self._refill_period / self._max_tokens)
                time.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0
```

### TikTok HTTP Error Mapping

```python
def _handle_response(self, response: httpx.Response) -> None:
    if response.status_code == 429:
        raise TikTokRateLimitError(f"Rate limited: {response.text}")
    if response.status_code in (401, 403):
        raise TikTokAuthError(f"Auth error {response.status_code}: {response.text}")
    response.raise_for_status()  # raises httpx.HTTPStatusError for other 4xx/5xx
```

Note: `TikTokRateLimitError` and `TikTokAuthError` should NOT be in the `retry_if_exception_type` list — they should propagate immediately. Only `httpx.HTTPStatusError` (5xx) and `httpx.TransportError` (network) should retry.

### Anthropic SDK Usage (LLMClient)

The `anthropic` package is already installed. Use it directly:

```python
import anthropic

class LLMClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_script(self, prompt: str, max_tokens: int = 1024) -> str:
        message = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(message.content[0].text)  # type: ignore[union-attr]
```

### fal.ai SDK Usage

The `fal-client` package needs to be added: `uv add fal-client`. Use:

```python
import fal_client

result = fal_client.submit(
    "fal-ai/kling-video/v1.6/standard/text-to-video",
    arguments={"prompt": prompt},
)
```

### Testing Strategy — No Real API Calls

All client tests use mocks. Preferred pattern:

```python
from unittest.mock import MagicMock, patch

def test_get_metrics_returns_model(self) -> None:
    with patch("httpx.Client") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "video_id": "vid_123",
            "view_count": 1000,
            ...
        }
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        result = client.get_metrics(account_id="acc1", video_id="vid_123")
        assert isinstance(result, TikTokVideoMetrics)
        assert result.view_count == 1000
```

For retry tests, use `tenacity`'s testing utilities or count call attempts manually.

### File Touch Map

**Implement (placeholder → full):**
- `tiktok_faceless/clients/__init__.py` — typed exceptions
- `tiktok_faceless/clients/tiktok.py`
- `tiktok_faceless/clients/elevenlabs.py`
- `tiktok_faceless/clients/creatomate.py`
- `tiktok_faceless/clients/fal.py`
- `tiktok_faceless/clients/llm.py`
- `tiktok_faceless/utils/retry.py`
- `tiktok_faceless/models/tiktok.py`
- `tiktok_faceless/models/elevenlabs.py`
- `tiktok_faceless/models/shop.py`

**Create new:**
- `tests/unit/clients/__init__.py` (if not exists)
- `tests/unit/clients/test_exceptions.py`
- `tests/unit/clients/test_models.py`
- `tests/unit/clients/test_tiktok.py`
- `tests/unit/clients/test_elevenlabs.py`
- `tests/unit/clients/test_creatomate.py`
- `tests/unit/clients/test_llm.py`
- `tests/unit/clients/test_fal.py`
- `tests/unit/utils/test_retry.py`

**Do NOT touch:**
- `tiktok_faceless/agents/*.py` — still placeholders
- `tiktok_faceless/state.py`, `config.py`, `db/` — done in 1.2, don't modify

### Dependencies to Add

Before implementing, run:
```bash
uv add fal-client anthropic
```

`anthropic` may already be installed transitively — check first. `fal-client` is new.

### Previous Story Learnings

- Write tool requires prior Read for existing files — use Read before every Write/Edit
- SQLAlchemy 2.0 `Mapped[]` + `ForeignKey()` must be explicit — `index=True` on `mapped_column` creates implicit index, don't also add in `__table_args__`
- ruff line length 100 — keep test assertions on multiple lines for long strings
- mypy strict: all functions need return type annotations; `dict` type args need explicit `[K, V]`

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "API Patterns", "Implementation Patterns > Process Patterns", "Naming Patterns > Typed exceptions"
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.3 (lines 306–343)
- Retry spec: architecture.md — "tenacity @retry on all external API calls (mandatory)"
- Rate limit spec: architecture.md — "Token bucket enforced in client wrappers (6 req/min TikTok)"

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 9 tasks completed. 78 tests pass (up from 38 in Story 1.2).
- `clients/__init__.py`: 7 typed exceptions — `TikTokRateLimitError`, `TikTokAuthError`, `TikTokAPIError`, `ElevenLabsError`, `RenderError`, `FalError`, `LLMError`.
- `utils/retry.py`: `api_retry` (3 attempts, 4s→30s, retries on `httpx.HTTPStatusError`/`TransportError`, `reraise=True`) and `render_retry` (5 attempts, 5s→60s).
- `clients/tiktok.py`: `TokenBucket` (thread-safe, 6 req/min), `TikTokAPIClient` with `_handle_response` mapping 429→`TikTokRateLimitError`, 401/403→`TikTokAuthError`. `get_metrics` uses POST (TikTok Analytics API requires POST for queries).
- `clients/elevenlabs.py`: `ElevenLabsClient.generate_voiceover` returns `bytes`, raises `ElevenLabsError` on non-200.
- `clients/creatomate.py`: `CreatomateClient` with `submit_render`, `poll_status` (deadline-based loop), `download_render`.
- `clients/llm.py`: `LLMClient` using `claude-haiku-4-5-20251001`, wraps all exceptions in `LLMError`.
- `clients/fal.py`: `FalClient` using `fal_client.submit` with Kling endpoint.
- `models/`: `TikTokVideoMetrics`, `TikTokPostResponse`, `ElevenLabsVoiceConfig`, `AffiliateProduct`, `CommissionRecord` — all Pydantic v2 BaseModel.
- Added `fal-client>=0.13.1` and `anthropic>=0.84.0` to `pyproject.toml`.
- All checks: `pytest` (78/78), `ruff check .` (0 errors), `mypy tiktok_faceless/` (0 issues in 35 files).

### File List

**Implemented (placeholder → full):**
- `tiktok_faceless/clients/__init__.py`
- `tiktok_faceless/clients/tiktok.py`
- `tiktok_faceless/clients/elevenlabs.py`
- `tiktok_faceless/clients/creatomate.py`
- `tiktok_faceless/clients/fal.py`
- `tiktok_faceless/clients/llm.py`
- `tiktok_faceless/utils/retry.py`
- `tiktok_faceless/models/tiktok.py`
- `tiktok_faceless/models/elevenlabs.py`
- `tiktok_faceless/models/shop.py`
- `pyproject.toml` (added fal-client, anthropic deps)

**Created new:**
- `tests/unit/clients/__init__.py`
- `tests/unit/clients/test_exceptions.py`
- `tests/unit/clients/test_models.py`
- `tests/unit/clients/test_tiktok.py`
- `tests/unit/clients/test_elevenlabs.py`
- `tests/unit/clients/test_creatomate.py`
- `tests/unit/clients/test_llm.py`
- `tests/unit/clients/test_fal.py`
- `tests/unit/utils/__init__.py`
- `tests/unit/utils/test_retry.py`
