"""Research Evaluator — LLM picks which research candidates to ingest (W11)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider
from theogony.agents.research_planner import PlannerContext
from theogony.config.settings import EvaluatorSettings
from theogony.curiosity.trigger import ResearchStep

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "research_evaluator.md"


class EvaluatorCandidate(BaseModel):
    """One candidate returned from a research step."""

    model_config = ConfigDict(extra="forbid")

    source_step: ResearchStep
    candidate_label: str
    summary: str = ""
    estimated_bytes: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RejectedEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: EvaluatorCandidate
    reason: str


class EvaluatorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: list[EvaluatorCandidate] = Field(default_factory=list, max_length=3)
    rejected: list[RejectedEvaluation] = Field(default_factory=list)
    rationale: str = ""
    evaluator_cost_eur: float = Field(default=0.0, ge=0.0)


class _EvaluatorLLMRejected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    reason: str = ""


class _EvaluatorLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: list[int] = Field(default_factory=list)
    rejected: list[_EvaluatorLLMRejected] = Field(default_factory=list)
    rationale: str = ""


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class Evaluator:
    """LLM ranker over executor-produced candidates."""

    def __init__(self, *, llm: LLMProvider, settings: EvaluatorSettings) -> None:
        self._llm = llm
        self._settings = settings
        self._system = _load_system_prompt()

    async def evaluate(
        self,
        *,
        context: PlannerContext,
        candidates: list[EvaluatorCandidate],
    ) -> EvaluatorDecision:
        if not candidates:
            return EvaluatorDecision()
        numbered = [
            {
                "index": i,
                "label": c.candidate_label,
                "summary": c.summary,
                "estimated_bytes": c.estimated_bytes,
            }
            for i, c in enumerate(candidates)
        ]
        user_prompt = json.dumps(
            {
                "origin_query": context.origin_query,
                "answer_text_or_none": context.answer_text_or_none,
                "answer_verdict": context.answer_verdict,
                "gap_class": context.gap_class.value,
                "region_descriptor": context.region_descriptor.model_dump(),
                "candidates": numbered,
            },
            ensure_ascii=False,
        )
        schema = _EvaluatorLLMOutput.model_json_schema()
        result = await self._llm.complete(
            user_prompt,
            system=self._system,
            json_schema=schema,
            max_output_tokens=self._settings.max_total_tokens,
            temperature=0.0,
        )
        parsed = _EvaluatorLLMOutput.model_validate_json(result.text)
        selected: list[EvaluatorCandidate] = []
        seen: set[int] = set()
        for idx in parsed.selected:
            if idx in seen or idx < 0 or idx >= len(candidates):
                continue
            seen.add(idx)
            selected.append(candidates[idx])
            if len(selected) >= 3:
                break
        rejected_rows: list[RejectedEvaluation] = []
        for row in parsed.rejected:
            if row.index < 0 or row.index >= len(candidates):
                continue
            rejected_rows.append(
                RejectedEvaluation(candidate=candidates[row.index], reason=row.reason)
            )
        return EvaluatorDecision(
            selected=selected,
            rejected=rejected_rows,
            rationale=parsed.rationale,
            evaluator_cost_eur=float(result.cost_eur),
        )


__all__ = [
    "Evaluator",
    "EvaluatorCandidate",
    "EvaluatorDecision",
    "RejectedEvaluation",
]
