"""
FalClient: Kling video generation via fal.ai.

Implementation: Story 1.3 — External API Client Wrappers
"""

import os

import fal_client

from tiktok_faceless.clients import FalError

_KLING_ENDPOINT = "fal-ai/kling-video/v1.6/standard/text-to-video"


class FalClient:
    """Typed wrapper for fal.ai Kling video generation."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        os.environ["FAL_KEY"] = api_key

    def generate_video(self, prompt: str, image_url: str | None = None) -> str:
        """
        Submit a Kling video generation job and return the output video URL.

        Raises FalError on any API failure.
        """
        try:
            arguments: dict[str, str] = {"prompt": prompt}
            if image_url is not None:
                arguments["image_url"] = image_url
            result = fal_client.submit(_KLING_ENDPOINT, arguments=arguments)
            output = result.get()
            return str(output["video"]["url"])
        except Exception as e:
            raise FalError(f"fal.ai generation failed: {e}") from e
