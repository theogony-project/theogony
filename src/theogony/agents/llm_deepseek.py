"""
DeepSeek LLM provider implementation.

Uses the official OpenAI-compatible DeepSeek API endpoint.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel

from theogony.agents.llm import (
    STRUCTURED_LLM_MIN_TIMEOUT_S,
    LLMProvider,
    LLMResult,
    ResearchPlannerCost,
)
from theogony.agents.spend import AccountBalance
from theogony.config.logging import get_logger

log = get_logger(__name__)

# DeepSeek's published prices in USD per 1M tokens, (off-peak, peak), read from
# https://api-docs.deepseek.com/quick_start/pricing on 2026-11-10. Off-peak is
# half of peak. Peak is 01:00-04:00 and 06:00-10:00 UTC, Monday to Friday,
# except Chinese public holidays, which this table does not know: a holiday is
# priced as peak, an overestimate, the safe side of a spend limit (PHX-1124).
PRICES_USD: dict[str, dict[str, tuple[float, float]]] = {
    "deepseek-flash": {
        "cache_hit": (0.003, 0.006),
        "cache_miss": (0.15, 0.30),
        "output": (0.60, 1.20),
    },
    "deepseek-v4-pro": {
        "cache_hit": (0.022, 0.044),
        "cache_miss": (0.66, 1.32),
        "output": (1.98, 3.96),
    },
}
# Names the API still accepts, and the model that serves them. deepseek-chat
# and deepseek-reasoner point to Flash's non-thinking and thinking modes (change
# log, 2026-04-24; a deepseek-chat call on 2026-11-10 came back as
# deepseek-flash); deepseek-v4-flash and deepseek-v4-flash-vision-exp are
# routed to V4.1 Flash and billed at its price (pricing page).
SERVED_BY: dict[str, str] = {
    "deepseek-chat": "deepseek-flash",
    "deepseek-reasoner": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}
_PEAK_HOURS_UTC = ((1, 4), (6, 10))
_WARNED: set[str] = set()
# A model the table does not know is priced at its dearest row.
_DEAREST = "deepseek-v4-pro"


def is_peak(at: datetime) -> bool:
    """Whether DeepSeek bills a call made at ``at`` at its peak rate."""
    at = at.astimezone(UTC)
    return at.weekday() < 5 and any(start <= at.hour < end for start, end in _PEAK_HOURS_UTC)


def price_row(model: str) -> dict[str, tuple[float, float]]:
    """The price row for a model name, an alias resolved to the model serving it."""
    return PRICES_USD.get(SERVED_BY.get(model, model), PRICES_USD[_DEAREST])


def cost_usd(
    model: str,
    *,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
    at: datetime,
) -> float:
    """What DeepSeek bills for one call, in USD."""
    row = price_row(model)
    rate = 1 if is_peak(at) else 0
    return (
        cache_hit_tokens * row["cache_hit"][rate]
        + cache_miss_tokens * row["cache_miss"][rate]
        + output_tokens * row["output"][rate]
    ) / 1_000_000


class DeepSeekLLMProvider(LLMProvider):
    """
    DeepSeek provider using the OpenAI-compatible API format.

    Priced from :data:`PRICES_USD` by the model the response says served the
    call, with cache hits, cache misses and the time of day kept apart, as
    DeepSeek bills them.
    """

    # EUR/USD conversion rate (approximate, matches Anthropic provider)
    _EUR_PER_USD = 0.93

    def __init__(self, api_key: str, model_id: str = "deepseek-chat") -> None:
        import httpx
        import openai

        self._model_id = model_id
        self._api_key = api_key
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            # openai 3.x types its `timeout` against httpx2 while still accepting
            # any httpx-compatible Timeout at runtime (verified against openai
            # 3.1.0 / httpx 0.28). Casting keeps the per-phase values — read=300s
            # matters for long structured extraction calls — instead of collapsing
            # them to a single float to satisfy whichever httpx the SDK pins today.
            timeout=cast(Any, httpx.Timeout(connect=60.0, read=300.0, write=60.0, pool=60.0)),
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def without_sdk_retries(self) -> DeepSeekLLMProvider:
        """Leave retries to the caller. The SDK resends a timed-out or failed
        request up to twice inside one call; behind a spend limit each attempt
        must be reserved and counted, so the limiter makes them (PHX-1124)."""
        self._client = self._client.with_options(max_retries=0)
        return self

    def knows_price_of(self, served_model_id: str) -> bool:
        """Whether the table prices the model a response named; an empty name
        is priced by the requested one."""
        return not served_model_id or served_model_id in PRICES_USD or served_model_id in SERVED_BY

    def worst_case_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """The most a call of this size can cost: every input token a cache
        miss, at the peak rate of the model the requested name resolves to."""
        row = price_row(self._model_id)
        return (input_tokens * row["cache_miss"][1] + output_tokens * row["output"][1]) / 1_000_000

    async def balance(self) -> AccountBalance:
        """The account's balance, from ``GET /user/balance`` (PHX-1124)."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        response.raise_for_status()
        data = response.json()
        by_currency = {
            str(info.get("currency")): float(info.get("total_balance") or 0.0)
            for info in data.get("balance_infos") or []
        }
        return AccountBalance(
            available=bool(data.get("is_available")),
            usd=by_currency.get("USD"),
            by_currency=by_currency,
        )

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

        called_at = datetime.now(UTC)
        start_time = time.monotonic()
        response = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        choice = response.choices[0]
        text = choice.message.content or ""

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        # DeepSeek reports the cache split beside the OpenAI fields; without it
        # every input token is priced as a miss, the dearer of the two.
        cache_hit = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0) if usage else 0
        cache_miss = int(getattr(usage, "prompt_cache_miss_tokens", 0) or 0) if usage else 0
        if cache_hit + cache_miss != input_tokens:
            cache_hit, cache_miss = 0, input_tokens
        served = str(getattr(response, "model", "") or "")
        if not self.knows_price_of(served):
            # Priced at the table's dearest row, which may still be cheaper than
            # the model that answered: a spend limit stops the run after this
            # call (SpendLimitedLLM), so no second one is priced by a guess.
            if served not in _WARNED:
                _WARNED.add(served)
                log.warning("DeepSeek served %s, which the price table does not know", served)
            priced_as = _DEAREST
        else:
            priced_as = served or self._model_id
        usd = cost_usd(
            priced_as,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            output_tokens=output_tokens,
            at=called_at,
        )

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=usd * self._EUR_PER_USD,
            cost_usd=usd,
            latency_ms=latency_ms,
            model_id=self._model_id,
            served_model_id=served,
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
