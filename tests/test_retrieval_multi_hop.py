"""
MultiHopRetriever unit tests (Plan §3.8 layer 5).

Asserts the retriever:
- delegates to ``KnowledgeStore.multi_hop_search`` with the right
  parameters (k, hops, min_weight, layer);
- emits a ``MultiHopResult`` whose fields map cleanly to
  ``MultiHopBreakdown`` (the pipeline's report writer assumes this);
- enforces the input-validation invariants (k>0, hops>=0, min_weight in [0,1]);
- pins Plan §4.2 defaults (k=10, hops=2) when the caller omits them.

A small in-memory fake store is used rather than ``InMemoryKnowledgeStore``
because the test is about *what the retriever passes through* — a fake
that records its arguments is more direct than building real fixture
nodes that happen to retrieve in a given order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

import pytest

from tests.conftest import make_node
from theogony.core.model import (
    Constellation,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    ScoreUpdate,
)
from theogony.core.store import Path, ScoredNode
from theogony.retrieval.multi_hop import MultiHopResult, MultiHopRetriever


class _RecordingStore:
    """Minimal KnowledgeStore stub that records every multi_hop call.

    Only ``multi_hop_search`` does anything meaningful; the other
    Protocol methods raise so any accidental coupling surfaces
    immediately in tests.
    """

    def __init__(self, scored_nodes: list[ScoredNode] | None = None) -> None:
        self._scored = scored_nodes or []
        self.calls: list[dict[str, Any]] = []

    async def multi_hop_search(
        self,
        embedding: list[float],
        k: int = 20,
        hops: int = 3,
        min_weight: float = 0.3,
        layer: Layer | None = None,
        *,
        pheromone_mode: str = "follow",
    ) -> list[ScoredNode]:
        self.calls.append(
            {
                "embedding": embedding,
                "k": k,
                "hops": hops,
                "min_weight": min_weight,
                "layer": layer,
                "pheromone_mode": pheromone_mode,
            }
        )
        return list(self._scored)

    # ----- everything below is "raise if touched" -----
    async def vector_search(self, *args: Any, **kwargs: Any) -> list[ScoredNode]:
        raise AssertionError("retriever should not call vector_search directly")

    async def traverse(self, *args: Any, **kwargs: Any) -> list[Path]:
        raise AssertionError("retriever should not call traverse directly")

    async def upsert_node(self, node: KnowledgeNode) -> str:
        raise AssertionError("retriever should not write")

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        raise AssertionError("retriever should not write")

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        raise AssertionError("retriever should not call get_node")

    async def get_neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        min_weight: float = 0.3,
        *,
        pheromone_mode: str = "follow",
    ) -> Constellation:
        raise AssertionError("retriever should not call get_neighborhood")

    async def delete_node(self, node_id: str) -> None:
        raise AssertionError("retriever should not write")

    async def promote(self, node_id: str) -> None:
        raise AssertionError("retriever should not promote")

    async def degrade(self, node_id: str) -> None:
        raise AssertionError("retriever should not degrade")

    async def update_scores(self, node_id: str, scores: dict[str, float]) -> None:
        raise AssertionError("retriever should not update scores")

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        raise AssertionError("retriever should not touch clusters")

    async def assign_cluster(
        self,
        node_id: str,
        cluster_id: str | None,
        *,
        cluster_label: str | None = None,
    ) -> None:
        raise AssertionError("retriever should not touch clusters")

    async def list_clusters(self) -> list:
        raise AssertionError("retriever should not touch clusters")

    async def get_cluster_members(self, cluster_id: str) -> AsyncIterator[str]:
        if False:  # pragma: no cover - empty async generator
            yield ""

    async def batch_upsert_nodes(self, nodes: Sequence[KnowledgeNode]) -> list[str]:
        raise AssertionError("retriever should not write")

    async def batch_upsert_edges(self, edges: Sequence[KnowledgeEdge]) -> None:
        raise AssertionError("retriever should not write")

    async def get_edges_among(
        self,
        node_ids: Sequence[str],
        min_weight: float = 0.0,
    ) -> list[KnowledgeEdge]:
        raise AssertionError("retriever should not call get_edges_among")

    async def batch_update_scores(self, updates: Sequence[ScoreUpdate]) -> None:
        raise AssertionError("retriever should not update scores")

    async def count_neighbors_in_layer(self, layer: Layer) -> dict[str, int]:
        raise AssertionError("retriever should not count neighbors")

    async def resolve_node(self, node_id: str, wikidata_id: str | None) -> bool:
        raise AssertionError("retriever should not resolve")

    def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        raise AssertionError("retriever should not export")

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        raise AssertionError("retriever should not import")

    async def list_pending_resolution(
        self, layer: Layer | None = None, limit: int = 100
    ) -> list[KnowledgeNode]:
        raise AssertionError("retriever should not touch resolution queue")

    async def count_nodes(self, layer: Layer | None = None) -> int:
        raise AssertionError("retriever should not count")

    async def health(self) -> dict[str, object]:
        raise AssertionError("retriever should not health-check")

    async def batch_bump_edges(
        self,
        edge_ids: Sequence[str],
        *,
        delta: float,
        ts: datetime,
    ) -> None:
        raise AssertionError("retriever should not bump pheromones")

    async def list_aged_pheromone_edges(
        self,
        *,
        horizon: datetime,
        epsilon: float,
    ) -> list[tuple[str, float]]:
        raise AssertionError("retriever should not list aged pheromones")

    async def batch_update_pheromone_deltas(
        self,
        updates: Sequence[tuple[str, float]],
    ) -> None:
        raise AssertionError("retriever should not batch-update pheromones")


class TestMultiHopRetrieverDelegation:
    async def test_passes_k_hops_min_weight_layer_through(self) -> None:
        store = _RecordingStore()
        retriever = MultiHopRetriever(store)
        await retriever.retrieve([0.1, 0.2, 0.3], k=5, hops=1, min_weight=0.4, layer=Layer.MNEME)
        assert len(store.calls) == 1
        call = store.calls[0]
        assert call["embedding"] == [0.1, 0.2, 0.3]
        assert call["k"] == 5
        assert call["hops"] == 1
        assert call["min_weight"] == 0.4
        assert call["layer"] is Layer.MNEME
        assert call["pheromone_mode"] == "follow"

    async def test_pins_plan_defaults(self) -> None:
        store = _RecordingStore()
        retriever = MultiHopRetriever(store)
        await retriever.retrieve([0.1, 0.2])
        call = store.calls[0]
        # Plan §4.2 retrieval defaults.
        assert call["k"] == 10
        assert call["hops"] == 2
        # Plan §2.6 floor.
        assert call["min_weight"] == 0.3
        assert call["layer"] is None
        assert call["pheromone_mode"] == "follow"

    async def test_passes_pheromone_mode_through(self) -> None:
        store = _RecordingStore()
        retriever = MultiHopRetriever(store)
        await retriever.retrieve([0.1], pheromone_mode="invert")
        assert store.calls[0]["pheromone_mode"] == "invert"


class TestMultiHopRetrieverResult:
    async def test_returns_multi_hop_result_with_scored_nodes(self) -> None:
        nodes = [
            ScoredNode(node=make_node("A"), score=0.92),
            ScoredNode(node=make_node("B"), score=0.81),
        ]
        store = _RecordingStore(scored_nodes=nodes)
        retriever = MultiHopRetriever(store)
        result = await retriever.retrieve([0.0, 1.0], k=10)
        assert isinstance(result, MultiHopResult)
        assert [s.node.label for s in result.scored_nodes] == ["A", "B"]

    async def test_seed_count_caps_at_returned_count_when_below_k(self) -> None:
        nodes = [ScoredNode(node=make_node(f"N{i}"), score=0.5) for i in range(3)]
        store = _RecordingStore(scored_nodes=nodes)
        retriever = MultiHopRetriever(store)
        result = await retriever.retrieve([0.0, 1.0], k=10)
        # min(k, len(scored)): we asked for 10 but the store returned 3.
        assert result.seed_count == 3

    async def test_seed_count_caps_at_k_when_returned_count_exceeds_k(self) -> None:
        nodes = [ScoredNode(node=make_node(f"N{i}"), score=0.5) for i in range(15)]
        store = _RecordingStore(scored_nodes=nodes)
        retriever = MultiHopRetriever(store)
        result = await retriever.retrieve([0.0, 1.0], k=10)
        # The store returned 15 (its expansion picked up extras), but the
        # initial seed count is bounded by k.
        assert result.seed_count == 10
        # PHX-0051: per-hop visibility is None (store does not expose it),
        # final_node_count is the truthful number.
        assert result.nodes_per_hop is None
        assert result.final_node_count == 15

    async def test_phx_0051_retriever_signals_no_per_hop_visibility(self) -> None:
        # PHX-0051 (Option A): the retriever does NOT fabricate a
        # synthetic ``nodes_per_hop`` list. It signals "store does
        # not expose per-hop visibility" by leaving the field None
        # and writes the truthful deduped count to final_node_count.
        nodes = [ScoredNode(node=make_node(f"M{i}"), score=0.5) for i in range(5)]
        store = _RecordingStore(scored_nodes=nodes)
        retriever = MultiHopRetriever(store)
        result = await retriever.retrieve([1.0, 0.0], k=10)
        assert result.nodes_per_hop is None
        assert result.final_node_count == 5

    async def test_duration_ms_is_non_negative(self) -> None:
        store = _RecordingStore()
        retriever = MultiHopRetriever(store)
        result = await retriever.retrieve([0.0])
        assert result.duration_ms >= 0


class TestMultiHopRetrieverValidation:
    async def test_rejects_non_positive_k(self) -> None:
        retriever = MultiHopRetriever(_RecordingStore())
        with pytest.raises(ValueError, match="k must be positive"):
            await retriever.retrieve([0.0], k=0)
        with pytest.raises(ValueError, match="k must be positive"):
            await retriever.retrieve([0.0], k=-1)

    async def test_rejects_negative_hops(self) -> None:
        retriever = MultiHopRetriever(_RecordingStore())
        with pytest.raises(ValueError, match="hops must be non-negative"):
            await retriever.retrieve([0.0], hops=-1)

    async def test_rejects_min_weight_outside_unit_interval(self) -> None:
        retriever = MultiHopRetriever(_RecordingStore())
        with pytest.raises(ValueError, match="min_weight must be in"):
            await retriever.retrieve([0.0], min_weight=-0.1)
        with pytest.raises(ValueError, match="min_weight must be in"):
            await retriever.retrieve([0.0], min_weight=1.5)
