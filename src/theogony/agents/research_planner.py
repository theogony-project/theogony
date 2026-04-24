"""ResearchPlanner — LLM-backed plan for curiosity acquisition (W11)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from theogony.agents.llm import LLMProvider
from theogony.config.settings import ResearchPlannerSettings
from theogony.curiosity.trigger import GapClass, ResearchPlan, ResearchStep
from theogony.reporting.models import RegionDescriptor

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "research_planner.md"


class PlannerContext(BaseModel):
    """Everything the planner needs to decide a plan."""

    model_config = ConfigDict(extra="forbid")

    origin_query: str
    answer_text_or_none: str | None
    answer_verdict: Literal["good", "partial", "poor", "failed"]
    cited_node_count: int
    gap_class: GapClass
    region_descriptor: RegionDescriptor


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _plan_output_model(max_steps: int) -> type[BaseModel]:
    cap = max(0, min(5, max_steps))
    return create_model(
        "ResearchPlanLLMOutput",
        __config__=ConfigDict(extra="forbid"),
        steps=(
            list[ResearchStep],
            Field(default_factory=list, max_length=cap),
        ),
    )


class ResearchPlanner:
    """LLM-backed planner returning a typed :class:`~theogony.curiosity.trigger.ResearchPlan`."""

    def __init__(self, *, llm: LLMProvider, settings: ResearchPlannerSettings) -> None:
        self._llm = llm
        self._settings = settings
        self._system = _load_system_prompt()

    async def plan(self, context: PlannerContext) -> ResearchPlan:
        out_model = _plan_output_model(self._settings.max_steps_per_plan)
        user_prompt = json.dumps(
            {
                "origin_query": context.origin_query,
                "answer_text_or_none": context.answer_text_or_none,
                "answer_verdict": context.answer_verdict,
                "cited_node_count": context.cited_node_count,
                "gap_class": context.gap_class.value,
                "region_descriptor": context.region_descriptor.model_dump(),
            },
            ensure_ascii=False,
        )
        raw, cost = await self._llm.complete_with_web_search_for_research_plan(
            system_prompt=self._system,
            user_prompt=user_prompt,
            output_schema=out_model,
            max_search_calls=self._settings.max_search_calls,
            max_total_tokens=self._settings.max_total_tokens,
        )
        validated = out_model.model_validate(raw.model_dump())
        raw_steps = validated.model_dump().get("steps") or []
        steps = [ResearchStep.model_validate(s) for s in raw_steps][
            : self._settings.max_steps_per_plan
        ]
        return ResearchPlan(
            steps=steps,
            planner_model_id=cost.model_id or self._llm.model_id,
            planner_cost_eur=float(cost.eur_cost),
        )


__all__ = ["PlannerContext", "ResearchPlanner"]
