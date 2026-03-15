"""
PipelineState, AgentError, and VideoLifecycle — shared contracts for all agents.

Zero imports from the rest of the project (prevents circular dependencies).
Implementation: Story 1.2 — Core State & Database Models
"""

import time
from enum import Enum
from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class VideoLifecycle(str, Enum):
    """Video state machine — all lifecycle transitions flow through this enum."""

    queued = "queued"
    rendering = "rendering"
    rendered = "rendered"
    scheduled = "scheduled"
    posted = "posted"
    analyzed = "analyzed"
    archived = "archived"
    promoted = "promoted"


class AgentError(BaseModel):
    """Structured error record emitted by agent nodes as state delta entries."""

    agent: str
    error_type: str
    message: str
    video_id: str | None = None
    recovery_suggestion: str | None = None
    timestamp: float = Field(default_factory=time.time)


class PipelineState(BaseModel):
    """
    Single source of truth for all pipeline state shared across LangGraph agent nodes.

    Fields annotated with Annotated[list[T], add] use LangGraph's reducer pattern —
    list items are appended (not replaced) when agent nodes return partial state deltas.
    """

    account_id: str
    phase: Literal["warmup", "tournament", "commit", "scale"] = "warmup"
    candidate_niches: list[str] = Field(default_factory=list)
    committed_niche: str | None = None
    selected_product: dict | None = None  # type: ignore[type-arg]
    product_validated: bool = False
    current_script: str | None = None
    hook_archetype: str | None = None
    hook_variants: list[dict] = Field(default_factory=list)  # type: ignore[type-arg]
    voiceover_path: str | None = None
    assembled_video_path: str | None = None
    published_video_id: str | None = None
    videos_produced_today: int = 0
    tournament_started_at: float = 0.0  # Unix timestamp when tournament phase began; 0.0 = not set
    last_post_timestamp: float = 0.0
    fyp_reach_rate: float = 1.0
    suppression_alert: bool = False
    niche_decay_alert: bool = False
    consecutive_decay_count: int = 0
    consecutive_suppression_count: int = 0
    kill_video_ids: Annotated[list[str], add] = Field(default_factory=list)
    affiliate_commission_week: float = 0.0
    last_reconciliation_at: float = 0.0
    agent_health: dict[str, bool] = Field(default_factory=dict)
    errors: Annotated[list[AgentError], add] = Field(default_factory=list)
