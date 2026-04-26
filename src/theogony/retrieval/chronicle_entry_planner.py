"""
LLM-backed planning of vector-search entry points for the Chronik (Explorer / ask).

When enabled, the model proposes several short ``search_queries``. Each is merged
with optional Explorer/CLI retrieval expansion (dialogue) before embedding;
retrievals are merged by best cosine score per node instead of using only a
single turn once.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import ChronicleEntryPlannerSettings
from theogony.core.store import ScoredNode
from theogony.retrieval.multi_hop import MultiHopResult

log = get_logger("retrieval.chronicle_entry_planner")

_RETRIEVAL_CONTEXT_MARKER = "\n---\nCurrent question:\n"

# Prompt shape aligns with demoGraphics Gutenberg ``get_context_question`` (see
# ``gutenbergApp/resources/text_resources.py``: vector-search task, "imagine" what
# relevant passages look like, standalone strings for a retriever that does not
# see chat, follow-up vs fresh question, short phrases / JSON array discipline).
_PLANNER_SYSTEM = """You plan vector-graph retrieval for the Pantheon Chronik. This
is the same *role* as a dedicated "context question" step before similarity search
in a RAG app: you output a resolved intent, then a small set of **vector hooks**.

**Task (cf. Gutenberg / Pinecone-style retrieval):** From the user input, produce
(1) one standalone ``contextual_query`` and (2) several short ``search_queries`` —
keywords, short phrases, or very short sentences — suitable for **embedding and
cosine similarity** against a graph-backed chronicle. The strings should be the kind
of wording that, if it appeared in a real node or passage, would *match* the user's
need. Imagine what relevant chronicle text might look like; choose search strings
that would land near those vectors.

**No chat in the retriever:** Each string is embedded on its own path. If the last
turn is vague or deictic ("what does that mean?", "be more specific", "and that?"),
you **must** resolve it using the full block (summary + dialogue + "Current
question:"), not by parroting the last line.

**Follow-up vs new topic:** If the turn is clearly a **follow-up** to the thread,
use prior turns to disambiguate. If it is a **new, self-contained** question, do
not spuriously bind it to old topics.

**Chronik content:** The corpus is self-referential (Theogony docs, architecture,
prompts). When the thread is *about* the system, include seeds for that meta-layer.

**Do not** emit deictic or meta-only hooks as the *only* content ("concrete
examples", "more detail", "what exactly") — always name the *thing* the user
means after resolution.

Keep each ``search_query`` short; the server enforces a per-phrase length cap.
Output JSON only, as requested in the user message."""


class _PlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contextual_query: str = ""
    search_queries: list[str] = Field(min_length=1)
    rationale: str = ""


ENTRY_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "search_queries": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 8,
        },
        "contextual_query": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["search_queries"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ChronicleEntryPlan:
    """Normalized sub-queries for retrieval.

    ``search_queries`` is the list used for multi-seed embedding (after
    :func:`normalize_sub_queries` on **model** ``search_queries`` only, plus
    optional anchor — same separation as Gutenberg: ``contextual_query`` is not
    a Pinecone-style vector hook; only the array strings are.

    ``contextual_query`` and ``context_question`` mirror the Gutenberg flow:
    * standalone resolved intent, then
    * vector search strings from the model **without** anchor injection — same
    roles as ``get_context_question`` in ``demoGraphics/gutenbergApp`` (Cockpit JSON).
    """

    search_queries: list[str]
    rationale: str
    used_llm: bool
    contextual_query: str = ""
    context_question: tuple[str, ...] = ()
    #: Filled when ``used_llm``; ``LLMResult.model_id`` (proves which model ran).
    planner_model_id: str = ""


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


def normalize_context_question_list(
    raw: list[str],
    *,
    limits: ChronicleEntryPlannerSettings,
) -> list[str]:
    """Trim, dedupe, cap; no anchor append — Gutenberg ``context_question`` array role."""
    out: list[str] = []
    seen: set[str] = set()
    max_c = limits.max_chars_per_sub_query
    max_n = limits.max_sub_queries
    for s in raw:
        t = (s or "").strip()
        if not t:
            continue
        if len(t) > max_c:
            t = t[: max_c - 1].rstrip() + "…"
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_n:
            break
    return out


def _clip_planner_str(s: str, *, max_chars: int) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    if len(t) > max_chars:
        return t[: max_chars - 1].rstrip() + "…"
    return t


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
        return ChronicleEntryPlan(
            [""], "", False, contextual_query="", context_question=("",), planner_model_id=""
        )
    if isinstance(llm, StubLLMProvider) or not limits.enabled:
        a = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
        seeds = [a] if a else ["theogony chronicle"]
        return ChronicleEntryPlan(
            seeds,
            "",
            False,
            contextual_query=a,
            context_question=tuple(seeds),
            planner_model_id="",
        )

    follow = _RETRIEVAL_CONTEXT_MARKER in uq
    prompt = (
        "### RETRIEVAL PLANNING INPUT START ###\n"
        f"{uq}\n"
        "### RETRIEVAL PLANNING INPUT END ###\n\n"
        + (
            "The block above is the **full retrieval context** (rolling summary, prior "
            "turns, then 'Current question:'). Per the system instructions: resolve "
            "the current line into a standalone ``contextual_query`` using the thread, "
            "then derive ``search_queries`` from that intent. Do not paraphrase only the "
            "last sentence.\n\n"
            if follow
            else ""
        )
        + "Respond with JSON only matching the schema: ``contextual_query`` (standalone "
        "resolved retrieval intent), ``search_queries`` (1–8 standalone strings), and "
        "optional ``rationale`` (one short sentence)."
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
        seeds = [a] if a else ["theogony chronicle"]
        return ChronicleEntryPlan(
            seeds,
            "",
            False,
            contextual_query=a,
            context_question=tuple(seeds),
            planner_model_id="",
        )
    except Exception as exc:  # pragma: no cover - network / vendor
        log.warning("chronicle entry planner LLM failed: %s", exc)
        a = anchor_turn_for_subqueries(uq, max_chars=limits.max_chars_per_sub_query)
        seeds = [a] if a else ["theogony chronicle"]
        return ChronicleEntryPlan(
            seeds,
            "",
            False,
            contextual_query=a,
            context_question=tuple(seeds),
            planner_model_id="",
        )

    max_c = limits.max_chars_per_sub_query
    cq = _clip_planner_str(payload.contextual_query, max_chars=max_c)
    if not cq:
        cq = _clip_planner_str(
            anchor_turn_for_subqueries(uq, max_chars=max_c),
            max_chars=max_c,
        )
    cqn = tuple(normalize_context_question_list(list(payload.search_queries), limits=limits))
    if not cqn:
        cqn = (cq,) if cq else ("theogony chronicle",)

    # Gutenberg ``get_answer`` / ``_build_search_queries``: vector passes use the
    # context_question array only; the raw user line is handled separately. Do not
    # prepend ``contextual_query`` into embedding seeds (it duplicated the intent
    # in Cockpit and displaced real search hooks).
    normalized = normalize_sub_queries(
        list(payload.search_queries),
        user_query=uq,
        limits=limits,
    )
    resolved_model = (result.model_id or "").strip() or llm.model_id
    log.info(
        "chronicle entry planner ok model_id=%s context_question_count=%d",
        resolved_model,
        len(cqn),
    )
    return ChronicleEntryPlan(
        search_queries=normalized,
        rationale=(payload.rationale or "").strip()[:800],
        used_llm=True,
        contextual_query=cq,
        context_question=cqn,
        planner_model_id=resolved_model,
    )


__all__ = [
    "ENTRY_PLAN_JSON_SCHEMA",
    "ChronicleEntryPlan",
    "anchor_turn_for_subqueries",
    "merge_multi_hop_results",
    "normalize_sub_queries",
    "plan_chronicle_entry_queries",
]
