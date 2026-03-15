"""Tests for Story 6.2 top bar helper functions and components."""

from datetime import datetime, timedelta
from unittest.mock import patch

from dashboard.components.phase_badge import render_phase_badge
from dashboard.components.time_utils import humanize_timedelta


class TestHumanizeTimedelta:
    def test_humanize_timedelta_minutes(self):
        delta = timedelta(minutes=3)
        assert humanize_timedelta(delta) == "3m ago"

    def test_humanize_timedelta_hours(self):
        delta = timedelta(hours=2, minutes=30)
        assert humanize_timedelta(delta) == "2h ago"

    def test_humanize_timedelta_days(self):
        delta = timedelta(days=1, hours=12)
        assert humanize_timedelta(delta) == "1d ago"


class TestRenderPhaseBadge:
    def test_render_phase_badge_tournament_with_day_counter(self):
        fixed_now = datetime(2024, 3, 10, 12, 0, 0)
        started_at = datetime(2024, 3, 5, 12, 0, 0)  # 5 days ago → Day 6
        captured: list[str] = []

        def fake_markdown(text, **kwargs):
            captured.append(text)

        with patch("dashboard.components.phase_badge.st") as mock_st:
            mock_st.markdown.side_effect = fake_markdown
            with patch("dashboard.components.phase_badge.datetime") as mock_dt:
                mock_dt.utcnow.return_value = fixed_now
                render_phase_badge("tournament", started_at)

        assert captured, "st.markdown was not called"
        assert "Tournament" in captured[0]
        assert "Day" in captured[0]

    def test_render_phase_badge_no_started_at(self):
        captured: list[str] = []

        def fake_markdown(text, **kwargs):
            captured.append(text)

        with patch("dashboard.components.phase_badge.st") as mock_st:
            mock_st.markdown.side_effect = fake_markdown
            render_phase_badge("commit", None)

        assert captured, "st.markdown was not called"
        assert "Commit" in captured[0]
        assert "Day" not in captured[0]
