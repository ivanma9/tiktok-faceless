"""Tests for tiktok_faceless/utils/video.py — ffmpeg helpers."""

import subprocess
from unittest.mock import MagicMock, patch

from tiktok_faceless.utils.video import get_video_duration, strip_metadata


class TestStripMetadata:
    def test_returns_path_string(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake_video_data")
        path = str(video_file)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = strip_metadata(path)

        assert isinstance(result, str)
        assert result == path

    def test_gracefully_handles_missing_ffmpeg(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake_video_data")
        path = str(video_file)

        with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
            result = strip_metadata(path)

        # Should return original path unchanged
        assert result == path

    def test_gracefully_handles_ffmpeg_failure(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake_video_data")
        path = str(video_file)

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
        ):
            result = strip_metadata(path)

        assert result == path


class TestGetVideoDuration:
    def test_returns_float(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = str(tmp_path / "test.mp4")

        mock_result = MagicMock()
        mock_result.stdout = "12.5\n"
        with patch("subprocess.run", return_value=mock_result):
            duration = get_video_duration(path)

        assert isinstance(duration, float)
        assert duration == 12.5

    def test_returns_zero_on_failure(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = str(tmp_path / "test.mp4")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            duration = get_video_duration(path)

        assert duration == 0.0
