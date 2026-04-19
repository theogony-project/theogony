"""
Parametrised KnowledgeStore contract suite (Plan §2.2, §3.8).

Every concrete KnowledgeStore implementation MUST pass every test in
this file. The InMemoryKnowledgeStore is the always-on parameter
(no external services). Neo4jKnowledgeStore joins the matrix when
``THEOGONY_TEST_NEO4J=1`` is set in the environment (Plan §3.8 + E7
brief): the fixture starts a ``testcontainers`` Neo4j container per
session, runs the same assertions against the production backend,
and tears the container down on session exit.

These tests assert behaviour, not implementation detail. The fixture
yields async-context-managed stores; every test gets a clean state
(``MATCH (n) DETACH DELETE n`` between tests for the Neo4j backend,
fresh ``InMemoryKnowledgeStore`` for the in-memory one).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

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

_NEO4J_GATE = os.environ.get("THEOGONY_TEST_NEO4J") == "1"

STORE_BACKENDS: list[str] = ["in_memory"]
if _NEO4J_GATE:
    STORE_BACKENDS.append("neo4j")

#: Embedding dim used by every test in this suite. The Neo4j HNSW
#: vector index is rebuilt at this dim per session. Production-default
#: 384 is covered by tests/test_neo4j_store_live.py separately.
_CONTRACT_EMBEDDING_DIM = 4


def _emb(*values: float) -> list[float]:
    """Pad / truncate ``values`` to the contract-suite embedding dim.

    Tests want short, inspectable vectors like ``_emb(1.0, 0.0)``;
    the Neo4j HNSW index needs them at the configured dim. Padding
    with zeros preserves cosine direction, so test assertions about
    ranking remain meaningful.
    """
    if len(values) > _CONTRACT_EMBEDDING_DIM:
        raise ValueError(f"emb takes at most {_CONTRACT_EMBEDDING_DIM} values; got {len(values)}")
    return [float(v) for v in values] + [0.0] * (_CONTRACT_EMBEDDING_DIM - len(values))


# Cache the testcontainers Neo4j container for the whole session — bringing
# it up costs ~30-60 s, the contract suite has ~50 tests; we share one
# container across all of them and reset state between tests.
_NEO4J_CONTAINER: Any = None
_NEO4J_URI: str | None = None
_NEO4J_USER: str | None = None
_NEO4J_PASSWORD: str | None = None


@pytest.fixture(scope="session")
def neo4j_container() -> Any:
    """Session-scoped testcontainers Neo4j 5.x.

    Skipped when ``THEOGONY_TEST_NEO4J`` is not ``1``. Tested against
    the same Community-edition default as ``docker-compose.yml`` (Plan
    §3.1a edition note — Pydantic-enforced existence; no Enterprise
    constraints).
    """
    if not _NEO4J_GATE:
        pytest.skip("Set THEOGONY_TEST_NEO4J=1 to run Neo4j contract suite.")

    global _NEO4J_CONTAINER, _NEO4J_URI, _NEO4J_USER, _NEO4J_PASSWORD
    if _NEO4J_CONTAINER is not None:
        return _NEO4J_CONTAINER

    try:
        from testcontainers.neo4j import Neo4jContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[neo4j] not installed: {exc}")

    # 5.18-community matches the docker-compose default + Plan §3.1a.
    # APOC / Bloom / Enterprise plugins are explicitly out of scope (E7 brief).
    container = Neo4jContainer("neo4j:5.18-community")
    container.start()
    _NEO4J_CONTAINER = container
    _NEO4J_URI = container.get_connection_url()
    _NEO4J_USER = container.username
    _NEO4J_PASSWORD = container.password
    return container


@pytest_asyncio.fixture(params=STORE_BACKENDS)
async def store(request: pytest.FixtureRequest) -> AsyncIterator[KnowledgeStore]:
    """Parametrised store fixture.

    Yields a connected store with clean state. For the in-memory backend
    a fresh dict-backed instance per test; for the Neo4j backend the
    session-cached container with a per-test ``MATCH (n) DETACH DELETE
    n`` reset so tests stay independent.
    """
    backend = request.param
    if backend == "in_memory":
        yield InMemoryKnowledgeStore()
        return
    if backend == "neo4j":
        # Lazy local imports keep test collection cheap when the
        # Neo4j matrix is gated out.
        from theogony.config.settings import Neo4jSettings
        from theogony.stores import Neo4jKnowledgeStore

        request.getfixturevalue("neo4j_container")  # ensure container started
        from pydantic import SecretStr

        settings = Neo4jSettings(
            uri=str(_NEO4J_URI),
            user=str(_NEO4J_USER),
            password=SecretStr(str(_NEO4J_PASSWORD)),
            database="neo4j",
        )
        # Contract-suite embeddings are 4-dim throughout for visual
        # clarity (cosine math stays inspectable in tests). The
        # production HNSW dim (384, BGE-small) is exercised separately
        # in tests/test_neo4j_store_live.py.
        async with Neo4jKnowledgeStore(
            settings, embedding_dim=_CONTRACT_EMBEDDING_DIM
        ) as neo_store:
            # Wipe between tests so no state leaks across fixture invocations.
            async with neo_store._session() as session:  # noqa: SLF001 — test fixture
                await session.run("MATCH (n) DETACH DELETE n")
            yield neo_store
        return
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
        a = make_node("A", embedding=_emb(1.0, 0.0, 0.0))
        b = make_node("B", embedding=_emb(0.9, 0.1, 0.0))
        c = make_node("C", embedding=_emb(0.0, 0.0, 1.0))
        for n in (a, b, c):
            await store.upsert_node(n)
        results = await store.vector_search(_emb(1.0, 0.0, 0.0), k=3)
        assert [r.node.label for r in results[:2]] == ["A", "B"]
        assert all(isinstance(r, ScoredNode) for r in results)
        assert results[0].score >= results[1].score >= results[2].score

    async def test_k_caps_result_count(self, store: KnowledgeStore) -> None:
        for i in range(5):
            await store.upsert_node(make_node(f"N{i}", embedding=_emb(1.0, float(i) / 10)))
        results = await store.vector_search(_emb(1.0, 0.0), k=2)
        assert len(results) == 2

    async def test_layer_filter_excludes_other_layer(self, store: KnowledgeStore) -> None:
        e_node = make_node("E", embedding=_emb(1.0, 0.0))
        m_node = make_node("M", embedding=_emb(1.0, 0.0))
        m_node.layer = Layer.MNEME
        await store.upsert_node(e_node)
        await store.upsert_node(m_node)
        ephemeral = await store.vector_search(_emb(1.0, 0.0), k=10, layer=Layer.EPHEMERA)
        assert {r.node.label for r in ephemeral} == {"E"}
        mneme = await store.vector_search(_emb(1.0, 0.0), k=10, layer=Layer.MNEME)
        assert {r.node.label for r in mneme} == {"M"}

    async def test_min_confidence_filter(self, store: KnowledgeStore) -> None:
        low = make_node("LowConf", embedding=_emb(1.0, 0.0), confidence=0.2)
        high = make_node("HighConf", embedding=_emb(1.0, 0.0), confidence=0.9)
        await store.upsert_node(low)
        await store.upsert_node(high)
        results = await store.vector_search(_emb(1.0, 0.0), k=5, min_confidence=0.5)
        assert {r.node.label for r in results} == {"HighConf"}

    async def test_node_type_filter(self, store: KnowledgeStore) -> None:
        person = make_node("Harrer", node_type=NodeType.PERSON, embedding=_emb(1.0, 0.0))
        place = make_node("Lhasa", node_type=NodeType.PLACE, embedding=_emb(1.0, 0.0))
        await store.upsert_node(person)
        await store.upsert_node(place)
        only_persons = await store.vector_search(
            _emb(1.0, 0.0), k=5, node_types=[NodeType.PERSON.value]
        )
        assert {r.node.label for r in only_persons} == {"Harrer"}

    async def test_nodes_without_embeddings_excluded(self, store: KnowledgeStore) -> None:
        # Nodes without embeddings have no defined similarity. Both
        # backends exclude them: InMemory by an early-continue, Neo4j
        # because the HNSW vector index never indexed them. The
        # contract is "vector_search returns only ranked, embedded
        # nodes".
        embedded = make_node("Embedded", embedding=_emb(1.0, 0.0))
        no_embed = make_node("NoEmbedding")
        await store.upsert_node(embedded)
        await store.upsert_node(no_embed)
        results = await store.vector_search(_emb(1.0, 0.0), k=10)
        labels = {r.node.label for r in results}
        assert "Embedded" in labels
        assert "NoEmbedding" not in labels


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
        a = make_node("A", embedding=_emb(1.0, 0.0))
        b = make_node("B", embedding=_emb(0.0, 1.0))  # not similar to query
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.upsert_edge(
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.7)
        )
        results = await store.multi_hop_search(_emb(1.0, 0.0), k=10, hops=1, min_weight=0.5)
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
        # Embedding values must be absent from the slim ConstellationNode
        # serialisation (Plan §9.1). 0.42 is the canary; the dim is the
        # contract-suite default so both backends store it identically.
        a = make_node("A", embedding=[0.42] * _CONTRACT_EMBEDDING_DIM)
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
        a = make_node("A", embedding=_emb(1.0, 0.0))
        b = make_node("B", embedding=_emb(3.0, 4.0))
        await store.upsert_node(a)
        await store.upsert_node(b)
        await store.assign_cluster(a.id, "cluster1")
        await store.assign_cluster(b.id, "cluster1")
        centroid = await store.get_cluster_centroid("cluster1")
        # Padded embeddings: ([1,0,0,0] + [3,4,0,0]) / 2 = [2,2,0,0].
        assert centroid == pytest.approx(_emb(2.0, 2.0))

    async def test_centroid_with_mixed_dim_returns_empty(
        self, store: KnowledgeStore, request: pytest.FixtureRequest
    ) -> None:
        # Constructing nodes with mismatched embedding dims is impossible
        # against the Neo4j store (Plan §3.1a "never silently truncate"
        # rejects writes whose embedding length differs from the index
        # dim). The mixed-dim centroid contract therefore stays
        # in-memory-only — Neo4j cannot reach the state this test
        # asserts about.
        if "neo4j" in request.node.callspec.id:
            pytest.skip("mixed-dim embeddings are unreachable on Neo4j (HNSW dim is fixed)")
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


class TestBatchUpsert:
    """PHX-0046: batch_upsert_nodes / batch_upsert_edges contract.

    Backend-agnostic. The Neo4j override uses one UNWIND round-trip;
    the InMemory default-loop uses N per-node calls. The contract is
    identical: same idempotency, same return-id ordering, same
    embedding-dim discipline.
    """

    async def test_batch_upsert_nodes_returns_ids_in_input_order(
        self, store: KnowledgeStore
    ) -> None:
        nodes = [make_node(f"N{i}") for i in range(5)]
        ids = await store.batch_upsert_nodes(nodes)
        assert ids == [n.id for n in nodes]

    async def test_batch_upsert_nodes_is_idempotent(self, store: KnowledgeStore) -> None:
        nodes = [make_node(f"N{i}") for i in range(3)]
        await store.batch_upsert_nodes(nodes)
        await store.batch_upsert_nodes(nodes)
        await store.batch_upsert_nodes(nodes)
        assert await store.count_nodes() == 3

    async def test_batch_upsert_nodes_empty_input_returns_empty(
        self, store: KnowledgeStore
    ) -> None:
        ids = await store.batch_upsert_nodes([])
        assert ids == []

    async def test_batch_upsert_edges_attaches_relations(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        c = make_node("C")
        await store.batch_upsert_nodes([a, b, c])
        edges = [
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.5),
            KnowledgeEdge(source_id=b.id, target_id=c.id, relation_type="LINKS_TO", weight=0.5),
        ]
        await store.batch_upsert_edges(edges)
        nb_a = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        nb_b = await store.get_neighborhood(b.id, depth=1, min_weight=0.0)
        # a has the (a→b) edge; b has both (a→b) and (b→c).
        assert any(e.source_id == a.id and e.target_id == b.id for e in nb_a.edges)
        assert any(e.source_id == b.id and e.target_id == c.id for e in nb_b.edges)

    async def test_batch_upsert_edges_is_idempotent(self, store: KnowledgeStore) -> None:
        a = make_node("A")
        b = make_node("B")
        await store.batch_upsert_nodes([a, b])
        edge = KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO")
        await store.batch_upsert_edges([edge, edge])
        await store.batch_upsert_edges([edge])
        nb = await store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        # Deterministic edge id (Plan §9.5a) collapses three batch-upserts
        # to one stored edge.
        assert sum(1 for e in nb.edges if e.source_id == a.id and e.target_id == b.id) == 1

    async def test_batch_upsert_edges_empty_input_is_noop(self, store: KnowledgeStore) -> None:
        await store.batch_upsert_edges([])  # must not raise


class TestGetEdgesAmong:
    """PHX-0050: bulk edges-among-N-nodes contract.

    Both backends return only edges where both endpoints are in the
    given ``node_ids`` and ``weight >= min_weight``. Exact edges,
    no extras, no synthesised endpoints.
    """

    async def test_returns_only_edges_with_both_endpoints_in_input(
        self, store: KnowledgeStore
    ) -> None:
        a, b, c, d, e_node = (make_node(label) for label in ("A", "B", "C", "D", "E"))
        await store.batch_upsert_nodes([a, b, c, d, e_node])
        # 4 edges spanning the (a,b,c,d,e) graph; one (a→e) is an
        # endpoint-pair the test will deliberately exclude from the
        # node-id query so the assertion has bite.
        all_edges = [
            KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="LINKS_TO", weight=0.5),
            KnowledgeEdge(source_id=b.id, target_id=c.id, relation_type="LINKS_TO", weight=0.5),
            KnowledgeEdge(source_id=c.id, target_id=d.id, relation_type="LINKS_TO", weight=0.5),
            # The "outsider" edge — its target e is NOT in the query set.
            KnowledgeEdge(source_id=a.id, target_id=e_node.id, relation_type="OTHER", weight=0.5),
        ]
        await store.batch_upsert_edges(all_edges)

        # Query only over (a, b, c, d) — the (a→e) edge must NOT appear.
        result = await store.get_edges_among([a.id, b.id, c.id, d.id])
        assert len(result) == 3
        endpoint_pairs = {(edge.source_id, edge.target_id) for edge in result}
        assert (a.id, b.id) in endpoint_pairs
        assert (b.id, c.id) in endpoint_pairs
        assert (c.id, d.id) in endpoint_pairs
        assert (a.id, e_node.id) not in endpoint_pairs

    async def test_min_weight_filter_excludes_low_weight_edges(self, store: KnowledgeStore) -> None:
        a, b = make_node("A"), make_node("B")
        await store.batch_upsert_nodes([a, b])
        await store.batch_upsert_edges(
            [
                KnowledgeEdge(source_id=a.id, target_id=b.id, relation_type="WEAK", weight=0.2),
                KnowledgeEdge(source_id=b.id, target_id=a.id, relation_type="STRONG", weight=0.8),
            ]
        )
        result = await store.get_edges_among([a.id, b.id], min_weight=0.5)
        types = {e.relation_type for e in result}
        assert types == {"STRONG"}

    async def test_empty_input_returns_empty_without_round_trip(
        self, store: KnowledgeStore
    ) -> None:
        result = await store.get_edges_among([])
        assert result == []


class TestResolveNode:
    async def test_resolve_with_qid_sets_external_id_clears_flag_bumps_tier(
        self, store: KnowledgeStore
    ) -> None:
        # Operator picks Q-ID for a previously unresolved tier-0 mention.
        node = KnowledgeNode(
            label="aufschnaiter",
            source_ref=make_source_ref(location="loc-aufsch"),
            manual_resolution_needed=True,
            resolution_tier=0,
        )
        await store.upsert_node(node)
        ok = await store.resolve_node(node.id, "Q123456")
        assert ok is True
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.external_ids.get("wikidata") == "Q123456"
        assert fetched.resolution_tier == 1
        assert fetched.manual_resolution_needed is False
        # And it must drop out of the resolve queue.
        assert all(n.id != node.id for n in await store.list_pending_resolution())

    async def test_resolve_with_none_clears_flag_only(self, store: KnowledgeStore) -> None:
        # Operator confirmed "none of the candidates fit" — flag clears,
        # tier stays at 0, no Wikidata id minted.
        node = KnowledgeNode(
            label="ambiguous",
            source_ref=make_source_ref(location="loc-amb"),
            manual_resolution_needed=True,
            resolution_tier=0,
        )
        await store.upsert_node(node)
        ok = await store.resolve_node(node.id, None)
        assert ok is True
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert "wikidata" not in fetched.external_ids
        assert fetched.resolution_tier == 0
        assert fetched.manual_resolution_needed is False

    async def test_resolve_unknown_id_returns_false(self, store: KnowledgeStore) -> None:
        # Silent no-op semantics matching promote / update_scores.
        ok = await store.resolve_node("AKA-deadbeefdead", "Q1")
        assert ok is False


# ---------------------------------------------------------------------------
# Bulk write + degree map (E8.5 / PHX-0048)
# ---------------------------------------------------------------------------


class TestCountNeighborsInLayer:
    """Plan §5 E8.5 step 2: bulk node-id → degree map for one layer.

    Both backends MUST satisfy the same contract:
    - Isolated nodes (degree 0) are present in the result.
    - Counts are symmetric: in-edges + out-edges.
    - Cross-layer edges count toward the in-layer node's degree.
    - Nodes in other layers are NOT in the result.
    """

    async def test_isolated_node_appears_with_degree_zero(self, store: KnowledgeStore) -> None:
        loner = make_node("Lonely")  # no edges
        await store.upsert_node(loner)
        result = await store.count_neighbors_in_layer(Layer.EPHEMERA)
        assert loner.id in result
        assert result[loner.id] == 0

    async def test_counts_in_and_out_edges_symmetrically(self, store: KnowledgeStore) -> None:
        hub = make_node("Hub")
        spoke_a = make_node("SpokeA")
        spoke_b = make_node("SpokeB")
        for n in (hub, spoke_a, spoke_b):
            await store.upsert_node(n)
        # hub → spoke_a (out edge for hub, in edge for spoke_a)
        # spoke_b → hub (in edge for hub, out edge for spoke_b)
        await store.upsert_edge(
            KnowledgeEdge(
                source_id=hub.id,
                target_id=spoke_a.id,
                relation_type="LINKS_TO",
            )
        )
        await store.upsert_edge(
            KnowledgeEdge(
                source_id=spoke_b.id,
                target_id=hub.id,
                relation_type="LINKS_TO",
            )
        )
        result = await store.count_neighbors_in_layer(Layer.EPHEMERA)
        assert result[hub.id] == 2  # one in + one out
        assert result[spoke_a.id] == 1
        assert result[spoke_b.id] == 1

    async def test_cross_layer_edge_counts_for_in_layer_node(self, store: KnowledgeStore) -> None:
        # An EPHEMERA node connected to a MNEME node has degree 1 in
        # the EPHEMERA result. The MNEME node is absent because we
        # asked only for EPHEMERA.
        eph = make_node("Eph")
        mne = make_node("Mne")
        mne.layer = Layer.MNEME
        await store.upsert_node(eph)
        await store.upsert_node(mne)
        await store.upsert_edge(
            KnowledgeEdge(
                source_id=eph.id,
                target_id=mne.id,
                relation_type="REFERS_TO",
            )
        )
        eph_result = await store.count_neighbors_in_layer(Layer.EPHEMERA)
        assert eph_result == {eph.id: 1}
        mne_result = await store.count_neighbors_in_layer(Layer.MNEME)
        assert mne_result == {mne.id: 1}


class TestBatchUpdateScores:
    """PHX-0048 (reopened by E8.5): bulk partial-update contract.

    Per row, only non-None fields are written; other fields keep
    their existing values. Empty input is a no-op. Missing node ids
    are silently skipped.
    """

    async def test_partial_update_writes_only_specified_fields(self, store: KnowledgeStore) -> None:
        from theogony.core.model import ScoreUpdate

        node = make_node("Hedin")
        node.scores.confidence = 0.5
        node.scores.relevance = 0.4
        node.scores.connectivity = 0.3
        node.scores.freshness = 0.6
        await store.upsert_node(node)
        await store.batch_update_scores(
            [
                ScoreUpdate(
                    node_id=node.id,
                    connectivity=0.9,
                    freshness=0.1,
                    vitality=0.42,
                )
            ]
        )
        fetched = await store.get_node(node.id)
        assert fetched is not None
        # Updated fields:
        assert fetched.scores.connectivity == pytest.approx(0.9)
        assert fetched.scores.freshness == pytest.approx(0.1)
        # Untouched fields preserve their original values:
        assert fetched.scores.confidence == pytest.approx(0.5)
        assert fetched.scores.relevance == pytest.approx(0.4)

    async def test_empty_input_is_silent_noop(self, store: KnowledgeStore) -> None:
        # Must not raise. The Neo4j override skips the round-trip
        # entirely; the InMemory store loops over zero rows.
        await store.batch_update_scores([])

    async def test_missing_node_id_is_silent_skip(self, store: KnowledgeStore) -> None:
        from theogony.core.model import ScoreUpdate

        node = make_node("ExistingNode")
        node.scores.connectivity = 0.5
        await store.upsert_node(node)
        # Mix one missing id with one existing id; the missing one
        # silently no-ops, the existing one updates.
        await store.batch_update_scores(
            [
                ScoreUpdate(
                    node_id="AKA-deadbeefdead",
                    connectivity=0.99,
                ),
                ScoreUpdate(node_id=node.id, connectivity=0.77),
            ]
        )
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.scores.connectivity == pytest.approx(0.77)
        # The missing id did not magically materialise.
        assert await store.get_node("AKA-deadbeefdead") is None

    async def test_repeated_identical_batch_is_idempotent(self, store: KnowledgeStore) -> None:
        from theogony.core.model import ScoreUpdate

        node = make_node("Idempotent")
        node.scores.confidence = 0.4
        await store.upsert_node(node)
        batch = [ScoreUpdate(node_id=node.id, confidence=0.8, vitality=0.65)]
        for _ in range(3):
            await store.batch_update_scores(batch)
        fetched = await store.get_node(node.id)
        assert fetched is not None
        assert fetched.scores.confidence == pytest.approx(0.8)


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
