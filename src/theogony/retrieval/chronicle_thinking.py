"""
Post-retrieval \"thinking\" rounds: the LLM may propose new search strings after
seeing the first constellation + draft answer, then retrieval widens and the
pipeline re-synthesizes (bounded by ``thinking_max`` per :meth:`QueryPipeline.ask`).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import ChronicleEntryPlannerSettings, ChronicleThinkingSettings
from theogony.core.model import Constellation
from theogony.retrieval.chronicle_entry_planner import normalize_sub_queries
from theogony.retrieval.synthesize import Answer

log = get_logger("retrieval.chronicle_thinking")

_THINKING_SYSTEM = """You refine vector-graph retrieval for the Pantheon Chronik.

You already ran one retrieval pass. You receive a compact JSON summary of what
was found (top node labels, gaps, answer excerpt, counts) plus every search
string already tried.

Decide whether another dive is worthwhile. If yes, output **new** short
English search strings (not full sentences) that are not near-duplicates of
strings already tried — complementary angles, missing entities, or sharper
keywords. If the evidence is sufficient or another pass would not help, set
continue to false and omit search_queries."""


class _ThinkingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    continue_retrieval: bool = Field(alias="continue")
    search_queries: list[str] = Field(default_factory=list)
    rationale: str = ""


THINKING_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "continue": {"type": "boolean"},
        "search_queries": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "rationale": {"type": "string"},
    },
    "required": ["continue"],
    "additionalProperties": False,
}


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def build_thinking_context(
    *,
    user_query: str,
    constellation: Constellation,
    answer: Answer,
    tried_subqueries: list[str],
    round_index: int,
) -> dict[str, Any]:
    """Small JSON-serialisable bundle for the thinking LLM."""
    nodes_sorted = sorted(
        constellation.nodes,
        key=lambda n: float(n.confidence or 0.0),
        reverse=True,
    )
    top_labels = [n.label for n in nodes_sorted[:14]]
    text = (answer.text or "").strip()
    if len(text) > 900:
        text = text[:897] + "..."
    return {
        "round": round_index,
        "user_query": user_query,
        "tried_search_strings": tried_subqueries,
        "top_node_labels": top_labels,
        "gaps": list(constellation.gaps),
        "answer_excerpt": text,
        "counts": {
            "nodes": len(constellation.nodes),
            "edges": len(constellation.edges),
            "cited": len(answer.cited_node_ids),
        },
    }


@dataclass(frozen=True)
class ChronicleThinkingRefine:
    """One thinking-round decision."""

    continue_retrieval: bool
    search_queries: list[str]
    rationale: str
    duration_ms: int
    used_llm: bool


async def plan_chronicle_thinking_refine(
    *,
    llm: LLMProvider,
    user_query: str,
    context: dict[str, Any],
    thinking_limits: ChronicleThinkingSettings,
    planner_limits: ChronicleEntryPlannerSettings,
) -> ChronicleThinkingRefine:
    """Ask the LLM for another retrieval pass, or refuse (continue=false)."""
    if isinstance(llm, StubLLMProvider):
        return ChronicleThinkingRefine(False, [], "", 0, False)

    t0 = time.perf_counter()
    prompt = (
        "Retrieval summary (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        'Respond with JSON only: {"continue": boolean, '
        '"search_queries": string[] (only if continue is true), '
        '"rationale": string (optional)}.'
    )
    try:
        result = await llm.complete(
            prompt,
            system=_THINKING_SYSTEM,
            json_schema=THINKING_JSON_SCHEMA,
            max_output_tokens=thinking_limits.max_planner_tokens,
            temperature=0.15,
            timeout_s=45.0,
        )
        payload = _ThinkingPayload.model_validate_json(_strip_json_fences(result.text))
    except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("chronicle thinking parse failed: %s", exc)
        return ChronicleThinkingRefine(False, [], "", int((time.perf_counter() - t0) * 1000), True)
    except Exception as exc:  # pragma: no cover - network
        log.warning("chronicle thinking LLM failed: %s", exc)
        return ChronicleThinkingRefine(False, [], "", int((time.perf_counter() - t0) * 1000), True)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    if not payload.continue_retrieval:
        return ChronicleThinkingRefine(
            False, [], (payload.rationale or "").strip(), duration_ms, True
        )

    normalized = normalize_sub_queries(
        list(payload.search_queries),
        user_query=user_query,
        limits=planner_limits,
    )
    tried_cf = {s.casefold() for s in context.get("tried_search_strings", []) if isinstance(s, str)}
    fresh = [q for q in normalized if q.casefold() not in tried_cf]
    if not fresh:
        return ChronicleThinkingRefine(
            False,
            [],
            (payload.rationale or "no new queries after dedupe").strip(),
            duration_ms,
            True,
        )
    return ChronicleThinkingRefine(
        True,
        fresh,
        (payload.rationale or "").strip(),
        duration_ms,
        True,
    )


__all__ = [
    "THINKING_JSON_SCHEMA",
    "ChronicleThinkingRefine",
    "build_thinking_context",
    "plan_chronicle_thinking_refine",
]
