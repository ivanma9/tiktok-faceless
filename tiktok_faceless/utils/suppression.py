"""
Suppression detection utilities — FYP reach rate computation.

Implementation: Story 4.3 — Shadowban & FYP Reach Monitoring
"""

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import VideoMetric


def compute_fyp_reach_rate(session: Session, account_id: str, window: int = 10) -> float:
    """
    Compute rolling FYP reach rate as average fyp_reach_pct across last N VideoMetric rows.

    Returns 1.0 (neutral/healthy) if no data is available for the account.
    """
    rows = (
        session.query(VideoMetric.fyp_reach_pct)
        .filter_by(account_id=account_id)
        .order_by(VideoMetric.recorded_at.desc())
        .limit(window)
        .all()
    )
    if not rows:
        return 1.0
    return sum(r.fyp_reach_pct for r in rows) / len(rows)
