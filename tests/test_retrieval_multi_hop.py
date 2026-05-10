"""Tests for ``SpreadingActivationRetriever`` (spreading-activation retrieval).

The historical module name ``test_retrieval_multi_hop`` is kept so CI
invocations remain stable; retrieval output still uses
:class:`~theogony.retrieval.multi_hop.MultiHopResult` for reports.
"""

from __future__ import annotations

import pytest

from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.retrieval.spreading_activation_retrieval import SpreadingActivationRetriever
from theogony.stores.memory import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="test", location=loc, language="en")


class _TinyEmbedder:
    @property
    def model_id(self) -> str:
        return "test-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.mark.asyncio
async def test_empty_store_returns_empty_result() -> None:
    store = InMemoryKnowledgeStore()
    r = SpreadingActivationRetriever(store, _TinyEmbedder())
    out = await r.retrieve([1.0, 0.0, 0.0, 0.0], k=5, hops=2)
    assert isinstance(out, MultiHopResult)
    assert out.scored_nodes == []


@pytest.mark.asyncio
async def test_rejects_non_positive_k() -> None:
    store = InMemoryKnowledgeStore()
    r = SpreadingActivationRetriever(store, _TinyEmbedder())
    with pytest.raises(ValueError, match="k must be positive"):
        await r.retrieve([0.0, 0.0, 0.0, 0.0], k=0)


@pytest.mark.asyncio
async def test_returns_scored_nodes_from_spreading() -> None:
    store = InMemoryKnowledgeStore()
    a = KnowledgeNode(
        label="A",
        node_type=NodeType.CONCEPT,
        source_ref=_src("a"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test@v1",
    )
    b = KnowledgeNode(
        label="B",
        node_type=NodeType.CONCEPT,
        source_ref=_src("b"),
        embedding=[0.9, 0.1, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="test@v1",
    )
    await store.batch_upsert_nodes([a, b])
    await store.batch_upsert_edges(
        [KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO")]
    )
    r = SpreadingActivationRetriever(store, _TinyEmbedder())
    out = await r.retrieve([1.0, 0.0, 0.0, 0.0], k=5, hops=2, min_weight=0.01)
    assert len(out.scored_nodes) >= 1
    labels = {s.node.label for s in out.scored_nodes}
    assert "A" in labels
    assert out.duration_ms >= 0


@pytest.mark.asyncio
async def test_rejects_unsupported_store_type() -> None:
    class _OtherStore:
        pass

    r = SpreadingActivationRetriever(_OtherStore(), _TinyEmbedder())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="SpreadingActivationRetriever requires"):
        await r.retrieve([1.0, 0.0, 0.0, 0.0])
