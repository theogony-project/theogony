"""Tests for GeminiLLMProvider."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from theogony.agents.llm import LLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider

# ---------------------------------------------------------------------------
# Helpers — fake google-genai client
# ---------------------------------------------------------------------------


def _fake_response(
    text: str = "ok",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> MagicMock:
    response = MagicMock()
    response.text = text
    usage = MagicMock()
    usage.prompt_token_count = input_tokens
    usage.candidates_token_count = output_tokens
    response.usage_metadata = usage
    return response


def _fake_client(
    response: MagicMock | None = None,
    delay_s: float = 0.0,
    capture: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a MagicMock with the same shape as google.genai.Client.

    `client.aio.models.generate_content(model=..., contents=..., config=...)`
    must be awaitable; we use a coroutine to satisfy that.
    """
    if response is None:
        response = _fake_response()

    async def generate_content(model: str, contents: Any, config: Any) -> MagicMock:
        if capture is not None:
            capture["model"] = model
            capture["contents"] = contents
            capture["config"] = config
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        return response

    client = MagicMock()
    client.aio.models.generate_content = generate_content
    return client


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_requires_api_key_or_client(self) -> None:
        with pytest.raises(ValueError, match="api_key or a pre-built client"):
            GeminiLLMProvider(api_key=None)

    def test_accepts_secretstr_api_key(self) -> None:
        provider = GeminiLLMProvider(api_key=SecretStr("g-fake"))
        # Repr must not leak the raw key.
        assert "g-fake" not in repr(provider)

    def test_accepts_string_api_key(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake-string")
        assert provider.model_id == "gemini-2.5-flash-lite"

    def test_default_model_id_is_flash_lite(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake")
        assert provider.model_id == "gemini-2.5-flash-lite"

    def test_model_id_is_overridable(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake", model_id="gemini-2.5-pro")
        assert provider.model_id == "gemini-2.5-pro"

    def test_protocol_conformance(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake")
        assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------


class TestCost:
    def test_default_pricing_matches_plan_3_3a(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake")
        # 1 M input + 1 M output: 0.10 + 0.40 = 0.50 USD = ~0.465 EUR
        cost = provider._cost_eur(1_000_000, 1_000_000)
        assert cost == pytest.approx(0.50 * 0.93, rel=1e-3)

    def test_pricing_overridable(self) -> None:
        provider = GeminiLLMProvider(
            api_key="g-fake",
            usd_per_m_input=1.0,
            usd_per_m_output=2.0,
        )
        cost = provider._cost_eur(1_000_000, 1_000_000)
        assert cost == pytest.approx(3.0 * 0.93, rel=1e-3)

    def test_zero_tokens_zero_cost(self) -> None:
        provider = GeminiLLMProvider(api_key="g-fake")
        assert provider._cost_eur(0, 0) == 0.0


# ---------------------------------------------------------------------------
# complete() — mocked client
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_returns_llm_result_with_text(self) -> None:
        client = _fake_client(_fake_response(text="answer text", input_tokens=20, output_tokens=8))
        provider = GeminiLLMProvider(api_key=None, client=client)
        result = await provider.complete("question?")
        assert result.text == "answer text"
        assert result.input_tokens == 20
        assert result.output_tokens == 8
        assert result.model_id == "gemini-2.5-flash-lite"

    async def test_cost_is_computed_from_tokens(self) -> None:
        client = _fake_client(_fake_response(input_tokens=1_000_000, output_tokens=1_000_000))
        provider = GeminiLLMProvider(api_key=None, client=client)
        result = await provider.complete("q")
        assert result.cost_eur == pytest.approx(0.50 * 0.93, rel=1e-3)

    async def test_latency_is_recorded(self) -> None:
        client = _fake_client(delay_s=0.05)
        provider = GeminiLLMProvider(api_key=None, client=client)
        result = await provider.complete("q")
        assert result.latency_ms >= 50

    async def test_system_instruction_passed_through(self) -> None:
        capture: dict[str, Any] = {}
        client = _fake_client(capture=capture)
        provider = GeminiLLMProvider(api_key=None, client=client)
        await provider.complete("q", system="be concise")
        assert capture["config"].system_instruction == "be concise"

    async def test_max_output_tokens_passed_through(self) -> None:
        capture: dict[str, Any] = {}
        client = _fake_client(capture=capture)
        provider = GeminiLLMProvider(api_key=None, client=client)
        await provider.complete("q", max_output_tokens=128)
        assert capture["config"].max_output_tokens == 128

    async def test_temperature_passed_through(self) -> None:
        capture: dict[str, Any] = {}
        client = _fake_client(capture=capture)
        provider = GeminiLLMProvider(api_key=None, client=client)
        await provider.complete("q", temperature=0.7)
        assert capture["config"].temperature == 0.7

    async def test_json_schema_sets_mime_and_schema(self) -> None:
        capture: dict[str, Any] = {}
        client = _fake_client(capture=capture)
        provider = GeminiLLMProvider(api_key=None, client=client)
        schema = {
            "type": "object",
            "properties": {"chosen": {"type": "string"}},
            "required": ["chosen"],
        }
        await provider.complete("disambiguate", json_schema=schema)
        cfg = capture["config"]
        assert cfg.response_mime_type == "application/json"
        # response_schema may be wrapped by Pydantic into the SDK's schema type;
        # we check the original dict made it through identifiably.
        schema_attr = cfg.response_schema
        # The SDK accepts dicts directly; we get them back unchanged (or
        # a Schema object whose representation contains our property name).
        assert "chosen" in str(schema_attr)

    async def test_no_json_schema_no_mime_set(self) -> None:
        capture: dict[str, Any] = {}
        client = _fake_client(capture=capture)
        provider = GeminiLLMProvider(api_key=None, client=client)
        await provider.complete("q")
        assert capture["config"].response_mime_type is None

    async def test_timeout_raises(self) -> None:
        client = _fake_client(delay_s=1.0)
        provider = GeminiLLMProvider(api_key=None, client=client)
        with pytest.raises(asyncio.TimeoutError):
            await provider.complete("q", timeout_s=0.05)


# ---------------------------------------------------------------------------
# Live integration (gated)
# ---------------------------------------------------------------------------


class TestLiveGeminiIntegration:
    """Live test against the real Gemini API.

    Skipped unless ``THEOGONY_RUN_GEMINI_INTEGRATION=1`` AND a usable
    key is present (``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``).
    """

    @pytest.mark.skipif(
        os.environ.get("THEOGONY_RUN_GEMINI_INTEGRATION") != "1"
        or not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        reason="set THEOGONY_RUN_GEMINI_INTEGRATION=1 + GEMINI_API_KEY/GOOGLE_API_KEY",
    )
    async def test_real_gemini_returns_a_short_answer(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        provider = GeminiLLMProvider(api_key=api_key)
        result = await provider.complete(
            "Answer in exactly one word: capital of France?",
            max_output_tokens=20,
        )
        assert result.text.strip()
        assert result.input_tokens > 0
        assert result.output_tokens > 0
        assert result.cost_eur >= 0.0
