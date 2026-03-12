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
        from unittest.mock import mock_open
        client = self._make_client()
        mock_init_response = MagicMock()
        mock_init_response.status_code = 200
        mock_init_response.json.return_value = {
            "data": {"publish_id": "new_vid_456", "upload_url": "https://upload.example.com/v", "share_url": None}
        }
        mock_upload_response = MagicMock()
        mock_upload_response.status_code = 200

        with (
            patch("os.path.getsize", return_value=5),
            patch("builtins.open", mock_open(read_data=b"video")),
            patch.object(client._http, "post", return_value=mock_init_response),
            patch.object(client._http, "put", return_value=mock_upload_response),
        ):
            result = client.post_video(
                account_id="acc1",
                video_path="/tmp/test.mp4",
                caption="Test video #affiliate",
            )

        assert isinstance(result, TikTokPostResponse)
        assert result.video_id == "new_vid_456"

    def test_post_video_reads_and_sends_file_bytes(self) -> None:
        """post_video must read the file and include bytes in the upload call."""
        from unittest.mock import mock_open
        client = self._make_client()

        fake_bytes = b"fake video content"

        # Mock the init response
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.json.return_value = {
            "data": {"publish_id": "pub_123", "upload_url": "https://upload.example.com/video", "share_url": None}
        }

        # Mock the upload response
        upload_response = MagicMock()
        upload_response.status_code = 200

        with (
            patch("os.path.getsize", return_value=len(fake_bytes)),
            patch("builtins.open", mock_open(read_data=fake_bytes)),
            patch.object(client._http, "post", return_value=init_response) as mock_post,
            patch.object(client._http, "put", return_value=upload_response) as mock_put,
        ):
            result = client.post_video(
                account_id="acc1",
                video_path="/tmp/test.mp4",
                caption="Test caption",
            )

        # Verify file bytes were sent in the PUT
        mock_put.assert_called_once()
        call_kwargs = mock_put.call_args
        assert call_kwargs.kwargs.get("content") == fake_bytes or \
               (call_kwargs.args and fake_bytes in call_kwargs.args)
        assert result.video_id == "pub_123"


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

    def test_skips_malformed_orders_missing_fields(self) -> None:
        """Orders missing order_id or product_id must be skipped, not raise KeyError."""
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "orders": [
                    {"order_id": "ord1", "product_id": "prod1", "commission_amount": 4.50},
                    {"product_id": "prod2", "commission_amount": 2.00},   # missing order_id
                    {"order_id": "ord3", "commission_amount": 1.00},       # missing product_id
                ]
            }
        }
        with patch.object(client._http, "post", return_value=mock_response):
            orders = client.get_affiliate_orders(account_id="acc1")

        assert len(orders) == 1
        assert orders[0].order_id == "ord1"

    def test_sends_start_date_in_request(self) -> None:
        """get_affiliate_orders must include a start_date ~7 days ago in the request body."""
        from datetime import datetime, timedelta, timezone
        client = TikTokAPIClient(access_token="tok", open_id="oid")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"orders": []}}

        with patch.object(client._http, "post", return_value=mock_response) as mock_post:
            client.get_affiliate_orders(account_id="acc1")

        call_json = mock_post.call_args.kwargs.get("json") or {}
        assert "start_date" in call_json, "start_date must be included in the request body"
        start = datetime.fromisoformat(call_json["start_date"])
        # Make timezone-aware for comparison
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        expected = datetime.now(timezone.utc) - timedelta(days=7)
        assert abs((start - expected).total_seconds()) < 120, "start_date must be ~7 days ago"


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
