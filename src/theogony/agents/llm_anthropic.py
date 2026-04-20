"""
AnthropicLLMProvider — Claude models behind :class:`~theogony.agents.llm.LLMProvider`.

When ``json_schema`` is set, uses a single forced tool whose
``input_schema`` is the caller's JSON Schema; the tool's ``input``
object is serialised to JSON text so downstream extractors can
``json.loads`` the result the same way they do for Gemini.

Plain text mode uses the Messages API without tools.

Pricing defaults follow Anthropic's public list pricing for
Claude Haiku 4.5 (USD per 1M tokens), converted to EUR for
:class:`~theogony.agents.llm.LLMResult`. Override via
``usd_per_m_input`` / ``usd_per_m_output`` when running an
older Haiku tier.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from pydantic import SecretStr

from theogony.agents.llm import LLMResult
from theogony.config.logging import get_logger

log = get_logger("agents.llm_anthropic")

_TOOL_NAME = "theogony_structured_output"


class AnthropicLLMProvider:
    """Async Anthropic Messages API behind the LLMProvider protocol."""

    USD_PER_M_INPUT_DEFAULT: float = 1.00
    USD_PER_M_OUTPUT_DEFAULT: float = 5.00
    USD_TO_EUR: float = 0.93

    def __init__(
        self,
        api_key: SecretStr | str | None,
        model_id: str = "claude-haiku-4-5-20251001",
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


__all__ = ["AnthropicLLMProvider"]
