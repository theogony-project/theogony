"""
Explorer endpoint — chat-style query + rich JSON metadata for d3 visualisation.

Runs the standard :class:`~theogony.retrieval.pipeline.QueryPipeline` and
returns a denormalised payload that the cockpit's d3 force-graph can render
without further round-trips:

- ``constellation``: nodes, edges, score, type, cluster
- ``cited_node_ids``: the answer's citations
- ``query_embedding_preview``: first ``preview_dim`` (32) coordinates of the
  **retrieval** query vector (same merge as the pipeline: last turn + optional
  prior summary/messages) — a small "vector signature" without shipping the
  full embedding to the browser
- ``timing_ms``: stage breakdown (chat prep / embed / retrieve / synthesize / total)
- ``chat``: rolling summary, ``prior_messages_kept`` (sync after compaction), token estimates
- ``retrieval``: ``seed_count``, ``final_node_count``, ``hops``, ``k``,
  ``thinking_max`` (cap on extra post-synthesis rounds), ``strategy``,
  optional ``nodes_per_hop`` (``None`` for ``fixed_depth``)
- ``entry_plan``: Chronicle entry planning metadata — ``contextual_query`` and
  ``context_question`` mirror the Gutenberg ``get_context_question`` shape
  (resolved intent, then model search strings; no anchor merge);
  ``sub_queries`` is the list after merge with the short current turn, used
  for multi-seed embedding
- ``synthesis_meta``: whether a :class:`~theogony.agents.llm.StubLLMProvider`
  produced the answer (UI can warn that prose is a placeholder)

For the SPA, :func:`stream_explorer_ask_sse` emits short **SSE** ``data:``
lines (chat compaction → embed → retrieve → synthesize, then a ``complete``
event with the same JSON shape as :func:`run_explorer_query`).
``POST /cockpit/api/ask`` remains a single JSON round-trip for agents and tests.

Payloads are passed through :func:`scrub_json_floats` so ``nan`` / ``inf`` scores
from the store never break JSON encoding (Python 3.13+ rejects them by default).
"""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.cockpit.explorer_chat import (
    parse_explorer_chat_messages,
    parse_explorer_rolling_summary,
    prepare_explorer_chat_for_synthesis,
    update_explorer_chat_history_summary,
)
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import EmbeddingProvider
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline, compose_query_for_retrieval
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesizer_factory import build_synthesizer

log = get_logger("cockpit.explorer")


def scrub_json_floats(obj: Any) -> Any:
    """Replace nan/inf floats so :func:`json.dumps` / ``JSONResponse`` never 500 (Py3.13+).

    Starlette rejects non-finite floats with ``ValueError: Out of range float values are
    not JSON compliant`` — the Explorer UI then surfaces a generic Internal Server Error.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: scrub_json_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_json_floats(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_json_floats(v) for v in obj)
    return obj


def explorer_page_context(settings: Settings, llm: LLMProvider | None) -> dict[str, Any]:
    """Jinja context for `/cockpit/explorer` — LLM mode strip at page load."""
    if llm is None:
        is_stub = True
        mid = (settings.llm.model_id or "").strip() or "—"
    else:
        is_stub = isinstance(llm, StubLLMProvider) or settings.llm.provider == "stub"
        mid = (getattr(llm, "model_id", None) or settings.llm.model_id or "").strip() or "—"
    label = f"{settings.llm.provider} · {mid}"
    return {
        "explorer_llm_stub": is_stub,
        "explorer_llm_label": label,
        "explorer_operator_worker": settings.cockpit.operator_worker_from_ui,
    }


EMBEDDING_PREVIEW_DIM = 32
ANSWER_MAX_CHARS = 4_000


@dataclass(frozen=True)
class ExplorerLimits:
    """Hard caps for one explorer call."""

    max_query_chars: int = 1_000
    min_k: int = 1
    max_k: int = 25
    min_hops: int = 0
    max_hops: int = 3
    min_thinking_max: int = 0
    max_thinking_max: int = 8


_LIMITS = ExplorerLimits()


def _build_pipeline(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter | None,
    growth_bridge: GrowthBridge | None = None,
) -> QueryPipeline:
    """Compose a QueryPipeline that mirrors mcp/server.py wiring."""
    mnemosyne = build_mnemosyne_classifier(settings, llm)
    return QueryPipeline(
        embedder=embedder,
        retriever=MultiHopRetriever(
            store,
            strategy=build_retrieval_strategy(store, settings),
        ),
        assembler=ConstellationAssembler(store),
        synthesizer=build_synthesizer(settings, llm, audit_log=audit),
        relevance=RelevanceTracker(
            store,
            relevance_delta=settings.relevance.relevance_delta,
        ),
        settings=settings,
        report_writer=report_writer,
        edge_pheromone=EdgePheromoneTracker(
            store,
            delta=settings.relevance.edge_pheromone_delta,
        ),
        stub_detector=StubDetector(settings.curiosity.stub_thresholds),
        mnemosyne=mnemosyne,
        entry_planner_llm=llm,
        growth_bridge=growth_bridge,
    )


def _resolve_llm(
    settings: Settings,
    fallback: LLMProvider | None,
) -> LLMProvider:
    """Use the real provider when configured; otherwise the stored / stub LLM."""
    try:
        return build_llm_from_settings(settings)
    except (ValueError, NotImplementedError):
        if fallback is not None:
            return fallback
        return StubLLMProvider(model_id=settings.llm.model_id or "stub-llm")


def _node_payload(constellation: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in constellation.nodes:
        out.append(
            {
                "id": n.id,
                "label": n.label,
                "node_type": n.node_type.value,
                "layer": n.layer.value,
                "confidence": float(n.confidence),
                "cluster_id": n.cluster_id,
                "source_type": getattr(n.source_ref, "source_type", None),
                "source_url": getattr(n.source_ref, "url", None),
            }
        )
    return out


def _edge_payload(constellation: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in constellation.edges:
        eid = getattr(e, "edge_id", "") or f"{e.source_id}:{e.relation_type}:{e.target_id}"
        out.append(
            {
                "id": eid,
                "source": e.source_id,
                "target": e.target_id,
                "relation_type": e.relation_type,
                "weight": float(e.weight),
                "pheromone_delta": float(getattr(e, "pheromone_delta", 0.0)),
                "confidence": float(getattr(e, "confidence", 0.0)),
            }
        )
    return out


async def run_explorer_query(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter | None,
    query: str,
    k: int,
    hops: int,
    thinking_max: int,
    conversation_summary: str | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    growth_bridge: GrowthBridge | None = None,
) -> dict[str, Any]:
    """Run one query and return a JSON-serialisable payload for d3."""
    q = (query or "").strip()
    if not q:
        return {"error": "query must be non-empty"}
    if len(q) > _LIMITS.max_query_chars:
        return {"error": f"query exceeds {_LIMITS.max_query_chars} characters"}

    k_eff = max(_LIMITS.min_k, min(_LIMITS.max_k, int(k)))
    hops_eff = max(_LIMITS.min_hops, min(_LIMITS.max_hops, int(hops)))
    thinking_eff = max(
        _LIMITS.min_thinking_max,
        min(_LIMITS.max_thinking_max, int(thinking_max)),
    )

    llm_eff = llm if llm is not None else _resolve_llm(settings, None)
    chat_block: str | None = None
    summary_out = ""
    msgs_out: list[dict[str, Any]] = []
    chat_meta: dict[str, Any] = {}
    try:
        prior = parse_explorer_chat_messages(conversation_messages)
        summary_in = parse_explorer_rolling_summary(conversation_summary)
        if prior or summary_in:
            block, summary_out, turns_out, chat_meta = await prepare_explorer_chat_for_synthesis(
                rolling_summary=summary_in,
                prior_messages=prior,
                llm=llm_eff,
            )
            chat_block = block if block.strip() else None
            msgs_out = [t.model_dump(mode="json") for t in turns_out]
        else:
            chat_meta = {
                "compacted": False,
                "summarization_ms": 0,
                "llm_summary_rounds": 0,
                "stub_dropped_turns": 0,
                "tokens_estimated_before": 0,
                "tokens_estimated_after": 0,
                "chat_prep_total_ms": 0,
            }
    except (ValueError, ValidationError) as exc:
        return {"error": str(exc)}

    pipeline = _build_pipeline(
        settings=settings,
        store=store,
        embedder=embedder,
        llm=llm_eff,
        audit=audit,
        report_writer=report_writer,
        growth_bridge=growth_bridge,
    )

    try:
        result = await pipeline.ask(
            q,
            layer=None,
            k=k_eff,
            hops=hops_eff,
            thinking_max=thinking_eff,
            synthesis_conversation_context=chat_block,
            retrieval_query_expansion=chat_block,
        )
    except Exception as exc:  # pragma: no cover - surfaced to UI
        log.exception("explorer ask failed")
        return {"error": f"pipeline failed: {exc}"}

    answer_text = (result.answer.text or "").strip()
    if len(answer_text) > ANSWER_MAX_CHARS:
        answer_text = answer_text[: ANSWER_MAX_CHARS - 3] + "..."

    entry_plan = result.entry_plan or {}
    cq_raw = entry_plan.get("context_question")
    context_questions = [str(x) for x in cq_raw] if isinstance(cq_raw, list) else []
    updated_summary, summary_meta = await update_explorer_chat_history_summary(
        rolling_summary=summary_out or summary_in,
        question=q,
        context_questions=context_questions,
        answer=answer_text,
        llm=llm_eff,
    )
    summary_out = updated_summary
    chat_meta.update(summary_meta)

    embed_preview: list[float] = []
    try:
        q_for_embed_preview = compose_query_for_retrieval(q, chat_block)
        vec = await embedder.embed(q_for_embed_preview)
        for x in vec[:EMBEDDING_PREVIEW_DIM]:
            f = float(x)
            embed_preview.append(f if math.isfinite(f) else 0.0)
    except Exception:  # pragma: no cover - non-fatal
        embed_preview = []

    cited_set = set(result.answer.cited_node_ids)
    nodes = _node_payload(result.constellation)
    for n in nodes:
        n["is_cited"] = n["id"] in cited_set

    report = result.report
    timing = {
        "embed_ms": int(report.embedding_duration_ms),
        "multi_hop_ms": int(report.multi_hop.duration_ms),
        "synthesis_ms": int(report.synthesis.latency_ms),
        "chat_prep_ms": int(chat_meta.get("chat_prep_total_ms", 0)),
        "total_ms": int(report.duration_s * 1000),
    }
    retrieval = {
        "seed_count": int(report.multi_hop.seed_count),
        "final_node_count": int(report.multi_hop.final_node_count),
        "duplicates_removed": int(report.multi_hop.duplicates_removed),
        "hops": hops_eff,
        "k": k_eff,
        "strategy": settings.retrieval.strategy,
        "nodes_per_hop": report.multi_hop.nodes_per_hop,
        "thinking_max": thinking_eff,
    }
    synth_llm = llm_eff
    is_stub = isinstance(synth_llm, StubLLMProvider) or settings.llm.provider == "stub"
    synthesis_meta: dict[str, Any] = {
        "stub_llm": is_stub,
        "mode": "offline_citations" if is_stub else "llm_prose",
        "llm_provider": settings.llm.provider,
        "llm_model_id": getattr(synth_llm, "model_id", None) or (settings.llm.model_id or ""),
    }
    out: dict[str, Any] = {
        "run_id": report.run_id,
        "query": q,
        "answer": {
            "text": answer_text,
            "cited_node_ids": list(result.answer.cited_node_ids),
        },
        "synthesis_meta": synthesis_meta,
        "verdict": report.verdict,
        "constellation": {
            "nodes": nodes,
            "edges": _edge_payload(result.constellation),
            "gaps": list(result.constellation.gaps),
        },
        "query_embedding_preview": embed_preview,
        "embedding_dim": int(settings.embedding.dim),
        "timing_ms": timing,
        "retrieval": retrieval,
        "entry_plan": result.entry_plan,
        "chat": {
            "rolling_summary": summary_out,
            "prior_messages_kept": msgs_out,
            "compacted": bool(chat_meta.get("compacted")),
            "summarization_ms": int(chat_meta.get("summarization_ms", 0)),
            "post_answer_summary_ms": int(chat_meta.get("post_answer_summary_ms", 0)),
            "post_answer_summary_used_llm": bool(
                chat_meta.get("post_answer_summary_used_llm", False)
            ),
            "post_answer_summary_model_id": str(
                chat_meta.get("post_answer_summary_model_id", "")
            ),
            "llm_summary_rounds": int(chat_meta.get("llm_summary_rounds", 0)),
            "stub_dropped_turns": int(chat_meta.get("stub_dropped_turns", 0)),
            "tokens_estimated_before": int(chat_meta.get("tokens_estimated_before", 0)),
            "tokens_estimated_after": int(chat_meta.get("tokens_estimated_after", 0)),
            "chat_prep_total_ms": int(chat_meta.get("chat_prep_total_ms", 0)),
        },
    }
    return cast(dict[str, Any], scrub_json_floats(out))


async def stream_explorer_ask_sse(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter | None,
    query: str,
    k: int,
    hops: int,
    thinking_max: int,
    conversation_summary: str | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    growth_bridge: GrowthBridge | None = None,
) -> AsyncIterator[bytes]:
    """SSE-style ``data:`` lines for the Explorer (one POST, streamed body)."""
    payload = await run_explorer_query(
        settings=settings,
        store=store,
        embedder=embedder,
        llm=llm,
        audit=audit,
        report_writer=report_writer,
        query=query,
        k=k,
        hops=hops,
        thinking_max=thinking_max,
        conversation_summary=conversation_summary,
        conversation_messages=conversation_messages,
        growth_bridge=growth_bridge,
    )
    if "error" in payload:
        yield (
            "data: "
            + json.dumps({"type": "error", "message": payload["error"]}, allow_nan=False)
            + "\n\n"
        ).encode()
        return
    timing = payload["timing_ms"]
    for phase, key in (
        ("chat_compact", "chat_prep_ms"),
        ("embed", "embed_ms"),
        ("retrieve", "multi_hop_ms"),
        ("synthesize", "synthesis_ms"),
    ):
        chunk = {"type": "phase", "phase": phase, "ms": int(timing.get(key, 0))}
        yield ("data: " + json.dumps(chunk, allow_nan=False) + "\n\n").encode()
    done = {"type": "complete", "payload": payload}
    yield ("data: " + json.dumps(done, allow_nan=False) + "\n\n").encode()
