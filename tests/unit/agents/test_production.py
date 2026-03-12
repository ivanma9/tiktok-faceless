"""Tests for tiktok_faceless/agents/production.py — production_node."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.production import production_node
from tiktok_faceless.clients import ElevenLabsError, RenderError
from tiktok_faceless.state import AgentError, PipelineState


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.elevenlabs_api_key = "el_key"
    cfg.elevenlabs_voice_id = "voice_id"
    cfg.creatomate_api_key = "cr_key"
    cfg.creatomate_template_id = "tmpl_123"
    return cfg


class TestProductionNodeGuards:
    def test_missing_script_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", current_script=None)
        result = production_node(state)
        assert "errors" in result
        assert len(result["errors"]) == 1
        err = result["errors"][0]
        assert isinstance(err, AgentError)
        assert err.agent == "production"
        assert err.error_type == "MissingScript"
        assert "voiceover_path" not in result
        assert "assembled_video_path" not in result


class TestProductionNodeSuccess:
    def test_returns_voiceover_and_video_paths(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        state = PipelineState(
            account_id="acc1",
            current_script="Test script for video",
            hook_archetype="problem_solution",
        )

        with patch(
            "tiktok_faceless.agents.production.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.production.ElevenLabsClient") as mock_el_cls:
                with patch(
                    "tiktok_faceless.agents.production.CreatomateClient"
                ) as mock_cr_cls:
                    with patch(
                        "tiktok_faceless.agents.production.Path"
                    ) as mock_path_cls:
                        # Setup ElevenLabs mock
                        mock_el = MagicMock()
                        mock_el.generate_voiceover.return_value = b"audio_data"
                        mock_el_cls.return_value = mock_el

                        # Setup Creatomate mock
                        mock_cr = MagicMock()
                        mock_cr.submit_render.return_value = "job_123"
                        mock_cr.poll_status.return_value = "https://cdn.example.com/out.mp4"
                        mock_cr.download_render.return_value = "/output/acc1/videos/xyz.mp4"
                        mock_cr_cls.return_value = mock_cr

                        # Setup Path mock
                        mock_path_instance = MagicMock()
                        mock_path_cls.return_value = mock_path_instance
                        mock_path_instance.__truediv__ = MagicMock(
                            return_value=mock_path_instance
                        )
                        mock_path_instance.__str__ = MagicMock(
                            return_value="/output/acc1/audio/abc.mp3"
                        )

                        result = production_node(state)

        assert "voiceover_path" in result
        assert "assembled_video_path" in result
        assert "errors" not in result or len(result.get("errors", [])) == 0


class TestProductionNodeErrors:
    def test_elevenlabs_error_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", current_script="Test script")

        with patch(
            "tiktok_faceless.agents.production.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.production.ElevenLabsClient"
            ) as mock_el_cls:
                mock_el = MagicMock()
                mock_el.generate_voiceover.side_effect = ElevenLabsError("API down")
                mock_el_cls.return_value = mock_el

                result = production_node(state)

        assert "errors" in result
        assert result["errors"][0].agent == "production"
        assert result["errors"][0].error_type == "ElevenLabsError"
        assert "voiceover_path" not in result
        assert "assembled_video_path" not in result

    def test_render_error_returns_agent_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        state = PipelineState(account_id="acc1", current_script="Test script")

        with patch(
            "tiktok_faceless.agents.production.load_account_config",
            return_value=_mock_config(),
        ):
            with patch(
                "tiktok_faceless.agents.production.ElevenLabsClient"
            ) as mock_el_cls:
                with patch(
                    "tiktok_faceless.agents.production.CreatomateClient"
                ) as mock_cr_cls:
                    with patch("tiktok_faceless.agents.production.Path"):
                        mock_el = MagicMock()
                        mock_el.generate_voiceover.return_value = b"audio"
                        mock_el_cls.return_value = mock_el

                        mock_cr = MagicMock()
                        mock_cr.submit_render.side_effect = RenderError("Render failed")
                        mock_cr_cls.return_value = mock_cr

                        result = production_node(state)

        assert "errors" in result
        assert result["errors"][0].error_type == "RenderError"
        assert "assembled_video_path" not in result
