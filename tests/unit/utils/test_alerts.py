"""Unit tests for send_phase_alert."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.utils.alerts import send_phase_alert

_MOD = "tiktok_faceless.utils.alerts"


class TestSendPhaseAlert:
    """Tests for Telegram phase transition notification."""

    def test_sends_telegram_message_on_transition(self) -> None:
        """Posts to Telegram API with phase change message."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("tok123", "chat456", "tournament", "commit", "fitness")
        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        assert "Tournament" in call_kwargs.kwargs["json"]["text"]
        assert "Commit" in call_kwargs.kwargs["json"]["text"]

    def test_committed_niche_in_message(self) -> None:
        """Committed niche name appears in message text."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("tok", "chat", "tournament", "commit", "fitness_gear")
        text = mock_httpx.post.call_args.kwargs["json"]["text"]
        assert "fitness_gear" in text

    def test_empty_token_is_noop(self) -> None:
        """Empty bot_token → httpx.post never called."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("", "chat456", "tournament", "commit")
        mock_httpx.post.assert_not_called()

    def test_empty_chat_id_is_noop(self) -> None:
        """Empty chat_id → httpx.post never called."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("tok123", "", "tournament", "commit")
        mock_httpx.post.assert_not_called()

    def test_httpx_failure_is_swallowed(self) -> None:
        """httpx.HTTPError is swallowed — no exception propagated."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("network error")
            # Must not raise
            send_phase_alert("tok", "chat", "tournament", "commit", "fitness")

    def test_no_committed_niche_still_sends(self) -> None:
        """committed_niche=None → httpx.post still called (niche line omitted)."""
        with patch(f"{_MOD}.httpx") as mock_httpx:
            send_phase_alert("tok", "chat", "tournament", "commit", committed_niche=None)
        mock_httpx.post.assert_called_once()
