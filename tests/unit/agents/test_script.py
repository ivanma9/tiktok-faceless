"""Tests for tiktok_faceless/agents/script.py — script_node."""

from unittest.mock import MagicMock, patch

import pytest

from tiktok_faceless.agents.script import (
    VALID_HOOK_ARCHETYPES,
    _select_hook_archetype,
    script_node,
)
from tiktok_faceless.clients import LLMError
from tiktok_faceless.state import AgentError, PipelineState

_MOD = "tiktok_faceless.agents.script"


@pytest.fixture(autouse=True)
def _patch_db():
    """Auto-patch get_session and get_archetype_scores for all tests."""
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
    mock_ctx.__exit__ = MagicMock(return_value=False)
    with (
        patch(f"{_MOD}.get_session", return_value=mock_ctx),
        patch(f"{_MOD}.get_archetype_scores", return_value={}),
    ):
        yield

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
    cfg.archetype_min_sample_size = 5
    return cfg


def _state() -> PipelineState:
    return PipelineState(account_id="acc1", selected_product=_PRODUCT)


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
            with patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"):
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
            with patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"):
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
            with patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"):
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
            patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
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
            patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
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

    def test_current_script_matches_selected_archetype(self) -> None:
        """current_script is the variant for the selected archetype (curiosity_gap = first variant)."""
        state = PipelineState(account_id="acc1", selected_product=_PRODUCT_WITH_BUYER_LANGUAGE)
        call_num = 0

        def side_effect(prompt: str) -> str:
            nonlocal call_num
            call_num += 1
            return f"Script {call_num}"

        with (
            patch("tiktok_faceless.agents.script.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
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
            patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
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
            patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
            patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate_script.return_value = "Script"
            mock_llm_cls.return_value = mock_llm
            result = script_node(state)
        assert result.get("product_validated") is not False  # shouldn't be an error
        assert "current_script" in result


def test_partial_success_returns_completed_variants() -> None:
    """If archetype 2 fails with LLMError, archetype 1's script must still be returned."""
    from tiktok_faceless.agents.script import script_node
    from tiktok_faceless.clients import LLMError
    from tiktok_faceless.state import PipelineState

    state = PipelineState(
        account_id="acc1",
        selected_product={
            "product_id": "p1", "product_name": "Widget", "product_url": "u",
            "commission_rate": 0.1, "sales_velocity_score": 0.5, "niche": "health",
            "buyer_language": [],
        },
    )
    call_count = 0

    def flaky_generate(prompt: str, **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise LLMError("archetype 2 failed")
        return f"script for call {call_count}"

    mock_cfg = MagicMock()
    mock_cfg.anthropic_api_key = "key"
    mock_cfg.persona_name = ""
    mock_cfg.persona_catchphrase = ""
    mock_cfg.persona_tone = "casual"

    with (
        patch("tiktok_faceless.agents.script.load_account_config", return_value=mock_cfg),
        patch(f"{_MOD}._select_hook_archetype", return_value="curiosity_gap"),
        patch("tiktok_faceless.agents.script.LLMClient") as mock_llm_cls,
    ):
        mock_llm = MagicMock()
        mock_llm.generate_script.side_effect = flaky_generate
        mock_llm_cls.return_value = mock_llm
        result = script_node(state)

    # Should have 2 variants (1 and 3), not return an error
    assert "hook_variants" in result
    assert len(result["hook_variants"]) == 2
    assert "errors" not in result
    assert "current_script" in result


class TestArchetypeSelection:
    """Tests for _select_hook_archetype helper and script_node archetype selection."""

    def test_empty_scores_returns_random_archetype(self):
        result = _select_hook_archetype(["curiosity_gap", "social_proof", "controversy"], {}, 5)
        assert result in ["curiosity_gap", "social_proof", "controversy"]

    def test_all_sampled_uses_score_weights(self):
        scores = {
            "curiosity_gap": (0.8, 10),
            "social_proof": (0.4, 10),
            "controversy": (0.2, 10),
        }
        result = _select_hook_archetype(["curiosity_gap", "social_proof", "controversy"], scores, 5)
        assert result in ["curiosity_gap", "social_proof", "controversy"]

    def test_undersampled_archetype_gets_boost(self):
        scores = {
            "curiosity_gap": (0.5, 10),
            "social_proof": (0.5, 10),
            "controversy": (0.01, 2),
        }
        archetypes = ["curiosity_gap", "social_proof", "controversy"]
        with patch("tiktok_faceless.agents.script.random.choices") as mock_choices:
            mock_choices.return_value = ["controversy"]
            _select_hook_archetype(archetypes, scores, 5)
            _, kwargs = mock_choices.call_args
            weights = kwargs.get("weights") or mock_choices.call_args[0][1]
            assert weights[2] == pytest.approx(0.03)
            assert weights[0] == pytest.approx(0.5)

    def test_unknown_archetype_treated_as_undersampled(self):
        scores = {"curiosity_gap": (0.5, 10)}
        archetypes = ["curiosity_gap", "social_proof", "controversy"]
        with patch("tiktok_faceless.agents.script.random.choices") as mock_choices:
            mock_choices.return_value = ["social_proof"]
            _select_hook_archetype(archetypes, scores, 5)
            _, kwargs = mock_choices.call_args
            weights = kwargs.get("weights") or mock_choices.call_args[0][1]
            assert weights[1] == pytest.approx(3.0)
            assert weights[2] == pytest.approx(3.0)

    def test_zero_score_floor_prevents_zero_weight(self):
        scores = {"curiosity_gap": (0.0, 10), "social_proof": (0.5, 10), "controversy": (0.3, 10)}
        archetypes = ["curiosity_gap", "social_proof", "controversy"]
        with patch("tiktok_faceless.agents.script.random.choices") as mock_choices:
            mock_choices.return_value = ["curiosity_gap"]
            _select_hook_archetype(archetypes, scores, 5)
            _, kwargs = mock_choices.call_args
            weights = kwargs.get("weights") or mock_choices.call_args[0][1]
            assert weights[0] == pytest.approx(0.01)

    def test_script_node_calls_get_archetype_scores(self):
        state = _state()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session") as mock_get_sess,
            patch(f"{_MOD}.get_archetype_scores", return_value={}) as mock_gas,
            patch(f"{_MOD}.LLMClient") as mock_client,
        ):
            mock_ctx = MagicMock()
            mock_get_sess.return_value = mock_ctx
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.generate_script.return_value = "script text"
            script_node(state)
        mock_gas.assert_called_once()

    def test_script_node_returns_selected_archetype(self):
        state = _state()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session") as mock_get_sess,
            patch(f"{_MOD}.get_archetype_scores", return_value={}),
            patch(f"{_MOD}._select_hook_archetype", return_value="social_proof"),
            patch(f"{_MOD}.LLMClient") as mock_client,
        ):
            mock_ctx = MagicMock()
            mock_get_sess.return_value = mock_ctx
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.generate_script.return_value = "script text"
            result = script_node(state)
        assert result["hook_archetype"] == "social_proof"

    def test_script_node_fallback_to_first_variant_if_selected_missing(self):
        state = _state()
        with (
            patch(f"{_MOD}.load_account_config", return_value=_mock_config()),
            patch(f"{_MOD}.get_session") as mock_get_sess,
            patch(f"{_MOD}.get_archetype_scores", return_value={}),
            patch(f"{_MOD}._select_hook_archetype", return_value="nonexistent_archetype"),
            patch(f"{_MOD}.LLMClient") as mock_client,
        ):
            mock_ctx = MagicMock()
            mock_get_sess.return_value = mock_ctx
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.generate_script.return_value = "script text"
            result = script_node(state)
        assert result["hook_archetype"] == "curiosity_gap"
