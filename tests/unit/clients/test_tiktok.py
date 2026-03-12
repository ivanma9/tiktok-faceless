"""Tests for TikTokAPIClient."""

import time
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.clients import TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient, TokenBucket
from tiktok_faceless.models.tiktok import TikTokPostResponse, TikTokVideoMetrics


class TestTokenBucket:
    def test_allows_up_to_max_tokens_immediately(self) -> None:
        bucket = TokenBucket(max_tokens=3, refill_period=60.0)
        # Should not sleep for first 3 calls
        with patch("time.sleep") as mock_sleep:
            bucket.consume()
            bucket.consume()
            bucket.consume()
            mock_sleep.assert_not_called()

    def test_sleeps_when_empty(self) -> None:
        bucket = TokenBucket(max_tokens=1, refill_period=60.0)
        bucket.consume()  # exhaust the bucket
        with patch("time.sleep") as mock_sleep:
            bucket.consume()
            mock_sleep.assert_called_once()

    def test_lock_not_held_during_sleep(self) -> None:
        """A second thread must be able to acquire the lock while the first is sleeping."""
        import threading

        bucket = TokenBucket(max_tokens=1, refill_period=60.0)
        bucket.consume()  # exhaust the bucket

        acquired_during_sleep = threading.Event()
        original_sleep = time.sleep

        def patched_sleep(duration: float) -> None:
            # Try to acquire the lock while sleeping
            got_it = bucket._lock.acquire(blocking=False)
            if got_it:
                acquired_during_sleep.set()
                bucket._lock.release()
            original_sleep(0)  # Don't actually sleep in tests

        with patch("tiktok_faceless.clients.tiktok.time.sleep", side_effect=patched_sleep):
            bucket.consume()

        assert acquired_during_sleep.is_set(), "Lock was held during sleep — deadlock risk"


class TestTikTokAPIClient:
    def _make_client(self) -> TikTokAPIClient:
        return TikTokAPIClient(access_token="test_token", open_id="test_open_id")

    def test_get_metrics_returns_model(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "video_id": "vid_123",
                "view_count": 1000,
                "like_count": 50,
                "comment_count": 10,
                "share_count": 5,
                "average_time_watched": 12.5,
                "traffic_source_type": {"FOR_YOU": 0.8},
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._http, "post", return_value=mock_response):
            result = client.get_metrics(account_id="acc1", video_id="vid_123")

        assert isinstance(result, TikTokVideoMetrics)
        assert result.video_id == "vid_123"
        assert result.view_count == 1000

    def test_401_raises_auth_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(TikTokAuthError):
                client.get_metrics(account_id="acc1", video_id="vid_123")

    def test_429_raises_rate_limit_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"

        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(TikTokRateLimitError):
                client.get_metrics(account_id="acc1", video_id="vid_123")

    def test_post_video_returns_response(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"video_id": "new_vid_456", "share_url": None}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._http, "post", return_value=mock_response):
            with patch("builtins.open", MagicMock()):
                result = client.post_video(
                    account_id="acc1",
                    video_path="/tmp/test.mp4",
                    caption="Test video #affiliate",
                )

        assert isinstance(result, TikTokPostResponse)
        assert result.video_id == "new_vid_456"


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
                        "commission_rate": 0.01,
                        "sales_velocity_score": 0.1,
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
                    account_id="acc1",
                    niche="health",
                    min_commission_rate=0.05,
                    min_sales_velocity=0.3,
                )


class TestGetAffiliateOrders:
    def test_returns_list_of_commission_records(self) -> None:
        from tiktok_faceless.models.shop import CommissionRecord
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "orders": [
                    {"order_id": "ord1", "product_id": "prod1", "commission_amount": 4.50},
                    {"order_id": "ord2", "product_id": "prod2", "commission_amount": 2.00},
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            orders = client.get_affiliate_orders(account_id="acc1")
        assert len(orders) == 2
        assert isinstance(orders[0], CommissionRecord)
        assert orders[0].order_id == "ord1"
        assert orders[0].commission_amount == pytest.approx(4.50)
        assert orders[1].order_id == "ord2"
        assert orders[1].commission_amount == pytest.approx(2.00)

    def test_returns_empty_list_when_no_orders(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"orders": []}}
        with patch.object(client._http, "post", return_value=mock_response):
            orders = client.get_affiliate_orders(account_id="acc1")
        assert orders == []

    def test_returns_empty_list_when_data_key_missing(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        with patch.object(client._http, "post", return_value=mock_response):
            orders = client.get_affiliate_orders(account_id="acc1")
        assert orders == []


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

    def test_returns_empty_list_when_data_key_missing(self) -> None:
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        with patch.object(client._http, "post", return_value=mock_response):
            comments = client.get_video_comments(video_id="vid123", max_count=20)
        assert comments == []
