"""
Research agent: product validation, comment mining, niche scanning, and decay detection.

Implementation: Story 2.1 — Product Validation via Buyer Intent Signals
"""

from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.queries import cache_product, get_cached_products
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState


def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the committed niche via TikTok Shop buyer intent signals.

    Returns state delta dict with selected_product + product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.

    Cache logic: products fetched within 24h are reused — no redundant API calls.
    """
    niche = state.committed_niche
    if not niche:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message=(
                        "committed_niche is not set — cannot validate products "
                        "without a target niche"
                    ),
                    recovery_suggestion=(
                        "Set committed_niche in state before calling research_node."
                    ),
                )
            ]
        }

    config = load_account_config(state.account_id)

    # Cache check: skip API if fresh products exist
    with get_session() as session:
        cached = get_cached_products(session, account_id=state.account_id, niche=niche)

    if cached:
        best = max(cached, key=lambda p: p.sales_velocity_score)
        return {
            "selected_product": best.model_dump(),
            "product_validated": True,
        }

    # Live API fetch
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )
    try:
        products = client.get_validated_products(
            account_id=state.account_id,
            niche=niche,
            min_commission_rate=config.min_commission_rate,
            min_sales_velocity=config.min_sales_velocity,
        )
    except (TikTokRateLimitError, TikTokAPIError) as e:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type=type(e).__name__,
                    message=str(e),
                    recovery_suggestion=(
                        "TikTok API error during product search. Check rate limits and credentials."
                    ),
                )
            ]
        }

    if not products:
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=(
                        f"No products in niche '{niche}' met the validation thresholds "
                        f"(min_commission={config.min_commission_rate}, "
                        f"min_velocity={config.min_sales_velocity})"
                    ),
                    recovery_suggestion=(
                        f"Try a different niche or lower the thresholds. Current niche: {niche}."
                    ),
                )
            ],
        }

    # Cache results
    with get_session() as session:
        for product in products:
            cache_product(session, account_id=state.account_id, product=product)

    best = products[0]  # already sorted by sales_velocity_score descending
    return {
        "selected_product": best.model_dump(),
        "product_validated": True,
    }
