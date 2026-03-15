"""
Shared tenacity retry decorators for all external API calls.

Usage:
    @api_retry
    def call_external_api(...): ...

Implementation: Story 1.3 — External API Client Wrappers
"""

import logging

import httpx
import tenacity
from anthropic import APIConnectionError, APIStatusError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _log_retry_attempt(retry_state: "tenacity.RetryCallState") -> None:
    """Log each retry attempt at DEBUG level."""
    logger.debug(
        "Retry attempt %d for %s — waiting %.1fs",
        retry_state.attempt_number,
        retry_state.fn.__name__ if retry_state.fn else "unknown",
        retry_state.next_action.sleep if retry_state.next_action else 0,
    )


# Standard retry for all external API calls: 3 attempts, 4s → 16s → 30s backoff.
# Only retries on transient HTTP/network errors — NOT on auth or rate-limit errors.
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)

# Longer retry for render polling: 5 attempts, 5s → 60s backoff.
render_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)

# Retry for transient Anthropic LLM errors: 3 attempts, 2s → 20s backoff.
llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type((APIStatusError, APIConnectionError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)


def make_api_retry(
    retryable_exceptions: tuple,
    max_attempts: int = 3,
    backoff_multiplier: int = 4,
    backoff_max_seconds: int = 30,
):
    """Factory for configurable API retry decorator.

    Args:
        retryable_exceptions: Tuple of exception types that trigger retry.
        max_attempts: Maximum retry attempts before raising.
        backoff_multiplier: Exponential backoff multiplier in seconds.
        backoff_max_seconds: Maximum wait between retries in seconds.

    Returns:
        tenacity retry decorator configured with exponential backoff.
    """
    return retry(
        retry=retry_if_exception_type(retryable_exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=backoff_multiplier, min=backoff_multiplier, max=backoff_max_seconds
        ),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
