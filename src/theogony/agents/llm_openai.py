"""
OpenAILLMProvider — first-class LLM behind :class:`~theogony.agents.llm.LLMProvider`.

Uses ``openai.AsyncOpenAI`` with ``chat.completions.create``. Structured
outputs use ``response_format`` with ``type: json_schema`` (non-strict)
so the JSON Schema fragments from the extraction pipeline (which may
not satisfy OpenAI's ``strict: true`` additionalProperties rules) still
work; downstream Pydantic validation remains the contract.

Pricing defaults are approximate public list prices (USD per 1M
tokens), multiplied by ``USD_TO_EUR`` for :class:`~theogony.agents.llm.LLMResult`.
Override via constructor kwargs when OpenAI changes pricing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, SecretStr

from theogony.agents.llm import STRUCTURED_LLM_MIN_TIMEOUT_S, LLMResult, ResearchPlannerCost
from theogony.config.logging import get_logger

log = get_logger("agents.llm_openai")


def _openai_reasoning_model_default_temperature_only(model_id: str) -> bool:
    """Whether ``model_id`` only allows the API default temperature (typically 1).

    OpenAI o-series reasoning models reject caller-supplied ``temperature=0``;
    the API returns ``unsupported_value`` on chat.completions.
    """

    m = (model_id or "").lower().strip()
    return m.startswith(("o1", "o3", "o4"))


class OpenAILLMProvider:
    """Async OpenAI Chat Completions behind the LLMProvider protocol."""

    USD_PER_M_INPUT_DEFAULT: float = 0.15
    USD_PER_M_OUTPUT_DEFAULT: float = 0.60
    USD_TO_EUR: float = 0.93

    def __init__(
        self,
        api_key: SecretStr | str | None,
        model_id: str = "gpt-5.4-mini",
        *,
        client: Any | None = None,
        usd_per_m_input: float | None = None,
        usd_per_m_output: float | None = None,
    ) -> None:
        if api_key is None and client is None:
            raise ValueError("OpenAILLMProvider requires either api_key or a pre-built client")
        self._api_key_raw: str | None = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )
        self._model_id = model_id
        self._client: Any | None = client
        self._usd_per_m_input = (
            usd_per_m_input if usd_per_m_input is not None else self.USD_PER_M_INPUT_DEFAULT
        )
        self._usd_per_m_output = (
            usd_per_m_output if usd_per_m_output is not None else self.USD_PER_M_OUTPUT_DEFAULT
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "OpenAILLMProvider requires the `openai` extra. "
                "Install with: pip install -e '.[openai]'"
            ) from exc
        self._client = AsyncOpenAI(api_key=self._api_key_raw)
        return self._client

    def _cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        usd = (input_tokens / 1_000_000) * self._usd_per_m_input + (
            output_tokens / 1_000_000
        ) * self._usd_per_m_output
        return usd * self.USD_TO_EUR

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
        client = self._ensure_client()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "messages": messages,
        }
        if not _openai_reasoning_model_default_temperature_only(self._model_id):
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_tokens"] = max_output_tokens
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "theogony_output",
                    "schema": json_schema,
                    "strict": False,
                },
            }

        effective_timeout_s = timeout_s
        if json_schema is not None:
            effective_timeout_s = max(timeout_s, STRUCTURED_LLM_MIN_TIMEOUT_S)

        started = time.perf_counter()
        try:
            async with asyncio.timeout(effective_timeout_s):
                resp = await client.chat.completions.create(**kwargs)
        except TimeoutError:
            log.warning(
                "openai timeout model_id=%s timeout_s=%s", self._model_id, effective_timeout_s
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        usage = resp.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=self._cost_eur(input_tokens, output_tokens),
            latency_ms=latency_ms,
            model_id=self._model_id,
        )

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type,
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        del system_prompt, user_prompt, output_schema, max_search_calls, max_total_tokens
        raise NotImplementedError("web_search planning requires Anthropic")


__all__ = ["OpenAILLMProvider"]
