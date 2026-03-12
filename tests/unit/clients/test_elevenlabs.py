"""Tests for ElevenLabsClient."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.clients import ElevenLabsError
from tiktok_faceless.clients.elevenlabs import ElevenLabsClient


class TestElevenLabsClient:
    def _make_client(self) -> ElevenLabsClient:
        return ElevenLabsClient(api_key="test_key")

    def test_generate_voiceover_returns_bytes(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio_bytes_here"
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._http, "post", return_value=mock_response):
            result = client.generate_voiceover(text="Hello world", voice_id="voice_abc")

        assert result == b"audio_bytes_here"

    def test_non_200_raises_elevenlabs_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Unprocessable"

        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(ElevenLabsError):
                client.generate_voiceover(text="Hello", voice_id="voice_abc")

    def test_500_raises_elevenlabs_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"

        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(ElevenLabsError):
                client.generate_voiceover(text="Hello", voice_id="voice_abc")
