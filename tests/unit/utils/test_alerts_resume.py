"""Tests for send_resume_alert in tiktok_faceless/utils/alerts.py."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.utils.alerts import send_resume_alert

_MOD = "tiktok_faceless.utils.alerts"


def _make_config(token: str = "tok123", chat_id: str = "chat456") -> MagicMock:
    cfg = MagicMock()
    cfg.telegram_bot_token = token
    cfg.telegram_chat_id = chat_id
    return cfg


class TestSendResumeAlert:
    def test_send_resume_alert_posts_correct_message(self) -> None:
        config = _make_config()
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_resume_alert(account_id="acc1", agent="production", config=config)
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        text = call_kwargs.kwargs["json"]["text"]
        assert "production" in text
        assert "acc1" in text

    def test_send_resume_alert_noop_when_token_empty(self) -> None:
        config = _make_config(token="")
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_resume_alert(account_id="acc1", agent="production", config=config)
        mock_httpx.post.assert_not_called()
