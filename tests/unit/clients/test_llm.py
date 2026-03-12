"""Tests for LLMClient."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.clients import LLMError
from tiktok_faceless.clients.llm import _MODEL_ID, LLMClient


class TestLLMClient:
    def test_model_id_is_haiku(self) -> None:
        assert _MODEL_ID == "claude-haiku-4-5-20251001"

    def test_generate_script_returns_string(self) -> None:
        client = LLMClient(api_key="test_key")
        mock_content = MagicMock()
        mock_content.text = "This is a generated script."
        mock_message = MagicMock()
        mock_message.content = [mock_content]

        with patch.object(client._client.messages, "create", return_value=mock_message):
            result = client.generate_script("Write a product script for Widget")

        assert result == "This is a generated script."

    def test_correct_model_used(self) -> None:
        client = LLMClient(api_key="test_key")
        mock_content = MagicMock()
        mock_content.text = "script"
        mock_message = MagicMock()
        mock_message.content = [mock_content]

        with patch.object(
            client._client.messages, "create", return_value=mock_message
        ) as mock_create:
            client.generate_script("prompt")
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"

    def test_api_exception_raises_llm_error(self) -> None:
        client = LLMClient(api_key="test_key")

        with patch.object(
            client._client.messages,
            "create",
            side_effect=Exception("API down"),
        ):
            with pytest.raises(LLMError):
                client.generate_script("prompt")
