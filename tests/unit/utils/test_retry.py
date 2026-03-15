"""Tests for shared retry decorators in tiktok_faceless/utils/retry.py."""

from unittest.mock import patch

import httpx
import pytest

from tiktok_faceless.utils.retry import api_retry, make_api_retry, render_retry


class TestApiRetry:
    def test_succeeds_on_first_try(self) -> None:
        call_count = 0

        @api_retry
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        assert fn() == "ok"
        assert call_count == 1

    def test_retries_on_transport_error(self) -> None:
        call_count = 0

        @api_retry
        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TransportError("network down")
            return "ok"

        # Patch wait to avoid sleeping in tests
        with patch("tenacity.wait_exponential.__call__", return_value=0):
            result = fn()
        assert result == "ok"
        assert call_count == 3

    def test_non_retryable_exception_propagates_immediately(self) -> None:
        call_count = 0

        @api_retry
        def fn() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            fn()
        assert call_count == 1

    def test_exhausted_retries_reraises_original(self) -> None:
        @api_retry
        def fn() -> None:
            raise httpx.TransportError("persistent failure")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(httpx.TransportError):
                fn()


class TestRenderRetry:
    def test_render_retry_is_callable(self) -> None:
        @render_retry
        def fn() -> str:
            return "rendered"

        assert fn() == "rendered"


class TestMakeApiRetry:
    """Tests for the make_api_retry factory function."""

    def test_retries_on_retryable_exception(self):
        """Retryable exception triggers retry up to max_attempts."""
        call_count = 0

        @make_api_retry(retryable_exceptions=(ValueError,), max_attempts=3)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ValueError("transient")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(ValueError):
                flaky()
        assert call_count == 3

    def test_raises_immediately_on_non_retryable_exception(self):
        """Non-retryable exception raises without any retry."""
        call_count = 0

        @make_api_retry(retryable_exceptions=(ValueError,), max_attempts=3)
        def fail_auth():
            nonlocal call_count
            call_count += 1
            raise TypeError("auth failure")

        with pytest.raises(TypeError):
            fail_auth()
        assert call_count == 1

    def test_reraises_typed_exception_after_exhaustion(self):
        """After all retries exhausted, the original typed exception propagates."""

        @make_api_retry(retryable_exceptions=(ValueError,), max_attempts=2)
        def always_fails():
            raise ValueError("rate limit")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(ValueError, match="rate limit"):
                always_fails()

    def test_succeeds_on_second_attempt(self):
        """Function succeeds on retry — returns result normally."""
        attempts = [0]

        @make_api_retry(retryable_exceptions=(ValueError,), max_attempts=3)
        def sometimes_fails():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("transient")
            return "ok"

        with patch("tenacity.nap.time.sleep"):
            result = sometimes_fails()
        assert result == "ok"
        assert attempts[0] == 2

    def test_configurable_max_attempts(self):
        """max_attempts parameter is respected."""
        call_count = 0

        @make_api_retry(retryable_exceptions=(ValueError,), max_attempts=2)
        def flaky():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with patch("tenacity.nap.time.sleep"):
            with pytest.raises(ValueError):
                flaky()
        assert call_count == 2
