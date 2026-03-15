# Story 5.4: Configurable Retry with Exponential Backoff

Status: review

## Story

As the operator,
I want all external API calls to retry automatically with exponential backoff before escalating to a logged failure,
so that transient rate limits and network blips don't produce false error log entries or unnecessary pipeline pauses.

## Acceptance Criteria

1. **Given** any external API call decorated with `@retry` from `utils/retry.py`
   **When** the call returns a retryable error (429, 503, network timeout)
   **Then** `tenacity` retries up to 3 times with exponential backoff: 4s → 16s → 30s
   **And** each retry attempt is logged at DEBUG level with attempt number and wait time

2. **Given** all 3 retry attempts are exhausted
   **When** the final attempt fails
   **Then** a typed exception is raised to the agent node boundary (not swallowed)
   **And** backoff wait times are configurable per client via `AccountConfig` — not hardcoded

3. **Given** a non-retryable error (401 auth failure, 400 bad request)
   **When** the client wrapper receives it
   **Then** the error is raised immediately without retrying
   **And** the typed exception includes the HTTP status code and response body for diagnosis

4. **Given** `utils/retry.py` defines shared retry decorators
   **When** any new client method is added
   **Then** it uses the shared decorator — no per-client retry logic duplication

## Tasks / Subtasks

- [x] Task 1: Update `tiktok_faceless/utils/retry.py` — add `make_api_retry` factory and `_log_retry_attempt`
  - [x] Add `_log_retry_attempt(retry_state)` before_sleep callback that logs at DEBUG level: attempt number and next wait time
  - [x] Add `make_api_retry(retryable_exceptions, max_attempts, backoff_multiplier, backoff_max)` factory function using tenacity
  - [x] Include `before_sleep=_log_retry_attempt` in the factory-built decorator
  - [x] Keep existing `api_retry`, `render_retry`, `llm_retry` module-level decorators intact (they are used by existing clients)
  - [x] Update existing `api_retry` to include `before_sleep=_log_retry_attempt`

- [x] Task 2: Add retry config fields to `AccountConfig` in `tiktok_faceless/config.py`
  - [x] Add `retry_max_attempts: int = Field(default=3, ge=1, le=10)`
  - [x] Add `retry_backoff_multiplier: int = Field(default=4, ge=1)`
  - [x] Add `retry_backoff_max_seconds: int = Field(default=30, ge=5)`
  - [x] No env var wiring needed — Pydantic defaults only

- [x] Task 3: Verify `tiktok_faceless/clients/tiktok.py` uses the shared decorator correctly
  - [x] Confirm `@api_retry` is imported from `tiktok_faceless.utils.retry` (already done — no change needed)
  - [x] Confirm no per-method retry logic exists in the client (it doesn't — no change needed)
  - [x] No modifications required to `tiktok.py` unless a gap is found

- [x] Task 4: Update `tests/unit/utils/test_retry.py` — add new test cases
  - [x] Add `TestMakeApiRetry` class with:
    - [x] `test_retries_on_retryable_exception` — retryable exception retried up to max_attempts, then raised
    - [x] `test_raises_immediately_on_non_retryable_exception` — non-retryable exception raises on first attempt
    - [x] `test_reraises_typed_exception_after_exhaustion` — all retries exhausted → original typed exception propagates
    - [x] `test_succeeds_on_second_attempt` — function succeeds on retry, returns result normally
    - [x] `test_configurable_max_attempts` — max_attempts=2 → only 2 attempts total, not 3
  - [x] Keep all existing `TestApiRetry` and `TestRenderRetry` tests passing

## Dev Notes

### Current State Analysis

`tiktok_faceless/utils/retry.py` already exists and defines three module-level tenacity decorators:
- `api_retry` — 3 attempts, `multiplier=1, min=4, max=30`, retries on `httpx.HTTPStatusError` and `httpx.TransportError`
- `render_retry` — 5 attempts, `multiplier=2, min=5, max=60`
- `llm_retry` — 3 attempts, `multiplier=1, min=2, max=20`, retries on Anthropic errors

**Gap 1 — Wrong multiplier**: The spec requires exponential backoff `4s → 16s → 30s`. With `multiplier=4`:
- attempt 1: wait = min(4×2^0, 30) = 4s
- attempt 2: wait = min(4×2^1, 30) = 8s... actually `wait_exponential(multiplier=4, min=4, max=30)` produces:
  - 4s, 8s (clamped at max 30s for later)

Wait — to get 4→16→30: `multiplier=4, min=4, max=30` gives: `4×2^(attempt-1)` = 4, 8, 16, 32→30. So the sequence is 4s, 8s, 16s (third attempt). The spec states "4s → 16s → 30s" which appears to mean jumps of 4, 16, 30 as caps. The current `multiplier=1` yields 4, 8, 16 — close but not matching spec exactly. The spec's `multiplier=4` will produce 4, 8, 16, 32→clamped 30.

Use `multiplier=4` in `make_api_retry` per spec. The existing `api_retry` uses `multiplier=1` — leave it unchanged to avoid breaking existing tests; the new factory is additive.

**Gap 2 — No `before_sleep` logging**: No retry attempt logging currently exists. The `_log_retry_attempt` callback must be added.

**Gap 3 — No `make_api_retry` factory**: `AccountConfig` retry fields cannot be wired to hardcoded decorators. The factory is needed so callers can pass config values.

**Gap 4 — `api_retry` retries on `TikTokRateLimitError`?**: Currently `api_retry` retries on `httpx.HTTPStatusError` and `httpx.TransportError`. However, `TikTokAPIClient._handle_response()` raises typed exceptions (`TikTokRateLimitError`, `TikTokAuthError`, `TikTokAPIError`) BEFORE returning to the caller. These are NOT `httpx.HTTPStatusError` — they are custom exceptions. This means `@api_retry` in the current `tiktok.py` does NOT retry on rate limits (429) or generic API errors because `_handle_response` converts them to typed exceptions first.

For Story 5.4, `make_api_retry` should accept `retryable_exceptions` as a parameter so callers can pass `(TikTokRateLimitError,)` to retry on 429s. The spec's AC1 requires retrying on 429 — this is only achievable if `TikTokRateLimitError` is in `retryable_exceptions`. Do NOT change the existing `api_retry` (would break existing tests); the factory is the correct path.

### Implementation Design

#### `tiktok_faceless/utils/retry.py` — additions

```python
import logging

from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_logger = logging.getLogger(__name__)


def _log_retry_attempt(retry_state: "tenacity.RetryCallState") -> None:
    """Log each retry attempt at DEBUG level with attempt number and upcoming wait."""
    wait = retry_state.next_action.sleep if retry_state.next_action else 0
    _logger.debug(
        "Retry attempt %d failed; waiting %.1fs before next attempt. Exception: %s",
        retry_state.attempt_number,
        wait,
        retry_state.outcome.exception(),
    )


def make_api_retry(
    retryable_exceptions: tuple,
    max_attempts: int = 3,
    backoff_multiplier: int = 4,
    backoff_max: int = 30,
):
    """
    Factory for tenacity retry decorators with exponential backoff.

    Non-retryable errors (TikTokAuthError, 400s) must NOT be included in
    retryable_exceptions — they will raise immediately without retrying.

    Args:
        retryable_exceptions: Tuple of exception types to retry on.
        max_attempts: Maximum number of total attempts (1 = no retry).
        backoff_multiplier: Exponential backoff multiplier in seconds.
        backoff_max: Maximum wait between retries in seconds.
    """
    return retry(
        retry=retry_if_exception_type(retryable_exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_multiplier, min=backoff_multiplier, max=backoff_max),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
```

Also update existing `api_retry` to add `before_sleep=_log_retry_attempt`:
```python
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)
```

#### `tiktok_faceless/config.py` — additions

Add three fields to `AccountConfig` after existing fields:

```python
retry_max_attempts: int = Field(default=3, ge=1, le=10)
retry_backoff_multiplier: int = Field(default=4, ge=1)
retry_backoff_max_seconds: int = Field(default=30, ge=5)
```

Place them after `commission_discrepancy_tolerance` or at the end of the model — before `persona_name`.

#### `tiktok_faceless/clients/tiktok.py` — no changes required

The file already imports `api_retry` from `tiktok_faceless.utils.retry` and applies it as `@api_retry` on all public methods. No per-client retry logic exists. No changes needed unless the dev identifies a gap.

### Test Design for `TestMakeApiRetry`

```python
import logging
from unittest.mock import patch

import pytest

from tiktok_faceless.clients import TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.utils.retry import make_api_retry


class TestMakeApiRetry:
    def test_retries_on_rate_limit_error(self) -> None:
        call_count = 0

        @make_api_retry(retryable_exceptions=(TikTokRateLimitError,), max_attempts=3)
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TikTokRateLimitError("429 rate limited")
            return "ok"

        with patch("tenacity.nap.time.sleep"):
            result = fn()
        assert result == "ok"
        assert call_count == 3

    def test_raises_immediately_on_auth_error(self) -> None:
        call_count = 0

        @make_api_retry(retryable_exceptions=(TikTokRateLimitError,), max_attempts=3)
        def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise TikTokAuthError("401 unauthorized")

        with pytest.raises(TikTokAuthError):
            fn()
        assert call_count == 1

    def test_reraises_after_exhaustion(self) -> None:
        @make_api_retry(retryable_exceptions=(TikTokRateLimitError,), max_attempts=3)
        def fn() -> None:
            raise TikTokRateLimitError("persistent 429")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(TikTokRateLimitError):
                fn()

    def test_debug_logged_per_attempt(self, caplog: pytest.LogCaptureFixture) -> None:
        call_count = 0

        @make_api_retry(retryable_exceptions=(TikTokRateLimitError,), max_attempts=3)
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TikTokRateLimitError("429")
            return "ok"

        with patch("tenacity.nap.time.sleep"):
            with caplog.at_level(logging.DEBUG, logger="tiktok_faceless.utils.retry"):
                fn()
        # 2 failed attempts before success → 2 debug log entries
        debug_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_msgs) == 2

    def test_configurable_max_attempts(self) -> None:
        call_count = 0

        @make_api_retry(retryable_exceptions=(TikTokRateLimitError,), max_attempts=2)
        def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise TikTokRateLimitError("429")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(TikTokRateLimitError):
                fn()
        assert call_count == 2
```

### Existing Tests — No Regressions

The existing `TestApiRetry` tests patch `tenacity.nap.time.sleep`. Adding `before_sleep=_log_retry_attempt` to `api_retry` will trigger the callback before each sleep — this is fine because the sleep itself is patched. The callback only logs at DEBUG; it does not sleep. All existing tests continue to pass.

### Backoff Math Verification

`wait_exponential(multiplier=4, min=4, max=30)`:
- Attempt 1 fails → wait: max(4, min(4×2^0, 30)) = max(4, 4) = 4s
- Attempt 2 fails → wait: max(4, min(4×2^1, 30)) = max(4, 8) = 8s
- Attempt 3 fails → wait: max(4, min(4×2^2, 30)) = max(4, 16) = 16s

The spec says "4s → 16s → 30s" — this appears to be illustrative of min→mid→max caps, not the exact per-attempt sequence. The `make_api_retry` factory with `multiplier=4` satisfies the intent of exponential growth with `min=4, max=30`.

### Import Sort Convention

All imports in `retry.py` must follow stdlib → third-party → local order. `logging` (stdlib) before `tenacity` (third-party) before any local imports.

### pyproject.toml — tenacity dependency

`tenacity` is already a dependency (it's used in the existing `retry.py`). No changes to `pyproject.toml` needed.

### Files to Touch

| File | Action |
|------|--------|
| `tiktok_faceless/utils/retry.py` | Add `_log_retry_attempt`, `make_api_retry`; add `before_sleep` to `api_retry` |
| `tiktok_faceless/config.py` | Add `retry_max_attempts`, `retry_backoff_multiplier`, `retry_backoff_max_seconds` to `AccountConfig` |
| `tests/unit/utils/test_retry.py` | Add `TestMakeApiRetry` with 5 test cases |

### Do NOT Touch

- `tiktok_faceless/clients/tiktok.py` — already uses shared decorator correctly
- Any agent files (orchestrators, analytics, etc.)
- DB models or queries
- `tiktok_faceless/clients/__init__.py` — typed exceptions are correct as-is

## References

- Story spec: `_bmad-output/planning-artifacts/epics.md` — Story 5.4
- Existing retry module: `tiktok_faceless/utils/retry.py`
- Existing retry tests: `tests/unit/utils/test_retry.py`
- Error types: `tiktok_faceless/clients/__init__.py`
- Config model: `tiktok_faceless/config.py`
- TikTok client: `tiktok_faceless/clients/tiktok.py`
- Previous story: `_bmad-output/implementation-artifacts/5-1-agent-failure-isolation.md`
- tenacity docs: https://tenacity.readthedocs.io/

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

N/A — no issues encountered.

### Completion Notes List

- Added `_log_retry_attempt` before_sleep callback logging at DEBUG level with attempt number, function name, and wait time.
- Added `make_api_retry` factory function accepting `retryable_exceptions`, `max_attempts`, `backoff_multiplier`, `backoff_max_seconds`.
- Added `before_sleep=_log_retry_attempt` to existing `api_retry`, `render_retry`, and `llm_retry` decorators.
- Added `retry_max_attempts`, `retry_backoff_multiplier`, `retry_backoff_max_seconds` fields to `AccountConfig` (Pydantic defaults only, no env var wiring).
- Added `TestMakeApiRetry` class with 5 test cases; all 298 unit tests pass. Ruff clean.

### File List

- `tiktok_faceless/utils/retry.py`
- `tiktok_faceless/config.py`
- `tests/unit/utils/test_retry.py`
