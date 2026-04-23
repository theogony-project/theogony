"""Unit tests for Mnemosyne LLM fallback (PHX-0071 / W5)."""

from __future__ import annotations

import json

import pytest

from theogony.agents.llm import LLMResult
from theogony.agents.mnemosyne_llm_fallback import MnemosyneLLMFallback
from theogony.reporting.models import MetaClassificationVerdict, SynthesisBreakdown
from theogony.retrieval.synthesize import Answer


class _FakeLLM:
    def __init__(self, *, cost_eur: float = 0.0, text: str = "") -> None:
        self._cost = cost_eur
        self._text = text

    @property
    def model_id(self) -> str:
        return "fake"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, object] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float = 30.0,
    ) -> LLMResult:
        return LLMResult(
            text=self._text,
            input_tokens=1,
            output_tokens=1,
            cost_eur=self._cost,
            latency_ms=0,
            model_id=self.model_id,
        )


@pytest.mark.asyncio
async def test_fallback_classify_returns_verdict_when_under_budget() -> None:
    line = json.dumps({"verdict": "self_referential", "rationale": "meta"})
    llm = _FakeLLM(cost_eur=0.0, text=f"{line}\n")
    fb = MnemosyneLLMFallback(llm, max_calls_per_hour=10, max_cost_eur_per_call=0.01)
    answer = Answer(text="answer", cited_node_ids=[], synthesis=SynthesisBreakdown())
    mc = await fb.classify(query="q", answer=answer)
    assert mc is not None
    assert mc.verdict == MetaClassificationVerdict.SELF_REFERENTIAL


@pytest.mark.asyncio
async def test_fallback_classify_returns_none_when_rate_limit_exhausted() -> None:
    line = json.dumps({"verdict": "self_referential", "rationale": "x"})
    llm = _FakeLLM(text=f"{line}\n")
    fb = MnemosyneLLMFallback(llm, max_calls_per_hour=1, max_cost_eur_per_call=0.01)
    answer = Answer(text="a", cited_node_ids=[], synthesis=SynthesisBreakdown())
    assert await fb.classify(query="q1", answer=answer) is not None
    assert await fb.classify(query="q2", answer=answer) is None


@pytest.mark.asyncio
async def test_fallback_classify_returns_none_when_per_call_cost_exceeded() -> None:
    line = json.dumps({"verdict": "self_referential", "rationale": "x"})
    llm = _FakeLLM(cost_eur=0.01, text=f"{line}\n")
    fb = MnemosyneLLMFallback(llm, max_calls_per_hour=10, max_cost_eur_per_call=0.001)
    answer = Answer(text="a", cited_node_ids=[], synthesis=SynthesisBreakdown())
    assert await fb.classify(query="q", answer=answer) is None


@pytest.mark.asyncio
async def test_fallback_validates_llm_response_shape() -> None:
    llm = _FakeLLM(text="not json at all\n")
    fb = MnemosyneLLMFallback(llm, max_calls_per_hour=10, max_cost_eur_per_call=0.01)
    answer = Answer(text="a", cited_node_ids=[], synthesis=SynthesisBreakdown())
    assert await fb.classify(query="q", answer=answer) is None
