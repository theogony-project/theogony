"""Mesh-backed Explorer service for the Cockpit (S4 preview, strangler-fig).

A read-only bridge that lets the existing Explorer UI render the **new MESH substrate**
(`src/theogony/mesh/`) instead of the Gen-1 Chronicle, without touching the Gen-1 path.
It maps a mesh :class:`~theogony.mesh.retrieval.constellation.Constellation` onto the exact
JSON shape the d3 force-graph already consumes (`constellation.nodes/edges`, `retrieval`,
`timing_ms`, `synthesis_meta`, …), so the frontend needs only a backend toggle.

Performance: the per-query CSR rebuild is the dominant cost at scale (PHX-1041, ~26 s on
the 100k subnet). This service builds the CSR + Propagator **once, lazily, on first query**
and caches them, so only the first mesh query pays the rebuild; the rest are ~sub-second.
Embedding the query and the one-time index build run in worker threads to keep the event
loop responsive.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from theogony.cockpit.explorer import scrub_json_floats
from theogony.config.logging import get_logger
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.retrieval.retrieve import RetrievalResult, retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m import build_embedder
from theogony.mesh.seeds.wikidata5m.embedder import MeshEmbedder
from theogony.mesh.storage.edges import EdgeCSR
from theogony.reporting.models import MeshQueryRunReport

log = get_logger("cockpit.mesh_explorer")

_EMBED_PREVIEW_DIM = 32


@dataclass
class MeshAskOutcome:
    payload: dict[str, Any]
    report: MeshQueryRunReport


def _verdict(result: RetrievalResult) -> tuple[str, str]:
    c = result.constellation
    if not c.nodes:
        return "poor", "no nodes activated"
    if not c.edges:
        return "partial", "nodes activated but no edges in working set"
    if not c.source_anchor_ids:
        return "partial", "no source-anchored provenance reached"
    return "good", "connected, provenance-anchored working set"


class MeshExplorerService:
    """Opens a mesh workspace and answers Explorer queries against it (cached CSR)."""

    def __init__(
        self,
        root: Path,
        *,
        embedder_name: str | None = None,
        embedder: MeshEmbedder | None = None,
    ) -> None:
        self.root = root
        self._embedder_name = embedder_name
        self._runtime: MeshRuntime | None = None
        self._csr: EdgeCSR | None = None
        self._propagator: Propagator | None = None
        # A pre-supplied embedder (e.g. for tests / non-default dims) skips auto-selection.
        self._embedder: MeshEmbedder | None = embedder
        self._index_lock = asyncio.Lock()
        self._embed_lock = asyncio.Lock()
        self.index_build_ms = 0

    def runtime(self) -> MeshRuntime:
        if self._runtime is None:
            self._runtime = MeshRuntime.open(self.root)
        return self._runtime

    def status(self) -> dict[str, Any]:
        rt = self.runtime()
        return {
            "root": str(self.root),
            "consolidated_nodes": rt.nodes.consolidated_count(),
            "mesh_edges": rt.edges.count_rows(),
            "semantic_dim": rt.semantic_dim,
            "index_built": self._propagator is not None,
            "index_build_ms": self.index_build_ms,
            "embedder_loaded": self._embedder is not None,
        }

    def has_data(self) -> bool:
        try:
            return self.runtime().edges.count_rows() > 0
        except Exception:  # noqa: BLE001 - a missing/corrupt workspace just disables the tab
            log.warning("mesh explorer: cannot open workspace at %s", self.root, exc_info=True)
            return False

    async def _embedder_for(self) -> MeshEmbedder:
        async with self._embed_lock:
            if self._embedder is not None:
                return self._embedder
            target = self.runtime().semantic_dim
            names = [self._embedder_name] if self._embedder_name else ["bge-m3", "bge-small-en"]
            for name in names:
                embedder = build_embedder(name)
                await embedder.embed_many(["mesh explorer probe"], batch_size=1)
                if embedder.dim == target:
                    self._embedder = embedder
                    return embedder
            raise ValueError(
                f"no embedder matches workspace semantic_dim={target}; "
                "set THEOGONY_COCKPIT__MESH_EMBEDDER"
            )

    async def embed(self, query: str) -> list[float]:
        embedder = await self._embedder_for()
        return (await embedder.embed_many([query], batch_size=1))[0]

    async def ensure_index(self) -> int:
        """Build + cache the CSR and Propagator once. Returns the one-time build ms (else 0)."""
        async with self._index_lock:
            if self._propagator is not None:
                return 0
            rt = self.runtime()
            t = time.perf_counter()
            csr = await asyncio.to_thread(rt.rebuild_csr)
            propagator = await asyncio.to_thread(Propagator, csr)
            self._csr = csr
            self._propagator = propagator
            self.index_build_ms = int((time.perf_counter() - t) * 1000.0)
            log.info(
                "mesh explorer: built activation index (%d nodes) in %d ms",
                len(csr.node_ids),
                self.index_build_ms,
            )
            return self.index_build_ms

    def _run_retrieval(
        self, query_vector: list[float], *, top_k: int, k_seeds: int, operator: str, query: str
    ) -> RetrievalResult:
        return retrieve(
            self.runtime(),
            query_vector,
            operator=operator,
            top_k=top_k,
            k_seeds=k_seeds,
            query=query,
            csr=self._csr,
            propagator=self._propagator,
        )

    def _payload(
        self,
        *,
        query: str,
        query_vector: list[float],
        result: RetrievalResult,
        run_id: str,
        verdict: str,
        embed_ms: int,
        index_ms: int,
    ) -> dict[str, Any]:
        c = result.constellation
        max_act = max((n.activation for n in c.nodes), default=1.0) or 1.0
        seed_ids = set(result.seed_node_ids)
        nodes: list[dict[str, Any]] = []
        for n in c.nodes:
            if n.is_source_anchor:
                node_type = "anchor"
            elif n.is_candidate:
                node_type = "candidate"
            else:
                node_type = "entity"
            nodes.append(
                {
                    "id": n.node_id,
                    "label": n.name,
                    "node_type": node_type,
                    "layer": f"tier_{n.tier}",
                    "confidence": min(1.0, n.activation / max_act),
                    "cluster_id": None,
                    "source_type": "wikidata" if n.qid else None,
                    "source_url": (f"https://www.wikidata.org/wiki/{n.qid}" if n.qid else None),
                    "is_cited": n.node_id in seed_ids,
                    "qid": n.qid,
                    "tier": n.tier,
                    "activation": n.activation,
                }
            )
        edges = [
            {
                "id": f"{e.source_id}:{e.relation_descriptor or '~'}:{e.target_id}",
                "source": e.source_id,
                "target": e.target_id,
                "relation_type": e.relation_descriptor or "related",
                "weight": e.weight,
                "confidence": e.weight,
                "pheromone_delta": 0.0,
            }
            for e in c.edges
        ]
        top = ", ".join(n.name for n in c.nodes[:5])
        answer = (
            f"Mesh working set ({result.operator}): {len(c.nodes)} nodes, "
            f"{len(c.edges)} edges. Top: {top}."
        )
        if c.gaps:
            answer += " Gaps: " + "; ".join(c.gaps) + "."
        timings = result.timings_ms
        out: dict[str, Any] = {
            "run_id": run_id,
            "query": query,
            "answer": {"text": answer, "cited_node_ids": list(result.seed_node_ids)},
            "synthesis_meta": {
                "stub_llm": True,
                "mode": "mesh_constellation",
                "llm_provider": "mesh",
                "llm_model_id": getattr(self._embedder, "model_id", "mesh"),
            },
            "verdict": verdict,
            "constellation": {
                "nodes": nodes,
                "edges": edges,
                "gaps": list(c.gaps),
            },
            "query_embedding_preview": [float(x) for x in query_vector[:_EMBED_PREVIEW_DIM]],
            "embedding_dim": self.runtime().semantic_dim,
            "timing_ms": {
                "embed_ms": embed_ms,
                "multi_hop_ms": int(timings.get("propagate_ms", 0.0)),
                "synthesis_ms": int(timings.get("assemble_ms", 0.0)),
                "chat_prep_ms": index_ms,
                "total_ms": embed_ms
                + index_ms
                + int(timings.get("propagate_ms", 0.0))
                + int(timings.get("assemble_ms", 0.0))
                + int(timings.get("ann_ms", 0.0)),
            },
            "retrieval": {
                "seed_count": len(seed_ids),
                "final_node_count": len(c.nodes),
                "duplicates_removed": 0,
                "hops": 0,
                "k": len(c.nodes),
                "strategy": f"mesh:{result.operator}",
                "nodes_per_hop": None,
                "thinking_max": 0,
            },
            "entry_plan": None,
            "chat": {
                "rolling_summary": "",
                "prior_messages_kept": [],
                "compacted": False,
                "summarization_ms": 0,
                "llm_summary_rounds": 0,
                "stub_dropped_turns": 0,
                "tokens_estimated_before": 0,
                "tokens_estimated_after": 0,
                "chat_prep_total_ms": 0,
            },
        }
        return cast(dict[str, Any], scrub_json_floats(out))

    async def ask(
        self, query: str, *, top_k: int = 30, k_seeds: int = 8, operator: str = "ppr"
    ) -> MeshAskOutcome:
        started_at = datetime.now(UTC)
        t = time.perf_counter()
        query_vector = await self.embed(query)
        embed_ms = int((time.perf_counter() - t) * 1000.0)
        index_ms = await self.ensure_index()
        result = await asyncio.to_thread(
            self._run_retrieval,
            query_vector,
            top_k=top_k,
            k_seeds=k_seeds,
            operator=operator,
            query=query,
        )
        verdict, reasoning = _verdict(result)
        finished_at = datetime.now(UTC)
        report = MeshQueryRunReport(
            started_at=started_at,
            finished_at=finished_at,
            duration_s=(finished_at - started_at).total_seconds(),
            status="completed",
            verdict=cast(Any, verdict),
            verdict_reasoning=f"{reasoning} (cockpit mesh explorer)",
            query=query,
            query_length_chars=len(query),
            embedding_duration_ms=embed_ms,
            operator=result.operator,
            frame_routed=result.frame_routed,
            ann_hit_count=result.ann_hit_count,
            seed_count=len(result.seed_node_ids),
            seed_node_ids=result.seed_node_ids,
            constellation_node_count=len(result.constellation.nodes),
            constellation_edge_count=len(result.constellation.edges),
            source_anchor_count=len(result.constellation.source_anchor_ids),
            gaps_identified=len(result.constellation.gaps),
            csr_duration_ms=index_ms,
            ann_duration_ms=int(result.timings_ms.get("ann_ms", 0.0)),
            propagate_duration_ms=int(result.timings_ms.get("propagate_ms", 0.0)),
            assemble_duration_ms=int(result.timings_ms.get("assemble_ms", 0.0)),
            cited_node_ids=[n.node_id for n in result.constellation.nodes],
        )
        payload = self._payload(
            query=query,
            query_vector=query_vector,
            result=result,
            run_id=report.run_id,
            verdict=verdict,
            embed_ms=embed_ms,
            index_ms=index_ms,
        )
        return MeshAskOutcome(payload=payload, report=report)

    def _activation_frames(
        self, result: RetrievalResult, *, max_frames: int = 12
    ) -> dict[str, Any] | None:
        """Per-iteration activation for the constellation's working set — the
        Spreading-Activation forward pass as animation frames (founding-demo
        Beat 1). Seed weights are uniform (the exact MMR weights are not part of
        :class:`RetrievalResult`), which preserves hop order and relative spread —
        honest for visualization; ranking stays with the real retrieval result."""
        if self._propagator is None or self._csr is None:
            return None
        c = result.constellation
        if not c.nodes:
            return None
        id_to_index = self._csr.id_to_index
        seeds = {id_to_index[i]: 1.0 for i in result.seed_node_ids if i in id_to_index}
        if not seeds:
            return None
        frames = self._propagator.propagate_frames(seeds, operator=result.operator)
        if not frames:
            return None
        frames = frames[:max_frames]
        indexed = [(n.node_id, id_to_index[n.node_id]) for n in c.nodes if n.node_id in id_to_index]
        peak = max((float(f.max()) for f in frames), default=1.0) or 1.0
        return {
            "type": "activation_frames",
            "operator": result.operator,
            "frames": [
                {node_id: round(float(f[idx]) / peak, 4) for node_id, idx in indexed}
                for f in frames
            ],
        }

    async def ask_streaming(
        self,
        query: str,
        *,
        top_k: int = 30,
        k_seeds: int = 8,
        operator: str = "ppr",
    ) -> AsyncIterator[dict[str, Any]]:
        """Step through embed → index → retrieve with incremental status events for SSE."""
        started_at = datetime.now(UTC)
        q = (query or "").strip()
        if not q:
            yield {"type": "error", "message": "query must be non-empty"}
            return

        yield {"type": "status", "message": "embedding query (bge-m3)…"}
        t = time.perf_counter()
        query_vector = await self.embed(query)
        embed_ms = int((time.perf_counter() - t) * 1000.0)
        yield {"type": "phase", "phase": "embed", "ms": embed_ms}

        if self._propagator is None:
            yield {
                "type": "status",
                "message": "building activation index (one-time, ~30s on 100k)…",
            }
        index_ms = await self.ensure_index()
        if index_ms > 0:
            yield {
                "type": "status",
                "message": f"activation index ready ({index_ms // 1000}s one-time build)",
            }
        yield {"type": "phase", "phase": "chat_compact", "ms": index_ms}

        yield {"type": "status", "message": "spreading activation (PPR)…"}
        result = await asyncio.to_thread(
            self._run_retrieval,
            query_vector,
            top_k=top_k,
            k_seeds=k_seeds,
            operator=operator,
            query=q,
        )
        verdict, reasoning = _verdict(result)
        finished_at = datetime.now(UTC)
        report = MeshQueryRunReport(
            started_at=started_at,
            finished_at=finished_at,
            duration_s=(finished_at - started_at).total_seconds(),
            status="completed",
            verdict=cast(Any, verdict),
            verdict_reasoning=f"{reasoning} (cockpit mesh explorer)",
            query=q,
            query_length_chars=len(q),
            embedding_duration_ms=embed_ms,
            operator=result.operator,
            frame_routed=result.frame_routed,
            ann_hit_count=result.ann_hit_count,
            seed_count=len(result.seed_node_ids),
            seed_node_ids=result.seed_node_ids,
            constellation_node_count=len(result.constellation.nodes),
            constellation_edge_count=len(result.constellation.edges),
            source_anchor_count=len(result.constellation.source_anchor_ids),
            gaps_identified=len(result.constellation.gaps),
            csr_duration_ms=index_ms,
            ann_duration_ms=int(result.timings_ms.get("ann_ms", 0.0)),
            propagate_duration_ms=int(result.timings_ms.get("propagate_ms", 0.0)),
            assemble_duration_ms=int(result.timings_ms.get("assemble_ms", 0.0)),
            cited_node_ids=[n.node_id for n in result.constellation.nodes],
        )
        payload = self._payload(
            query=q,
            query_vector=query_vector,
            result=result,
            run_id=report.run_id,
            verdict=verdict,
            embed_ms=embed_ms,
            index_ms=index_ms,
        )
        yield {
            "type": "phase",
            "phase": "retrieve",
            "ms": int(result.timings_ms.get("propagate_ms", 0.0)),
        }
        frames_event = await asyncio.to_thread(self._activation_frames, result)
        if frames_event is not None:
            yield frames_event
        yield {
            "type": "phase",
            "phase": "synthesize",
            "ms": int(result.timings_ms.get("assemble_ms", 0.0)),
        }
        yield {"type": "complete", "payload": payload, "report": report}


def _sse(chunk: dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(chunk, allow_nan=False) + "\n\n").encode()


async def stream_mesh_ask_sse(
    service: MeshExplorerService,
    *,
    query: str,
    top_k: int,
    k_seeds: int,
    operator: str,
    report_writer: Any | None = None,
) -> AsyncIterator[bytes]:
    """SSE with incremental status during embed, index build, and retrieval."""
    try:
        async for event in service.ask_streaming(
            query, top_k=top_k, k_seeds=k_seeds, operator=operator
        ):
            if event.get("type") == "complete":
                report = event.get("report")
                if report_writer is not None and report is not None:
                    with contextlib.suppress(Exception):
                        report_writer.write(report)
                yield _sse({"type": "complete", "payload": event["payload"]})
            else:
                yield _sse(event)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        log.exception("mesh explorer ask failed")
        yield _sse({"type": "error", "message": f"mesh retrieval failed: {exc}"})
