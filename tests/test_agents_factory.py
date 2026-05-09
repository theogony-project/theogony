"""Unit tests for :func:`build_llm_from_settings`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMResult, StubLLMProvider
from theogony.agents.llm_anthropic import AnthropicLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.agents.llm_openai import (
    OpenAILLMProvider,
    _openai_reasoning_model_default_temperature_only,
    _openai_uses_max_completion_tokens,
)
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
        s = _settings(provider="openai", openai_key="sk-x", model_id="gpt-5.4-mini")
        provider = build_llm_from_settings(s)
        assert isinstance(provider, OpenAILLMProvider)
        assert provider.model_id == "gpt-5.4-mini"

    def test_openai_without_key_raises_value_error(self) -> None:
        s = _settings(provider="openai", openai_key=None, model_id="gpt-5.4-mini")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            build_llm_from_settings(s)


class TestAnthropicProvider:
    def test_anthropic_returns_anthropic_provider_with_key(self) -> None:
        s = _settings(
            provider="anthropic",
            anthropic_key="sk-ant-x",
            model_id="claude-sonnet-4-6",
        )
        provider = build_llm_from_settings(s)
        assert isinstance(provider, AnthropicLLMProvider)
        assert provider.model_id == "claude-sonnet-4-6"

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
            llm=LLMSettings(provider="gemini", fallback_provider=None),
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


class _DummyProvider:
    def __init__(self, model_id: str, *, fail: bool = False) -> None:
        self._model_id = model_id
        self._fail = fail
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    async def complete(self, prompt: str, **_: object) -> LLMResult:
        self.calls += 1
        if self._fail:
            raise RuntimeError("boom")
        return LLMResult(text=f"{self._model_id}:{prompt}", model_id=self._model_id)

    async def complete_with_web_search_for_research_plan(self, **_: object):
        if self._fail:
            raise RuntimeError("boom")
        return object(), object()


class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_fallback_is_used_when_primary_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import theogony.agents.factory as factory_mod

        providers: dict[str, _DummyProvider] = {
            "openai": _DummyProvider("gpt-5.4-mini", fail=True),
            "anthropic": _DummyProvider("claude-haiku-4-5"),
        }

        def _fake_build_single_provider(settings, provider_name: str, model_id: str):  # type: ignore[no-untyped-def]
            del settings, model_id
            return providers[provider_name]

        monkeypatch.setattr(factory_mod, "_build_single_provider", _fake_build_single_provider)
        s = _settings(
            provider="openai",
            model_id="gpt-5.4-mini",
            openai_key="sk-x",
            anthropic_key="sk-ant-x",
        )
        object.__setattr__(s.llm, "fallback_provider", "anthropic")
        object.__setattr__(s.llm, "fallback_model_id", "claude-haiku-4-5")

        provider = build_llm_from_settings(s)
        out = await provider.complete("hello")
        assert out.model_id == "claude-haiku-4-5"
        assert providers["openai"].calls == 1
        assert providers["anthropic"].calls == 1

    @pytest.mark.asyncio
    async def test_primary_success_emits_complete_ok_log(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import theogony.agents.factory as factory_mod

        prov_openai = _DummyProvider("gpt-5.4-mini", fail=False)
        prov_anth = _DummyProvider("claude-fallback", fail=False)

        def _fake_build_single_provider(settings, provider_name: str, model_id: str):  # type: ignore[no-untyped-def]
            del settings, model_id
            if provider_name == "openai":
                return prov_openai
            return prov_anth

        monkeypatch.setattr(factory_mod, "_build_single_provider", _fake_build_single_provider)
        s = _settings(
            provider="openai",
            model_id="gpt-5.4-mini",
            openai_key="sk-x",
            anthropic_key="sk-ant-x",
        )
        object.__setattr__(s.llm, "fallback_provider", "anthropic")
        object.__setattr__(s.llm, "fallback_model_id", "claude-fallback")

        provider = build_llm_from_settings(s)
        out = await provider.complete("ping")
        assert "gpt-5.4-mini" in out.text
        assert prov_openai.calls == 1
        assert prov_anth.calls == 0

    def test_rejects_same_provider_as_fallback(self) -> None:
        s = _settings(provider="openai", model_id="gpt-5.4-mini", openai_key="sk-x")
        object.__setattr__(s.llm, "fallback_provider", "openai")
        with pytest.raises(ValueError, match="must differ"):
            build_llm_from_settings(s)


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("o4-mini", True),
        ("o3-mini-2025-01-31", True),
        ("o1", True),
        ("gpt-4o", False),
        ("gpt-5.4-mini", False),
        ("deepseek-chat", False),
    ],
)
def test_openai_reasoning_model_default_temperature_only(model_id: str, expected: bool) -> None:
    assert _openai_reasoning_model_default_temperature_only(model_id) is expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gpt-5.4-mini", True),
        ("gpt-5-nano", True),
        ("gpt-4o-mini", False),
        ("gpt-4o", False),
        ("o4-mini", False),
    ],
)
def test_openai_uses_max_completion_tokens(model_id: str, expected: bool) -> None:
    assert _openai_uses_max_completion_tokens(model_id) is expected
