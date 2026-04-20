"""
LLMProvider factory — bridges :class:`~theogony.config.settings.Settings`
to a concrete :class:`~theogony.agents.llm.LLMProvider`.

The single switch point in the codebase. ``settings.llm.provider``
selects one of:

- ``"openai"``    → :class:`~theogony.agents.llm_openai.OpenAILLMProvider`
- ``"anthropic"`` → :class:`~theogony.agents.llm_anthropic.AnthropicLLMProvider`
- ``"gemini"``    → :class:`~theogony.agents.llm_gemini.GeminiLLMProvider`
- ``"stub"``      → :class:`~theogony.agents.llm.StubLLMProvider`

CLI commands (and any other callsite that needs the active LLM)
import ``build_llm_from_settings`` rather than constructing
providers directly.

Honest-failure: when the active provider needs an API key that is not
set in the environment, the factory raises a clear ``ValueError``
naming the expected env var.
"""

from __future__ import annotations

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.llm_anthropic import AnthropicLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.agents.llm_openai import OpenAILLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import Settings

log = get_logger("agents.factory")


def build_llm_from_settings(settings: Settings) -> LLMProvider:
    """Construct the LLMProvider implied by ``settings.llm.provider``.

    Raises:
        ValueError: when the active provider needs an API key that
            isn't available in the environment, or when the configured
            provider name is unknown.
        ImportError: indirectly via the provider's lazy SDK import
            when the matching optional extra is not installed.
    """
    provider_name = settings.llm.provider
    if provider_name == "stub":
        log.info("LLM provider: stub (offline; for tests / dev only)")
        return StubLLMProvider(model_id=settings.llm.model_id or "stub-llm")

    if provider_name == "openai":
        api_key = settings.active_llm_api_key()
        if api_key is None:
            raise ValueError(
                "OpenAI provider selected but no API key found. Set "
                "OPENAI_API_KEY in the environment (or .env file)."
            )
        log.info("LLM provider: openai model_id=%s", settings.llm.model_id)
        return OpenAILLMProvider(api_key=api_key, model_id=settings.llm.model_id)

    if provider_name == "anthropic":
        api_key = settings.active_llm_api_key()
        if api_key is None:
            raise ValueError(
                "Anthropic provider selected but no API key found. Set "
                "ANTHROPIC_API_KEY in the environment (or .env file)."
            )
        log.info("LLM provider: anthropic model_id=%s", settings.llm.model_id)
        return AnthropicLLMProvider(api_key=api_key, model_id=settings.llm.model_id)

    if provider_name == "gemini":
        api_key = settings.active_llm_api_key()
        if api_key is None:
            raise ValueError(
                "Gemini provider selected but no API key found. Set "
                "GEMINI_API_KEY or GOOGLE_API_KEY in the environment "
                "(or .env file)."
            )
        log.info("LLM provider: gemini model_id=%s", settings.llm.model_id)
        return GeminiLLMProvider(api_key=api_key, model_id=settings.llm.model_id)

    raise ValueError(
        f"Unknown LLM provider {provider_name!r}; expected one of "
        "{'gemini', 'openai', 'anthropic', 'stub'}"
    )


__all__ = ["build_llm_from_settings"]
