"""Tests for tiktok_faceless/utils/timing.py — posting window helpers."""

from unittest.mock import patch

from tiktok_faceless.utils.timing import get_random_posting_offset, is_within_posting_window


class TestGetRandomPostingOffset:
    def test_returns_float(self) -> None:
        result = get_random_posting_offset()
        assert isinstance(result, float)

    def test_within_range(self) -> None:
        result = get_random_posting_offset(min_minutes=5.0, max_minutes=30.0)
        assert 5.0 * 60 <= result <= 30.0 * 60

    def test_custom_range(self) -> None:
        result = get_random_posting_offset(min_minutes=1.0, max_minutes=2.0)
        assert 60.0 <= result <= 120.0


class TestIsWithinPostingWindow:
    def test_within_normal_window(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 20
            assert is_within_posting_window(18, 22) is True

    def test_outside_normal_window(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 10
            assert is_within_posting_window(18, 22) is False

    def test_at_window_boundary_start(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 18
            assert is_within_posting_window(18, 22) is True

    def test_at_window_boundary_end(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 22
            assert is_within_posting_window(18, 22) is True

    def test_overnight_window_within(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 23
            assert is_within_posting_window(22, 2) is True

    def test_overnight_window_within_early_morning(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 1
            assert is_within_posting_window(22, 2) is True

    def test_overnight_window_outside(self) -> None:
        with patch("tiktok_faceless.utils.timing.datetime") as mock_dt:
            mock_dt.utcnow.return_value.hour = 12
            assert is_within_posting_window(22, 2) is False
