"""
Monetization agent: affiliate link generation and commission tracking.

Implementation: Story 1.5 — Basic Script & Affiliate Link Generation
                Story 4.5 — Commission Reconciliation on Schedule
"""

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import Error, Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState
from tiktok_faceless.utils.recovery import get_recovery_suggestion


def _reconcile_commissions(
    session,
    account_id: str,
    orders: list,
    tolerance: float,
) -> None:
    """Compare aggregate system clicks vs TikTok order count for last 7 days.

    Writes Error row if discrepancy exceeds tolerance threshold.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = (
        session.query(VideoMetric)
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .all()
    )
    system_clicks = sum(r.affiliate_clicks for r in rows)
    tiktok_order_count = len(orders)

    if system_clicks == 0 and tiktok_order_count == 0:
        return

    ratio_diff = abs(system_clicks - tiktok_order_count) / max(1, system_clicks)
    if ratio_diff > tolerance:
        session.add(
            Error(
                account_id=account_id,
                agent="monetization",
                error_type="commission_discrepancy",
                message=(
                    f"Click/order discrepancy: system_clicks={system_clicks}, "
                    f"tiktok_orders={tiktok_order_count}, "
                    f"ratio_diff={ratio_diff:.3f} > tolerance={tolerance:.3f}"
                ),
                recovery_suggestion=get_recovery_suggestion("commission_discrepancy"),
            )
        )


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
                    recovery_suggestion=get_recovery_suggestion("MissingProduct"),
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
                    recovery_suggestion=get_recovery_suggestion("TikTokRateLimitError"),
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
                    recovery_suggestion=get_recovery_suggestion("TikTokAuthError"),
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
                    recovery_suggestion=get_recovery_suggestion("TikTokAPIError"),
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

    # Commission reconciliation — guarded by configurable interval
    now_ts = time.time()
    if now_ts - state.last_reconciliation_at >= config.reconciliation_interval_hours * 3600:
        try:
            orders = client.get_affiliate_orders(account_id=state.account_id)
            delta["affiliate_commission_week"] = sum(o.commission_amount for o in orders)
            with get_session() as rec_session:
                _reconcile_commissions(
                    rec_session,
                    account_id=state.account_id,
                    orders=orders,
                    tolerance=config.commission_discrepancy_tolerance,
                )
                rec_session.commit()
            delta["last_reconciliation_at"] = now_ts
        except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError):
            pass  # Non-fatal: skip this cycle, preserve last_reconciliation_at

    return delta
