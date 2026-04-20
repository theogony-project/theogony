"""Unit tests for :func:`build_llm_from_settings`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import StubLLMProvider
from theogony.agents.llm_anthropic import AnthropicLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.agents.llm_openai import OpenAILLMProvider
from theogony.config.settings import LLMSettings, Settings


def _settings(
    *,
    provider: str = "stub",
    model_id: str | None = None,
    gemini_key: str | None = None,
    openai_key: str | None = None,
    anthropic_key: str | None = None,
) -> Settings:
    llm_kw: dict[str, object] = {"provider": provider}
    if model_id is not None:
        llm_kw["model_id"] = model_id
    return Settings(  # type: ignore[call-arg]
        OPENAI_API_KEY=SecretStr(openai_key) if openai_key else None,  # type: ignore[arg-type]
        ANTHROPIC_API_KEY=SecretStr(anthropic_key) if anthropic_key else None,  # type: ignore[arg-type]
        GEMINI_API_KEY=SecretStr(gemini_key) if gemini_key else None,  # type: ignore[arg-type]
        GOOGLE_API_KEY=None,
        llm=LLMSettings(**llm_kw),  # type: ignore[arg-type]
    )


class TestStubProvider:
    def test_stub_returns_stub_provider(self) -> None:
        s = _settings(provider="stub")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, StubLLMProvider)
        assert provider.model_id == "stub-llm"

    def test_stub_does_not_require_api_key(self) -> None:
        # No API keys set; stub still constructs.
        s = _settings(provider="stub")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, StubLLMProvider)


class TestOpenAIProvider:
    def test_openai_returns_openai_provider_with_key(self) -> None:
        s = _settings(provider="openai", openai_key="sk-x", model_id="gpt-4o-mini")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, OpenAILLMProvider)
        assert provider.model_id == "gpt-4o-mini"

    def test_openai_without_key_raises_value_error(self) -> None:
        s = _settings(provider="openai", openai_key=None, model_id="gpt-4o-mini")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            build_llm_from_settings(s)


class TestAnthropicProvider:
    def test_anthropic_returns_anthropic_provider_with_key(self) -> None:
        s = _settings(
            provider="anthropic",
            anthropic_key="sk-ant-x",
            model_id="claude-haiku-4-5-20251001",
        )
        provider = build_llm_from_settings(s)
        assert isinstance(provider, AnthropicLLMProvider)
        assert provider.model_id == "claude-haiku-4-5-20251001"

    def test_anthropic_without_key_raises_value_error(self) -> None:
        s = _settings(provider="anthropic", anthropic_key=None)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            build_llm_from_settings(s)


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
