"""
Database engine setup and session context manager.

Usage:
    engine = get_engine()          # reads DATABASE_URL env var
    init_db(engine)                # SQLite dev only — use Alembic in production
    with get_session(engine) as session:
        ...

Implementation: Story 1.2 — Core State & Database Models
"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tiktok_faceless.db.models import Base

_DEFAULT_DATABASE_URL = "sqlite:///./tiktok_faceless_dev.db"


def get_engine(database_url: str | None = None) -> Engine:
    """
    Create a SQLAlchemy engine.

    Uses the provided URL, then DATABASE_URL env var, then SQLite dev default.
    """
    url = database_url or os.environ.get("DATABASE_URL") or _DEFAULT_DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    """
    Create all tables from ORM metadata.

    For SQLite dev use only. In production, use `alembic upgrade head`.
    """
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    """Yield a transactional database session, rolling back on exception."""
    resolved_engine = engine or get_engine()
    factory = sessionmaker(bind=resolved_engine, autocommit=False, autoflush=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
