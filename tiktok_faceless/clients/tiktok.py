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
from tiktok_faceless.models.shop import AffiliateProduct
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
                time.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


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
        """Upload and publish a video. Returns TikTokPostResponse with video_id."""
        self._bucket.consume()
        with open(video_path, "rb"):
            response = self._http.post(
                "/v2/post/publish/video/init/",
                json={
                    "post_info": {"title": caption, "privacy_level": "SELF_ONLY"},
                    "source_info": {"source": "FILE_UPLOAD"},
                },
            )
        self._handle_response(response)
        data = response.json()["data"]
        return TikTokPostResponse(
            video_id=data.get("video_id", ""),
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

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._http.close()
