"""
Production agent: ElevenLabs TTS voiceover + Creatomate video assembly.

Single public export: production_node(state) -> dict (state delta only).
Implementation: Story 1.4 — Video Production Agent
"""

import base64
import os
import uuid
from pathlib import Path
from typing import Any

from tiktok_faceless.clients import ElevenLabsError, RenderError
from tiktok_faceless.clients.creatomate import CreatomateClient
from tiktok_faceless.clients.elevenlabs import ElevenLabsClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.db.queries import get_pending_video, save_rendered_video
from tiktok_faceless.db.session import get_session
from tiktok_faceless.state import AgentError, PipelineState
from tiktok_faceless.utils.recovery import get_recovery_suggestion


def production_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate voiceover audio + assembled video from state.current_script.

    Returns state delta dict with voiceover_path and assembled_video_path on success,
    or errors list on failure. Never returns full PipelineState.
    """
    if state.current_script is None:
        return {
            "errors": [
                AgentError(
                    agent="production",
                    error_type="MissingScript",
                    message="current_script is None — cannot produce without a script",
                    recovery_suggestion=get_recovery_suggestion("MissingScript"),
                )
            ]
        }

    # Reuse an existing rendered-but-unposted video if available (saves API quota)
    with get_session() as session:
        pending = get_pending_video(session, state.account_id)
    if pending is not None:
        return {
            "voiceover_path": pending.voiceover_path or "",
            "assembled_video_path": pending.assembled_video_path,
        }

    config = load_account_config(state.account_id)

    # ── Step 1: Generate voiceover ──────────────────────────────────────────
    voiceover_path: str
    try:
        el_client = ElevenLabsClient(api_key=config.elevenlabs_api_key)
        audio_bytes = el_client.generate_voiceover(
            text=state.current_script,
            voice_id=config.elevenlabs_voice_id,
        )
        audio_dir = Path("output") / state.account_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        voiceover_path = str(audio_dir / f"{uuid.uuid4()}.mp3")
        Path(voiceover_path).write_bytes(audio_bytes)
    except ElevenLabsError as e:
        return {
            "errors": [
                AgentError(
                    agent="production",
                    error_type="ElevenLabsError",
                    message=str(e),
                    recovery_suggestion=get_recovery_suggestion("ElevenLabsError"),
                )
            ]
        }

    # ── Step 2: Submit render → poll → download ─────────────────────────────
    try:
        cr_client = CreatomateClient(api_key=config.creatomate_api_key)
        vps_host = os.environ.get("VPS_HOST", "5.78.141.19")
        public_audio_url = f"http://{vps_host}/{voiceover_path}"
        job_id = cr_client.submit_render(
            template_id=config.creatomate_template_id,
            data={
                "Text-1": state.current_script,
                "Music": public_audio_url,
            },
        )
        output_url = cr_client.poll_status(job_id, timeout_seconds=600)
        video_dir = Path("output") / state.account_id / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = str(video_dir / f"{uuid.uuid4()}.mp4")
        cr_client.download_render(output_url, video_path)
    except RenderError as e:
        return {
            "errors": [
                AgentError(
                    agent="production",
                    error_type="RenderError",
                    message=str(e),
                    recovery_suggestion=get_recovery_suggestion("RenderError"),
                )
            ]
        }

    niche = (state.selected_product or {}).get("niche", "unknown") if state.selected_product else "unknown"
    with get_session() as session:
        save_rendered_video(
            session,
            account_id=state.account_id,
            voiceover_path=voiceover_path,
            assembled_video_path=video_path,
            script_text=state.current_script,
            niche=niche,
        )

    return {
        "voiceover_path": voiceover_path,
        "assembled_video_path": video_path,
    }
