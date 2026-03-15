"""Tests for get_active_accounts query."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Account, Base
from tiktok_faceless.db.queries import get_active_accounts


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def _make_account(account_id: str, phase: str) -> Account:
    return Account(
        id=str(uuid.uuid4()),
        account_id=account_id,
        tiktok_access_token="tok",
        tiktok_open_id="oid",
        phase=phase,
    )


class TestGetActiveAccounts:
    def test_get_active_accounts_returns_non_archived(self, session) -> None:
        """Accounts with warmup/tournament/commit/scale phases are returned; archived is not."""
        for account_id, phase in [
            ("acc-warmup", "warmup"),
            ("acc-tournament", "tournament"),
            ("acc-commit", "commit"),
            ("acc-scale", "scale"),
            ("acc-archived", "archived"),
        ]:
            session.add(_make_account(account_id, phase))
        session.commit()

        result = get_active_accounts(session)
        result_ids = [a.account_id for a in result]

        assert "acc-warmup" in result_ids
        assert "acc-tournament" in result_ids
        assert "acc-commit" in result_ids
        assert "acc-scale" in result_ids
        assert "acc-archived" not in result_ids

    def test_get_active_accounts_excludes_archived(self, session) -> None:
        """When all accounts are archived, returns empty list."""
        session.add(_make_account("acc-only-archived", "archived"))
        session.commit()

        result = get_active_accounts(session)
        assert result == []

    def test_get_active_accounts_ordered_by_account_id(self, session) -> None:
        """Results are ordered ascending by account_id."""
        for account_id in ["acc-c", "acc-a", "acc-b"]:
            session.add(_make_account(account_id, "warmup"))
        session.commit()

        result = get_active_accounts(session)
        result_ids = [a.account_id for a in result]
        assert result_ids == sorted(result_ids)

    def test_get_active_accounts_empty_db(self, session) -> None:
        """No accounts in DB returns empty list."""
        result = get_active_accounts(session)
        assert result == []
