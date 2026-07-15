"""Anthropic provider vs. the 4.7+/5 model generation (PHX-1045 pilot findings).

Two live-surfaced defects, pinned here at the HTTP layer:

1. Claude 4.7+/5-generation models reject the ``temperature`` parameter with a
   400 — the Sonnet-5 pilot failed on every paragraph call. The provider must
   omit it there and keep sending it on older models.
2. Cost accounting used hardcoded Sonnet prices for every model, recording
   Haiku runs ~3x too expensive. Prices must resolve per model prefix.
"""

from __future__ import annotations

import json

import httpx
import respx
from anthropic import AsyncAnthropic

from theogony.agents.llm_anthropic import AnthropicLLMProvider

_TEXT_RESPONSE = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "ok"}],
    "model": "claude-x",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


async def _complete_and_capture_body(model_id: str) -> dict:
    captured: dict = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode()))
        return httpx.Response(200, json=_TEXT_RESPONSE)

    with respx.mock:
        respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_handler)
        async with httpx.AsyncClient() as http:
            anthropic = AsyncAnthropic(api_key="sk-ant-test", http_client=http)
            provider = AnthropicLLMProvider(
                api_key="sk-ant-test", model_id=model_id, client=anthropic
            )
            await provider.complete("probe")
    return captured


async def test_temperature_omitted_on_sampling_locked_models() -> None:
    for model_id in ("claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"):
        body = await _complete_and_capture_body(model_id)
        assert "temperature" not in body, model_id


async def test_temperature_still_sent_on_older_models() -> None:
    body = await _complete_and_capture_body("claude-sonnet-4-6")
    assert body["temperature"] == 0.0


def test_cost_table_resolves_per_model() -> None:
    def cost_in_only(model_id: str) -> float:
        p = AnthropicLLMProvider(api_key="sk-ant-test", model_id=model_id)
        return p._cost_eur(1_000_000, 0)

    haiku = cost_in_only("claude-haiku-4-5")
    sonnet = cost_in_only("claude-sonnet-5")
    opus = cost_in_only("claude-opus-4-8")
    assert haiku < sonnet < opus
    # Haiku input is $1/MTok — a third of the old hardcoded Sonnet price.
    assert abs(haiku - 1.00 * AnthropicLLMProvider.USD_TO_EUR) < 1e-9


def test_explicit_price_override_wins() -> None:
    p = AnthropicLLMProvider(
        api_key="sk-ant-test", model_id="claude-haiku-4-5", usd_per_m_input=2.0
    )
    assert abs(p._cost_eur(1_000_000, 0) - 2.0 * AnthropicLLMProvider.USD_TO_EUR) < 1e-9
