"""W12 — HestiaSentinel + Argus wiring tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.agents.argus import ArgusAgent, ArgusOutcome
from theogony.agents.argus_ingest_runner import IngestRunner
from theogony.agents.hestia_sentinel import HestiaSentinel
from theogony.agents.llm import ResearchPlannerCost, StubLLMProvider
from theogony.agents.research_evaluator import EvaluatorCandidate
from theogony.agents.research_planner import PlannerContext
from theogony.config.settings import ArgusSettings, HestiaSentinelSettings, Settings
from theogony.curiosity.research_executor import ResearchExecutor
from theogony.curiosity.trigger import (
    GapClass,
    ResearchStep,
    ResearchStepKind,
)
from theogony.reporting.models import RegionDescriptor


def _ctx() -> PlannerContext:
    return PlannerContext(
        origin_query="public geography topic",
        answer_text_or_none=None,
        answer_verdict="partial",
        cited_node_count=0,
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1),
    )


def _ec(
    *,
    kind: ResearchStepKind,
    source: SourceCandidate,
    label: str = "x",
    summary: str = "",
    est: int = 1024,
) -> EvaluatorCandidate:
    step = ResearchStep(kind=kind, target="t", rationale="r")
    meta = dict(source.metadata)
    meta["_source_candidate"] = source.model_dump()
    return EvaluatorCandidate(
        source_step=step,
        candidate_label=label,
        summary=summary,
        estimated_bytes=est,
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_hestia_sentinel_approves_wikipedia_by_default() -> None:
    llm = StubLLMProvider(default="{}")
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings())
    src = SourceCandidate(
        source_type="wikipedia",
        identifier="Foo",
        title="Foo",
        authors=[],
        languages=["en"],
        url="https://en.wikipedia.org/wiki/Foo",
        download_url="https://en.wikipedia.org/wiki/Foo",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.WIKIPEDIA_FETCH, source=src)
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "approved"
    assert hr.rule_fired == "gutenberg_or_wikidata_or_wikipedia_default_approve"


@pytest.mark.asyncio
async def test_hestia_sentinel_approves_gutenberg_by_default() -> None:
    llm = StubLLMProvider(default="{}")
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings())
    src = SourceCandidate(
        source_type="gutenberg",
        identifier="1",
        title="Book",
        authors=[],
        languages=["en"],
        url="https://gutenberg.org/1",
        download_url="https://gutenberg.org/1.txt",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.GUTENBERG_SEARCH, source=src)
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "approved"


@pytest.mark.asyncio
async def test_hestia_sentinel_rejects_locked_block_list_host() -> None:
    llm = StubLLMProvider(default="{}")
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings())
    src = SourceCandidate(
        source_type="web",
        identifier="abc",
        title="x",
        authors=[],
        languages=[],
        url="https://www.facebook.com/foo",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.WEB_FETCH, source=src)
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "rejected"
    assert hr.rule_fired == "url_scheme_or_host_invalid"


@pytest.mark.asyncio
async def test_hestia_sentinel_rejects_hard_block_keyword_in_label() -> None:
    llm = StubLLMProvider(default="{}")
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings())
    src = SourceCandidate(
        source_type="wikipedia",
        identifier="X",
        title="X",
        authors=[],
        languages=["en"],
        url="https://en.wikipedia.org/wiki/X",
        download_url="https://en.wikipedia.org/wiki/X",
        metadata={},
    )
    ec = _ec(
        kind=ResearchStepKind.WIKIPEDIA_FETCH,
        source=src,
        label="article about csam policy",
        summary="",
    )
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "rejected"
    assert hr.rule_fired == "hard_block_keywords_in_label_or_summary"


@pytest.mark.asyncio
async def test_hestia_sentinel_rejects_oversized_candidate() -> None:
    llm = StubLLMProvider(default="{}")
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings(max_candidate_bytes=100))
    src = SourceCandidate(
        source_type="wikipedia",
        identifier="X",
        title="X",
        authors=[],
        languages=["en"],
        url="https://en.wikipedia.org/wiki/X",
        download_url="https://en.wikipedia.org/wiki/X",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.WIKIPEDIA_FETCH, source=src, est=10_000)
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "rejected"
    assert hr.rule_fired == "content_size_excessive"


@pytest.mark.asyncio
async def test_hestia_sentinel_calls_llm_fallback_for_unknown_web_candidate() -> None:
    llm = StubLLMProvider(default=json.dumps({"decision": "approved", "reason": "news outlet"}))
    s = HestiaSentinel(llm=llm, settings=HestiaSentinelSettings(llm_fallback_enabled=True))
    src = SourceCandidate(
        source_type="web",
        identifier="ab" * 8,
        title="https://example.com/news/1",
        authors=[],
        languages=[],
        url="https://example.com/news/1",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.WEB_FETCH, source=src, label="Example News", summary="headline")
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "approved"
    assert hr.llm_called is True
    assert hr.rule_fired == "llm_fallback"


@pytest.mark.asyncio
async def test_hestia_sentinel_rejects_when_llm_fallback_fails() -> None:
    class _BoomLLM(StubLLMProvider):
        async def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("offline")

    s = HestiaSentinel(
        llm=_BoomLLM(default=""), settings=HestiaSentinelSettings(llm_fallback_enabled=True)
    )
    src = SourceCandidate(
        source_type="web",
        identifier="ab" * 8,
        title="u",
        authors=[],
        languages=[],
        url="https://example.org/page",
        metadata={},
    )
    ec = _ec(kind=ResearchStepKind.WEB_FETCH, source=src)
    hr = await s.review(candidate=ec, context=_ctx())
    assert hr.decision == "rejected"
    assert hr.reason == "llm_fallback_unavailable"


class _WdExec:
    @property
    def source_type(self) -> str:
        return "wikidata"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="wikidata",
                identifier="Q1",
                title="Universe",
                authors=[],
                languages=["en"],
                url="https://www.wikidata.org/wiki/Q1",
                download_url="https://www.wikidata.org/wiki/Q1",
                metadata={"wikidata_description": "all", "estimated_bytes": 50},
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        body = "Q1 is a test item.\n"
        return RawContent(
            source_type="wikidata",
            identifier=candidate.identifier,
            title=candidate.title,
            language="en",
            content=body,
            content_format="text/plain; charset=utf-8",
            url=candidate.url,
            bytes_acquired=len(body.encode("utf-8")),
            metadata={"wikidata_qid": candidate.identifier},
        )

    async def aclose(self) -> None:
        return None


class _GutenbergStub:
    @property
    def source_type(self) -> str:
        return "gutenberg"

    def supports(self, source_type: str) -> bool:
        return source_type == "gutenberg"

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        del query, limit
        return []

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        raise AssertionError("not used")

    async def aclose(self) -> None:
        return None


class _StubIngestRunner(IngestRunner):
    async def run_from_raw_content(self, raw: RawContent) -> str:
        del raw
        return "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class _EmptyWiki:
    @property
    def source_type(self) -> str:
        return "wikipedia"

    def supports(self, source_type: str) -> bool:
        return source_type == "wikipedia"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        return []

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        raise AssertionError(candidate)

    async def aclose(self) -> None:
        return None


class _EmptyWeb:
    @property
    def source_type(self) -> str:
        return "web"

    def supports(self, source_type: str) -> bool:
        return source_type == "web"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        raise NotImplementedError

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        raise AssertionError(candidate)

    async def aclose(self) -> None:
        return None


class _PlanAndEvalLLM(StubLLMProvider):
    """Planner structured output + evaluator JSON on ``complete``."""

    def __init__(self) -> None:
        super().__init__(default=json.dumps({"selected": [0], "rejected": [], "rationale": "pick"}))

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type,
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[object, ResearchPlannerCost]:
        del system_prompt, user_prompt, max_search_calls, max_total_tokens
        step = ResearchStep(kind=ResearchStepKind.WIKIDATA_LOOKUP, target="Q1", rationale="t")
        body = output_schema(steps=[step])
        cost = ResearchPlannerCost(
            usd_cost=0.0, eur_cost=0.0, search_call_count=0, model_id="plan-eval"
        )
        return body, cost


@pytest.mark.asyncio
async def test_argus_dispatch_with_sentinel_when_settings_enabled(tmp_path: Path) -> None:
    from theogony.agents.research_evaluator import Evaluator
    from theogony.agents.research_planner import ResearchPlanner
    from theogony.curiosity.trigger import (
        AcquisitionSpec,
        CuriosityTrigger,
        TriggerBudget,
        TriggerReason,
    )

    rr = tmp_path / "run_reports"
    (rr / "query").mkdir(parents=True)
    base = Settings().model_copy(
        update={
            "data_dir": tmp_path,
            "run_reports_dir": rr,
            "curiosity": Settings().curiosity.model_copy(
                update={
                    "research_planner": Settings().curiosity.research_planner.model_copy(
                        update={"enabled": True}
                    ),
                    "evaluator": Settings().curiosity.evaluator.model_copy(
                        update={"enabled": True}
                    ),
                    "hestia_sentinel": Settings().curiosity.hestia_sentinel.model_copy(
                        update={"enabled": True, "llm_fallback_enabled": False}
                    ),
                }
            ),
        }
    )
    llm = _PlanAndEvalLLM()
    planner = ResearchPlanner(llm=llm, settings=base.curiosity.research_planner)
    executor = ResearchExecutor(
        wikidata=_WdExec(),
        gutenberg=_GutenbergStub(),
        wikipedia=_EmptyWiki(),
        web_fetch=_EmptyWeb(),
    )
    evaluator = Evaluator(llm=llm, settings=base.curiosity.evaluator)
    hestia = HestiaSentinel(llm=llm, settings=base.curiosity.hestia_sentinel)
    argus = ArgusAgent(
        adapter=_GutenbergStub(),
        hestia=hestia,
        ingest_runner=_StubIngestRunner(),
        settings=ArgusSettings(enabled=True, min_candidate_score=0.0, search_limit=5),
        use_research_planner=True,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        run_reports_dir=rr,
    )
    trig = CuriosityTrigger(
        origin_query="universe",
        origin_query_run_id="q1",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1], seed_node_count=1),
        stub_signal_strength=0.9,
        proposed_acquisition_spec=AcquisitionSpec(search_query="universe"),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=0,
    )
    res = await argus.process(trig, dry_run=True)
    assert res.outcome == ArgusOutcome.DRY_RUN
    assert res.updated_trigger is not None
    assert res.updated_trigger.research_plan is not None
