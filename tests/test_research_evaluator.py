"""W11 — Research Evaluator."""

from __future__ import annotations

import json

import pytest

from theogony.acquisition.base import SourceCandidate
from theogony.agents.llm import LLMResult, StubLLMProvider
from theogony.agents.research_evaluator import Evaluator, EvaluatorCandidate
from theogony.agents.research_planner import PlannerContext
from theogony.config.settings import EvaluatorSettings
from theogony.curiosity.trigger import GapClass, ResearchStep, ResearchStepKind
from theogony.reporting.models import RegionDescriptor


def _ctx() -> PlannerContext:
    return PlannerContext(
        origin_query="Q?",
        answer_text_or_none=None,
        answer_verdict="partial",
        cited_node_count=0,
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1], seed_node_count=1),
    )


def _step() -> ResearchStep:
    return ResearchStep(
        kind=ResearchStepKind.WIKIDATA_LOOKUP,
        target="Q1",
        rationale="r",
    )


@pytest.mark.asyncio
async def test_evaluator_returns_empty_selection_when_candidates_empty() -> None:
    ev = Evaluator(llm=StubLLMProvider(default="unused"), settings=EvaluatorSettings(enabled=True))
    out = await ev.evaluate(context=_ctx(), candidates=[])
    assert out.selected == []
    assert out.evaluator_cost_eur == 0.0


@pytest.mark.asyncio
async def test_evaluator_caps_selection_at_three() -> None:
    class _PickManyStub(StubLLMProvider):
        async def complete(self, prompt: str, **kwargs: object) -> LLMResult:
            del prompt, kwargs
            text = json.dumps({"selected": [0, 1, 2, 3], "rejected": [], "rationale": "want four"})
            return LLMResult(
                text=text,
                input_tokens=1,
                output_tokens=1,
                cost_eur=0.001,
                latency_ms=0,
                model_id="stub",
            )

    cands: list[EvaluatorCandidate] = []
    for i in range(4):
        sc = SourceCandidate(
            source_type="wikidata",
            identifier=f"Q{i}",
            title=f"T{i}",
            authors=[],
            languages=["en"],
            url=f"https://www.wikidata.org/wiki/Q{i}",
            download_url=f"https://www.wikidata.org/wiki/Q{i}",
            metadata={"copyright": False},
        )
        cands.append(
            EvaluatorCandidate(
                source_step=_step(),
                candidate_label=f"c{i}",
                summary="s",
                estimated_bytes=100,
                metadata={"_source_candidate": sc.model_dump()},
            )
        )
    ev = Evaluator(llm=_PickManyStub(), settings=EvaluatorSettings(enabled=True))
    out = await ev.evaluate(context=_ctx(), candidates=cands)
    assert len(out.selected) == 3
