"""Tests for CreatomateClient."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.clients import RenderError
from tiktok_faceless.clients.creatomate import CreatomateClient


class TestCreatomateClient:
    def _make_client(self) -> CreatomateClient:
        return CreatomateClient(api_key="test_key")

    def test_submit_render_returns_job_id(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "job_abc123", "status": "planned"}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._http, "post", return_value=mock_response):
            job_id = client.submit_render(template_id="tmpl_1", data={"product_name": "Widget"})

        assert job_id == "job_abc123"

    def test_submit_render_failure_raises_render_error(self) -> None:
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Invalid template"

        with patch.object(client._http, "post", return_value=mock_response):
            with pytest.raises(RenderError):
                client.submit_render(template_id="bad_tmpl", data={})

    def test_poll_status_succeeds(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "job_abc",
            "status": "succeeded",
            "url": "https://cdn.example.com/out.mp4",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._http, "get", return_value=mock_resp):
            url = client.poll_status("job_abc")

        assert url == "https://cdn.example.com/out.mp4"

    def test_poll_status_failed_raises_render_error(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "job_abc", "status": "failed"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._http, "get", return_value=mock_resp):
            with pytest.raises(RenderError):
                client.poll_status("job_abc")

    def test_poll_status_timeout_raises_render_error(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "job_abc", "status": "rendering"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._http, "get", return_value=mock_resp):
            with patch("time.sleep"):
                with pytest.raises(RenderError, match="timed out"):
                    client.poll_status("job_abc", timeout_seconds=0)
