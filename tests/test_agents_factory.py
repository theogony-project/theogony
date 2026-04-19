"""Unit tests for :func:`build_llm_from_settings`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import StubLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.config.settings import LLMSettings, Settings


def _settings(
    *,
    provider: str = "gemini",
    model_id: str = "gemini-2.5-flash-lite",
    gemini_key: str | None = None,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
) -> Settings:
    return Settings(  # type: ignore[call-arg]
        OPENAI_API_KEY=SecretStr(openai_key) if openai_key else None,  # type: ignore[arg-type]
        ANTHROPIC_API_KEY=SecretStr(anthropic_key) if anthropic_key else None,  # type: ignore[arg-type]
        GEMINI_API_KEY=SecretStr(gemini_key) if gemini_key else None,  # type: ignore[arg-type]
        GOOGLE_API_KEY=None,
        llm=LLMSettings(provider=provider, model_id=model_id),  # type: ignore[arg-type]
    )


class TestStubProvider:
    def test_stub_returns_stub_provider(self) -> None:
        s = _settings(provider="stub", model_id="stub-llm")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, StubLLMProvider)
        assert provider.model_id == "stub-llm"

    def test_stub_does_not_require_api_key(self) -> None:
        # No API keys set; stub still constructs.
        s = _settings(provider="stub")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, StubLLMProvider)


class TestGeminiProvider:
    def test_gemini_returns_gemini_provider_with_key(self) -> None:
        s = _settings(provider="gemini", gemini_key="x-gemini-key")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, GeminiLLMProvider)
        assert provider.model_id == "gemini-2.5-flash-lite"

    def test_gemini_without_key_raises_value_error(self) -> None:
        s = _settings(provider="gemini", gemini_key=None)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            build_llm_from_settings(s)

    def test_gemini_falls_back_to_google_api_key(self) -> None:
        # Both env-vars are valid Gemini keys per
        # Settings.active_llm_api_key.
        s = Settings(  # type: ignore[call-arg]
            GEMINI_API_KEY=None,
            GOOGLE_API_KEY=SecretStr("x-google-key"),
            llm=LLMSettings(provider="gemini"),
        )
        provider = build_llm_from_settings(s)
        assert isinstance(provider, GeminiLLMProvider)


class TestReservedProviders:
    @pytest.mark.parametrize("name", ["openai", "anthropic"])
    def test_reserved_providers_raise_not_implemented(self, name: str) -> None:
        s = _settings(provider=name, openai_key="x", anthropic_key="x")
        with pytest.raises(NotImplementedError, match="PHX-0027"):
            build_llm_from_settings(s)


class TestUnknownProvider:
    def test_unknown_provider_raises_value_error(self) -> None:
        # We bypass the Settings literal type by constructing
        # LLMSettings directly with a string the type system would
        # reject — the factory's defensive branch catches this.
        s = _settings()
        # Mutate after construction to dodge the typing.Literal check.
        object.__setattr__(s.llm, "provider", "made-up")
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            build_llm_from_settings(s)
