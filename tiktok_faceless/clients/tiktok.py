"""
TikTokAPIClient: post_video, get_metrics, generate_affiliate_link,
token bucket rate limiter (6 req/min), and HTTP error mapping.

Implementation: Story 1.3 — External API Client Wrappers
"""

import threading
import time

import httpx

from tiktok_faceless.clients import (
    TikTokAPIError,
    TikTokAuthError,
    TikTokRateLimitError,
)
from tiktok_faceless.models.shop import AffiliateProduct, CommissionRecord
from tiktok_faceless.models.tiktok import TikTokPostResponse, TikTokVideoMetrics
from tiktok_faceless.utils.retry import api_retry

_TIKTOK_BASE_URL = "https://open.tiktokapis.com"


class TokenBucket:
    """Thread-safe token bucket — enforces max N requests per refill_period seconds."""

    def __init__(self, max_tokens: int = 6, refill_period: float = 60.0) -> None:
        self._max_tokens = max_tokens
        self._tokens = float(max_tokens)
        self._refill_period = refill_period
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

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


class TikTokAPIClient:
    """
    Typed wrapper for TikTok Content Posting and Analytics APIs.

    All methods enforce the 6 req/min token bucket before each request.
    HTTP errors are mapped to typed exceptions before reaching callers.
    """

    def __init__(self, access_token: str, open_id: str) -> None:
        self._access_token = access_token
        self._open_id = open_id
        self._bucket = TokenBucket(max_tokens=6, refill_period=60.0)
        self._http = httpx.Client(
            base_url=_TIKTOK_BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    def _handle_response(self, response: httpx.Response) -> None:
        """Map HTTP error codes to typed exceptions. Must be called before .json()."""
        if response.status_code == 429:
            raise TikTokRateLimitError(f"Rate limited: {response.text}")
        if response.status_code in (401, 403):
            raise TikTokAuthError(f"Auth error {response.status_code}: {response.text}")
        if response.status_code >= 400:
            raise TikTokAPIError(f"API error {response.status_code}: {response.text}")

    @api_retry
    def get_metrics(self, account_id: str, video_id: str) -> TikTokVideoMetrics:
        """Fetch analytics for a single video. Returns parsed TikTokVideoMetrics."""
        self._bucket.consume()
        # TikTok Analytics API uses POST for queries despite being a read operation
        response = self._http.post(
            "/v2/video/query/",
            params={"fields": "video_id,view_count,like_count,comment_count,share_count,"
                              "average_time_watched,traffic_source_type"},
            json={"filters": {"video_ids": [video_id]}},
        )
        self._handle_response(response)
        data = response.json()["data"]
        return TikTokVideoMetrics(
            video_id=data.get("video_id", video_id),
            view_count=data.get("view_count", 0),
            like_count=data.get("like_count", 0),
            comment_count=data.get("comment_count", 0),
            share_count=data.get("share_count", 0),
            average_time_watched=data.get("average_time_watched", 0.0),
            traffic_source_type=data.get("traffic_source_type", {}),
        )

    @api_retry
    def post_video(
        self, account_id: str, video_path: str, caption: str
    ) -> TikTokPostResponse:
        """Upload and publish a video using TikTok's two-step init+upload flow."""
        import os
        self._bucket.consume()
        file_size = os.path.getsize(video_path)

        # Step 1: Initialize the upload
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

    @api_retry
    def generate_affiliate_link(self, account_id: str, product_id: str) -> str:
        """Generate a TikTok Shop affiliate link for the given product."""
        self._bucket.consume()
        response = self._http.post(
            "/v2/tiktok_shop/affiliate/link/generate/",
            json={"product_id": product_id, "open_id": self._open_id},
        )
        self._handle_response(response)
        return str(response.json()["data"]["affiliate_link"])

    @api_retry
    def get_validated_products(
        self,
        account_id: str,
        niche: str,
        min_commission_rate: float = 0.05,
        min_sales_velocity: float = 0.3,
    ) -> list[AffiliateProduct]:
        """
        Search TikTok Shop for affiliate products in the given niche.
        Filters by min_commission_rate and min_sales_velocity before returning.
        Returns list sorted by sales_velocity_score descending.
        """
        self._bucket.consume()
        response = self._http.post(
            "/v2/tiktok_shop/affiliate/products/search/",
            json={"niche": niche, "open_id": self._open_id},
        )
        self._handle_response(response)
        raw_products = response.json().get("data", {}).get("products", [])
        results: list[AffiliateProduct] = []
        for p in raw_products:
            commission_rate = float(p.get("commission_rate", 0.0))
            sales_velocity = float(p.get("sales_velocity_score", 0.0))
            if commission_rate >= min_commission_rate and sales_velocity >= min_sales_velocity:
                results.append(
                    AffiliateProduct(
                        product_id=str(p["product_id"]),
                        product_name=str(p["product_name"]),
                        product_url=str(p["product_url"]),
                        commission_rate=commission_rate,
                        sales_velocity_score=sales_velocity,
                        niche=niche,
                    )
                )
        results.sort(key=lambda x: x.sales_velocity_score, reverse=True)
        return results

    @api_retry
    def get_video_comments(self, video_id: str, max_count: int = 20) -> list[str]:
        """Fetch comment text strings from a TikTok video. Returns empty list if none."""
        self._bucket.consume()
        response = self._http.post(
            "/v2/video/comment/list/",
            json={"video_id": video_id, "max_count": max_count, "open_id": self._open_id},
        )
        self._handle_response(response)
        comments = response.json().get("data", {}).get("comments", [])
        return [str(c.get("text", "")) for c in comments if c.get("text")]

    @api_retry
    def archive_video(self, account_id: str, video_id: str) -> None:
        """
        Permanently delete a video on TikTok (TikTok-side deletion, not soft-archive).
        Non-recoverable — use only after kill-switch decision.
        """
        self._bucket.consume()
        response = self._http.post(
            "/v2/video/delete/",
            json={"video_id": video_id, "open_id": self._open_id},
        )
        self._handle_response(response)

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

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._http.close()
