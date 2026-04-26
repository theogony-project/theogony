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

from typing import Any

from pydantic import BaseModel

from theogony.agents.llm import LLMProvider, LLMResult, ResearchPlannerCost, StubLLMProvider
from theogony.agents.llm_anthropic import AnthropicLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.agents.llm_openai import OpenAILLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import LLMSettings, Settings

log = get_logger("agents.factory")


class _FallbackLLMProvider:
    """Retry LLM calls on a secondary provider when primary fails."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def model_id(self) -> str:
        return f"{self._primary.model_id}|fallback:{self._fallback.model_id}"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float = 30.0,
    ) -> LLMResult:
        try:
            res = await self._primary.complete(
                prompt,
                system=system,
                json_schema=json_schema,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )
            log.info(
                "LLM complete ok route=primary model_id=%s in_tok=%s out_tok=%s",
                self._primary.model_id,
                res.input_tokens,
                res.output_tokens,
            )
            return res
        except Exception as exc:
            log.warning(
                "LLM primary failed model_id=%s err=%s; trying fallback model_id=%s",
                self._primary.model_id,
                type(exc).__name__,
                self._fallback.model_id,
            )
            res = await self._fallback.complete(
                prompt,
                system=system,
                json_schema=json_schema,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )
            log.info(
                "LLM complete ok route=fallback model_id=%s in_tok=%s out_tok=%s",
                self._fallback.model_id,
                res.input_tokens,
                res.output_tokens,
            )
            return res

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        try:
            out = await self._primary.complete_with_web_search_for_research_plan(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_schema=output_schema,
                max_search_calls=max_search_calls,
                max_total_tokens=max_total_tokens,
            )
            log.info(
                "LLM research plan ok route=primary model_id=%s",
                self._primary.model_id,
            )
            return out
        except Exception as exc:
            log.warning(
                "LLM primary web-search plan failed model_id=%s err=%s; "
                "trying fallback model_id=%s",
                self._primary.model_id,
                type(exc).__name__,
                self._fallback.model_id,
            )
            out = await self._fallback.complete_with_web_search_for_research_plan(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_schema=output_schema,
                max_search_calls=max_search_calls,
                max_total_tokens=max_total_tokens,
            )
            log.info(
                "LLM research plan ok route=fallback model_id=%s",
                self._fallback.model_id,
            )
            return out


def _build_single_provider(settings: Settings, provider_name: str, model_id: str) -> LLMProvider:
    if provider_name == "stub":
        return StubLLMProvider(model_id=model_id or "stub-llm")

    if provider_name == "openai":
        api_key = settings.llm_api_key_for("openai")
        if api_key is None:
            raise ValueError(
                "OpenAI provider selected but no API key found. Set "
                "OPENAI_API_KEY in the environment (or .env file)."
            )
        return OpenAILLMProvider(api_key=api_key, model_id=model_id)

    if provider_name == "anthropic":
        api_key = settings.llm_api_key_for("anthropic")
        if api_key is None:
            raise ValueError(
                "Anthropic provider selected but no API key found. Set "
                "ANTHROPIC_API_KEY in the environment (or .env file)."
            )
        return AnthropicLLMProvider(api_key=api_key, model_id=model_id)

    if provider_name == "gemini":
        api_key = settings.llm_api_key_for("gemini")
        if api_key is None:
            raise ValueError(
                "Gemini provider selected but no API key found. Set "
                "GEMINI_API_KEY or GOOGLE_API_KEY in the environment "
                "(or .env file)."
            )
        return GeminiLLMProvider(api_key=api_key, model_id=model_id)

    raise ValueError(
        f"Unknown LLM provider {provider_name!r}; expected one of "
        "{'gemini', 'openai', 'anthropic', 'stub'}"
    )


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
    primary = _build_single_provider(settings, provider_name, settings.llm.model_id)
    if provider_name == "stub":
        log.info("LLM provider: stub model_id=%s", primary.model_id)
        return primary
    fallback_name = settings.llm.fallback_provider
    if fallback_name is not None and settings.llm_api_key_for(fallback_name) is None:
        log.warning(
            "LLM fallback %s requested but no API key for that provider; primary only",
            fallback_name,
        )
        fallback_name = None
    if fallback_name is None:
        log.info("LLM provider: %s model_id=%s", provider_name, primary.model_id)
        return primary
    if fallback_name == provider_name:
        raise ValueError("LLM fallback_provider must differ from primary provider")
    fallback_model_id = settings.llm.fallback_model_id.strip()
    if not fallback_model_id:
        fallback_model_id = LLMSettings(
            provider=fallback_name,
            model_id="",
            fallback_provider=None,
            fallback_model_id="",
        ).model_id
    fallback = _build_single_provider(settings, fallback_name, fallback_model_id)
    log.info(
        "LLM provider: %s model_id=%s fallback=%s model_id=%s",
        provider_name,
        primary.model_id,
        fallback_name,
        fallback.model_id,
    )
    return _FallbackLLMProvider(primary=primary, fallback=fallback)


__all__ = ["build_llm_from_settings"]
