"""
Pydantic models for TikTok Shop: AffiliateProduct, CommissionRecord.

Implementation: Story 1.3 — External API Client Wrappers
"""

import time

from pydantic import BaseModel, Field


class AffiliateProduct(BaseModel):
    """A validated TikTok Shop affiliate product with commission metadata."""

    product_id: str
    product_name: str
    product_url: str
    commission_rate: float
    sales_velocity_score: float = 0.0
    niche: str
    top_video_id: str | None = None


class CommissionRecord(BaseModel):
    """A single affiliate commission event recorded from TikTok Shop."""

    order_id: str
    product_id: str
    commission_amount: float
    recorded_at: float = Field(default_factory=time.time)
