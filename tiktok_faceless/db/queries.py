"""
Typed query functions — all scoped by account_id.

Implementation: Story 1.2 — Core State & Database Models
Implementation: Story 2.1 — Product caching (cache_product, get_cached_products)
"""

import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Account, AgentDecision, Error, Product, Video, VideoMetric
from tiktok_faceless.models.shop import AffiliateProduct

_PRODUCT_CACHE_TTL_HOURS = 24
_queries_logger = logging.getLogger("tiktok_faceless.db.queries")


def cache_product(session: Session, account_id: str, product: AffiliateProduct) -> None:
    """Insert or update a product row. Upsert key: account_id + product_id."""
    existing = (
        session.query(Product)
        .filter_by(account_id=account_id, product_id=product.product_id)
        .first()
    )
    if existing is not None:
        existing.product_name = product.product_name
        existing.product_url = product.product_url
        existing.commission_rate = product.commission_rate
        existing.sales_velocity_score = product.sales_velocity_score
        existing.niche = product.niche
        existing.cached_at = datetime.utcnow()
        existing.eliminated = False  # Re-caching un-eliminates a product
    else:
        session.add(
            Product(
                id=str(uuid.uuid4()),
                account_id=account_id,
                niche=product.niche,
                product_id=product.product_id,
                product_name=product.product_name,
                product_url=product.product_url,
                commission_rate=product.commission_rate,
                sales_velocity_score=product.sales_velocity_score,
                cached_at=datetime.utcnow(),
                eliminated=False,
            )
        )
    session.commit()


def get_commission_per_view(
    session: Session,
    account_id: str,
    niche: str,
    days: int = 7,
) -> float:
    """
    Calculate commission-per-view proxy for a niche over the last N days.

    Uses affiliate_orders / view_count as a proxy for commission revenue per view.
    Returns 0.0 if no data available (not an error).
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.sum(VideoMetric.view_count).label("total_views"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            Video.niche == niche,
            VideoMetric.recorded_at >= cutoff,
        )
        .first()
    )
    if result is None or not result.total_views:
        return 0.0
    return float(result.total_orders or 0) / float(result.total_views)


def get_commission_totals(
    session: Session,
    account_id: str,
    days: int = 7,
) -> dict[str, dict[str, int]]:
    """
    Aggregate affiliate orders and views by niche over the last N days.
    Returns: {niche: {"total_orders": int, "total_views": int}}
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.niche,
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.sum(VideoMetric.view_count).label("total_views"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.niche)
        .all()
    )
    return {
        row.niche: {
            "total_orders": int(row.total_orders or 0),
            "total_views": int(row.total_views or 0),
        }
        for row in rows
    }


def get_cached_products(
    session: Session,
    account_id: str,
    niche: str,
    ttl_hours: int | None = _PRODUCT_CACHE_TTL_HOURS,
) -> list[AffiliateProduct]:
    """Return cached products for account+niche. Pass ttl_hours=None to skip TTL check."""
    q = session.query(Product).filter(
        Product.account_id == account_id,
        Product.niche == niche,
        Product.eliminated == False,  # noqa: E712
    )
    if ttl_hours is not None:
        cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
        q = q.filter(Product.cached_at >= cutoff)
    rows = q.all()
    return [
        AffiliateProduct(
            product_id=row.product_id,
            product_name=row.product_name,
            product_url=row.product_url,
            commission_rate=row.commission_rate,
            sales_velocity_score=row.sales_velocity_score,
            niche=row.niche,
        )
        for row in rows
    ]


def get_niche_scores(
    session: Session,
    account_id: str,
    days: int = 7,
    min_video_count: int = 1,
) -> list[tuple[str, float]]:
    """
    Compute a weighted tournament score per niche for the given account.

    Score formula (range 0.0–1.0):
      0.40 * min(1.0, affiliate_ctr) + 0.30 * avg_retention_3s + 0.30 * normalized_orders

    Only niches with >= min_video_count distinct posted videos are included.
    Returns list of (niche, score) tuples sorted descending by score.
    Returns empty list if no data exists.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.niche,
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
            func.avg(VideoMetric.retention_3s).label("avg_retention_3s"),
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.count(func.distinct(VideoMetric.video_id)).label("video_count"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.niche)
        .all()
    )

    # Filter by minimum video count
    rows = [r for r in rows if (r.video_count or 0) >= min_video_count]
    if not rows:
        return []

    max_orders = max(int(r.total_orders or 0) for r in rows)

    scored: list[tuple[str, float]] = []
    for row in rows:
        aff_ctr = min(1.0, int(row.total_clicks or 0) / max(int(row.total_views or 0), 1))
        retention = max(0.0, min(1.0, float(row.avg_retention_3s or 0.0)))
        norm_orders = int(row.total_orders or 0) / max(max_orders, 1)
        score = 0.40 * aff_ctr + 0.30 * retention + 0.30 * norm_orders
        scored.append((row.niche, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def get_archetype_scores(
    session: Session,
    account_id: str,
    days: int = 30,
) -> dict[str, tuple[float, int]]:
    """Return composite hook archetype scores from recent VideoMetric rows.

    Joins VideoMetric with Video to get hook_archetype (stored on Video, not VideoMetric).

    Returns:
        Dict mapping archetype name → (composite_score, video_count).
        Empty dict if no data.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.hook_archetype,
            func.avg(VideoMetric.retention_3s).label("avg_ret3"),
            func.avg(VideoMetric.retention_15s).label("avg_ret15"),
            func.avg(VideoMetric.affiliate_clicks / func.nullif(VideoMetric.view_count, 0)).label(
                "avg_ctr"
            ),
            func.count().label("cnt"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            VideoMetric.account_id == account_id,
            Video.hook_archetype.isnot(None),
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.hook_archetype)
        .all()
    )
    result: dict[str, tuple[float, int]] = {}
    for row in rows:
        avg_ret3 = float(row.avg_ret3 or 0.0)
        avg_ret15 = float(row.avg_ret15 or 0.0)
        avg_ctr = float(row.avg_ctr or 0.0)
        score = 0.50 * avg_ret3 + 0.30 * avg_ret15 + 0.20 * avg_ctr
        result[row.hook_archetype] = (score, int(row.cnt))
    return result


def write_agent_errors(
    session: Session,
    account_id: str,
    errors: list,  # list[AgentError] — avoid circular import with state.py
) -> None:
    """Persist AgentError state entries to the errors DB table.

    Called by orchestrator_node instead of inline session.add() loops.
    """
    for err in errors:
        session.add(
            Error(
                account_id=account_id,
                agent=err.agent,
                error_type=err.error_type,
                message=err.message,
                video_id=err.video_id,
                recovery_suggestion=err.recovery_suggestion,
            )
        )
    if errors:
        session.commit()


def get_active_errors(session: Session, account_id: str) -> list:
    """Return Error rows with resolved_at IS NULL for the given account.

    Used for dashboard queries to show unresolved failures.
    """
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.resolved_at.is_(None),
        )
        .order_by(Error.timestamp.desc())
        .all()
    )


def pause_agent_queue(session: Session, account_id: str, agent: str) -> None:
    """Add agent to the paused list for the account. Idempotent."""
    account = session.query(Account).filter_by(account_id=account_id).one()
    paused: list[str] = json.loads(account.paused_agent_queues or "[]")
    if agent not in paused:
        paused.append(agent)
    account.paused_agent_queues = json.dumps(paused)
    session.commit()


def resume_agent_queue(session: Session, account_id: str, agent: str) -> None:
    """Remove agent from the paused list for the account."""
    account = session.query(Account).filter_by(account_id=account_id).one()
    paused: list[str] = json.loads(account.paused_agent_queues or "[]")
    if agent in paused:
        paused.remove(agent)
    account.paused_agent_queues = json.dumps(paused)
    session.commit()


def resolve_agent_errors(session: Session, account_id: str, agent: str) -> None:
    """Stamp resolved_at on all open Error rows for the given account+agent."""
    rows = (
        session.query(Error)
        .filter(Error.account_id == account_id, Error.agent == agent, Error.resolved_at.is_(None))
        .all()
    )
    for row in rows:
        row.resolved_at = datetime.utcnow()
    session.commit()


def get_paused_agents(session: Session, account_id: str) -> list[str]:
    """Return list of paused agent names for the account."""
    account = session.query(Account).filter_by(account_id=account_id).one()
    return json.loads(account.paused_agent_queues or "[]")


def get_last_post_time(session: Session, account_id: str) -> datetime | None:
    """Return the most recent posted_at for videos in terminal lifecycle states."""
    _posted_states = ("posted", "analyzed", "archived", "promoted")
    result = (
        session.query(func.max(Video.posted_at))
        .filter(
            Video.account_id == account_id,
            Video.lifecycle_state.in_(_posted_states),
        )
        .scalar()
    )
    return result


def get_videos_posted_today(session: Session, account_id: str) -> int:
    """Return count of videos posted since UTC midnight today."""
    _posted_states = ("posted", "analyzed", "archived", "promoted")
    today_midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.query(func.count(Video.id))
        .filter(
            Video.account_id == account_id,
            Video.lifecycle_state.in_(_posted_states),
            Video.posted_at >= today_midnight,
        )
        .scalar()
        or 0
    )


def get_pending_video(session: Session, account_id: str) -> Video | None:
    """Return the most recently created rendered-but-unposted video, or None."""
    return (
        session.query(Video)
        .filter(
            Video.account_id == account_id,
            Video.lifecycle_state == "rendered",
            Video.assembled_video_path.isnot(None),
        )
        .order_by(Video.created_at.desc())
        .first()
    )


def save_rendered_video(
    session: Session,
    account_id: str,
    voiceover_path: str,
    assembled_video_path: str,
    script_text: str,
    niche: str,
) -> Video:
    """Insert a new Video row with lifecycle_state='rendered'. Returns the row."""
    video = Video(
        id=str(uuid.uuid4()),
        account_id=account_id,
        niche=niche,
        lifecycle_state="rendered",
        script_text=script_text,
        voiceover_path=voiceover_path,
        assembled_video_path=assembled_video_path,
        created_at=datetime.utcnow(),
    )
    session.add(video)
    session.commit()
    return video


def get_account_phase(session: Session, account_id: str) -> str:
    """Return the current phase for the account; defaults to 'warmup' if not found."""
    account = session.query(Account).filter_by(account_id=account_id).first()
    return account.phase if account is not None else "warmup"


def get_phase_started_at(session: Session, account_id: str) -> datetime | None:
    """Return created_at of the most recent phase_transition decision to the current phase."""
    current_phase = get_account_phase(session, account_id)
    row = (
        session.query(AgentDecision)
        .filter(
            AgentDecision.account_id == account_id,
            AgentDecision.decision_type == "phase_transition",
            AgentDecision.to_value == current_phase,
        )
        .order_by(AgentDecision.created_at.desc())
        .first()
    )
    return row.created_at if row else None


def get_unresolved_errors(session: Session, account_id: str) -> list[Error]:
    """Return all unresolved Error rows for the account, newest first."""
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.resolved_at.is_(None),
        )
        .order_by(Error.timestamp.desc())
        .all()
    )


def get_agent_decisions(
    session: Session,
    account_id: str,
    limit: int = 100,
) -> list[AgentDecision]:
    """Return agent_decisions rows for the account, newest first, up to limit.

    Used by dashboard/pages/decisions.py to render the decision audit log.
    """
    return (
        session.query(AgentDecision)
        .filter(AgentDecision.account_id == account_id)
        .order_by(AgentDecision.created_at.desc())
        .limit(limit)
        .all()
    )


def get_resolved_errors(
    session: Session,
    account_id: str,
    limit: int = 50,
) -> list[Error]:
    """Return resolved Error rows (resolved_at IS NOT NULL) for the account, newest first.

    Used by dashboard/pages/errors.py to populate the collapsed resolved-errors expander.
    """
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.resolved_at.isnot(None),
        )
        .order_by(Error.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_active_suppression(session: Session, account_id: str) -> Error | None:
    """Return the most recent unresolved suppression_detected error, or None."""
    return (
        session.query(Error)
        .filter(
            Error.account_id == account_id,
            Error.error_type == "suppression_detected",
            Error.resolved_at.is_(None),
        )
        .order_by(Error.timestamp.desc())
        .first()
    )


def get_agent_health_from_errors(session: Session, account_id: str) -> dict[str, bool]:
    """Return health map for all known agents derived from unresolved errors."""
    known_agents = [
        "orchestrator",
        "research",
        "script",
        "production",
        "publishing",
        "analytics",
        "monetization",
    ]
    unhealthy_agents = (
        session.query(Error.agent)
        .filter(Error.account_id == account_id, Error.resolved_at.is_(None))
        .distinct()
        .all()
    )
    unhealthy_set = {row.agent for row in unhealthy_agents}
    return {agent: agent not in unhealthy_set for agent in known_agents}


def get_kpi_revenue(session: Session, account_id: str, days: int = 7) -> float:
    """Sum affiliate_orders * commission_rate via join to Products.

    Falls back to SUM(affiliate_orders) if no products are linked yet.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("revenue")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
            Video.product_id.isnot(None),
        )
        .first()
    )
    if rows is not None and rows.revenue is not None:
        return float(rows.revenue)
    # Fallback: no products linked yet
    fallback = (
        session.query(func.sum(VideoMetric.affiliate_orders).label("total"))
        .filter(VideoMetric.account_id == account_id, VideoMetric.recorded_at >= cutoff)
        .scalar()
    )
    return float(fallback or 0.0)


def get_kpi_retention_3s(session: Session, account_id: str, days: int = 7) -> float | None:
    """AVG(retention_3s) for the last N days. Returns None if no rows."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(func.avg(VideoMetric.retention_3s).label("avg_val"))
        .filter(VideoMetric.account_id == account_id, VideoMetric.recorded_at >= cutoff)
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_retention_15s(session: Session, account_id: str, days: int = 7) -> float | None:
    """AVG(retention_15s) for the last N days. Returns None if no rows."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(func.avg(VideoMetric.retention_15s).label("avg_val"))
        .filter(VideoMetric.account_id == account_id, VideoMetric.recorded_at >= cutoff)
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_affiliate_ctr(session: Session, account_id: str, days: int = 7) -> float | None:
    """SUM(affiliate_clicks) / MAX(SUM(view_count), 1) for the window. Returns None if no rows."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
        )
        .filter(VideoMetric.account_id == account_id, VideoMetric.recorded_at >= cutoff)
        .first()
    )
    if result is None or result.total_clicks is None:
        return None
    return float(result.total_clicks) / max(float(result.total_views or 0), 1.0)


def get_kpi_fyp_reach_rate(session: Session, account_id: str, days: int = 7) -> float | None:
    """AVG(fyp_reach_pct) for the last N days. Returns None if no rows."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = (
        session.query(func.avg(VideoMetric.fyp_reach_pct).label("avg_val"))
        .filter(VideoMetric.account_id == account_id, VideoMetric.recorded_at >= cutoff)
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_sparkline(
    session: Session,
    account_id: str,
    metric: str,
    days: int = 7,
) -> list[float]:
    """Return exactly `days` daily average values oldest→newest; missing days filled with 0.0."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    col_map = {
        "retention_3s": func.avg(VideoMetric.retention_3s),
        "retention_15s": func.avg(VideoMetric.retention_15s),
        "fyp_reach_pct": func.avg(VideoMetric.fyp_reach_pct),
        "affiliate_ctr": func.sum(VideoMetric.affiliate_clicks)
        / func.nullif(func.sum(VideoMetric.view_count), 0),
        "revenue": func.sum(VideoMetric.affiliate_orders),
    }
    agg_expr = col_map[metric]

    rows = (
        session.query(
            func.date(VideoMetric.recorded_at).label("day"),
            agg_expr.label("val"),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(func.date(VideoMetric.recorded_at))
        .order_by(func.date(VideoMetric.recorded_at))
        .all()
    )

    day_map: dict[str, float] = {str(row.day): float(row.val or 0.0) for row in rows}
    result: list[float] = []
    for i in range(days):
        day = (cutoff + timedelta(days=i + 1)).date()
        result.append(day_map.get(str(day), 0.0))
    return result


def get_kpi_freshness(session: Session, account_id: str) -> datetime | None:
    """Return MAX(VideoMetric.recorded_at) for the account; None if no rows."""
    result = (
        session.query(func.max(VideoMetric.recorded_at))
        .filter(VideoMetric.account_id == account_id)
        .scalar()
    )
    return result


def get_kpi_prior_retention_3s(session: Session, account_id: str, days: int = 7) -> float | None:
    """Return avg retention_3s for the prior window (days+1 to 2*days ago)."""
    now = datetime.utcnow()
    current_cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=days * 2)
    result = (
        session.query(func.avg(VideoMetric.retention_3s))
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= prior_cutoff,
            VideoMetric.recorded_at < current_cutoff,
        )
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_prior_retention_15s(session: Session, account_id: str, days: int = 7) -> float | None:
    """Return avg retention_15s for the prior window (days+1 to 2*days ago)."""
    now = datetime.utcnow()
    current_cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=days * 2)
    result = (
        session.query(func.avg(VideoMetric.retention_15s))
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= prior_cutoff,
            VideoMetric.recorded_at < current_cutoff,
        )
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_prior_affiliate_ctr(session: Session, account_id: str, days: int = 7) -> float | None:
    """Return affiliate CTR for the prior window (days+1 to 2*days ago)."""
    now = datetime.utcnow()
    current_cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=days * 2)
    row = (
        session.query(
            func.sum(VideoMetric.affiliate_clicks).label("clicks"),
            func.sum(VideoMetric.view_count).label("views"),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= prior_cutoff,
            VideoMetric.recorded_at < current_cutoff,
        )
        .first()
    )
    if row is None or row.clicks is None:
        return None
    return float(row.clicks) / max(float(row.views or 0), 1.0)


def get_kpi_prior_fyp_reach_rate(session: Session, account_id: str, days: int = 7) -> float | None:
    """Return avg fyp_reach_pct for the prior window (days+1 to 2*days ago)."""
    now = datetime.utcnow()
    current_cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=days * 2)
    result = (
        session.query(func.avg(VideoMetric.fyp_reach_pct))
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= prior_cutoff,
            VideoMetric.recorded_at < current_cutoff,
        )
        .scalar()
    )
    return float(result) if result is not None else None


def get_kpi_prior_revenue(session: Session, account_id: str, days: int = 7) -> float:
    """Return total revenue for the prior window (days+1 to 2*days ago)."""
    now = datetime.utcnow()
    current_cutoff = now - timedelta(days=days)
    prior_cutoff = now - timedelta(days=days * 2)
    result = (
        session.query(func.sum(VideoMetric.affiliate_orders))
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= prior_cutoff,
            VideoMetric.recorded_at < current_cutoff,
        )
        .scalar()
    )
    return float(result or 0.0)


def get_top_videos_by_commission(
    session: Session,
    account_id: str,
    limit: int = 20,
) -> list[dict]:
    """Return top N videos by total commission earned, descending.

    Joins Video + VideoMetric + Product (optional) to compute commission.
    Returns list of dicts with keys:
      hook_archetype, retention_3s_pct, affiliate_ctr_pct, commission_earned, lifecycle_state
    """
    rows = (
        session.query(
            Video.hook_archetype,
            Video.lifecycle_state,
            func.avg(VideoMetric.retention_3s).label("avg_retention_3s"),
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label(
                "commission_earned"
            ),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .outerjoin(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            Video.account_id == account_id,
            Video.tiktok_video_id.isnot(None),
        )
        .group_by(Video.id, Video.hook_archetype, Video.lifecycle_state)
        .order_by(func.sum(VideoMetric.affiliate_orders * Product.commission_rate).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "hook_archetype": row.hook_archetype or "—",
            "retention_3s_pct": float(row.avg_retention_3s or 0.0),
            "affiliate_ctr_pct": (
                float(row.total_clicks or 0) / max(float(row.total_views or 0), 1.0)
            ),
            "commission_earned": float(row.commission_earned or 0.0),
            "lifecycle_state": row.lifecycle_state,
        }
        for row in rows
    ]


def get_tournament_niche_table(
    session: Session,
    account_id: str,
    days: int = 7,
) -> list[dict]:
    """Return niche tournament rankings with status assignment.

    Returns list of dicts with keys:
      rank, niche, video_count, avg_ctr_pct, avg_retention_3s_pct, total_revenue, status
    Sorted by score descending. Returns [] if no data.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        session.query(
            Video.niche,
            func.sum(VideoMetric.affiliate_clicks).label("total_clicks"),
            func.sum(VideoMetric.view_count).label("total_views"),
            func.avg(VideoMetric.retention_3s).label("avg_retention_3s"),
            func.sum(VideoMetric.affiliate_orders).label("total_orders"),
            func.count(func.distinct(VideoMetric.video_id)).label("video_count"),
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .filter(
            Video.account_id == account_id,
            VideoMetric.recorded_at >= cutoff,
        )
        .group_by(Video.niche)
        .all()
    )

    if not rows:
        return []

    max_orders = max(int(r.total_orders or 0) for r in rows)

    scored = []
    for row in rows:
        aff_ctr = int(row.total_clicks or 0) / max(int(row.total_views or 0), 1)
        retention = max(0.0, min(1.0, float(row.avg_retention_3s or 0.0)))
        norm_orders = int(row.total_orders or 0) / max(max_orders, 1)
        score = 0.40 * min(1.0, aff_ctr) + 0.30 * retention + 0.30 * norm_orders
        scored.append((row, aff_ctr, score))

    scored.sort(key=lambda x: x[2], reverse=True)

    eliminated_niches = {
        row.niche
        for row in session.query(Product.niche)
        .filter(Product.account_id == account_id, Product.eliminated == True)  # noqa: E712
        .distinct()
        .all()
    }

    result = []
    for rank, (row, aff_ctr, score) in enumerate(scored, start=1):
        if row.niche in eliminated_niches:
            status = "Eliminated"
        elif rank == 1:
            status = "Leading"
        else:
            status = "Trailing"

        result.append(
            {
                "rank": rank,
                "niche": row.niche,
                "video_count": int(row.video_count or 0),
                "avg_ctr_pct": aff_ctr,
                "avg_retention_3s_pct": float(row.avg_retention_3s or 0.0),
                "total_revenue": float(row.total_orders or 0),
                "status": status,
            }
        )
    return result


def flag_eliminated_niches(
    session: Session,
    account_id: str,
    niche_scores: list[tuple[str, float]],
    threshold_score: float,
) -> list[str]:
    """
    Set Product.eliminated = True for all products in niches scoring <= threshold_score.

    Returns list of niche names NEWLY flagged as eliminated (previously not eliminated).
    Idempotent: repeated calls with same inputs return [] on subsequent calls.
    """
    eliminated: list[str] = []
    for niche, score in niche_scores:
        if score <= threshold_score:
            updated = (
                session.query(Product)
                .filter_by(account_id=account_id, niche=niche, eliminated=False)
                .update({"eliminated": True})
            )
            if updated > 0:
                eliminated.append(niche)
    if eliminated:
        session.commit()
    return eliminated


def get_first_commission_amount(session: Session, account_id: str) -> float | None:
    """Return total lifetime commission for the account if > 0, else None.

    Used by dashboard to trigger the first-commission milestone banner.
    Returns None when no commission has ever been recorded.
    """
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("total")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    if result is None or result <= 0:
        return None
    return float(result)


def get_latest_phase_transition(session: Session, account_id: str) -> AgentDecision | None:
    """Return the most recent phase_transition AgentDecision within the last 24h, or None.

    Used by dashboard to trigger the phase-transition milestone banner.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        session.query(AgentDecision)
        .filter(
            AgentDecision.account_id == account_id,
            AgentDecision.decision_type == "phase_transition",
            AgentDecision.created_at >= cutoff,
        )
        .order_by(AgentDecision.created_at.desc())
        .first()
    )


def get_active_accounts(session: Session) -> list[Account]:
    """Return all Account rows where phase is not 'archived', ordered by account_id."""
    return (
        session.query(Account)
        .filter(Account.phase != "archived")
        .order_by(Account.account_id)
        .all()
    )


def provision_account(session: Session, account_id: str) -> bool:
    """Insert a new Account row with phase='warmup'. Idempotent — returns False if already exists."""  # noqa: E501
    existing = session.query(Account).filter_by(account_id=account_id).first()
    if existing is not None:
        _queries_logger.warning("Account %s already exists — skipping provision", account_id)
        return False
    session.add(
        Account(
            id=str(uuid.uuid4()),
            account_id=account_id,
            tiktok_access_token="",
            tiktok_open_id="",
            phase="warmup",
            paused_agent_queues=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    session.commit()
    return True


def get_monthly_revenue(session: Session, account_id: str) -> float:
    """Return total commission revenue for the current calendar month (UTC).

    Used by dashboard to trigger the $1K/month milestone banner.
    Returns 0.0 if no revenue data exists.
    """
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = (
        session.query(
            func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("revenue")
        )
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= month_start,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    return float(result or 0.0)


def get_account_summary_row(session: Session, account_id: str) -> dict:
    """Return a summary dict for one account for the dashboard portfolio table."""
    account = session.query(Account).filter_by(account_id=account_id).first()
    if account is None:
        return {
            "account_id": account_id,
            "phase": "unknown",
            "pipeline_healthy": True,
            "revenue_today": 0.0,
            "last_post_timedelta": None,
        }

    phase = account.phase

    errors = get_unresolved_errors(session, account_id)
    pipeline_healthy = len(errors) == 0

    now = datetime.utcnow()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    revenue_result = (
        session.query(func.sum(VideoMetric.affiliate_orders * Product.commission_rate).label("rev"))
        .join(Video, VideoMetric.video_id == Video.tiktok_video_id)
        .join(
            Product,
            (Product.account_id == Video.account_id) & (Product.product_id == Video.product_id),
        )
        .filter(
            VideoMetric.account_id == account_id,
            VideoMetric.recorded_at >= today_midnight,
            Video.product_id.isnot(None),
        )
        .scalar()
    )
    revenue_today = float(revenue_result or 0.0)

    last_video = (
        session.query(Video)
        .filter(
            Video.account_id == account_id,
            Video.posted_at.isnot(None),
        )
        .order_by(Video.posted_at.desc())
        .first()
    )
    last_post_timedelta = (now - last_video.posted_at) if last_video is not None else None

    return {
        "account_id": account_id,
        "phase": phase,
        "pipeline_healthy": pipeline_healthy,
        "revenue_today": revenue_today,
        "last_post_timedelta": last_post_timedelta,
    }
