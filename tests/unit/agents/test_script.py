"""Tests for tiktok_faceless/agents/script.py — script_node."""

from unittest.mock import MagicMock, patch

from tiktok_faceless.agents.script import VALID_HOOK_ARCHETYPES, script_node
from tiktok_faceless.clients import LLMError
from tiktok_faceless.state import AgentError, PipelineState

_PRODUCT = {
    "product_id": "p1",
    "product_name": "Widget Pro",
    "product_url": "https://example.com/widget",
    "commission_rate": 0.15,
    "niche": "health",
    "sales_velocity_score": 0.8,
}

_PRODUCT_WITH_BUYER_LANGUAGE = {
    "product_id": "p1",
    "product_name": "Widget Pro",
    "product_url": "https://example.com/widget",
    "commission_rate": 0.15,
    "niche": "health",
    "sales_velocity_score": 0.8,
    "buyer_language": ["where can I get this", "does it work"],
}


def _mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.anthropic_api_key = "ant_key"
    cfg.persona_name = ""
    cfg.persona_catchphrase = ""
    cfg.persona_tone = "casual"
    return cfg


class TestScriptNodeGuards:
    def test_missing_product_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=None)
        result = script_node(state)
        assert "errors" in result
        assert len(result["errors"]) == 1
        err = result["errors"][0]
        assert isinstance(err, AgentError)
        assert err.agent == "script"
        assert err.error_type == "MissingProduct"
        assert "current_script" not in result
        assert "hook_archetype" not in result


class TestScriptNodeSuccess:
    def test_returns_script_and_hook_archetype(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.script.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls:
                mock_llm = MagicMock()
                mock_llm.generate_script.return_value = "Widget changes everything! Click now."
                mock_llm_cls.return_value = mock_llm

                result = script_node(state)

        assert "current_script" in result
        assert isinstance(result["current_script"], str)
        assert len(result["current_script"]) > 0
        assert "hook_archetype" in result
        assert "errors" not in result

    def test_hook_archetype_is_valid(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.script.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls:
                mock_llm = MagicMock()
                mock_llm.generate_script.return_value = "Great script text here."
                mock_llm_cls.return_value = mock_llm

                result = script_node(state)

        assert result["hook_archetype"] in VALID_HOOK_ARCHETYPES


class TestScriptNodeErrors:
    def test_llm_error_returns_agent_error(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT)

        with patch(
            "tiktok_faceless.agents.script.load_account_config",
            return_value=_mock_config(),
        ):
            with patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls:
                mock_llm = MagicMock()
                mock_llm.generate_script.side_effect = LLMError("Timeout")
                mock_llm_cls.return_value = mock_llm

                result = script_node(state)

        assert "errors" in result
        assert result["errors"][0].agent == "script"
        assert result["errors"][0].error_type == "LLMError"
        assert "current_script" not in result
        assert "hook_archetype" not in result


class TestScriptNodeHookVariants:
    def test_llm_called_three_times(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Some script text"
            mock_llm_cls.return_value = mock_llm
            script_node(state)
        assert mock_llm.generate_script.call_count == 3

    def test_all_three_variants_in_hook_variants(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Some script"
            mock_llm_cls.return_value = mock_llm
            result = script_node(state)
        assert "hook_variants" in result
        assert len(result["hook_variants"]) == 3
        archetypes = [v["archetype"] for v in result["hook_variants"]]
        assert "curiosity_gap" in archetypes
        assert "social_proof" in archetypes
        assert "controversy" in archetypes

    def test_current_script_is_first_variant(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        call_num = 0

        def side_effect(prompt: str) -> str:
            nonlocal call_num
            call_num += 1
            return f"Script {call_num}"

        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.side_effect = side_effect
            mock_llm_cls.return_value = mock_llm
            result = script_node(state)
        assert result["current_script"] == "Script 1"
        assert result["hook_archetype"] == "curiosity_gap"

    def test_buyer_language_in_prompts(self) -> None:
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Script"
            mock_llm_cls.return_value = mock_llm
            script_node(state)
        all_prompts = " ".join(
            call.args[0] if call.args else call.kwargs.get("prompt", "")
            for call in mock_llm.generate_script.call_args_list
        )
        assert "where can I get this" in all_prompts

    def test_missing_buyer_language_handled_gracefully(self) -> None:
        product_no_lang = {k: v for k, v in _PRODUCT.items()}  # no buyer_language key
        state = PipelineState(account_id="acc1", selected_product=product_no_lang)
        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Script"
            mock_llm_cls.return_value = mock_llm
            result = script_node(state)
        assert result.get("product_validated") is not False  # shouldn't be an error
        assert "current_script" in result
