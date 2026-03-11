"""
AccountConfig and environment variable loading.

Call load_env() once at startup (in main.py only) before using load_account_config().
Implementation: Story 1.2 — Core State & Database Models
"""

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AccountConfig(BaseModel):
    """Per-account configuration with validated thresholds and posting parameters."""

    account_id: str
    tiktok_access_token: str
    tiktok_client_key: str
    tiktok_client_secret: str
    tiktok_open_id: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    anthropic_api_key: str
    creatomate_api_key: str = ""
    creatomate_template_id: str = ""
    niche_pool: list[str] = Field(default_factory=list)
    max_posts_per_day: int = Field(default=3, ge=1, le=15)
    posting_window_start: int = Field(default=18, ge=0, le=23)
    posting_window_end: int = Field(default=22, ge=0, le=23)
    tournament_duration_days: int = Field(default=14, ge=7)
    retention_kill_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    fyp_suppression_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    commit_phase_min_videos: int = Field(default=5, ge=1)
    min_commission_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    min_sales_velocity: float = Field(default=0.3, ge=0.0, le=1.0)


def load_env() -> None:
    """Load .env file into environment. Call once in main.py only."""
    load_dotenv()


def load_account_config(account_id: str) -> AccountConfig:
    """
    Build AccountConfig for the given account_id from environment variables.

    Environment variables are read at call time — call load_env() first in main.py.
    """
    return AccountConfig(
        account_id=account_id,
        tiktok_access_token=os.environ["TIKTOK_ACCESS_TOKEN"],
        tiktok_client_key=os.environ["TIKTOK_CLIENT_KEY"],
        tiktok_client_secret=os.environ["TIKTOK_CLIENT_SECRET"],
        tiktok_open_id=os.environ["TIKTOK_OPEN_ID"],
        elevenlabs_api_key=os.environ["ELEVENLABS_API_KEY"],
        elevenlabs_voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        creatomate_api_key=os.environ.get("CREATOMATE_API_KEY", ""),
        creatomate_template_id=os.environ.get("CREATOMATE_TEMPLATE_ID", ""),
    )
