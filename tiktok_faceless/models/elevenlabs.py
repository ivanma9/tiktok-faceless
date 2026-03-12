"""
Pydantic models for ElevenLabs API: ElevenLabsVoiceConfig.

Implementation: Story 1.3 — External API Client Wrappers
"""

from pydantic import BaseModel


class ElevenLabsVoiceConfig(BaseModel):
    """Voice generation parameters for ElevenLabs TTS API."""

    voice_id: str
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
