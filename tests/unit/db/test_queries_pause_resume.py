"""Tests for pause/resume DB query helpers in tiktok_faceless/db/queries.py."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Account, Base, Error
from tiktok_faceless.db.queries import (
    get_paused_agents,
    pause_agent_queue,
    resolve_agent_errors,
    resume_agent_queue,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    s = factory()
    yield s
    s.close()


def _make_account(session, account_id: str = "acc1") -> Account:
    acc = Account(
        id=str(uuid.uuid4()),
        account_id=account_id,
        tiktok_access_token="tok",
        tiktok_open_id="oid",
    )
    session.add(acc)
    session.commit()
    return acc


def _make_error(
    session,
    account_id: str = "acc1",
    agent: str = "production",
    resolved_at: datetime | None = None,
) -> Error:
    err = Error(
        account_id=account_id,
        agent=agent,
        error_type="TestError",
        message="test",
        resolved_at=resolved_at,
    )
    session.add(err)
    session.commit()
    return err


class TestPauseAgentQueue:
    def test_pause_agent_queue_adds_to_list(self, session) -> None:
        _make_account(session)
        pause_agent_queue(session, "acc1", "production")
        assert get_paused_agents(session, "acc1") == ["production"]

    def test_pause_agent_queue_idempotent(self, session) -> None:
        _make_account(session)
        pause_agent_queue(session, "acc1", "production")
        pause_agent_queue(session, "acc1", "production")
        assert get_paused_agents(session, "acc1") == ["production"]


class TestResumeAgentQueue:
    def test_resume_agent_queue_removes_from_list(self, session) -> None:
        _make_account(session)
        pause_agent_queue(session, "acc1", "production")
        pause_agent_queue(session, "acc1", "script")
        resume_agent_queue(session, "acc1", "production")
        assert get_paused_agents(session, "acc1") == ["script"]


class TestResolveAgentErrors:
    def test_resolve_agent_errors_stamps_resolved_at(self, session) -> None:
        _make_account(session)
        err = _make_error(session, agent="production")
        resolve_agent_errors(session, "acc1", "production")
        session.refresh(err)
        assert err.resolved_at is not None

    def test_resolve_agent_errors_ignores_already_resolved(self, session) -> None:
        _make_account(session)
        already_resolved = datetime(2024, 1, 1, 12, 0, 0)
        err = _make_error(session, agent="production", resolved_at=already_resolved)
        resolve_agent_errors(session, "acc1", "production")
        session.refresh(err)
        # Already resolved rows are not changed by the query (filter excludes them)
        assert err.resolved_at == already_resolved


class TestGetPausedAgents:
    def test_get_paused_agents_returns_empty_for_null(self, session) -> None:
        _make_account(session)
        result = get_paused_agents(session, "acc1")
        assert result == []
