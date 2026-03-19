"""
Analytics agent: metrics retrieval (Story 4.1).
Kill switch and suppression monitoring in Stories 4.2–4.3.

Implementation: Stories 4.1 (Metrics Retrieval), 4.2 (Kill Switch) & 4.3 (Shadowban & FYP Reach)
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokAuthError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.models import AgentDecision, Video, VideoMetric
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import PipelineState
from tiktok_faceless.utils.alerts import send_suppression_alert
from tiktok_faceless.utils.suppression import compute_fyp_reach_rate


def analytics_node(state: PipelineState) -> dict[str, Any]:
    """
    Poll TikTok metrics for all posted videos and store as append-only event log.

    Returns state delta with updated fyp_reach_rate if FYP data was collected.
    Never returns full PipelineState — only a state delta dict.
    """
    config = load_account_config(state.account_id)
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    with get_session() as session:
        posted_videos = (
            session.query(Video)
            .filter_by(account_id=state.account_id, lifecycle_state="posted")
            .all()
        )

        fyp_values: list[float] = []
        # Shared timestamp for all rows in this poll run (snapshot time)
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)  # store as naive UTC

        for video in posted_videos:
            if not video.tiktok_video_id:
                continue
            try:
                metrics = client.get_metrics(
                    account_id=state.account_id,
                    video_id=video.tiktok_video_id,
                )
            except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError):
                continue  # Non-fatal: skip this video, try next

            retention_3s = min(1.0, metrics.average_time_watched / 3.0)
            retention_15s = min(1.0, metrics.average_time_watched / 15.0)
            fyp_reach_pct = metrics.traffic_source_type.get("FOR_YOU", 0.0)

            session.add(
                VideoMetric(
                    video_id=video.tiktok_video_id,
                    account_id=state.account_id,
                    recorded_at=now,
                    view_count=metrics.view_count,
                    like_count=metrics.like_count,
                    comment_count=metrics.comment_count,
                    share_count=metrics.share_count,
                    average_time_watched=metrics.average_time_watched,
                    retention_3s=retention_3s,
                    retention_15s=retention_15s,
                    fyp_reach_pct=fyp_reach_pct,
                    affiliate_clicks=0,  # populated by monetization agent
                    affiliate_orders=0,  # populated by monetization agent
                )
            )
            fyp_values.append(fyp_reach_pct)

        # Kill switch evaluation — 48h+ posted videos
        session.flush()  # Ensure just-inserted metrics are visible to kill-switch queries
        cutoff_48h = now - timedelta(hours=48)

        for video in posted_videos:
            if not video.tiktok_video_id:
                continue
            if video.posted_at is None or video.posted_at > cutoff_48h:
                continue  # Under 48h — defer to next cycle

            # Get latest metrics row (autoflush ensures just-inserted rows are visible)
            latest = (
                session.query(VideoMetric)
                .filter_by(video_id=video.tiktok_video_id, account_id=state.account_id)
                .order_by(VideoMetric.recorded_at.desc())
                .first()
            )
            if latest is None:
                continue  # No metrics yet — defer

            if latest.view_count < config.minimum_view_threshold:
                continue  # Insufficient data — defer

            aff_ctr = latest.affiliate_clicks / max(1, latest.view_count)

            # Both conditions must fail — a video with poor retention but high CTR is still earning
            if (
                latest.retention_3s < config.retention_kill_threshold
                and aff_ctr < config.ctr_kill_threshold
            ):
                decision_type = "kill_switch"
                new_lifecycle = "archived"
                try:
                    client.archive_video(
                        account_id=state.account_id, video_id=video.tiktok_video_id
                    )
                except (TikTokAuthError, TikTokRateLimitError, TikTokAPIError):
                    pass  # Non-fatal — DB update still proceeds
            else:
                decision_type = "promoted"
                new_lifecycle = "promoted"

            session.add(
                AgentDecision(
                    account_id=state.account_id,
                    agent="analytics",
                    decision_type=decision_type,
                    from_value="posted",
                    to_value=new_lifecycle,
                    rationale=(
                        f"48h kill switch: retention_3s={latest.retention_3s:.3f}, "
                        f"aff_ctr={aff_ctr:.4f}, view_count={latest.view_count}"
                    ),
                    supporting_data=json.dumps(
                        {
                            "video_id": video.tiktok_video_id,
                            "view_count": latest.view_count,
                            "retention_3s": round(latest.retention_3s, 4),
                            "aff_ctr": round(aff_ctr, 4),
                        }
                    ),
                )
            )
            video.lifecycle_state = new_lifecycle

        session.commit()  # Single commit: metrics inserts + lifecycle updates + audit rows

    # Suppression detection — rolling FYP reach rate from DB
    with get_session() as session:
        current_fyp_rate = compute_fyp_reach_rate(
            session, account_id=state.account_id, window=config.suppression_window
        )

        state_delta: dict[str, Any] = {"fyp_reach_rate": current_fyp_rate}

        if current_fyp_rate < config.fyp_suppression_threshold:
            new_count = state.consecutive_suppression_count + 1
            state_delta["consecutive_suppression_count"] = new_count

            if new_count >= 2 and not state.suppression_alert:
                state_delta["suppression_alert"] = True
                session.add(
                    AgentDecision(
                        account_id=state.account_id,
                        agent="analytics",
                        decision_type="suppression_detected",
                        from_value=None,
                        to_value="suppressed",
                        rationale=(
                            f"FYP reach rate {current_fyp_rate:.3f} below "
                            f"threshold {config.fyp_suppression_threshold:.3f} "
                            f"for {new_count} consecutive intervals."
                        ),
                        supporting_data=json.dumps(
                            {
                                "fyp_reach_rate": round(current_fyp_rate, 4),
                                "threshold": config.fyp_suppression_threshold,
                                "consecutive_suppression_count": new_count,
                            }
                        ),
                    )
                )
        else:
            # Above threshold — clear suppression state
            state_delta["consecutive_suppression_count"] = 0
            state_delta["suppression_alert"] = False

        session.commit()  # Unconditional — no-op if nothing added

    if state_delta.get("suppression_alert") is True and not state.suppression_alert:
        send_suppression_alert(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            fyp_rate=current_fyp_rate,
            threshold=config.fyp_suppression_threshold,
            account_id=state.account_id,
            timestamp=time.time(),
        )

    return state_delta
