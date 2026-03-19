"""
ffmpeg helpers: metadata strip and video duration probe.

All functions degrade gracefully if ffmpeg/ffprobe is unavailable.
Implementation: Story 1.4 — Video Production Agent
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def strip_metadata(video_path: str) -> str:
    """
    Strip identifying metadata from a video file using ffmpeg.

    Replaces the original file in-place.
    Returns video_path unchanged if ffmpeg is unavailable or fails.
    """
    tmp_path = video_path + ".tmp.mp4"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                video_path,
                "-map_metadata",
                "-1",
                "-c",
                "copy",
                tmp_path,
                "-y",
            ],
            capture_output=True,
            check=True,
        )
        Path(tmp_path).replace(Path(video_path))
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning("strip_metadata failed (ffmpeg unavailable?): %s", e)
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
    return video_path


def get_video_duration(video_path: str) -> float:
    """
    Return video duration in seconds using ffprobe.

    Returns 0.0 if ffprobe is unavailable or the file cannot be probed.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except (FileNotFoundError, ValueError) as e:
        logger.warning("get_video_duration failed: %s", e)
        return 0.0
