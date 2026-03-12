"""
Unit tests for tiktok_faceless/config.py — AccountConfig and env loading.
"""

import pytest

from tiktok_faceless.config import AccountConfig


def _valid_kwargs() -> dict:  # type: ignore[type-arg]
    return {
        "account_id": "acc1",
        "tiktok_access_token": "tok_abc",
        "tiktok_client_key": "key_abc",
        "tiktok_client_secret": "secret_abc",
        "tiktok_open_id": "open_abc",
        "elevenlabs_api_key": "el_abc",
        "elevenlabs_voice_id": "voice_abc",
        "anthropic_api_key": "anth_abc",
    }


class TestAccountConfig:
    def test_valid_instantiation(self) -> None:
        cfg = AccountConfig(**_valid_kwargs())
        assert cfg.account_id == "acc1"
        assert cfg.max_posts_per_day == 3
        assert cfg.posting_window_start == 18
        assert cfg.posting_window_end == 22
        assert cfg.tournament_duration_days == 14
        assert cfg.retention_kill_threshold == 0.25
        assert cfg.fyp_suppression_threshold == 0.40

    def test_max_posts_per_day_min(self) -> None:
        cfg = AccountConfig(**{**_valid_kwargs(), "max_posts_per_day": 1})
        assert cfg.max_posts_per_day == 1

    def test_max_posts_per_day_max(self) -> None:
        cfg = AccountConfig(**{**_valid_kwargs(), "max_posts_per_day": 15})
        assert cfg.max_posts_per_day == 15

    def test_max_posts_per_day_too_high_raises(self) -> None:
        with pytest.raises(Exception):
            AccountConfig(**{**_valid_kwargs(), "max_posts_per_day": 16})

    def test_max_posts_per_day_too_low_raises(self) -> None:
        with pytest.raises(Exception):
            AccountConfig(**{**_valid_kwargs(), "max_posts_per_day": 0})

    def test_posting_window_start_bounds(self) -> None:
        AccountConfig(**{**_valid_kwargs(), "posting_window_start": 0})
        AccountConfig(**{**_valid_kwargs(), "posting_window_start": 23})
        with pytest.raises(Exception):
            AccountConfig(**{**_valid_kwargs(), "posting_window_start": 24})

    def test_retention_kill_threshold_bounds(self) -> None:
        AccountConfig(**{**_valid_kwargs(), "retention_kill_threshold": 0.0})
        AccountConfig(**{**_valid_kwargs(), "retention_kill_threshold": 1.0})
        with pytest.raises(Exception):
            AccountConfig(**{**_valid_kwargs(), "retention_kill_threshold": 1.1})

    def test_env_var_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "env_tok")
        monkeypatch.setenv("TIKTOK_CLIENT_KEY", "env_key")
        monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "env_secret")
        monkeypatch.setenv("TIKTOK_OPEN_ID", "env_open")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "env_el")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env_voice")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env_anth")

        from tiktok_faceless.config import load_account_config

        cfg = load_account_config("acc_env")
        assert cfg.account_id == "acc_env"
        assert cfg.tiktok_access_token == "env_tok"
        assert cfg.elevenlabs_api_key == "env_el"
