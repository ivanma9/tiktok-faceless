"""Time utility helpers for the dashboard — Story 6.2."""

from datetime import timedelta


def humanize_timedelta(delta: timedelta) -> str:
    """Return a human-readable string like '3m ago', '2h ago', '1d ago'."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    return f"{total_seconds // 86400}d ago"
