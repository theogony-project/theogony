"""
Parametrised KnowledgeStore contract suite (Plan §2.2, §3.8).

Every concrete KnowledgeStore implementation MUST pass every test in
this file. The InMemoryKnowledgeStore exists primarily so this suite
can run on every CI without a Neo4j container; Neo4jKnowledgeStore
joins the matrix in Week 3 (parameter ``"neo4j"`` will be added with
a testcontainers-gated skip).

These tests assert behaviour, not implementation detail. They use the
fixture helpers from ``tests/conftest.py`` so the same nodes can be
shared across backends without leaking through implementation
particularities.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from tests.conftest import make_node, make_source_ref
from theogony.core import (
    Constellation,
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeStore,
    Layer,
    NodeType,
    Path,
    ScoredNode,
)
from theogony.stores import InMemoryKnowledgeStore

# ---------------------------------------------------------------------------
# Backend matrix
# ---------------------------------------------------------------------------

STORE_BACKENDS = ["in_memory"]


@pytest.fixture(params=STORE_BACKENDS)
def store(request: pytest.FixtureRequest) -> KnowledgeStore:
    """Parametrised store fixture.

    Adding a new backend means: (a) install in this fixture, (b) add
    its name to ``STORE_BACKENDS``. The Neo4jKnowledgeStore lands in
    Week 3 with a ``testcontainers``-gated branch here.
    """
    backend = request.param
    if backend == "in_memory":
        return InMemoryKnowledgeStore()
    raise NotImplementedError(f"unknown backend: {backend}")


# ---------------------------------------------------------------------------
# Upsert / get / delete
# ---------------------------------------------------------------------------


class TestNodeCrud:
    async def test_upsert_returns_id(self, store: KnowledgeStore) -> None:
        node = make_node("Harrer")
        returned_id = await store.upsert_node(node)
        assert returned_id == node.id

    async def test_get_node_returns_what_was_upserted(self, store: KnowledgeStore) -> None:
        node = make_node("Harrer", node_type=NodeType.PERSON)
        await store.upsert_node(node)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.id == node.id
        assert fetched.label == "Harrer"
        assert fetched.node_type == NodeType.PERSON

    async def test_get_unknown_node_returns_none(self, store: KnowledgeStore) -> None:
        assert await store.get_node("AKA-does-not-exist") is None

    async def test_upsert_is_idempotent_with_deterministic_ids(self, store: KnowledgeStore) -> None:
        first = make_node("Harrer", location="ch3:p1")
        await store.upsert_node(first)
        second = make_node("Harrer", location="ch3:p1")
        assert second.id == first.id  # §9.5
        await store.upsert_node(second)
        assert await store.count_nodes() == 1

    async def test_delete_removes_node_and_incident_edges(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        await store.upsert_node(a)
        await store.upsert_node(b)
        edge = KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO")
        await store.upsert_edge(edge)
        await store.delete_node(a.id)
        assert await store.get_node(a.id) is None
        assert await store.get_node(b.id) is not None
        # The edge's other endpoint should still exist with no surviving edge.
        nb = await store.get_neighborhood(b.id, depth=1)
        assert all(e.source_id != a.id and e.target_id != a.id for e in nb.edges)

    async def test_delete_unknown_node_is_noop(self, store: KnowledgeStore) -> None:
        await store.delete_node("AKA-does-not-exist")  # must not raise


# ---------------------------------------------------------------------------
# Edge upsert
# ---------------------------------------------------------------------------


class TestEdgeCrud:
    async def test_upsert_edge_persists(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        await store.upsert_node(a)
        await store.upsert_node(b)
        edge = KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="MET", weight=0.7)
        await store.upsert_edge(edge)
        nb = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        assert any(e.source_id == a.id and e.target_id == b.id for e in nb.edges)

    async def test_upsert_edge_is_idempotent_with_same_evidence(
        self, store: KnowledgeStore
    ) -> None:
        a = make_node("A")
        b = make_node("B")
        await store.upsert_node(a)
        await store.upsert_node(b)
        e1 = KnowledgeEdge(
            source_id=a.id, target_id=b.id, relation_type="MET", evidence_span="A met B."
        )
        e2 = KnowledgeEdge(
            source_id=a.id, target_id=b.id, relation_type="MET", evidence_span="A met B."
        )
        assert e1.id == e2.id  # §9.5a
        await store.upsert_edge(e1)
        await store.upsert_edge(e2)
        nb = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        assert sum(1 for e in nb.edges if e.relation_type == "MET") == 1

    async def test_different_evidence_spans_yield_distinct_edges(
        self, store: KnowledgeStore
    ) -> None:
        a = make_node("A")
        b = make_node("B")
        await store.upsert_node(a)
        await store.upsert_node(b)
        e1 = KnowledgeEdge(
            source_id=a.id, target_id=b.id, relation_type="MET", evidence_span="They met in Bombay."
        )
        e2 = KnowledgeEdge(
            source_id=a.id, target_id=b.id, relation_type="MET", evidence_span="They met in Lhasa."
        )
        await store.upsert_edge(e1)
        await store.upsert_edge(e2)
        nb = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        assert sum(1 for e in nb.edges if e.relation_type == "MET") == 2


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------


class TestVectorSearch:
    async def test_returns_scored_nodes_in_descending_order(self, store: KnowledgeStore) -> None:
        a = make_node("A", embedding=[1.0, 0.0, 0.0])
        b = make_node("B", embedding=[0.9, 0.1, 0.0])
        c = make_node("C", embedding=[0.0, 0.0, 1.0])
        for n in (a, b, c):
            await store.upsert_node(n)
        results = await store.vector_search([1.0, 0.0, 0.0], k=3)
        assert [r.node.label for r in results[:2]] == ["A", "B"]
        assert all(isinstance(r, ScoredNode) for r in results)
        assert results[0].score >= results[1].score >= results[2].score

    async def test_k_caps_result_count(self, store: KnowledgeStore) -> None:
        for i in range(5):
            await store.upsert_node(make_node(f"N{i}", embedding=[1.0, float(i) / 10]))
        results = await store.vector_search([1.0, 0.0], k=2)
        assert len(results) == 2

    async def test_layer_filter_excludes_other_layer(self, store: KnowledgeStore) -> None:
        e_node = make_node("E", embedding=[1.0, 0.0])
        m_node = make_node("M", embedding=[1.0, 0.0])
        m_node.layer = Layer.MNEME
        await store.upsert_node(e_node)
        await store.upsert_node(m_node)
        ephemeral = await store.vector_search([1.0, 0.0], k=10, layer=Layer.EPHEMERA)
        assert {r.node.label for r in ephemeral} == {"E"}
        mneme = await store.vector_search([1.0, 0.0], k=10, layer=Layer.MNEME)
        assert {r.node.label for r in mneme} == {"M"}

    async def test_min_confidence_filter(self, store: KnowledgeStore) -> None:
        low = make_node("LowConf", embedding=[1.0, 0.0], confidence=0.2)
        high = make_node("HighConf", embedding=[1.0, 0.0], confidence=0.9)
        await store.upsert_node(low)
        await store.upsert_node(high)
        results = await store.vector_search([1.0, 0.0], k=5, min_confidence=0.5)
        assert {r.node.label for r in results} == {"HighConf"}

    async def test_node_type_filter(self, store: KnowledgeStore) -> None:
        person = make_node("Harrer", node_type=NodeType.PERSON, embedding=[1.0, 0.0])
        place = make_node("Lhasa", node_type=NodeType.PLACE, embedding=[1.0, 0.0])
        await store.upsert_node(person)
        await store.upsert_node(place)
        only_persons = await store.vector_search(
            [1.0, 0.0], k=5, node_types=[NodeType.PERSON.value]
        )
        assert {r.node.label for r in only_persons} == {"Harrer"}

    async def test_node_without_embedding_scores_zero(self, store: KnowledgeStore) -> None:
        nope = make_node("NoEmbedding")
        await store.upsert_node(nope)
        results = await store.vector_search([1.0, 0.0, 0.0], k=10)
        assert any(r.node.label == "NoEmbedding" and r.score == 0.0 for r in results)


# ---------------------------------------------------------------------------
# Traverse
# ---------------------------------------------------------------------------


class TestTraverse:
    async def _build_chain(self, store: KnowledgeStore) -> tuple[str, str, str]:
        a = make_node("A")
        b = make_node("B")
        c = make_node("C")
        for n in (a, b, c):
            await store.upsert_node(n)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.8)
        )
        await store.upsert_edge(
            KnowledgeEdge(source_id=b.id, target_id=c.id, relation_type="LINKS_TO", weight=0.6)
        )
        return a.id, b.id, c.id

    async def test_traverse_unknown_returns_empty(self, store: KnowledgeStore) -> None:
        paths = await store.traverse("AKA-nonexistent", max_depth=3)
        assert paths == []

    async def test_traverse_respects_max_depth(self, store: KnowledgeStore) -> None:
        a, _, c = await self._build_chain(store)
        depth_1 = await store.traverse(a, max_depth=1, min_weight=0.0)
        endpoints_1 = {p.nodes[-1].id for p in depth_1}
        assert c not in endpoints_1
        depth_2 = await store.traverse(a, max_depth=2, min_weight=0.0)
        endpoints_2 = {p.nodes[-1].id for p in depth_2}
        assert c in endpoints_2

    async def test_traverse_skips_low_weight_edges(self, store: KnowledgeStore) -> None:
        a, b, c = await self._build_chain(store)
        # min_weight=0.7 cuts off the b→c edge (weight 0.6)
        paths = await store.traverse(a, max_depth=3, min_weight=0.7)
        endpoints = {p.nodes[-1].id for p in paths}
        assert b in endpoints
        assert c not in endpoints

    async def test_traverse_filters_by_relation_type(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        c = make_node("C")
        for n in (a, b, c):
            await store.upsert_node(n)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="MET", weight=0.8)
        )
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=c.id, relation_type="REACHED", weight=0.8)
        )
        only_met = await store.traverse(a.id, max_depth=1, relation_types=["MET"])
        endpoints = {p.nodes[-1].id for p in only_met}
        assert endpoints == {b.id}

    async def test_path_returns_concrete_pydantic_path(self, store: KnowledgeStore) -> None:
        a, _, _ = await self._build_chain(store)
        paths = await store.traverse(a, max_depth=2, min_weight=0.0)
        assert all(isinstance(p, Path) for p in paths)


# ---------------------------------------------------------------------------
# Multi-hop search
# ---------------------------------------------------------------------------


class TestMultiHopSearch:
    async def test_includes_seeds_and_neighbours(self, store: KnowledgeStore) -> None:
        a = make_node("A", embedding=[1.0, 0.0])
        b = make_node("B", embedding=[0.0, 1.0])  # not similar to query
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.7)
        )
        results = await store.multi_hop_search([1.0, 0.0], k=10, hops=1, min_weight=0.5)
        labels = {r.node.label for r in results}
        assert "A" in labels  # seed
        assert "B" in labels  # discovered via traversal


# ---------------------------------------------------------------------------
# get_neighborhood (Hover-Lupe)
# ---------------------------------------------------------------------------


class TestGetNeighborhood:
    async def test_unknown_node_returns_empty_constellation(self, store: KnowledgeStore) -> None:
        nb = await store.get_neighborhood("AKA-nonexistent")
        assert isinstance(nb, Constellation)
        assert nb.nodes == []
        assert nb.edges == []

    async def test_returns_slim_dtos_not_full_records(self, store: KnowledgeStore) -> None:
        a = make_node("A", embedding=[0.42] * 384)
        b = make_node("B")
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.7)
        )
        nb = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        dumped = nb.model_dump_json()
        assert "0.42" not in dumped  # §9.1 — embeddings stay out of payload
        assert "embedding" not in dumped

    async def test_bidirectional_neighbourhood(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        c = make_node("C")
        for n in (a, b, c):
            await store.upsert_node(n)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.7)
        )
        await store.upsert_edge(
            KnowledgeEdge(source_id=c.id, target_id=b.id, relation_type="LINKS_TO", weight=0.7)
        )
        # Asking for B's neighbourhood should reach both A (incoming) and... no other.
        nb = await store.get_neighborhood(b.id, depth=1, min_weight=0.0)
        labels = {n.label for n in nb.nodes}
        assert labels == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_promote_moves_to_mneme(self, store: KnowledgeStore) -> None:
        node = make_node("X")
        await store.upsert_node(node)
        await store.promote(node.id)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.layer == Layer.MNEME

    async def test_degrade_moves_back_to_ephemera(self, store: KnowledgeStore) -> None:
        node = make_node("X")
        node.layer = Layer.MNEME
        await store.upsert_node(node)
        await store.degrade(node.id)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.layer == Layer.EPHEMERA

    async def test_promote_unknown_node_is_noop(self, store: KnowledgeStore) -> None:
        await store.promote("AKA-nope")  # must not raise

    async def test_update_scores_changes_named_fields(self, store: KnowledgeStore) -> None:
        node = make_node("X")
        await store.upsert_node(node)
        await store.update_scores(node.id, {"confidence": 0.91, "connectivity": 0.42})
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.scores.confidence == pytest.approx(0.91)
        assert fetched.scores.connectivity == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Cluster management
# ---------------------------------------------------------------------------


class TestClusters:
    async def test_centroid_of_unknown_cluster_is_empty(self, store: KnowledgeStore) -> None:
        assert await store.get_cluster_centroid("nope") == []

    async def test_assign_cluster_then_centroid_is_mean(self, store: KnowledgeStore) -> None:
        a = make_node("A", embedding=[1.0, 0.0])
        b = make_node("B", embedding=[3.0, 4.0])
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.assign_cluster(a.id, "cluster1")
        await store.assign_cluster(b.id, "cluster1")
        centroid = await store.get_cluster_centroid("cluster1")
        assert centroid == pytest.approx([2.0, 2.0])

    async def test_centroid_with_mixed_dim_returns_empty(self, store: KnowledgeStore) -> None:
        a = make_node("A", embedding=[1.0, 2.0])
        b = make_node("B", embedding=[1.0, 2.0, 3.0])
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.assign_cluster(a.id, "weird")
        await store.assign_cluster(b.id, "weird")
        assert await store.get_cluster_centroid("weird") == []


# ---------------------------------------------------------------------------
# Bulk export / import (Phoenix process scaffolding)
# ---------------------------------------------------------------------------


class TestBulkOps:
    async def test_export_layer_yields_only_that_layer(self, store: KnowledgeStore) -> None:
        e = make_node("E")
        m = make_node("M")
        m.layer = Layer.MNEME
        await store.upsert_node(e)
        await store.upsert_node(m)
        exported = [n async for n in store.export_layer(Layer.MNEME)]
        assert {n.label for n in exported} == {"M"}

    async def test_import_round_trips_via_export(self, store: KnowledgeStore) -> None:
        for label in ("X", "Y", "Z"):
            node = make_node(label)
            node.layer = Layer.MNEME
            await store.upsert_node(node)

        async def _stream(src: KnowledgeStore) -> AsyncIterator[KnowledgeNode]:
            async for n in src.export_layer(Layer.MNEME):
                yield n

        target = InMemoryKnowledgeStore()
        await target.import_nodes(_stream(store))
        assert await target.count_nodes() == 3


# ---------------------------------------------------------------------------
# Resolution-honesty queries (§9.6)
# ---------------------------------------------------------------------------


class TestPendingResolution:
    async def test_returns_only_manual_resolution_nodes(self, store: KnowledgeStore) -> None:
        ok = KnowledgeNode(
            label="resolved",
            source_ref=make_source_ref(location="loc-ok"),
            external_ids={"wikidata": "Q1"},
            resolution_tier=4,
        )
        pending = KnowledgeNode(
            label="aufschnaiter",
            source_ref=make_source_ref(location="loc-pending"),
            manual_resolution_needed=True,
            resolution_tier=0,
        )
        await store.upsert_node(ok)
        await store.upsert_node(pending)
        result = await store.list_pending_resolution()
        assert {n.label for n in result} == {"aufschnaiter"}

    async def test_layer_filter_works(self, store: KnowledgeStore) -> None:
        eph = KnowledgeNode(
            label="eph_pending",
            source_ref=make_source_ref(location="eph"),
            manual_resolution_needed=True,
            resolution_tier=0,
        )
        mn = KnowledgeNode(
            label="mn_pending",
            source_ref=make_source_ref(location="mn"),
            layer=Layer.MNEME,
            manual_resolution_needed=True,
            resolution_tier=0,
        )
        await store.upsert_node(eph)
        await store.upsert_node(mn)
        eph_only = await store.list_pending_resolution(layer=Layer.EPHEMERA)
        assert {n.label for n in eph_only} == {"eph_pending"}

    async def test_limit_caps_results(self, store: KnowledgeStore) -> None:
        for i in range(5):
            await store.upsert_node(
                KnowledgeNode(
                    label=f"pending{i}",
                    source_ref=make_source_ref(location=f"loc{i}"),
                    manual_resolution_needed=True,
                    resolution_tier=0,
                )
            )
        result = await store.list_pending_resolution(limit=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    async def test_count_nodes_total(self, store: KnowledgeStore) -> None:
        for label in ("A", "B", "C"):
            await store.upsert_node(make_node(label))
        assert await store.count_nodes() == 3

    async def test_count_nodes_by_layer(self, store: KnowledgeStore) -> None:
        e = make_node("E")
        m = make_node("M")
        m.layer = Layer.MNEME
        await store.upsert_node(e)
        await store.upsert_node(m)
        assert await store.count_nodes(layer=Layer.EPHEMERA) == 1
        assert await store.count_nodes(layer=Layer.MNEME) == 1

    async def test_health_is_a_dict(self, store: KnowledgeStore) -> None:
        h = await store.health()
        assert isinstance(h, dict)
        assert "nodes" in h
        assert "edges" in h
