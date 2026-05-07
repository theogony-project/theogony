"""
DeepSeek LLM provider implementation.

Uses the official OpenAI-compatible DeepSeek API endpoint.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from theogony.agents.llm import (
    STRUCTURED_LLM_MIN_TIMEOUT_S,
    LLMProvider,
    LLMResult,
    ResearchPlannerCost,
)


class DeepSeekLLMProvider(LLMProvider):
    """
    DeepSeek provider using the OpenAI-compatible API format.

    Pricing (as of May 2026, deepseek-chat):
    - Input: $0.14 / 1M tokens
    - Output: $0.28 / 1M tokens
    """

    # EUR/USD conversion rate (approximate, matches Anthropic provider)
    _EUR_PER_USD = 0.93

    # Pricing per 1M tokens (USD)
    _PRICING_USD = {
        "deepseek-chat": {"input": 0.14, "output": 0.28},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    }

    def __init__(self, api_key: str, model_id: str = "deepseek-chat") -> None:
        import httpx
        import openai

        self._model_id = model_id
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            timeout=httpx.Timeout(connect=60.0, read=300.0, write=60.0, pool=60.0),
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def _calculate_cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        rates = self._PRICING_USD.get(self._model_id, self._PRICING_USD["deepseek-chat"])
        cost_usd = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        return cost_usd * self._EUR_PER_USD

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> LLMResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        effective_timeout_s = timeout_s
        if json_schema is not None:
            effective_timeout_s = max(timeout_s, STRUCTURED_LLM_MIN_TIMEOUT_S)

        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "messages": messages,
            "temperature": temperature,
            "timeout": effective_timeout_s,
        }

        if max_output_tokens is not None:
            kwargs["max_tokens"] = max_output_tokens

        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
            # DeepSeek requires the prompt to explicitly mention JSON when using json_object
            if "json" not in prompt.lower() and (not system or "json" not in system.lower()):
                messages[-1]["content"] += "\n\nPlease return the result as a JSON object."

        start_time = time.monotonic()
        response = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        choice = response.choices[0]
        text = choice.message.content or ""

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        cost_eur = self._calculate_cost_eur(input_tokens, output_tokens)

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=cost_eur,
            latency_ms=latency_ms,
            model_id=self._model_id,
        )

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        raise NotImplementedError("Web search not yet implemented for DeepSeek provider.")
