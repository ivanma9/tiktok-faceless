"""
Shared pytest fixtures and configuration.

Additional fixtures will be added as stories are implemented.
"""
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def _checkpoint_db_in_memory(tmp_path_factory):
    """Redirect SqliteSaver to a temp file so tests don't write checkpoints.db to repo root."""
    tmp = tmp_path_factory.mktemp("checkpoints") / "checkpoints.db"
    os.environ["CHECKPOINT_DB_PATH"] = str(tmp)
    yield
    os.environ.pop("CHECKPOINT_DB_PATH", None)
