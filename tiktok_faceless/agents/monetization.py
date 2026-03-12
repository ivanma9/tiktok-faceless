"""
Monetization agent: affiliate link generation and commission tracking.

Implementation: Story 1.5 — Basic Script & Affiliate Link Generation
"""

import uuid
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import Video
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState


def monetization_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate a TikTok Shop affiliate link for state.selected_product and persist to DB.

    Returns state delta dict with product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.
    """
    if state.selected_product is None:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="MissingProduct",
                    message="selected_product is None — no product to generate affiliate link",
                )
            ]
        }

    config = load_account_config(state.account_id)
    product_id: str = state.selected_product["product_id"]

    try:
        client = TikTokAPIClient(
            access_token=config.tiktok_access_token,
            open_id=config.tiktok_open_id,
        )
        affiliate_link = client.generate_affiliate_link(
            account_id=state.account_id,
            product_id=product_id,
        )
    except TikTokRateLimitError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokRateLimitError",
                    message=str(e),
                )
            ]
        }
    except TikTokAuthError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokAuthError",
                    message=str(e),
                )
            ]
        }
    except TikTokAPIError as e:
        return {
            "errors": [
                AgentError(
                    agent="monetization",
                    error_type="TikTokAPIError",
                    message=str(e),
                )
            ]
        }

    with get_session() as session:
        video = (
            session.query(Video)
            .filter_by(account_id=state.account_id, lifecycle_state="queued")
            .filter(Video.product_id.is_(None))     # only unassigned videos
            .order_by(Video.created_at.desc())
            .first()
        )
        if video is None:
            video = Video(
                id=str(uuid.uuid4()),
                account_id=state.account_id,
                niche=state.committed_niche or "unknown",
            )
            session.add(video)
        video.affiliate_link = affiliate_link
        video.product_id = product_id

    delta: dict[str, Any] = {"product_validated": True}

    # Commission reconciliation polling (non-fatal — TikTok data has reporting lag)
    try:
        orders = client.get_affiliate_orders(account_id=state.account_id)
        delta["affiliate_commission_week"] = sum(o.commission_amount for o in orders)
    except Exception:  # noqa: BLE001
        pass  # preserve existing state.affiliate_commission_week on error

    return delta
