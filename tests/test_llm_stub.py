"""Tests for LLMProvider protocol + StubLLMProvider."""

from __future__ import annotations

import pytest

from theogony.agents.llm import LLMProvider, LLMResult, StubLLMProvider


class TestProtocol:
    def test_stub_satisfies_protocol(self) -> None:
        assert isinstance(StubLLMProvider(), LLMProvider)


class TestLLMResult:
    def test_defaults(self) -> None:
        r = LLMResult(text="hello")
        assert r.text == "hello"
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.cost_eur == 0.0
        assert r.latency_ms == 0
        assert r.model_id == ""

    def test_negative_token_counts_rejected(self) -> None:
        with pytest.raises(ValueError):
            LLMResult(text="x", input_tokens=-1)
        with pytest.raises(ValueError):
            LLMResult(text="x", output_tokens=-1)
        with pytest.raises(ValueError):
            LLMResult(text="x", cost_eur=-0.01)


class TestStubResponses:
    async def test_default_response_when_no_match(self) -> None:
        stub = StubLLMProvider(default="fallback answer")
        result = await stub.complete("anything")
        assert result.text == "fallback answer"

    async def test_exact_prefix_match(self) -> None:
        stub = StubLLMProvider(
            responses={"Extract relations from:": "[]"},
            default="should not be used",
        )
        result = await stub.complete("Extract relations from:\nHarrer reached Lhasa.")
        assert result.text == "[]"

    async def test_longest_prefix_wins(self) -> None:
        stub = StubLLMProvider(
            responses={
                "Extract": "short",
                "Extract relations": "longer",
            },
        )
        result = await stub.complete("Extract relations from one sentence")
        assert result.text == "longer"

    async def test_add_response_extends_script(self) -> None:
        stub = StubLLMProvider()
        stub.add_response("Synthesize:", "Heinrich Harrer reached Tibet in 1944.")
        result = await stub.complete("Synthesize:\nConstellation about Harrer")
        assert result.text == "Heinrich Harrer reached Tibet in 1944."


class TestStubCallRecording:
    async def test_calls_are_recorded_in_order(self) -> None:
        stub = StubLLMProvider(default="ok")
        await stub.complete("first prompt")
        await stub.complete("second prompt", system="be helpful", temperature=0.7)
        assert len(stub.calls) == 2
        assert stub.calls[0]["prompt"] == "first prompt"
        assert stub.calls[1]["system"] == "be helpful"
        assert stub.calls[1]["temperature"] == 0.7

    async def test_json_schema_is_recorded(self) -> None:
        stub = StubLLMProvider(default='{"chosen": "Q1"}')
        schema = {"type": "object", "properties": {"chosen": {"type": "string"}}}
        await stub.complete("disambiguate", json_schema=schema)
        assert stub.calls[0]["json_schema"] == schema


class TestStubResultMetadata:
    async def test_token_counts_use_word_count_proxy(self) -> None:
        stub = StubLLMProvider(default="three words here")
        result = await stub.complete("two words")
        assert result.input_tokens == 2
        assert result.output_tokens == 3

    async def test_system_tokens_counted_too(self) -> None:
        stub = StubLLMProvider(default="x")
        result = await stub.complete("user prompt", system="system header tokens")
        # 2 prompt words + 3 system words = 5 input tokens
        assert result.input_tokens == 5

    async def test_model_id_propagates_to_result(self) -> None:
        stub = StubLLMProvider(default="x", model_id="stub@1.0")
        result = await stub.complete("anything")
        assert result.model_id == "stub@1.0"

    async def test_latency_is_reported(self) -> None:
        stub = StubLLMProvider(default="x", latency_ms=42)
        result = await stub.complete("anything")
        assert result.latency_ms == 42
