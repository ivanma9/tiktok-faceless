"""
Typed query functions — all scoped by account_id.

Implementation: Story 1.2 — Core State & Database Models
Implementation: Story 2.1 — Product caching (cache_product, get_cached_products)
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Product
from tiktok_faceless.models.shop import AffiliateProduct

_PRODUCT_CACHE_TTL_HOURS = 24


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
        existing.cached_at = datetime.utcnow()
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
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from tiktok_faceless.db.models import Video, VideoMetric

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
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from tiktok_faceless.db.models import Video, VideoMetric

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
    ttl_hours: int = _PRODUCT_CACHE_TTL_HOURS,
) -> list[AffiliateProduct]:
    """Return cached products for account+niche still within TTL window."""
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
    rows = (
        session.query(Product)
        .filter(
            Product.account_id == account_id,
            Product.niche == niche,
            Product.cached_at >= cutoff,
        )
        .all()
    )
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
