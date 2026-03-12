"""
LLMClient: script generation via Anthropic claude-haiku-4-5-20251001.

Implementation: Story 1.3 — External API Client Wrappers
"""

import anthropic

from tiktok_faceless.clients import LLMError
from tiktok_faceless.utils.retry import llm_retry

_MODEL_ID = "claude-haiku-4-5-20251001"


class LLMClient:
    """Typed wrapper for Anthropic Messages API."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_script(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Generate a script using claude-haiku-4-5-20251001.

        Returns the response text string.
        Raises LLMError on any API failure (including after retries).
        """
        try:
            return self._generate_with_retry(prompt=prompt, max_tokens=max_tokens)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            raise LLMError(f"LLM generation failed after retries: {e}") from e

    @llm_retry
    def _generate_with_retry(self, prompt: str, max_tokens: int = 1024) -> str:
        try:
            message = self._client.messages.create(
                model=_MODEL_ID,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return str(message.content[0].text)  # type: ignore[union-attr]
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            raise  # let llm_retry handle transient errors
        except Exception as e:
            raise LLMError(f"LLM generation failed: {e}") from e
