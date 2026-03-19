"""Recovery suggestions for structured error logging (Story 5.2)."""

RECOVERY_SUGGESTIONS: dict[str, str] = {
    "TikTokRateLimitError": (
        "TikTok rate limit hit — pipeline will retry automatically on the next cycle"
    ),
    "TikTokAuthError": ("TikTok authentication failed — refresh access token in AccountConfig"),
    "TikTokAPIError": ("TikTok API error — check TikTok developer dashboard for service status"),
    "ElevenLabsError": (
        "ElevenLabs API error — check API key validity or upgrade plan for higher quota"
    ),
    "RenderError": (
        "Video render failed — verify Creatomate template ID and API key in AccountConfig"
    ),
    "MissingProduct": ("No product selected — run research agent to populate niche products"),
    "MissingScript": ("No script available — script agent must run before production"),
    "MissingVideo": ("No rendered video available — production agent must run before publishing"),
    "LLMError": ("LLM API error — check Anthropic API key or retry on next cycle"),
    "commission_discrepancy": (
        "Click/order discrepancy detected — review TikTok Shop affiliate attribution settings"
    ),
}


def get_recovery_suggestion(error_type: str) -> str | None:
    """Return plain-English recovery suggestion for a given error type, or None if unknown."""
    return RECOVERY_SUGGESTIONS.get(error_type)
