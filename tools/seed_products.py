"""
Seed fitness supplement affiliate products into the DB.

Run once on the VPS:
    uv run python tools/seed_products.py

Products use placeholder affiliate URLs — replace with your Amazon Associates
links once you have an associate ID (format: ?tag=YOUR_ID-20).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from tiktok_faceless.db.queries import cache_product
from tiktok_faceless.db.session import get_session
from tiktok_faceless.models.shop import AffiliateProduct

ACCOUNT_ID = "acc1"

PRODUCTS = [
    AffiliateProduct(
        product_id="on-gold-whey-5lb",
        product_name="Optimum Nutrition Gold Standard 100% Whey Protein 5lb",
        product_url="https://www.amazon.com/dp/B000QSNYGI?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.05,
        sales_velocity_score=0.92,
        niche="protein powder",
    ),
    AffiliateProduct(
        product_id="cellucor-c4-preworkout",
        product_name="Cellucor C4 Original Pre Workout Powder",
        product_url="https://www.amazon.com/dp/B009NLDXGE?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.05,
        sales_velocity_score=0.88,
        niche="pre-workout",
    ),
    AffiliateProduct(
        product_id="creatine-monohydrate-micronized",
        product_name="Optimum Nutrition Micronized Creatine Monohydrate 600g",
        product_url="https://www.amazon.com/dp/B002DYIZEO?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.05,
        sales_velocity_score=0.85,
        niche="creatine",
    ),
    AffiliateProduct(
        product_id="legion-pulse-preworkout",
        product_name="Legion Pulse Pre Workout Supplement",
        product_url="https://www.amazon.com/dp/B00PHAPU9G?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.08,
        sales_velocity_score=0.82,
        niche="pre-workout",
    ),
    AffiliateProduct(
        product_id="transparent-labs-bulk",
        product_name="Transparent Labs BULK Pre-Workout",
        product_url="https://www.amazon.com/dp/B07WQYXJ7R?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.08,
        sales_velocity_score=0.80,
        niche="fitness supplements",
    ),
    AffiliateProduct(
        product_id="garden-of-life-protein",
        product_name="Garden of Life Organic Protein Powder",
        product_url="https://www.amazon.com/dp/B00J074W7Q?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.06,
        sales_velocity_score=0.78,
        niche="protein powder",
    ),
    AffiliateProduct(
        product_id="ghost-whey-protein",
        product_name="GHOST Whey Protein Powder",
        product_url="https://www.amazon.com/dp/B07KQJP8KY?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.07,
        sales_velocity_score=0.76,
        niche="protein powder",
    ),
    AffiliateProduct(
        product_id="hydroxycut-hardcore-elite",
        product_name="Hydroxycut Hardcore Elite Weight Loss Supplement",
        product_url="https://www.amazon.com/dp/B00CTKH5OE?tag=REPLACE_WITH_YOUR_TAG",
        commission_rate=0.06,
        sales_velocity_score=0.72,
        niche="fat burners",
    ),
]


def main():
    with get_session() as session:
        for product in PRODUCTS:
            cache_product(session, account_id=ACCOUNT_ID, product=product)
            print(f"Seeded: {product.product_name} [{product.niche}]")
    print(f"\nDone — {len(PRODUCTS)} products seeded for account {ACCOUNT_ID}")


if __name__ == "__main__":
    main()
