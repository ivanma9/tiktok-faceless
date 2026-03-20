"""
Shared pytest fixtures and configuration.

Additional fixtures will be added as stories are implemented.
"""

import os

import pytest

from tiktok_faceless.db.session import get_engine, init_db


@pytest.fixture(autouse=True, scope="session")
def _test_database(tmp_path_factory):
    """
    Point DATABASE_URL at a temp SQLite file with all tables created.

    This ensures tests in CI (where tiktok_faceless_dev.db doesn't exist)
    still have a valid schema to query against.
    """
    tmp = tmp_path_factory.mktemp("db") / "test.db"
    db_url = f"sqlite:///{tmp}"
    os.environ["DATABASE_URL"] = db_url
    engine = get_engine(db_url)
    init_db(engine)
    yield
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture(autouse=True, scope="session")
def _checkpoint_db_in_memory(tmp_path_factory):
    """Redirect SqliteSaver to a temp file so tests don't write checkpoints.db to repo root."""
    tmp = tmp_path_factory.mktemp("checkpoints") / "checkpoints.db"
    os.environ["CHECKPOINT_DB_PATH"] = str(tmp)
    yield
    os.environ.pop("CHECKPOINT_DB_PATH", None)
