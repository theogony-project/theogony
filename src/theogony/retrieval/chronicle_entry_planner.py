"""
LLM-backed planning of vector-search entry points for the Chronik (Explorer / ask).

When enabled, the model proposes several short ``search_queries`` that are
embedded independently; retrievals are merged by best cosine score per node
instead of embedding only the raw user question once.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import ChronicleEntryPlannerSettings
from theogony.core.store import ScoredNode
from theogony.retrieval.multi_hop import MultiHopResult

log = get_logger("retrieval.chronicle_entry_planner")

_PLANNER_SYSTEM = """You plan vector-graph retrieval for the Pantheon Chronik.

Given a user question, output JSON with distinct **search_queries**: short
English strings (not full sentences) that should each be embedded and used
as a separate entry point into the knowledge graph. Prefer concrete entity
names, document titles, doctrine keywords, and complementary angles — avoid
near-duplicates.

The Chronik is self-referential (Theogony docs, prompts, architecture); bias
queries toward that corpus when the user asks about the system itself."""


class _PlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_queries: list[str] = Field(min_length=1)
    rationale: str = ""


ENTRY_PLAN_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "search_queries": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 8,
        },
        "rationale": {"type": "string"},
    },
    "required": ["search_queries"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ChronicleEntryPlan:
    """Normalized sub-queries for retrieval."""

    search_queries: list[str]
    rationale: str
    used_llm: bool


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def normalize_sub_queries(
    raw: list[str],
    *,
    user_query: str,
    limits: ChronicleEntryPlannerSettings,
) -> list[str]:
    """Trim, cap length, dedupe (case-fold), cap count, ensure non-empty."""
    uq = user_query.strip()
    out: list[str] = []
    seen: set[str] = set()
    max_c = limits.max_chars_per_sub_query
    max_n = limits.max_sub_queries
    for s in raw:
        t = (s or "").strip()
        if not t or len(t) > max_c:
            continue
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_n:
            break
    if not out:
        return [uq] if uq else ["theogony chronicle"]
    if uq and uq.casefold() not in {x.casefold() for x in out}:
        out.insert(0, uq)
        out = out[:max_n]
    return out


def merge_multi_hop_results(results: list[MultiHopResult], *, cap: int) -> MultiHopResult:
    """Union retrieved nodes; keep the best score per node id, then top-``cap``."""
    if not results:
        return MultiHopResult(
            scored_nodes=[],
            seed_count=0,
            nodes_per_hop=None,
            final_node_count=0,
            duplicates_removed=0,
            duration_ms=0,
        )
    best: dict[str, ScoredNode] = {}
    duplicates_removed = 0
    total_duration = 0
    total_seeds = 0
    for r in results:
        total_duration += r.duration_ms
        total_seeds += r.seed_count
        for sn in r.scored_nodes:
            prev = best.get(sn.node.id)
            if prev is None or sn.score > prev.score:
                if prev is not None:
                    duplicates_removed += 1
                best[sn.node.id] = sn
    merged = sorted(best.values(), key=lambda x: x.score, reverse=True)[:cap]
    return MultiHopResult(
        scored_nodes=merged,
        seed_count=min(total_seeds, len(merged)),
        nodes_per_hop=None,
        final_node_count=len(merged),
        duplicates_removed=duplicates_removed,
        duration_ms=total_duration,
    )


async def plan_chronicle_entry_queries(
    *,
    llm: LLMProvider,
    user_query: str,
    limits: ChronicleEntryPlannerSettings,
) -> ChronicleEntryPlan:
    """Ask the LLM for sub-queries, or fall back to the user question alone."""
    uq = user_query.strip()
    if not uq:
        return ChronicleEntryPlan([""], "", False)
    if isinstance(llm, StubLLMProvider) or not limits.enabled:
        return ChronicleEntryPlan([uq], "", False)

    prompt = (
        f"User question:\n{uq}\n\n"
        "Respond with JSON only matching the schema: search_queries (1–8 strings) "
        "and optional rationale (one short sentence)."
    )
    try:
        result = await llm.complete(
            prompt,
            system=_PLANNER_SYSTEM,
            json_schema=ENTRY_PLAN_JSON_SCHEMA,
            max_output_tokens=limits.max_planner_tokens,
            temperature=0.2,
            timeout_s=45.0,
        )
        payload = _PlanPayload.model_validate_json(_strip_json_fences(result.text))
    except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("chronicle entry planner parse failed: %s", exc)
        return ChronicleEntryPlan([uq], "", False)
    except Exception as exc:  # pragma: no cover - network / vendor
        log.warning("chronicle entry planner LLM failed: %s", exc)
        return ChronicleEntryPlan([uq], "", False)

    normalized = normalize_sub_queries(
        list(payload.search_queries),
        user_query=uq,
        limits=limits,
    )
    return ChronicleEntryPlan(
        search_queries=normalized,
        rationale=(payload.rationale or "").strip()[:800],
        used_llm=True,
    )


__all__ = [
    "ENTRY_PLAN_JSON_SCHEMA",
    "ChronicleEntryPlan",
    "merge_multi_hop_results",
    "normalize_sub_queries",
    "plan_chronicle_entry_queries",
]
