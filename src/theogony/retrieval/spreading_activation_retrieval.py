"""
Spreading-activation retrieval (TARGET_ARCHITECTURE.md).

Replaces multi-hop graph walks: export the store into a :class:`TensorMeshEngine`,
inject the query embedding as stimulus, map activated rows back to
:class:`~theogony.core.store.ScoredNode` for the existing constellation pipeline.
"""

from __future__ import annotations

import time
from typing import Literal

import torch

from theogony.config.logging import get_logger
from theogony.core.knowledge_to_mesh import tensor_mesh_engine_from_knowledge
from theogony.core.model import Layer
from theogony.core.store import KnowledgeStore, ScoredNode
from theogony.core.tensor_engine import TensorMeshEngine
from theogony.extraction.embedding import EmbeddingProvider
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.stores.lancedb_store import LanceDBKnowledgeStore
from theogony.stores.memory import InMemoryKnowledgeStore

log = get_logger("retrieval.spreading_activation")


class SpreadingActivationRetriever:
    """Retrieve via CSR spreading activation — no multi-hop strategy stack."""

    def __init__(
        self,
        store: KnowledgeStore,
        embedder: EmbeddingProvider,
        *,
        device: str = "cpu",
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._device = device

    @property
    def store(self) -> KnowledgeStore:
        return self._store

    async def retrieve(
        self,
        query_embedding: list[float],
        *,
        k: int = 10,
        hops: int = 2,
        min_weight: float = 0.3,
        layer: Layer | None = None,
        pheromone_mode: Literal["follow", "ignore", "invert"] = "follow",
    ) -> MultiHopResult:
        t0 = time.perf_counter()
        if pheromone_mode != "follow":
            log.debug(
                "spreading: pheromone_mode=%s not applied in tensor layer (store-level only)",
                pheromone_mode,
            )
        if k <= 0:
            raise ValueError(f"k must be positive; got {k}")
        max_hops = max(1, min(int(hops), 8))
        stim = torch.tensor(query_embedding, dtype=torch.float32, device=self._device)

        id_by_row: list[str] = []
        engine: TensorMeshEngine

        if isinstance(self._store, InMemoryKnowledgeStore):
            nodes, edges = await self._store.export_graph_for_spreading()
            if not nodes:
                return MultiHopResult(duration_ms=int((time.perf_counter() - t0) * 1000))
            node_copies = [n.model_copy(deep=True) for n in nodes]
            edge_copies = [e.model_copy(deep=True) for e in edges]
            engine = await tensor_mesh_engine_from_knowledge(
                node_copies,
                edge_copies,
                self._embedder,
                device=self._device,
            )
            id_by_row = [n.id for n in node_copies]
        elif isinstance(self._store, LanceDBKnowledgeStore):
            engine = TensorMeshEngine(device=self._device)
            self._store.load_into_tensor_engine(engine)
            row_ids = getattr(self._store, "_mesh_row_node_ids", None) or []
            if not row_ids or engine.row_ptr is None:
                return MultiHopResult(duration_ms=int((time.perf_counter() - t0) * 1000))
            id_by_row = row_ids
        else:
            raise TypeError(
                "SpreadingActivationRetriever requires InMemoryKnowledgeStore or "
                f"LanceDBKnowledgeStore; got {type(self._store).__name__}"
            )

        idx, energy = engine.spreading_activation(
            stim,
            max_hops=max_hops,
            top_k_seeds=min(k, 64),
        )
        emax = float(energy.max()) if energy.numel() else 0.0

        scored: list[ScoredNode] = []
        for j in range(int(idx.shape[0])):
            if len(scored) >= k:
                break
            row_i = int(idx[j].item())
            e = float(energy[j].item())
            if row_i < 0 or row_i >= len(id_by_row):
                continue
            nid = id_by_row[row_i]
            node = await self._store.get_node(nid)
            if node is None:
                continue
            if layer is not None and node.layer != layer:
                continue
            norm_score = e / emax if emax > 1e-12 else 0.0
            if norm_score < min_weight:
                continue
            scored.append(ScoredNode(node=node, score=min(1.0, max(-1.0, norm_score))))

        duration_ms = int((time.perf_counter() - t0) * 1000)
        log.debug(
            "spreading k=%d hops=%d min_weight=%.2f layer=%s -> %d nodes in %d ms",
            k,
            hops,
            min_weight,
            layer.value if layer is not None else "any",
            len(scored),
            duration_ms,
        )
        return MultiHopResult(
            scored_nodes=scored,
            seed_count=min(k, len(id_by_row)),
            nodes_per_hop=None,
            final_node_count=len(scored),
            duplicates_removed=0,
            duration_ms=duration_ms,
        )


__all__ = ["SpreadingActivationRetriever"]
