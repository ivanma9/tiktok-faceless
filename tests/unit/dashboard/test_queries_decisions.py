"""Tests for Story 6.5 — get_agent_decisions and get_resolved_errors query functions."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import AgentDecision, Base, Error
from tiktok_faceless.db.queries import get_agent_decisions, get_resolved_errors

_ACCOUNT = "acc_decisions_test"
_OTHER = "acc_other"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _make_decision(
    session,
    account_id: str = _ACCOUNT,
    agent: str = "orchestrator",
    decision_type: str = "phase_transition",
    from_value: str | None = "warmup",
    to_value: str | None = "tournament",
    rationale: str = "CTR threshold met",
    supporting_data: str | None = None,
    created_at: datetime | None = None,
) -> AgentDecision:
    d = AgentDecision(
        account_id=account_id,
        agent=agent,
        decision_type=decision_type,
        from_value=from_value,
        to_value=to_value,
        rationale=rationale,
        supporting_data=supporting_data,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(d)
    session.flush()
    return d


def _make_error(
    session,
    account_id: str = _ACCOUNT,
    agent: str = "production",
    error_type: str = "VideoAssemblyError",
    message: str = "Assembly failed",
    resolved_at: datetime | None = None,
    timestamp: datetime | None = None,
) -> Error:
    e = Error(
        account_id=account_id,
        agent=agent,
        error_type=error_type,
        message=message,
        resolved_at=resolved_at,
        timestamp=timestamp or datetime.utcnow(),
    )
    session.add(e)
    session.flush()
    return e


# --- get_agent_decisions ---


def test_get_agent_decisions_returns_empty_when_no_rows(session):
    result = get_agent_decisions(session, _ACCOUNT)
    assert result == []


def test_get_agent_decisions_returns_newest_first(session):
    now = datetime.utcnow()
    _make_decision(session, created_at=now - timedelta(hours=2))
    _make_decision(session, created_at=now - timedelta(hours=1))
    _make_decision(session, created_at=now)
    result = get_agent_decisions(session, _ACCOUNT)
    assert len(result) == 3
    assert result[0].created_at >= result[1].created_at >= result[2].created_at


def test_get_agent_decisions_scoped_to_account_id(session):
    _make_decision(session, account_id=_ACCOUNT)
    _make_decision(session, account_id=_OTHER)
    result = get_agent_decisions(session, _ACCOUNT)
    assert len(result) == 1
    assert result[0].account_id == _ACCOUNT


def test_get_agent_decisions_respects_limit(session):
    now = datetime.utcnow()
    for i in range(110):
        _make_decision(session, created_at=now - timedelta(seconds=i))
    result = get_agent_decisions(session, _ACCOUNT, limit=100)
    assert len(result) == 100


# --- get_resolved_errors ---


def test_get_resolved_errors_returns_empty_when_none(session):
    _make_error(session, resolved_at=None)
    _make_error(session, resolved_at=None)
    result = get_resolved_errors(session, _ACCOUNT)
    assert result == []


def test_get_resolved_errors_returns_only_resolved(session):
    resolved = _make_error(session, resolved_at=datetime.utcnow())
    _make_error(session, resolved_at=None)
    result = get_resolved_errors(session, _ACCOUNT)
    assert len(result) == 1
    assert result[0].id == resolved.id


def test_get_resolved_errors_returns_newest_first(session):
    now = datetime.utcnow()
    _make_error(session, resolved_at=now, timestamp=now - timedelta(hours=2))
    _make_error(session, resolved_at=now, timestamp=now - timedelta(hours=1))
    _make_error(session, resolved_at=now, timestamp=now)
    result = get_resolved_errors(session, _ACCOUNT)
    assert len(result) == 3
    assert result[0].timestamp >= result[1].timestamp >= result[2].timestamp


def test_get_resolved_errors_respects_limit(session):
    now = datetime.utcnow()
    for i in range(60):
        _make_error(session, resolved_at=now, timestamp=now - timedelta(seconds=i))
    result = get_resolved_errors(session, _ACCOUNT, limit=50)
    assert len(result) == 50
