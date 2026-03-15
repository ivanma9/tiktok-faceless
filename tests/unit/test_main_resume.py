"""Tests for CLI resume functionality in tiktok_faceless/main.py."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.main import main, parse_args

_MAIN_MOD = "tiktok_faceless.main"


class TestParseArgs:
    def test_resume_cli_parses_args(self) -> None:
        with patch.object(
            sys, "argv", ["prog", "--resume-agent", "production", "--account-id", "acc1"]
        ):
            ns = parse_args()
        assert ns.resume_agent == "production"
        assert ns.account_id == "acc1"


class TestResumeCli:
    def _make_session_ctx(self):
        mock_session_obj = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_session_obj)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx, mock_session_obj

    def test_resume_cli_calls_resume_queue_and_resolve_errors(self) -> None:
        ctx, session_obj = self._make_session_ctx()
        with (
            patch.object(
                sys, "argv", ["prog", "--resume-agent", "production", "--account-id", "acc1"]
            ),
            patch(f"{_MAIN_MOD}.load_account_config"),
            patch(f"{_MAIN_MOD}.get_session", return_value=ctx),
            patch(f"{_MAIN_MOD}.resume_agent_queue") as mock_resume,
            patch(f"{_MAIN_MOD}.resolve_agent_errors") as mock_resolve,
            patch(f"{_MAIN_MOD}.send_resume_alert"),
        ):
            main()
        mock_resume.assert_called_once()
        mock_resolve.assert_called_once()

    def test_resume_cli_sends_telegram_alert(self) -> None:
        ctx, _ = self._make_session_ctx()
        with (
            patch.object(
                sys, "argv", ["prog", "--resume-agent", "production", "--account-id", "acc1"]
            ),
            patch(f"{_MAIN_MOD}.load_account_config") as mock_cfg,
            patch(f"{_MAIN_MOD}.get_session", return_value=ctx),
            patch(f"{_MAIN_MOD}.resume_agent_queue"),
            patch(f"{_MAIN_MOD}.resolve_agent_errors"),
            patch(f"{_MAIN_MOD}.send_resume_alert") as mock_alert,
        ):
            main()
        mock_alert.assert_called_once_with(
            account_id="acc1",
            agent="production",
            config=mock_cfg.return_value,
        )

    def test_resume_cli_missing_args_exits_nonzero(self) -> None:
        with (
            patch.object(sys, "argv", ["prog", "--resume-agent", "production"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code != 0
