"""Tests for dashboard.auth.check_password — Story 6.1."""

import os
from unittest.mock import patch

from dashboard.auth import check_password


class TestCheckPassword:
    def _env(self, password: str = "secret"):
        return patch.dict(os.environ, {"DASHBOARD_PASSWORD": password})

    def test_check_password_returns_true_when_session_authenticated(self):
        with self._env():
            with patch("dashboard.auth.st") as mock_st:
                mock_st.session_state = {"authenticated": True}
                result = check_password()
        assert result is True

    def test_check_password_returns_false_when_not_authenticated(self):
        with self._env():
            with patch("dashboard.auth.st") as mock_st:
                mock_st.session_state = {}
                mock_st.text_input.return_value = ""
                mock_st.button.return_value = False
                result = check_password()
        assert result is False

    def test_check_password_sets_session_on_correct_password(self):
        session: dict = {}
        with self._env("secret"):
            with patch("dashboard.auth.st") as mock_st:
                mock_st.session_state = session
                mock_st.text_input.return_value = "secret"
                mock_st.button.return_value = True
                check_password()
        assert session.get("authenticated") is True

    def test_check_password_shows_error_on_wrong_password(self):
        with self._env("secret"):
            with patch("dashboard.auth.st") as mock_st:
                mock_st.session_state = {}
                mock_st.text_input.return_value = "wrong"
                mock_st.button.return_value = True
                check_password()
        mock_st.error.assert_called_once()
