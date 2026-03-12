"""
Research agent: product validation, comment mining, niche scanning, and decay detection.

Implementation: Story 2.1 — Product Validation via Buyer Intent Signals
"""

from typing import Any

from tiktok_faceless.clients import TikTokAPIError, TikTokRateLimitError
from tiktok_faceless.clients.tiktok import TikTokAPIClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.queries import cache_product, get_cached_products, get_commission_per_view
from tiktok_faceless.db.session import get_session
from tiktok_faceless.models.shop import AffiliateProduct
from tiktok_faceless.state import AgentError, PipelineState


def research_node(state: PipelineState) -> dict[str, Any]:
    """
    Validate products for the configured niche(s) via TikTok Shop buyer intent signals.

    In tournament phase: scans all candidate_niches and picks the best product overall.
    In other phases: scans only committed_niche.

    Returns state delta dict with selected_product + product_validated=True on success,
    or errors list on failure. Never returns full PipelineState.

    Cache logic: products fetched within 24h are reused — no redundant API calls.
    """
    # Determine niches to scan based on phase
    if state.phase == "tournament":
        niches = state.candidate_niches
    else:
        niches = [state.committed_niche] if state.committed_niche else []

    if not niches:
        return {
            "errors": [
                AgentError(
                    agent="research",
                    error_type="MissingNiche",
                    message=(
                        "No niches to scan. Set committed_niche (commit/other phases) "
                        "or candidate_niches (tournament phase)."
                    ),
                    recovery_suggestion=(
                        "Populate committed_niche or candidate_niches in state before "
                        "calling research_node."
                    ),
                )
            ]
        }

    config = load_account_config(state.account_id)
    client = TikTokAPIClient(
        access_token=config.tiktok_access_token,
        open_id=config.tiktok_open_id,
    )

    # Collect best product per niche
    all_best: list[AffiliateProduct] = []

    for niche in niches:
        # Cache check per niche
        with get_session() as session:
            cached = get_cached_products(session, account_id=state.account_id, niche=niche)

        if cached:
            all_best.append(max(cached, key=lambda p: p.sales_velocity_score))
            continue

        # Live API fetch for this niche
        try:
            products = client.get_validated_products(
                account_id=state.account_id,
                niche=niche,
                min_commission_rate=config.min_commission_rate,
                min_sales_velocity=config.min_sales_velocity,
            )
        except (TikTokRateLimitError, TikTokAPIError):
            # Non-fatal per niche — continue to next niche
            continue

        if products:
            with get_session() as session:
                for product in products:
                    cache_product(session, account_id=state.account_id, product=product)
            all_best.append(products[0])

    if not all_best:
        return {
            "product_validated": False,
            "errors": [
                AgentError(
                    agent="research",
                    error_type="NoValidatedProducts",
                    message=f"No products in niches {niches} met the validation thresholds.",
                    recovery_suggestion="Try different niches or lower thresholds.",
                )
            ],
        }

    # Pick winner across all niches
    best = max(all_best, key=lambda p: p.sales_velocity_score)

    # Mine buyer-language comments only when a real video ID is available (non-fatal)
    comments: list[str] = []
    if best.top_video_id:
        try:
            comments = client.get_video_comments(video_id=best.top_video_id, max_count=20)
        except (TikTokRateLimitError, TikTokAPIError):
            comments = []

    # Decay detection (commit phase only, non-fatal)
    decay_delta: dict[str, Any] = {}
    if state.phase == "commit" and state.committed_niche:
        try:
            with get_session() as session:
                cpv = get_commission_per_view(
                    session, account_id=state.account_id, niche=state.committed_niche
                )
            if cpv > 0 and cpv < config.decay_threshold:
                new_count = state.consecutive_decay_count + 1
                decay_delta["consecutive_decay_count"] = new_count
                if new_count >= 2:
                    decay_delta["niche_decay_alert"] = True
            elif cpv >= config.decay_threshold:
                decay_delta["consecutive_decay_count"] = 0
        except Exception:  # noqa: BLE001
            pass  # Never block pipeline on decay detection failure

    product_dict = best.model_dump()
    product_dict["buyer_language"] = comments
    return {
        "selected_product": product_dict,
        "product_validated": True,
        **decay_delta,
    }
