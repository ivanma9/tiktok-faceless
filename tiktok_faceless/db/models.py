"""
SQLAlchemy ORM models: Account, Video, VideoMetric, Product, AgentDecision, Error.

Uses SQLAlchemy 2.0 Mapped/mapped_column syntax throughout — never legacy Column().
All tables include account_id for per-account isolation.
Implementation: Story 1.2 — Core State & Database Models
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    """Per-account configuration and phase state."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    tiktok_access_token: Mapped[str] = mapped_column(String, nullable=False)
    tiktok_open_id: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False, default="warmup")
    paused_agent_queues: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Video(Base):
    """Video lifecycle state machine — one row per produced video."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    niche: Mapped[str] = mapped_column(String, nullable=False)
    hook_archetype: Mapped[str | None] = mapped_column(String, nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    script_text: Mapped[str | None] = mapped_column(String, nullable=True)
    voiceover_path: Mapped[str | None] = mapped_column(String, nullable=True)
    assembled_video_path: Mapped[str | None] = mapped_column(String, nullable=True)
    tiktok_video_id: Mapped[str | None] = mapped_column(String, nullable=True)
    affiliate_link: Mapped[str | None] = mapped_column(String, nullable=True)
    product_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VideoMetric(Base):
    """
    Append-only analytics event log — never update rows, only insert.

    One row per analytics poll per video. Trends computed at query time.
    """

    __tablename__ = "video_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_time_watched: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retention_3s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retention_15s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fyp_reach_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    affiliate_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affiliate_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_video_metrics_video_id_recorded_at", "video_id", "recorded_at"),)


class Product(Base):
    """Validated product research cache — 24h TTL enforced in application code."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    niche: Mapped[str] = mapped_column(String, nullable=False)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    commission_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sales_velocity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cached_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    eliminated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("account_id", "product_id", name="uq_product_account_product"),
    )


class AgentDecision(Base):
    """
    Immutable audit log of all phase transitions and significant agent decisions.

    Phase changes must write here before updating PipelineState.
    """

    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    decision_type: Mapped[str] = mapped_column(String, nullable=False)
    from_value: Mapped[str | None] = mapped_column(String, nullable=True)
    to_value: Mapped[str | None] = mapped_column(String, nullable=True)
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    supporting_data: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Error(Base):
    """Structured error log surfaced in dashboard with recovery guidance."""

    __tablename__ = "errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    error_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    video_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recovery_suggestion: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
