"""
Explorer endpoint — chat-style query + rich JSON metadata for d3 visualisation.

Runs the standard :class:`~theogony.retrieval.pipeline.QueryPipeline` and
returns a denormalised payload that the cockpit's d3 force-graph can render
without further round-trips:

- ``constellation``: nodes, edges, score, type, cluster
- ``cited_node_ids``: the answer's citations
- ``query_embedding_preview``: first ``preview_dim`` (32) coordinates of the
  query vector — enough for a small "vector signature" sparkline without
  shipping the full embedding to the browser
- ``timing_ms``: stage breakdown (embed / retrieve / synthesize / total)
- ``retrieval``: ``seed_count``, ``final_node_count``, ``hops``, ``strategy``,
  optional ``nodes_per_hop`` (``None`` for ``fixed_depth``)
- ``synthesis_meta``: whether a :class:`~theogony.agents.llm.StubLLMProvider`
  produced the answer (UI can warn that prose is a placeholder)

For the SPA, :func:`stream_explorer_ask_sse` emits short **SSE** ``data:``
lines (embed → retrieve → synthesize phases, then a ``complete`` event with
the same JSON shape as :func:`run_explorer_query`). ``POST /cockpit/api/ask``
remains a single JSON round-trip for agents and tests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.mnemosyne_classifier import build_mnemosyne_classifier
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import EmbeddingProvider
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesizer_factory import build_synthesizer

log = get_logger("cockpit.explorer")

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


_LIMITS = ExplorerLimits()


def _build_pipeline(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter | None,
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
) -> dict[str, Any]:
    """Run one query and return a JSON-serialisable payload for d3."""
    q = (query or "").strip()
    if not q:
        return {"error": "query must be non-empty"}
    if len(q) > _LIMITS.max_query_chars:
        return {"error": f"query exceeds {_LIMITS.max_query_chars} characters"}

    k_eff = max(_LIMITS.min_k, min(_LIMITS.max_k, int(k)))
    hops_eff = max(_LIMITS.min_hops, min(_LIMITS.max_hops, int(hops)))

    llm_eff = llm if llm is not None else _resolve_llm(settings, None)
    pipeline = _build_pipeline(
        settings=settings,
        store=store,
        embedder=embedder,
        llm=llm_eff,
        audit=audit,
        report_writer=report_writer,
    )

    try:
        result = await pipeline.ask(q, layer=None, k=k_eff, hops=hops_eff)
    except Exception as exc:  # pragma: no cover - surfaced to UI
        log.exception("explorer ask failed")
        return {"error": f"pipeline failed: {exc}"}

    answer_text = (result.answer.text or "").strip()
    if len(answer_text) > ANSWER_MAX_CHARS:
        answer_text = answer_text[: ANSWER_MAX_CHARS - 3] + "..."

    embed_preview: list[float] = []
    try:
        vec = await embedder.embed(q)
        embed_preview = [float(x) for x in vec[:EMBEDDING_PREVIEW_DIM]]
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
    }
    synth_llm = llm_eff
    synthesis_meta: dict[str, Any] = {
        "stub_llm": isinstance(synth_llm, StubLLMProvider),
        "llm_model_id": getattr(synth_llm, "model_id", None) or (settings.llm.model_id or ""),
    }
    return {
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
    }


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
    )
    if "error" in payload:
        yield f"data: {json.dumps({'type': 'error', 'message': payload['error']})}\n\n".encode()
        return
    timing = payload["timing_ms"]
    for phase, key in (
        ("embed", "embed_ms"),
        ("retrieve", "multi_hop_ms"),
        ("synthesize", "synthesis_ms"),
    ):
        chunk = {"type": "phase", "phase": phase, "ms": int(timing.get(key, 0))}
        yield f"data: {json.dumps(chunk)}\n\n".encode()
    done = {"type": "complete", "payload": payload}
    yield f"data: {json.dumps(done)}\n\n".encode()
