"""Tests for typed exceptions in tiktok_faceless/clients/__init__.py."""

from tiktok_faceless.clients import (
    ElevenLabsError,
    FalError,
    LLMError,
    RenderError,
    TikTokAPIError,
    TikTokAuthError,
    TikTokRateLimitError,
)


class TestExceptionsAreExceptions:
    def test_tiktok_rate_limit_error(self) -> None:
        err = TikTokRateLimitError("rate limited")
        assert isinstance(err, Exception)
        assert str(err) == "rate limited"

    def test_tiktok_auth_error(self) -> None:
        assert issubclass(TikTokAuthError, Exception)

    def test_tiktok_api_error(self) -> None:
        assert issubclass(TikTokAPIError, Exception)

    def test_elevenlabs_error(self) -> None:
        assert issubclass(ElevenLabsError, Exception)

    def test_render_error(self) -> None:
        assert issubclass(RenderError, Exception)

    def test_fal_error(self) -> None:
        assert issubclass(FalError, Exception)

    def test_llm_error(self) -> None:
        assert issubclass(LLMError, Exception)

    def test_all_raiseable(self) -> None:
        for exc_cls in [
            TikTokRateLimitError,
            TikTokAuthError,
            TikTokAPIError,
            ElevenLabsError,
            RenderError,
            FalError,
            LLMError,
        ]:
            try:
                raise exc_cls("test")
            except Exception as e:
                assert str(e) == "test"
