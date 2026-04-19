"""
LLMProvider factory — bridges :class:`~theogony.config.settings.Settings`
to a concrete :class:`~theogony.agents.llm.LLMProvider`.

The single switch point in the codebase. ``settings.llm.provider``
selects one of:

- ``"gemini"``   → :class:`~theogony.agents.llm_gemini.GeminiLLMProvider`
- ``"stub"``     → :class:`~theogony.agents.llm.StubLLMProvider`
- ``"openai"``   → reserved (Plan §2.3 lists OpenAILLMProvider as
  optional; not yet implemented in code)
- ``"anthropic"`` → reserved (same)

CLI commands (and any other callsite that needs the active LLM)
import ``build_llm_from_settings`` rather than constructing
providers directly. That keeps provider-name → provider-class wiring
in one place — when the OpenAI / Anthropic providers land, only
this module needs an update.

Honest-failure: when the active provider is "gemini" but no API key
is set in the environment, the factory raises a clear ``ValueError``
naming the missing key (rather than constructing a provider that
would fail on first call).
"""

from __future__ import annotations

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
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
            (e.g. ``GeminiLLMProvider`` raises with install instructions
            when the ``gemini`` extra is not present).
    """
    provider_name = settings.llm.provider
    if provider_name == "stub":
        log.info("LLM provider: stub (offline; for tests / dev only)")
        return StubLLMProvider(model_id=settings.llm.model_id or "stub-llm")

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

    if provider_name in ("openai", "anthropic"):
        # Plan §2.3 + §3.3a list these as first-class alternatives
        # behind the LLMProvider protocol, but their concrete
        # providers do not yet exist in code. Filed as a deferred
        # item in the LLM-provider PHX line; see PHX-0027.
        raise NotImplementedError(
            f"LLM provider {provider_name!r} is reserved by Settings but "
            "the concrete provider class is not yet implemented (see "
            "PHX-0027). Use 'gemini' or 'stub' for now."
        )

    raise ValueError(
        f"Unknown LLM provider {provider_name!r}; expected one of "
        "{'gemini', 'openai', 'anthropic', 'stub'}"
    )


__all__ = ["build_llm_from_settings"]
