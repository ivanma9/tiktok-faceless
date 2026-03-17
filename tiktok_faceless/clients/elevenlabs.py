"""
ElevenLabsClient: generate_voiceover via ElevenLabs TTS API.

Implementation: Story 1.3 — External API Client Wrappers
"""

import httpx

from tiktok_faceless.clients import ElevenLabsError
from tiktok_faceless.models.elevenlabs import ElevenLabsVoiceConfig
from tiktok_faceless.utils.retry import api_retry

_ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"


class ElevenLabsClient:
    """Typed wrapper for ElevenLabs Text-to-Speech API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=_ELEVENLABS_BASE_URL,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            timeout=60.0,
        )

    @api_retry
    def generate_voiceover(
        self,
        text: str,
        voice_id: str,
        config: ElevenLabsVoiceConfig | None = None,
    ) -> bytes:
        """
        Generate speech audio bytes for the given text and voice.

        Raises ElevenLabsError on any non-200 response.
        """
        cfg = config or ElevenLabsVoiceConfig(voice_id=voice_id)
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": cfg.stability,
                "similarity_boost": cfg.similarity_boost,
                "style": cfg.style,
            },
        }
        response = self._http.post(f"/v1/text-to-speech/{voice_id}", json=payload)
        if response.status_code != 200:
            raise ElevenLabsError(
                f"ElevenLabs API error {response.status_code}: {response.text}"
            )
        return bytes(response.content)

    def close(self) -> None:
        self._http.close()
