"""
Randomized posting window logic for suppression-resistant cadence.

Implementation: Story 1.6 — Publishing Agent with Suppression-Resistant Cadence
"""

import random
from datetime import datetime


def get_random_posting_offset(min_minutes: float = 5.0, max_minutes: float = 30.0) -> float:
    """
    Return a random offset in seconds within [min_minutes*60, max_minutes*60].

    Used to introduce human-variability in posting cadence (FR20).
    """
    return random.uniform(min_minutes * 60.0, max_minutes * 60.0)


def is_within_posting_window(window_start: int, window_end: int) -> bool:
    """
    Return True if the current UTC hour falls within [window_start, window_end] inclusive.

    Handles overnight wrap-around (e.g., start=22, end=2).
    """
    hour = datetime.utcnow().hour
    if window_start <= window_end:
        return window_start <= hour <= window_end
    # Overnight wrap: e.g., start=22, end=2
    return hour >= window_start or hour <= window_end
