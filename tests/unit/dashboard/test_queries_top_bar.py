"""Tests for Story 6.2 top bar query functions in tiktok_faceless.db.queries."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tiktok_faceless.db.models import Account, Base, Error, Video
from tiktok_faceless.db.queries import (
    get_account_phase,
    get_active_suppression,
    get_agent_health_from_errors,
    get_last_post_time,
    get_unresolved_errors,
    get_videos_posted_today,
)

_POSTED_STATES = ("posted", "analyzed", "archived", "promoted")


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _account(account_id: str = "acc1") -> Account:
    return Account(
        id=str(uuid.uuid4()),
        account_id=account_id,
        tiktok_access_token="tok",
        tiktok_open_id="oid",
        phase="warmup",
    )


def _video(
    account_id: str = "acc1",
    lifecycle_state: str = "posted",
    posted_at: datetime | None = None,
) -> Video:
    return Video(
        id=str(uuid.uuid4()),
        account_id=account_id,
        niche="pets",
        lifecycle_state=lifecycle_state,
        posted_at=posted_at or datetime.utcnow(),
    )


def _error(
    account_id: str = "acc1",
    agent: str = "publishing",
    error_type: str = "generic",
    resolved_at: datetime | None = None,
) -> Error:
    return Error(
        account_id=account_id,
        agent=agent,
        error_type=error_type,
        message="something broke",
        resolved_at=resolved_at,
    )


class TestGetLastPostTime:
    def test_returns_none_when_no_videos(self, session):
        result = get_last_post_time(session, "acc1")
        assert result is None

    def test_returns_max_posted_at(self, session):
        earlier = datetime(2024, 1, 1, 10, 0, 0)
        later = datetime(2024, 1, 2, 10, 0, 0)
        session.add(_video(posted_at=earlier))
        session.add(_video(posted_at=later))
        session.commit()
        result = get_last_post_time(session, "acc1")
        assert result == later

    def test_excludes_unposted_lifecycles(self, session):
        session.add(_video(lifecycle_state="queued", posted_at=datetime(2024, 1, 1)))
        session.commit()
        result = get_last_post_time(session, "acc1")
        assert result is None


class TestGetVideosPostedToday:
    def test_returns_zero_when_none(self, session):
        result = get_videos_posted_today(session, "acc1")
        assert result == 0

    def test_counts_only_today(self, session):
        today = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        session.add(_video(posted_at=today, lifecycle_state="posted"))
        session.add(_video(posted_at=yesterday, lifecycle_state="posted"))
        session.commit()
        result = get_videos_posted_today(session, "acc1")
        assert result == 1


class TestGetAccountPhase:
    def test_returns_warmup_default(self, session):
        result = get_account_phase(session, "nonexistent")
        assert result == "warmup"

    def test_returns_account_phase(self, session):
        acc = _account("acc2")
        acc.phase = "tournament"
        session.add(acc)
        session.commit()
        result = get_account_phase(session, "acc2")
        assert result == "tournament"


class TestGetUnresolvedErrors:
    def test_excludes_resolved(self, session):
        session.add(_error(resolved_at=datetime.utcnow()))
        session.add(_error(resolved_at=None))
        session.commit()
        result = get_unresolved_errors(session, "acc1")
        assert len(result) == 1
        assert result[0].resolved_at is None


class TestGetActiveSuppression:
    def test_returns_none_when_resolved(self, session):
        session.add(_error(error_type="suppression_detected", resolved_at=datetime.utcnow()))
        session.commit()
        result = get_active_suppression(session, "acc1")
        assert result is None

    def test_returns_active_suppression(self, session):
        session.add(_error(error_type="suppression_detected", resolved_at=None))
        session.commit()
        result = get_active_suppression(session, "acc1")
        assert result is not None
        assert result.error_type == "suppression_detected"


class TestGetAgentHealthFromErrors:
    def test_marks_agent_unhealthy(self, session):
        session.add(_error(agent="publishing", resolved_at=None))
        session.commit()
        result = get_agent_health_from_errors(session, "acc1")
        assert result["publishing"] is False
        assert result["orchestrator"] is True
