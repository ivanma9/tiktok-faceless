"""
Script agent: hook variant generation and persona application.

Implementation: Story 1.5 — Basic Script & Affiliate Link Generation
Implementation: Story 2.4 — Full Script Generation with Hook Archetypes & Persona
"""

from typing import Any

from tiktok_faceless.clients import LLMError
from tiktok_faceless.clients.llm import LLMClient
from tiktok_faceless.config import load_account_config
from tiktok_faceless.state import AgentError, PipelineState

THREE_HOOK_ARCHETYPES: list[str] = [
    "curiosity_gap",
    "social_proof",
    "controversy",
]

# Keep for backwards compatibility
VALID_HOOK_ARCHETYPES = THREE_HOOK_ARCHETYPES


def _build_script_prompt(
    product: dict[str, Any],
    hook_archetype: str,
    buyer_language: list[str] | None = None,
    persona_name: str = "",
    persona_catchphrase: str = "",
    persona_tone: str = "casual",
) -> str:
    buyer_section = ""
    if buyer_language:
        phrases = ", ".join(f'"{p}"' for p in buyer_language[:3])
        buyer_section = f"\nBuyer phrases to incorporate: {phrases}"
    persona_section = ""
    if persona_name:
        persona_section = (
            f"\nPersona: {persona_name}. "
            f"Catchphrase: '{persona_catchphrase}'. Tone: {persona_tone}."
        )
    return (
        f"You are a viral TikTok creator. Generate a short (<60s) video script "
        f"for a {hook_archetype.replace('_', ' ')} style hook.\n\n"
        f"Product: {product.get('product_name', 'Unknown Product')}\n"
        f"Niche: {product.get('niche', 'general')}\n"
        f"URL: {product.get('product_url', '')}\n"
        f"Commission: {product.get('commission_rate', 0):.0%}\n"
        f"{buyer_section}{persona_section}\n"
        f"Script (60 words max, no hashtags, end with clear CTA):"
    )


def script_node(state: PipelineState) -> dict[str, Any]:
    """
    Generate 3 hook variant scripts for the selected product.

    Returns state delta with current_script (first variant), hook_archetype,
    and hook_variants (all 3) on success. Fails on missing product or LLM error.
    """
    if state.selected_product is None:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="MissingProduct",
                    message="selected_product is None — cannot generate script without a product",
                )
            ]
        }

    config = load_account_config(state.account_id)
    buyer_language: list[str] = state.selected_product.get("buyer_language") or []

    try:
        llm = LLMClient(api_key=config.anthropic_api_key)
        variants = []
        for archetype in THREE_HOOK_ARCHETYPES:
            prompt = _build_script_prompt(
                state.selected_product,
                archetype,
                buyer_language=buyer_language,
                persona_name=config.persona_name,
                persona_catchphrase=config.persona_catchphrase,
                persona_tone=config.persona_tone,
            )
            text = llm.generate_script(prompt=prompt)
            if not text or not text.strip():
                raise LLMError(f"LLM returned empty script for archetype '{archetype}'")
            variants.append({"archetype": archetype, "script": text.strip()})
    except LLMError as e:
        return {
            "errors": [
                AgentError(
                    agent="script",
                    error_type="LLMError",
                    message=str(e),
                    recovery_suggestion=(
                        "LLM API error during script generation. Check API key and quota."
                    ),
                )
            ]
        }

    selected = variants[0]
    return {
        "current_script": selected["script"],
        "hook_archetype": selected["archetype"],
        "hook_variants": variants,
    }
