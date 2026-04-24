"""Optional live Anthropic planner smoke (W11) — not run in CI."""

from __future__ import annotations

import os

import pytest

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.research_planner import PlannerContext, ResearchPlanner
from theogony.config.settings import ResearchPlannerSettings, Settings
from theogony.curiosity.trigger import GapClass
from theogony.reporting.models import RegionDescriptor


@pytest.mark.live_anthropic
@pytest.mark.asyncio
async def test_live_planner_smoke_sven_hedin() -> None:
    if not os.environ.get("THEOGONY_RUN_LIVE_ANTHROPIC"):
        pytest.skip("THEOGONY_RUN_LIVE_ANTHROPIC not set")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    settings = Settings()
    llm = build_llm_from_settings(settings)
    planner = ResearchPlanner(
        llm=llm,
        settings=ResearchPlannerSettings(
            enabled=True,
            max_search_calls=3,
            max_total_tokens=4000,
            max_steps_per_plan=3,
        ),
    )
    ctx = PlannerContext(
        origin_query="Wer war Sven Hedin und was hat er in Tibet erforscht?",
        answer_text_or_none=None,
        answer_verdict="partial",
        cited_node_count=0,
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1),
    )
    import time

    t0 = time.perf_counter()
    plan = await planner.plan(ctx)
    elapsed = time.perf_counter() - t0
    assert len(plan.steps) >= 1
    assert plan.planner_cost_eur < 0.05
    assert elapsed < 30.0
