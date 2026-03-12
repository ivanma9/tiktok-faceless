"""
Pydantic models for TikTok API responses: TikTokVideoMetrics, TikTokPostResponse.

Implementation: Story 1.3 — External API Client Wrappers
"""

from pydantic import BaseModel


class TikTokVideoMetrics(BaseModel):
    """Parsed response from TikTok Analytics API for a single video."""

    video_id: str
    view_count: int
    like_count: int
    comment_count: int
    share_count: int
    average_time_watched: float
    traffic_source_type: dict[str, float]


class TikTokPostResponse(BaseModel):
    """Parsed response from TikTok Content Posting API after a successful upload."""

    video_id: str
    share_url: str | None = None
