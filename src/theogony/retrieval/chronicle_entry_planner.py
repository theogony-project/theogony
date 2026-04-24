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

_RETRIEVAL_CONTEXT_MARKER = "\n---\nCurrent question:\n"

_PLANNER_SYSTEM = """You plan vector-graph retrieval for the Pantheon Chronik.

The input may be a single user turn, OR a long block: rolling summary / prior user &
assistant turns, then "---" and "Current question:" with the latest user turn
(Explorer chat). Treat **the entire block** as evidence of intent — not only the
last line.

Infer from the **whole thread**: themes already opened, entities and proper names
on both sides, technical terms the user adopted, implicit constraints, whether the
user is deepening a topic or changing angle. Turn that understanding into **several
distinct search_queries** (short phrases, ideally several when any prior context
exists) so vector search gets **multiple independent hooks** into the graph: core
concepts, named things, adjacent subtopics, alternate phrasings, and Chronicle-
specific vocabulary where relevant.

Each string is embedded alone — avoid near-duplicates, avoid one long vague
sentence; prefer concrete anchors a dense knowledge base would index under.

The Chronik is self-referential (Theogony docs, prompts, architecture); when the
thread is about the system itself, include seeds that hit that meta-corpus too."""


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


def anchor_turn_for_subqueries(user_query: str, *, max_chars: int) -> str:
    """The short latest user line for seeds — not the full retrieval blend (can be 10k+ chars)."""
    u = (user_query or "").strip()
    if not u:
        return ""
    if _RETRIEVAL_CONTEXT_MARKER in u:
        tail = u.split(_RETRIEVAL_CONTEXT_MARKER, 1)[-1].strip()
        if tail:
            u = tail
    if len(u) > max_chars:
        return u[: max_chars - 1].rstrip() + "…"
    return u


def normalize_sub_queries(
    raw: list[str],
    *,
    user_query: str,
    limits: ChronicleEntryPlannerSettings,
) -> list[str]:
    """Trim, cap length, dedupe (case-fold), cap count, ensure non-empty."""
    uq = user_query.strip()
    anchor = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
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
        return [anchor] if anchor else ["theogony chronicle"]
    # Keep model-chosen keywords first in the list; append the short current turn if
    # there is room (never insert the full multi-turn blend — that broke follow-ups).
    if anchor and anchor.casefold() not in {x.casefold() for x in out} and len(out) < max_n:
        out.append(anchor)
    elif anchor and anchor.casefold() not in {x.casefold() for x in out}:
        out.insert(0, anchor)
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
    # PHX-0051: merged multi-seed runs cannot truthfully combine per-hop lists.
    # A single partial result still carries the strategy's hop visibility unchanged.
    hop_meta: list[int] | None = None
    if len(results) == 1:
        hop_meta = results[0].nodes_per_hop
    return MultiHopResult(
        scored_nodes=merged,
        seed_count=min(total_seeds, len(merged)),
        nodes_per_hop=hop_meta,
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
        a = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
        return ChronicleEntryPlan([a] if a else ["theogony chronicle"], "", False)

    follow = _RETRIEVAL_CONTEXT_MARKER in uq
    prompt = (
        f"Retrieval planning input:\n{uq}\n\n"
        + (
            "The block above is the **full retrieval context** (summary + dialogue + "
            "final 'Current question:'). Design search_queries using **everything** in "
            "it that could matter for recall — not paraphrasing the last sentence alone.\n\n"
            if follow
            else ""
        )
        + "Respond with JSON only matching the schema: search_queries (1–8 strings) "
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
        a = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
        return ChronicleEntryPlan([a] if a else ["theogony chronicle"], "", False)
    except Exception as exc:  # pragma: no cover - network / vendor
        log.warning("chronicle entry planner LLM failed: %s", exc)
        a = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
        return ChronicleEntryPlan([a] if a else ["theogony chronicle"], "", False)

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
    "anchor_turn_for_subqueries",
    "merge_multi_hop_results",
    "normalize_sub_queries",
    "plan_chronicle_entry_queries",
]
