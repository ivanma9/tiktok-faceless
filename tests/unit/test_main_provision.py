"""Tests for --provision-account CLI and _run_provision in tiktok_faceless/main.py."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.main import _run_provision, main


def test_provision_account_cli_arg_calls_run_provision() -> None:
    with patch("tiktok_faceless.main._run_provision") as mock_provision:
        sys.argv = ["main", "--provision-account", "acc2"]
        main()
        mock_provision.assert_called_once_with("acc2")


def test_run_provision_calls_load_account_config() -> None:
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with patch("tiktok_faceless.main.load_account_config") as mock_load, \
         patch("tiktok_faceless.main.provision_account", return_value=True), \
         patch("tiktok_faceless.main.get_session", return_value=mock_session_cm):
        _run_provision("acc2")
        mock_load.assert_called_once_with("acc2")


def test_run_provision_calls_provision_account() -> None:
    mock_session = MagicMock()
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with patch("tiktok_faceless.main.load_account_config"), \
         patch("tiktok_faceless.main.provision_account", return_value=True) as mock_prov, \
         patch("tiktok_faceless.main.get_session", return_value=mock_session_cm):
        _run_provision("acc2")
        mock_prov.assert_called_once_with(mock_session, "acc2")


def test_run_provision_missing_env_var_propagates() -> None:
    with patch("tiktok_faceless.main.load_account_config", side_effect=KeyError("MISSING_VAR")):
        with pytest.raises(KeyError):
            _run_provision("acc2")


def test_run_provision_idempotent_no_error() -> None:
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__ = MagicMock(return_value=MagicMock())
    mock_session_cm.__exit__ = MagicMock(return_value=False)

    with patch("tiktok_faceless.main.load_account_config"), \
         patch("tiktok_faceless.main.provision_account", return_value=False), \
         patch("tiktok_faceless.main.get_session", return_value=mock_session_cm):
        # Should not raise
        _run_provision("acc2")
