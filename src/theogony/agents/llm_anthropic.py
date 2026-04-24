"""
AnthropicLLMProvider — Claude models behind :class:`~theogony.agents.llm.LLMProvider`.

When ``json_schema`` is set, uses a single forced tool whose
``input_schema`` is the caller's JSON Schema; the tool's ``input``
object is serialised to JSON text so downstream extractors can
``json.loads`` the result the same way they do for Gemini.

Plain text mode uses the Messages API without tools.

Pricing defaults follow Anthropic's public list pricing for
Claude Sonnet 4.6 (USD per 1M tokens), converted to EUR for
:class:`~theogony.agents.llm.LLMResult`. Override via
``usd_per_m_input`` / ``usd_per_m_output`` for other tiers.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from pydantic import BaseModel, SecretStr

from theogony.agents.llm import LLMResult, ResearchPlannerCost
from theogony.config.logging import get_logger

log = get_logger("agents.llm_anthropic")

_TOOL_NAME = "theogony_structured_output"
_RESEARCH_PLAN_TOOL = "theogony_research_plan"


class AnthropicLLMProvider:
    """Async Anthropic Messages API behind the LLMProvider protocol."""

    USD_PER_M_INPUT_DEFAULT: float = 3.00
    USD_PER_M_OUTPUT_DEFAULT: float = 15.00
    USD_TO_EUR: float = 0.93

    def __init__(
        self,
        api_key: SecretStr | str | None,
        model_id: str = "claude-sonnet-4-6",
        *,
        client: Any | None = None,
        usd_per_m_input: float | None = None,
        usd_per_m_output: float | None = None,
    ) -> None:
        if api_key is None and client is None:
            raise ValueError("AnthropicLLMProvider requires either api_key or a pre-built client")
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
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "AnthropicLLMProvider requires the `anthropic` extra. "
                "Install with: pip install -e '.[anthropic]'"
            ) from exc
        self._client = AsyncAnthropic(api_key=self._api_key_raw)
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
        max_tokens = max_output_tokens if max_output_tokens is not None else 4096

        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                if json_schema is not None:
                    message = await client.messages.create(
                        model=self._model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system or "",
                        messages=[{"role": "user", "content": prompt}],
                        tools=[
                            {
                                "name": _TOOL_NAME,
                                "description": "Return extraction output matching the schema.",
                                "input_schema": json_schema,
                            }
                        ],
                        tool_choice={"type": "tool", "name": _TOOL_NAME},
                    )
                else:
                    message = await client.messages.create(
                        model=self._model_id,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system or "",
                        messages=[{"role": "user", "content": prompt}],
                    )
        except TimeoutError:
            log.warning("anthropic timeout model_id=%s timeout_s=%s", self._model_id, timeout_s)
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = ""
        if json_schema is not None:
            for block in message.content:
                if (
                    getattr(block, "type", None) == "tool_use"
                    and getattr(block, "name", None) == _TOOL_NAME
                ):
                    text = json.dumps(block.input)
                    break
            else:
                raise RuntimeError(
                    f"AnthropicLLMProvider: forced tool {_TOOL_NAME!r} not found in response "
                    f"for model_id={self._model_id}; got block types "
                    f"{[getattr(b, 'type', None) for b in message.content]}"
                )
        else:
            parts: list[str] = []
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    parts.append(getattr(block, "text", "") or "")
            text = "".join(parts).strip()

        usage = message.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

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
        output_schema: type[BaseModel],
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        client = self._ensure_client()
        schema = output_schema.model_json_schema()
        _started = time.perf_counter()
        message = await client.messages.create(
            model=self._model_id,
            max_tokens=max_total_tokens,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_search_calls,
                },
                {
                    "name": _RESEARCH_PLAN_TOOL,
                    "description": "Return the research plan JSON matching the locked schema.",
                    "input_schema": schema,
                },
            ],
            tool_choice={"type": "auto"},
        )
        _ = int((time.perf_counter() - _started) * 1000)

        plan_payload: dict[str, Any] | None = None
        for block in message.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == _RESEARCH_PLAN_TOOL
            ):
                plan_payload = dict(block.input)
                break
        if plan_payload is None:
            raise RuntimeError(
                f"AnthropicLLMProvider: research plan tool {_RESEARCH_PLAN_TOOL!r} missing; "
                f"blocks={[getattr(b, 'type', None) for b in message.content]}"
            )

        validated = output_schema.model_validate(plan_payload)
        usage = message.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        usd = (input_tokens / 1_000_000) * self._usd_per_m_input + (
            output_tokens / 1_000_000
        ) * self._usd_per_m_output
        n_search = 0
        for block in message.content:
            if (
                getattr(block, "type", None) == "server_tool_use"
                and getattr(block, "name", None) == "web_search"
            ):
                n_search += 1
        cost = ResearchPlannerCost(
            usd_cost=usd,
            eur_cost=self._cost_eur(input_tokens, output_tokens),
            search_call_count=n_search,
            model_id=self._model_id,
        )
        return validated, cost


__all__ = ["AnthropicLLMProvider"]
