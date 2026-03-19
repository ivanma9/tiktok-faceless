"""
Unit tests for tiktok_faceless/db/models.py — SQLAlchemy ORM model structure.
"""

from tiktok_faceless.db.models import (
    Account,
    AgentDecision,
    Base,
    Error,
    Product,
    Video,
    VideoMetric,
)


class TestTableNames:
    def test_accounts_table_name(self) -> None:
        assert Account.__tablename__ == "accounts"

    def test_videos_table_name(self) -> None:
        assert Video.__tablename__ == "videos"

    def test_video_metrics_table_name(self) -> None:
        assert VideoMetric.__tablename__ == "video_metrics"

    def test_products_table_name(self) -> None:
        assert Product.__tablename__ == "products"

    def test_agent_decisions_table_name(self) -> None:
        assert AgentDecision.__tablename__ == "agent_decisions"

    def test_errors_table_name(self) -> None:
        assert Error.__tablename__ == "errors"


class TestCompositeIndex:
    def test_video_metrics_composite_index_exists(self) -> None:
        index_names = {idx.name for idx in VideoMetric.__table__.indexes}
        assert "ix_video_metrics_video_id_recorded_at" in index_names


class TestAccountColumns:
    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in Account.__table__.columns}
        for col in [
            "id",
            "account_id",
            "tiktok_access_token",
            "tiktok_open_id",
            "phase",
            "created_at",
            "updated_at",
        ]:
            assert col in cols, f"Missing column: {col}"


class TestVideoColumns:
    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in Video.__table__.columns}
        for col in [
            "id",
            "account_id",
            "niche",
            "hook_archetype",
            "lifecycle_state",
            "script_text",
            "voiceover_path",
            "assembled_video_path",
            "tiktok_video_id",
            "affiliate_link",
            "product_id",
            "created_at",
            "posted_at",
        ]:
            assert col in cols, f"Missing column: {col}"

    def test_account_id_fk(self) -> None:
        fk_targets = {fk.target_fullname for fk in Video.__table__.foreign_keys}
        assert "accounts.account_id" in fk_targets


class TestVideoMetricColumns:
    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in VideoMetric.__table__.columns}
        for col in [
            "id",
            "video_id",
            "account_id",
            "recorded_at",
            "view_count",
            "like_count",
            "comment_count",
            "share_count",
            "average_time_watched",
            "retention_3s",
            "retention_15s",
            "fyp_reach_pct",
            "affiliate_clicks",
            "affiliate_orders",
        ]:
            assert col in cols, f"Missing column: {col}"


class TestAllTablesInBase:
    def test_six_tables_registered(self) -> None:
        table_names = set(Base.metadata.tables.keys())
        assert table_names == {
            "accounts",
            "videos",
            "video_metrics",
            "products",
            "agent_decisions",
            "errors",
        }
