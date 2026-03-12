"""
Shared tenacity retry decorators for all external API calls.

Usage:
    @api_retry
    def call_external_api(...): ...

Implementation: Story 1.3 — External API Client Wrappers
"""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Standard retry for all external API calls: 3 attempts, 4s → 16s → 30s backoff.
# Only retries on transient HTTP/network errors — NOT on auth or rate-limit errors.
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    reraise=True,
)

# Longer retry for render polling: 5 attempts, 5s → 60s backoff.
render_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    reraise=True,
)
