"""Single-query retrieval orchestrator (Step S3).

Wires the S3 pieces into one call: a query **vector** in, a :class:`Constellation` out.

    query vector
      -> ANN seeds (vector search over consolidated nodes)
      -> diversified injection (MMR + weight-class stratification)   [S3b]
      -> [optional] frame routing (masked SpMV)                      [S3c]
      -> Spreading Activation (PPR default)                          [S3a]
      -> Constellation assembly                                      [S3c]

The orchestrator is embedder-agnostic: callers pass a query vector already in the
workspace's semantic space (the ``theogony mesh ask`` CLI does the text->vector step).
No synthesis, no LLM, no feedback write-back (three-factor RL is a later step).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import torch

from theogony.mesh.retrieval.constellation import (
    Constellation,
    ConstellationNode,
    assemble_constellation,
)
from theogony.mesh.retrieval.diversified import SeedCandidate, select_seeds
from theogony.mesh.retrieval.frame_routing import build_frame_routed_csr
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode
from theogony.mesh.storage.edges import EdgeCSR


@dataclass
class RetrievalResult:
    """Constellation plus the operational metadata a RunReport needs."""

    constellation: Constellation
    seed_node_ids: list[str]
    operator: str
    frame_routed: bool
    ann_hit_count: int
    timings_ms: dict[str, float] = field(default_factory=dict)


def _in_strength(csr: EdgeCSR) -> torch.Tensor:
    n = len(csr.node_ids)
    if n == 0 or csr.col_indices.numel() == 0:
        return torch.zeros(n, dtype=torch.float32)
    return torch.zeros(n, dtype=torch.float32).scatter_add_(
        0, csr.col_indices, csr.values.to(torch.float32)
    )


def _aligned_node_frames(runtime: MeshRuntime, csr: EdgeCSR) -> torch.Tensor:
    """Build a (N, frame_dim) tensor of node frame vectors aligned to CSR order.

    Only invoked when frame routing is requested (opt-in); on the structural seed all
    frames are zero, so the default path never pays this scan.
    """
    dim = runtime.frame_dim
    frames = torch.zeros((len(csr.node_ids), dim), dtype=torch.float32)
    for node in runtime.nodes.load_all_consolidated():
        idx = csr.id_to_index.get(str(node.id))
        if idx is not None and node.frame_vector:
            frames[idx] = torch.tensor(node.frame_vector[:dim], dtype=torch.float32)
    return frames


def _vector_only_constellation(
    runtime: MeshRuntime,
    query_vector: Sequence[float],
    hits: list[ConsolidatedNode],
    *,
    top_k: int,
    operator: str,
    query: str | None,
) -> Constellation:
    """Degenerate fallback when the mesh has no edges: rank ANN hits by cosine."""
    q = torch.tensor(list(query_vector), dtype=torch.float32)
    q = q / q.norm().clamp_min(1e-12)
    scored: list[tuple[float, ConsolidatedNode]] = []
    for h in hits:
        vec = h.semantic_vector
        if not vec:
            continue
        v = torch.tensor(vec, dtype=torch.float32)
        cos = float((v @ q / v.norm().clamp_min(1e-12)).item())
        scored.append((cos, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    nodes = []
    for cos, h in scored[:top_k]:
        qid = h.qids[0].qid if h.qids else None
        name = h.description or (h.tags[0] if h.tags else (qid or str(h.id)))
        nodes.append(
            ConstellationNode(
                node_id=str(h.id),
                name=name,
                qid=qid,
                tags=h.tags[:8],
                description=h.description,
                tier=h.consolidation_tier,
                activation=max(cos, 0.0),
                is_source_anchor=h.is_source_anchor,
            )
        )
    return Constellation(
        query=query,
        operator=operator,
        nodes=nodes,
        gaps=["no edges in mesh — vector-only retrieval (no Spreading Activation)"],
    )


def retrieve(
    runtime: MeshRuntime,
    query_vector: Sequence[float],
    *,
    operator: str = "ppr",
    top_k: int = 30,
    k_seeds: int = 8,
    ann_limit: int = 64,
    mmr_lambda: float = 0.6,
    hops: int = 3,
    damping: float = 0.5,
    ppr_alpha: float = 0.15,
    ppr_iters: int = 12,
    query_frame: Sequence[float] | None = None,
    frame_threshold: float = 0.0,
    vector_column: str = "semantic_vector",
    query: str | None = None,
    csr: EdgeCSR | None = None,
    propagator: Propagator | None = None,
) -> RetrievalResult:
    """Run one diversified-injection + Spreading-Activation query; return a Constellation.

    ``csr`` / ``propagator`` may be supplied pre-built (and cached by the caller) to skip
    the per-query CSR rebuild — the dominant cost at scale (PHX-1041). When omitted they
    are built from ``runtime``. A supplied ``propagator`` is ignored when frame routing is
    active (the routed adjacency requires a fresh one).
    """
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    if csr is None:
        csr = runtime.rebuild_csr()
    timings["csr_ms"] = (time.perf_counter() - t0) * 1000.0
    n = len(csr.node_ids)

    t1 = time.perf_counter()
    hits = runtime.nodes.search_consolidated_by_vector(
        list(query_vector), vector_column_name=vector_column, limit=ann_limit
    )
    timings["ann_ms"] = (time.perf_counter() - t1) * 1000.0

    if n == 0:
        constellation = _vector_only_constellation(
            runtime, query_vector, hits, top_k=top_k, operator=operator, query=query
        )
        return RetrievalResult(
            constellation=constellation,
            seed_node_ids=[],
            operator=operator,
            frame_routed=False,
            ann_hit_count=len(hits),
            timings_ms=timings,
        )

    strength = _in_strength(csr)
    candidates: list[SeedCandidate] = []
    for h in hits:
        node_id = str(h.id)
        idx = csr.id_to_index.get(node_id)
        if idx is None:
            continue
        vec = h.description_vector if vector_column == "description_vector" else None
        if not vec:
            vec = h.semantic_vector
        if not vec:
            continue
        candidates.append(
            SeedCandidate(
                index=idx,
                node_id=node_id,
                vector=vec,
                potential=float(strength[idx].item()),
                qid=h.qids[0].qid if h.qids else None,
            )
        )
    seeds = select_seeds(list(query_vector), candidates, k=k_seeds, lambda_=mmr_lambda)

    active_csr = csr
    frame_routed = False
    if query_frame is not None and any(abs(float(x)) > 0.0 for x in query_frame):
        node_frames = _aligned_node_frames(runtime, csr)
        active_csr = build_frame_routed_csr(
            csr, node_frames, query_frame, threshold=frame_threshold
        )
        frame_routed = True
        propagator = Propagator(active_csr)

    if propagator is None:
        propagator = Propagator(active_csr)

    t2 = time.perf_counter()
    activation = propagator.propagate(
        seeds,
        operator=operator,
        hops=hops,
        damping=damping,
        ppr_alpha=ppr_alpha,
        ppr_iters=ppr_iters,
    )
    timings["propagate_ms"] = (time.perf_counter() - t2) * 1000.0

    t3 = time.perf_counter()
    constellation = assemble_constellation(
        runtime,
        activation,
        csr,
        top_k=top_k,
        seed_indices=set(seeds),
        operator=operator,
        query=query,
        frame_routed=frame_routed,
    )
    timings["assemble_ms"] = (time.perf_counter() - t3) * 1000.0

    return RetrievalResult(
        constellation=constellation,
        seed_node_ids=[csr.node_ids[i] for i in seeds if 0 <= i < n],
        operator=operator,
        frame_routed=frame_routed,
        ann_hit_count=len(hits),
        timings_ms=timings,
    )
