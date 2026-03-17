"""
CreatomateClient: submit_render, poll_status, and download_render.

Implementation: Story 1.3 — External API Client Wrappers
"""

import time

import httpx

from tiktok_faceless.clients import RenderError
from tiktok_faceless.utils.retry import api_retry

_CREATOMATE_BASE_URL = "https://api.creatomate.com"
_POLL_INTERVAL_SECONDS = 10


class CreatomateClient:
    """Typed wrapper for Creatomate video rendering API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=_CREATOMATE_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    @api_retry
    def submit_render(self, template_id: str, data: dict[str, str]) -> str:
        """
        Submit a render job for the given template and dynamic data.

        Returns the render job ID string.
        Raises RenderError on API failure.
        """
        response = self._http.post(
            "/v1/renders",
            json={"template_id": template_id, "modifications": data},
        )
        if response.status_code not in (200, 201, 202):
            raise RenderError(f"Creatomate submit failed {response.status_code}: {response.text}")
        renders = response.json()
        return str(renders[0]["id"])

    def poll_status(self, job_id: str, timeout_seconds: int = 600) -> str:
        """
        Poll until render status is 'succeeded' or timeout is reached.

        Returns the output file URL on success.
        Raises RenderError on failure or timeout.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self._http.get(f"/v1/renders/{job_id}")
            if response.status_code != 200:
                raise RenderError(f"Poll error {response.status_code}: {response.text}")
            render = response.json()
            status = render.get("status", "")
            if status == "succeeded":
                return str(render.get("url", ""))
            if status == "failed":
                raise RenderError(f"Render job {job_id} failed")
            time.sleep(_POLL_INTERVAL_SECONDS)

        raise RenderError(f"Render job {job_id} timed out after {timeout_seconds}s")

    @api_retry
    def download_render(self, output_url: str, dest_path: str) -> str:
        """Download a rendered file to dest_path. Returns dest_path."""
        response = httpx.get(output_url, follow_redirects=True, timeout=120.0)
        if response.status_code != 200:
            raise RenderError(f"Download failed {response.status_code}")
        with open(dest_path, "wb") as f:
            f.write(response.content)
        return dest_path

    def close(self) -> None:
        self._http.close()
