"""Tests for FalClient."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.clients import FalError
from tiktok_faceless.clients.fal import FalClient


class TestFalClient:
    def test_generate_video_returns_url(self) -> None:
        client = FalClient(api_key="test_key")
        mock_result = MagicMock()
        mock_result.get.return_value = {"video": {"url": "https://cdn.fal.ai/out.mp4"}}

        with patch("fal_client.submit", return_value=mock_result):
            url = client.generate_video(prompt="A product showcase video")

        assert url == "https://cdn.fal.ai/out.mp4"

    def test_exception_raises_fal_error(self) -> None:
        client = FalClient(api_key="test_key")

        with patch("fal_client.submit", side_effect=Exception("fal down")):
            with pytest.raises(FalError):
                client.generate_video(prompt="A product video")

    def test_submit_called_with_correct_endpoint(self) -> None:
        client = FalClient(api_key="test_key")
        mock_result = MagicMock()
        mock_result.get.return_value = {"video": {"url": "https://cdn.fal.ai/out.mp4"}}

        with patch("fal_client.submit", return_value=mock_result) as mock_submit:
            client.generate_video(prompt="test prompt")
            endpoint = mock_submit.call_args[0][0]
            assert "kling" in endpoint
