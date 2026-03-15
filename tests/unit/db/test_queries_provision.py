"""Tests for provision_account DB query helper in tiktok_faceless/db/queries.py."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Account, Base
from tiktok_faceless.db.queries import provision_account


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def test_provision_account_inserts_row(session) -> None:
    result = provision_account(session, "acc1")
    assert result is True
    row = session.query(Account).filter_by(account_id="acc1").first()
    assert row is not None


def test_provision_account_sets_warmup_phase(session) -> None:
    provision_account(session, "acc1")
    account = session.query(Account).filter_by(account_id="acc1").first()
    assert account.phase == "warmup"


def test_provision_account_idempotent(session) -> None:
    provision_account(session, "acc1")
    result = provision_account(session, "acc1")
    assert result is False
    count = session.query(Account).filter_by(account_id="acc1").count()
    assert count == 1


def test_provision_account_does_not_overwrite_phase(session) -> None:
    # Seed an account with phase="commit"
    session.add(
        Account(
            id=str(uuid.uuid4()),
            account_id="acc1",
            tiktok_access_token="tok",
            tiktok_open_id="oid",
            phase="commit",
        )
    )
    session.commit()

    provision_account(session, "acc1")

    account = session.query(Account).filter_by(account_id="acc1").first()
    assert account.phase == "commit"
