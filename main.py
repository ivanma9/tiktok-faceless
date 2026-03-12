"""
Entry point for the tiktok-faceless autonomous pipeline.

Usage:
    uv run python main.py

Environment variables required:
    ACCOUNT_ID          — unique identifier for this TikTok account
    (see .env.example for full list)

Secrets are loaded from .env locally; systemd EnvironmentFile= in production.
Implementation: Story 1.7 — Orchestrator Pipeline Wiring & Crash Recovery
"""

import logging
import os
import sys

from tiktok_faceless.config import load_env
from tiktok_faceless.db.session import get_engine, init_db
from tiktok_faceless.graph import build_graph
from tiktok_faceless.state import PipelineState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_env()
    init_db(get_engine())

    account_id = os.environ.get("ACCOUNT_ID", "default_account")

    state = PipelineState(
        account_id=account_id,
        selected_product={
            "product_id": os.environ.get("TEST_PRODUCT_ID", "test_prod_1"),
            "product_name": os.environ.get("TEST_PRODUCT_NAME", "Test Widget"),
            "product_url": os.environ.get("TEST_PRODUCT_URL", "https://example.com"),
            "commission_rate": 0.15,
            "niche": os.environ.get("TEST_NICHE", "health"),
            "sales_velocity_score": 1.0,
        },
    )

    graph = build_graph()
    logger.info("Starting pipeline for account_id=%s", account_id)

    result = graph.invoke(
        state.model_dump(),
        config={"configurable": {"thread_id": account_id}},
    )
    logger.info("Pipeline complete: published_video_id=%s", result.get("published_video_id"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by operator")
        sys.exit(0)
