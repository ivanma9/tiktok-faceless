"""
Typed exceptions for all external API client wrappers.

Agents catch these at their boundary and convert to AgentError state deltas.
Clients raise, agents catch — never swallow.
"""


class TikTokRateLimitError(Exception):
    """Raised after exhausting retries on TikTok 429 rate limit responses."""


class TikTokAuthError(Exception):
    """Raised on TikTok 401/403 authentication/authorization failures."""


class TikTokAPIError(Exception):
    """Raised on generic TikTok API errors not covered by specific subclasses."""


class ElevenLabsError(Exception):
    """Raised on any ElevenLabs API failure."""


class RenderError(Exception):
    """Raised on Creatomate render failure, timeout, or unexpected status."""


class FalError(Exception):
    """Raised on fal.ai API failure."""


class LLMError(Exception):
    """Raised on LLM (Anthropic) API failure."""
