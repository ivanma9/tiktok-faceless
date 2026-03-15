"""
Telegram webhook sender for suppression alerts, pipeline pause, and health checks.

Implementation: Stories 3.4 (Phase Alerts) & 4.3 (Suppression Alerts)
Implementation: Story 5.3 — Agent Queue Pause & Manual Resume
"""

import datetime
import logging

import httpx

from tiktok_faceless.config import AccountConfig

logger = logging.getLogger(__name__)


def send_phase_alert(
    bot_token: str,
    chat_id: str,
    from_phase: str,
    to_phase: str,
    committed_niche: str | None = None,
    timestamp: float | None = None,
) -> None:
    """
    Send a Telegram message for a phase transition. Non-fatal — all errors swallowed.

    No-op if bot_token or chat_id is empty (Telegram not configured).
    """
    if not bot_token or not chat_id:
        return
    try:
        text = f"Phase changed: {from_phase.title()} → {to_phase.title()}."
        if committed_niche:
            text += f" Winning niche: {committed_niche}."
        if timestamp is not None:
            dt = datetime.datetime.fromtimestamp(
                timestamp, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
            text += f"\nTime: {dt}"
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001
        pass  # Never block pipeline on notification failure


def send_suppression_alert(
    bot_token: str,
    chat_id: str,
    fyp_rate: float,
    threshold: float,
    account_id: str,
    timestamp: float | None = None,
) -> None:
    """
    Send a Telegram suppression alert. Non-fatal — all errors swallowed.

    No-op if bot_token or chat_id is empty (Telegram not configured).
    """
    if not bot_token or not chat_id:
        return
    try:
        text = (
            f"[SUPPRESSION] Suppression detected for {account_id}: "
            f"FYP reach {fyp_rate:.1%} below threshold {threshold:.1%}."
        )
        if timestamp is not None:
            dt = datetime.datetime.fromtimestamp(
                timestamp, tz=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
            text += f"\nTime: {dt}"
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001
        pass  # Never block pipeline on notification failure


def send_resume_alert(account_id: str, agent: str, config: AccountConfig) -> None:
    """
    Send a Telegram message when an agent queue is manually resumed.

    No-op if bot_token or chat_id is empty (Telegram not configured).
    Non-fatal — all errors swallowed.
    """
    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.info("send_resume_alert: no Telegram config, skipping")
        return
    try:
        message = f"Agent {agent} resumed for account {account_id}"
        httpx.post(
            f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage",
            json={"chat_id": config.telegram_chat_id, "text": message},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001
        pass  # Never block pipeline on notification failure
