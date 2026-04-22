"""Tests for :class:`~theogony.clustering.cluster_index.ClusterIndex`."""

from __future__ import annotations

import pytest

from theogony.clustering.cluster_index import ClusterIndex
from theogony.core.model import ClusterSummary, KnowledgeNode, NodeType, SourceRef
from theogony.stores.memory import InMemoryKnowledgeStore


def test_cluster_index_empty_assigns_none() -> None:
    idx = ClusterIndex()
    assert idx.assign([1.0, 0.0, 0.0]) is None


def test_cluster_index_assign_picks_nearest_centroid() -> None:
    idx = ClusterIndex()
    idx.replace(
        [
            ClusterSummary(
                cluster_id="a",
                cluster_label=None,
                member_count=1,
                centroid=[1.0, 0.0, 0.0],
                dominant_node_type=None,
                dominant_source_type=None,
            ),
            ClusterSummary(
                cluster_id="b",
                cluster_label=None,
                member_count=1,
                centroid=[0.0, 1.0, 0.0],
                dominant_node_type=None,
                dominant_source_type=None,
            ),
        ]
    )
    assert idx.assign([0.99, 0.01, 0.0]) == "a"


@pytest.mark.asyncio
async def test_cluster_index_rebuild_from_store_loads_summaries() -> None:
    store = InMemoryKnowledgeStore()
    n = KnowledgeNode(
        label="x",
        source_ref=SourceRef(source_type="t", identifier="1"),
        embedding=[1.0, 0.0],
        embedding_dim=2,
        node_type=NodeType.CONCEPT,
        cluster_id="c1",
    )
    await store.upsert_node(n)
    idx = ClusterIndex()
    await idx.rebuild_from_store(store)
    assert idx.assign([1.0, 0.0]) == "c1"


def test_cluster_index_replace_atomically_swaps_state() -> None:
    idx = ClusterIndex()
    idx.replace(
        [
            ClusterSummary(
                cluster_id="old",
                cluster_label=None,
                member_count=1,
                centroid=[1.0, 0.0],
                dominant_node_type=None,
                dominant_source_type=None,
            ),
        ]
    )
    idx.replace(
        [
            ClusterSummary(
                cluster_id="new",
                cluster_label=None,
                member_count=1,
                centroid=[0.0, 1.0],
                dominant_node_type=None,
                dominant_source_type=None,
            ),
        ]
    )
    assert idx.assign([1.0, 0.0]) == "new"
