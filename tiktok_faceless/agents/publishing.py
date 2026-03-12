"""
Publishing agent: TikTok posting with suppression-resistant cadence randomization.

Implementation: Story 1.6 — Publishing Agent with Suppression-Resistant Cadence
"""

import time
from datetime import UTC, datetime
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import Video
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState
from tiktok_faceless.utils.timing import is_within_posting_window

_MIN_POST_INTERVAL_SECONDS: float = 3600.0


def publishing_node(state: PipelineState) -> dict[str, Any]:
    """
    Post the assembled video to TikTok within the configured posting window.

    Returns state delta dict with published_video_id and last_post_timestamp on success,
    {"deferred": True} if outside window or interval not met,
    or errors list on failure. Never returns full PipelineState.
    """
    if state.assembled_video_path is None:
        return {
            "errors": [
                AgentError(
                    agent="publishing",
                    error_type="MissingVideo",
                    message="assembled_video_path is None — nothing to publish",
                )
            ]
        }

    config = load_account_config(state.account_id)

    if not is_within_posting_window(config.posting_window_start, config.posting_window_end):
        return {"deferred": True}

    if time.time() - state.last_post_timestamp < _MIN_POST_INTERVAL_SECONDS:
        return {"deferred": True}

    # Build caption — use current_script; append affiliate link from DB if available
    caption = state.current_script or ""
    with get_session() as session:
        video = (
            session.query(Video)
            .filter_by(account_id=state.account_id)
            .filter(Video.lifecycle_state.in_(["queued", "rendered"]))
            .order_by(Video.created_at.desc())
            .first()
        )
        if video and video.affiliate_link:
            caption = f"{caption}\n\nShop here: {video.affiliate_link}".strip()

    # Post to TikTok
    try:
        client = TikTokAPIClient(
            access_token=config.tiktok_access_token,
            open_id=config.tiktok_open_id,
        )
        response = client.post_video(
            account_id=state.account_id,
            video_path=state.assembled_video_path,
            caption=caption,
        )
    except TikTokRateLimitError as e:
        return {
            "errors": [
                AgentError(
                    agent="publishing",
                    error_type="TikTokRateLimitError",
                    message=str(e),
                )
            ]
        }
    except TikTokAuthError as e:
        return {
            "errors": [
                AgentError(
                    agent="publishing",
                    error_type="TikTokAuthError",
                    message=str(e),
                )
            ]
        }
    except TikTokAPIError as e:
        return {
            "errors": [
                AgentError(
                    agent="publishing",
                    error_type="TikTokAPIError",
                    message=str(e),
                )
            ]
        }

    # Update DB row to posted
    with get_session() as session:
        video = (
            session.query(Video)
            .filter_by(account_id=state.account_id)
            .filter(Video.lifecycle_state.in_(["queued", "rendered"]))
            .order_by(Video.created_at.desc())
            .first()
        )
        if video is not None:
            video.lifecycle_state = "posted"
            video.tiktok_video_id = response.video_id
            video.posted_at = datetime.now(UTC)

    return {
        "published_video_id": response.video_id,
        "last_post_timestamp": time.time(),
    }
