"""Tests for shared retry decorators in tiktok_faceless/utils/retry.py."""

from unittest.mock import patch

import httpx
import pytest

from tiktok_faceless.utils.retry import api_retry, render_retry


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
