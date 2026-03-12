"""
Unit tests for tiktok_faceless/db/session.py — engine setup and session management.
"""

from sqlalchemy.orm import Session

from tiktok_faceless.db.models import Account
from tiktok_faceless.db.session import get_engine, get_session, init_db


class TestGetEngine:
    def test_creates_sqlite_engine(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        assert engine is not None
        assert "sqlite" in str(engine.url)

    def test_default_falls_back_to_sqlite(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("DATABASE_URL", raising=False)
        engine = get_engine()
        assert "sqlite" in str(engine.url)


class TestInitDb:
    def test_creates_all_tables(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        init_db(engine)
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {"accounts", "videos", "video_metrics", "products", "agent_decisions", "errors"}
        assert expected.issubset(tables)


class TestGetSession:
    def test_returns_session(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        init_db(engine)
        with get_session(engine) as session:
            assert isinstance(session, Session)

    def test_session_can_query(self) -> None:
        engine = get_engine("sqlite:///:memory:")
        init_db(engine)
        with get_session(engine) as session:
            result = session.query(Account).all()
            assert result == []
