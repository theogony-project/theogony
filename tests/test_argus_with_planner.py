"""W11 — Argus with ResearchPlanner path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.agents.argus import ArgusAgent, ArgusOutcome, ArgusSettings
from theogony.agents.argus_ingest_runner import IngestRunner
from theogony.agents.llm import ResearchPlannerCost, StubLLMProvider
from theogony.agents.research_evaluator import Evaluator
from theogony.agents.research_planner import ResearchPlanner
from theogony.config.settings import (
    EvaluatorSettings,
    ResearchPlannerSettings,
)
from theogony.curiosity.research_executor import ResearchExecutor
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    ResearchStep,
    ResearchStepKind,
    TriggerBudget,
    TriggerReason,
)
from theogony.curiosity.verification_pool import PoolEntry
from theogony.reporting.models import RegionDescriptor


def _region() -> RegionDescriptor:
    return RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1)


def _trigger() -> CuriosityTrigger:
    return CuriosityTrigger(
        origin_query="Sven Hedin Tibet",
        origin_query_run_id="run-query-1",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=_region(),
        stub_signal_strength=0.8,
        proposed_acquisition_spec=AcquisitionSpec(search_query="Sven Hedin Tibet"),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=0,
    )


class _FixedPlanLLM:
    model_id = "plan-mock"

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
        step = ResearchStep(
            kind=ResearchStepKind.WIKIDATA_LOOKUP,
            target="Q205184",
            rationale="test",
        )
        body = output_schema(steps=[step])
        cost = ResearchPlannerCost(
            usd_cost=0.0, eur_cost=0.01, search_call_count=0, model_id="plan-mock"
        )
        return body, cost


class _EmptyPlanLLM:
    model_id = "empty-plan"

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
        body = output_schema(steps=[])
        cost = ResearchPlannerCost(
            usd_cost=0.0, eur_cost=0.0, search_call_count=0, model_id="empty-plan"
        )
        return body, cost


class _WdExec:
    @property
    def source_type(self) -> str:
        return "wikidata"

    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]:
        del query, limit
        return [
            SourceCandidate(
                source_type="wikidata",
                identifier="Q205184",
                title="Sven Hedin",
                authors=[],
                languages=["en"],
                url="https://www.wikidata.org/wiki/Q205184",
                download_url="https://www.wikidata.org/wiki/Q205184",
                metadata={"wikidata_description": "explorer", "copyright": False},
            )
        ]

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        body = "Sven Hedin was a Swedish explorer.\n"
        return RawContent(
            source_type="wikidata",
            identifier=candidate.identifier,
            title=candidate.title,
            language="en",
            content=body,
            content_format="text/plain; charset=utf-8",
            url=candidate.url,
            bytes_acquired=len(body.encode("utf-8")),
            metadata={"wikidata_qid": candidate.identifier, "copyright": False},
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
    def __init__(self) -> None:
        self.raws: list[RawContent] = []

    async def run_from_raw_content(self, raw: RawContent) -> str:
        self.raws.append(raw)
        return "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class _StubVerificationPool:
    def __init__(self) -> None:
        self.entries: list[PoolEntry] = []

    def register(
        self,
        candidate_label: str,
        ingest_run_id: str | None = None,
        *,
        source_type: str | None = None,
        source_identifier: str | None = None,
        target_node_ids: list[str] | None = None,
    ) -> PoolEntry:
        entry = PoolEntry(
            candidate_label=candidate_label,
            ingest_run_id=ingest_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
            target_node_ids=list(target_node_ids or ()),
        )
        self.entries.append(entry)
        return entry


def _run_reports_root(tmp_path: Path) -> Path:
    root = tmp_path / "run_reports"
    (root / "query").mkdir(parents=True)
    return root


@pytest.mark.asyncio
async def test_argus_with_planner_happy_path_writes_plan_then_decision_to_curiosity_report(
    tmp_path: Path,
) -> None:
    rr = _run_reports_root(tmp_path)
    llm_plan = _FixedPlanLLM()
    llm_eval = StubLLMProvider(
        default=json.dumps({"selected": [0], "rejected": [], "rationale": "pick wikidata"})
    )
    planner = ResearchPlanner(
        llm=llm_plan, settings=ResearchPlannerSettings(enabled=True, max_steps_per_plan=3)
    )
    executor = ResearchExecutor(wikidata=_WdExec(), gutenberg=_GutenbergStub())
    evaluator = Evaluator(llm=llm_eval, settings=EvaluatorSettings(enabled=True))
    runner = _StubIngestRunner()
    agent = ArgusAgent(
        adapter=_GutenbergStub(),
        ingest_runner=runner,
        verification_pool=_StubVerificationPool(),  # type: ignore[arg-type]
        settings=ArgusSettings(enabled=True, min_candidate_score=0.0, search_limit=5),
        use_research_planner=True,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        run_reports_dir=rr,
    )
    res = await agent.process(_trigger(), dry_run=False)
    assert res.outcome == ArgusOutcome.APPROVED_AND_INGESTED
    assert res.updated_trigger is not None
    assert res.updated_trigger.research_plan is not None
    assert len(res.updated_trigger.research_plan.steps) == 1
    assert res.evaluator_decision is not None
    assert len(res.evaluator_decision.selected) == 1
    assert len(runner.raws) == 1


@pytest.mark.asyncio
async def test_argus_outcome_no_planned_steps_when_planner_returns_empty(tmp_path: Path) -> None:
    rr = _run_reports_root(tmp_path)
    planner = ResearchPlanner(llm=_EmptyPlanLLM(), settings=ResearchPlannerSettings(enabled=True))
    executor = ResearchExecutor(wikidata=_WdExec(), gutenberg=_GutenbergStub())
    evaluator = Evaluator(
        llm=StubLLMProvider(default="{}"),
        settings=EvaluatorSettings(enabled=True),
    )
    agent = ArgusAgent(
        adapter=_GutenbergStub(),
        ingest_runner=_StubIngestRunner(),
        verification_pool=_StubVerificationPool(),  # type: ignore[arg-type]
        settings=ArgusSettings(enabled=True),
        use_research_planner=True,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        run_reports_dir=rr,
    )
    res = await agent.process(_trigger())
    assert res.outcome == ArgusOutcome.NO_PLANNED_STEPS
    assert res.updated_trigger is not None
    assert res.updated_trigger.research_plan is not None
    assert res.updated_trigger.research_plan.steps == []


@pytest.mark.asyncio
async def test_argus_outcome_no_candidate_selected_when_evaluator_picks_none(
    tmp_path: Path,
) -> None:
    rr = _run_reports_root(tmp_path)
    planner = ResearchPlanner(llm=_FixedPlanLLM(), settings=ResearchPlannerSettings(enabled=True))
    executor = ResearchExecutor(wikidata=_WdExec(), gutenberg=_GutenbergStub())
    evaluator = Evaluator(
        llm=StubLLMProvider(
            default=json.dumps({"selected": [], "rejected": [], "rationale": "skip all"})
        ),
        settings=EvaluatorSettings(enabled=True),
    )
    agent = ArgusAgent(
        adapter=_GutenbergStub(),
        ingest_runner=_StubIngestRunner(),
        verification_pool=_StubVerificationPool(),  # type: ignore[arg-type]
        settings=ArgusSettings(enabled=True),
        use_research_planner=True,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        run_reports_dir=rr,
    )
    res = await agent.process(_trigger())
    assert res.outcome == ArgusOutcome.NO_CANDIDATE_SELECTED
    assert res.evaluator_decision is not None


@pytest.mark.asyncio
async def test_argus_legacy_path_still_works_when_planner_disabled() -> None:
    from tests.test_argus import _good_candidate, _raw_small, _StubAdapter

    adapter = _StubAdapter(candidates=[_good_candidate()], raw=_raw_small())
    agent = ArgusAgent(
        adapter=adapter,
        ingest_runner=_StubIngestRunner(),
        verification_pool=_StubVerificationPool(),  # type: ignore[arg-type]
        settings=ArgusSettings(enabled=True, min_candidate_score=0.0, search_limit=5),
        use_research_planner=False,
    )
    res = await agent.process(_trigger())
    assert res.outcome == ArgusOutcome.APPROVED_AND_INGESTED
