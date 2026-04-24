"""W11 — ResearchPlanner + Anthropic planner transport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from theogony.agents.llm import ResearchPlannerCost, StubLLMProvider
from theogony.agents.llm_anthropic import AnthropicLLMProvider
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.agents.llm_openai import OpenAILLMProvider
from theogony.agents.research_planner import (
    PlannerContext,
    ResearchPlanner,
    _load_system_prompt,
    _plan_output_model,
)
from theogony.config.settings import ResearchPlannerSettings
from theogony.curiosity.trigger import GapClass, ResearchStep, ResearchStepKind
from theogony.reporting.models import RegionDescriptor


def _ctx() -> PlannerContext:
    return PlannerContext(
        origin_query="Sven Hedin explored Tibet",
        answer_text_or_none=None,
        answer_verdict="partial",
        cited_node_count=0,
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1),
    )


class _EmptyPlanLLM:
    model_id = "mock-empty"

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type,
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[Any, ResearchPlannerCost]:
        del system_prompt, user_prompt, max_search_calls, max_total_tokens
        empty = output_schema(steps=[])
        cost = ResearchPlannerCost(
            usd_cost=0.0, eur_cost=0.01, search_call_count=0, model_id="mock-empty"
        )
        return empty, cost


@pytest.mark.asyncio
async def test_planner_returns_empty_plan_when_llm_returns_empty_steps() -> None:
    planner = ResearchPlanner(llm=_EmptyPlanLLM(), settings=ResearchPlannerSettings(enabled=True))
    plan = await planner.plan(_ctx())
    assert plan.steps == []


@pytest.mark.asyncio
async def test_planner_rejects_more_than_max_steps_via_schema() -> None:
    st = ResearchStep(
        kind=ResearchStepKind.WIKIDATA_LOOKUP,
        target="Q1",
        rationale="r",
    )
    M = _plan_output_model(2)
    with pytest.raises(ValidationError):
        M.model_validate({"steps": [st.model_dump()] * 4})


@pytest.mark.asyncio
async def test_planner_records_cost_on_returned_plan() -> None:
    class _CostLLM:
        model_id = "cost-mock"

        async def complete_with_web_search_for_research_plan(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            output_schema: type,
            max_search_calls: int = 3,
            max_total_tokens: int = 4000,
        ) -> tuple[Any, ResearchPlannerCost]:
            del system_prompt, user_prompt, max_search_calls, max_total_tokens
            body = output_schema(
                steps=[
                    ResearchStep(
                        kind=ResearchStepKind.GUTENBERG_SEARCH,
                        target="Hedin Tibet",
                        rationale="x",
                    )
                ]
            )
            cost = ResearchPlannerCost(
                usd_cost=0.01, eur_cost=0.042, search_call_count=0, model_id="cost-mock"
            )
            return body, cost

    planner = ResearchPlanner(llm=_CostLLM(), settings=ResearchPlannerSettings(enabled=True))
    plan = await planner.plan(_ctx())
    assert plan.planner_cost_eur == pytest.approx(0.042)
    assert plan.planner_model_id == "cost-mock"


@pytest.mark.asyncio
async def test_stub_provider_returns_deterministic_one_step_plan() -> None:
    planner = ResearchPlanner(
        llm=StubLLMProvider(),
        settings=ResearchPlannerSettings(enabled=True, max_steps_per_plan=3),
    )
    plan = await planner.plan(_ctx())
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == ResearchStepKind.WIKIDATA_LOOKUP
    assert plan.steps[0].target == "Sven"


@pytest.mark.asyncio
async def test_other_providers_raise_not_implemented_for_planner() -> None:
    oa = OpenAILLMProvider(api_key="sk-test")
    with pytest.raises(NotImplementedError, match="Anthropic"):
        await oa.complete_with_web_search_for_research_plan(
            system_prompt="s",
            user_prompt="{}",
            output_schema=_plan_output_model(3),
        )
    gm = GeminiLLMProvider(api_key="k")
    with pytest.raises(NotImplementedError, match="Anthropic"):
        await gm.complete_with_web_search_for_research_plan(
            system_prompt="s",
            user_prompt="{}",
            output_schema=_plan_output_model(3),
        )


@pytest.mark.asyncio
async def test_anthropic_provider_invokes_web_search_tool_for_planner() -> None:
    import respx
    from anthropic import AsyncAnthropic

    payload = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "theogony_research_plan",
                "input": {"steps": []},
            }
        ],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 5},
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        tools = body.get("tools") or []
        types = [t.get("type") for t in tools if isinstance(t, dict)]
        assert "web_search_20250305" in types
        return httpx.Response(200, json=payload)

    with respx.mock:
        respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_handler)
        transport = httpx.AsyncHTTPTransport(retries=1)
        async with httpx.AsyncClient(transport=transport) as http:
            anthropic = AsyncAnthropic(api_key="sk-ant-test", http_client=http)
            client = AnthropicLLMProvider(api_key="sk-ant-test", client=anthropic)
            out, cost = await client.complete_with_web_search_for_research_plan(
                system_prompt="sys",
                user_prompt="{}",
                output_schema=_plan_output_model(3),
            )
    assert list(getattr(out, "steps", [])) == []
    assert cost.search_call_count == 0


def test_planner_prompt_file_is_non_empty() -> None:
    assert "Research Planner" in _load_system_prompt()
