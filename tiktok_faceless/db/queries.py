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
