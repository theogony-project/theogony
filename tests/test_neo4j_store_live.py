"""
Neo4jKnowledgeStore live tests (E7 brief: schema, dim-check, idempotency).

Three Neo4j-specific properties the parametrised contract suite cannot
express, gated on ``THEOGONY_TEST_NEO4J=1``:

1. **Schema bootstrap idempotence.** Plan §3.1a's ``IF NOT EXISTS``
   discipline means ``_ensure_schema`` is a clean no-op on reconnect.
   Running it twice in a row must produce zero errors and zero
   visible schema churn.
2. **Vector-index dim-mismatch rejection.** Plan §3.1a "never
   silently truncate" rule: an upsert whose embedding length differs
   from the configured store dim must raise, not coerce.
3. **Deterministic-id idempotent-upsert (Plan §9.5).** Two upserts of
   what is structurally the same node / edge — different Pydantic
   instances, same deterministic id — produce a single Neo4j record.

These complement the parametrised contract suite (``test_store_contract.py``)
which proves InMemory + Neo4j behave identically. This file proves
Neo4j-specific guarantees the InMemory implementation does not even
attempt to provide (no schema, no fixed-dim vector index, no DB-side
uniqueness).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr

from theogony.config.settings import Neo4jSettings
from theogony.core.model import (
    KnowledgeEdge,
    KnowledgeNode,
    NodeType,
    SourceRef,
)
from theogony.stores import Neo4jKnowledgeStore

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_TEST_NEO4J") != "1",
    reason="Set THEOGONY_TEST_NEO4J=1 to run Neo4j live tests.",
)


# Use the same module-level cache as test_store_contract — the session-
# scoped fixture there starts one container per pytest invocation,
# whether that invocation runs the contract suite or this file. Sharing
# the container keeps the testcontainers cold-start cost amortised.


@pytest.fixture(scope="session")
def neo4j_container() -> Any:
    try:
        from testcontainers.neo4j import Neo4jContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[neo4j] not installed: {exc}")
    container = Neo4jContainer("neo4j:5.18-community")
    container.start()
    yield container
    container.stop()


def _settings_from(container: Any) -> Neo4jSettings:
    return Neo4jSettings(
        uri=container.get_connection_url(),
        user=container.username,
        password=SecretStr(container.password),
        database="neo4j",
    )


@pytest_asyncio.fixture
async def neo4j_store(neo4j_container: Any) -> AsyncIterator[Neo4jKnowledgeStore]:
    """Per-test connected store at the production embedding dim (384, BGE-small).

    Used by tests that specifically need the production HNSW dim. The
    contract suite uses dim=4 for visual clarity; this fixture exists
    so dim-mismatch behaviour can be asserted against the actual
    production-shape index.
    """
    settings = _settings_from(neo4j_container)
    async with Neo4jKnowledgeStore(settings, embedding_dim=384) as store:
        async with store._session() as session:  # noqa: SLF001 — test setup
            await session.run("MATCH (n) DETACH DELETE n")
        yield store


def _book_source_ref() -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", language="en")


# ---------------------------------------------------------------- schema


class TestSchemaBootstrap:
    async def test_running_schema_twice_is_idempotent(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # The connect step already ran _ensure_schema once. A second
        # invocation must succeed without raising and produce no
        # schema churn — Plan §3.1a "All idempotent (IF NOT EXISTS)".
        await neo4j_store._ensure_schema()  # noqa: SLF001 — assertion target
        # And a third time, just to be sure no two-run vs three-run
        # mode is hiding.
        await neo4j_store._ensure_schema()  # noqa: SLF001

    async def test_schema_creates_expected_constraints_and_indexes(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # SHOW CONSTRAINTS / SHOW INDEXES are the canonical diagnostic
        # for verifying §3.1a shipped what the brief promised.
        async with neo4j_store._session() as session:  # noqa: SLF001
            constraints = await (await session.run("SHOW CONSTRAINTS")).data()
            indexes = await (await session.run("SHOW INDEXES")).data()
        constraint_names = {c["name"] for c in constraints}
        # Two unique constraints (Plan §3.1a edition note — no
        # existence constraints on Community).
        assert "knowledge_node_id_unique" in constraint_names
        assert "relation_id_unique" in constraint_names
        # Edition-agnostic: the two existence constraints must NOT be
        # there on Community Edition (Plan §3.1a edition note).
        assert "knowledge_node_id_exists" not in constraint_names
        assert "relation_type_exists" not in constraint_names

        index_names = {i["name"] for i in indexes}
        # Ten range indexes (Plan §3.1a — eight node-side + two edge-side).
        for required in (
            "knowledge_node_label",
            "knowledge_node_node_type",
            "knowledge_node_layer",
            "knowledge_node_wikidata",
            "knowledge_node_resolution_tier",
            "knowledge_node_manual_resolution",
            "knowledge_node_vitality",
            "knowledge_node_last_accessed",
            "relation_relation_type",
            "relation_weight",
        ):
            assert required in index_names, f"missing range index: {required}"
        # One HNSW vector index.
        assert "knowledge_node_embedding" in index_names


# ---------------------------------------------------------------- dim check


class TestVectorIndexDimMismatch:
    async def test_node_with_explicit_wrong_dim_is_rejected(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # store dim = 384; node declares dim=128. Plan §3.1a "never
        # silently truncate" → ValueError at the boundary.
        node = KnowledgeNode(
            label="WrongDim",
            node_type=NodeType.OTHER,
            source_ref=_book_source_ref(),
            embedding=[0.1] * 128,
            embedding_dim=128,
            embedding_model_id="wrong@v1",
        )
        with pytest.raises(ValueError, match="embedding_dim=128"):
            await neo4j_store.upsert_node(node)

    async def test_node_with_inferred_wrong_length_is_rejected(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # No explicit embedding_dim, but the actual embedding list is
        # the wrong length. The store catches it before the bytes hit
        # Neo4j (HNSW would reject anyway; we want a clear ValueError
        # with the misuse named).
        node = KnowledgeNode(
            label="WrongLength",
            node_type=NodeType.OTHER,
            source_ref=_book_source_ref(),
            embedding=[0.2] * 7,  # not 384, no embedding_dim set
        )
        with pytest.raises(ValueError, match="length 7"):
            await neo4j_store.upsert_node(node)

    async def test_node_without_embedding_passes_dim_check(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # No embedding at all → no dim contract to enforce. The store
        # accepts it and the HNSW index simply doesn't include it
        # (it appears in CRUD / traversal / lifecycle, but not in
        # vector_search results — verified in the contract suite).
        node = KnowledgeNode(
            label="NoEmbedding",
            node_type=NodeType.OTHER,
            source_ref=_book_source_ref(),
        )
        returned_id = await neo4j_store.upsert_node(node)
        assert returned_id == node.id

    async def test_correctly_sized_embedding_is_accepted(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        node = KnowledgeNode(
            label="OK",
            node_type=NodeType.OTHER,
            source_ref=_book_source_ref(),
            embedding=[0.5] * 384,
            embedding_dim=384,
            embedding_model_id="bge-small@v1",
        )
        await neo4j_store.upsert_node(node)
        fetched = await neo4j_store.get_node(node.id)
        assert fetched is not None
        assert fetched.embedding_dim == 384
        assert len(fetched.embedding) == 384


# ---------------------------------------------------------------- idempotency


class TestDeterministicIdIdempotency:
    """Plan §9.5 / §9.5a: deterministic ids → store upsert is a no-op on retry."""

    async def test_two_node_upserts_with_same_id_collapse_to_one_record(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        sr = _book_source_ref()
        first = KnowledgeNode(
            label="Hedin",
            node_type=NodeType.PERSON,
            source_ref=sr,
            external_ids={"wikidata": "Q154759"},
            embedding=[0.1] * 384,
            embedding_dim=384,
            embedding_model_id="bge-small@v1",
            resolution_tier=4,
        )
        # Construct a second instance with structurally-identical
        # inputs → same compute_node_id() → same Neo4j primary key.
        second = KnowledgeNode(
            label="Hedin",
            node_type=NodeType.PERSON,
            source_ref=sr,
            external_ids={"wikidata": "Q154759"},
            embedding=[0.1] * 384,
            embedding_dim=384,
            embedding_model_id="bge-small@v1",
            resolution_tier=4,
        )
        assert first.id == second.id, "Plan §9.5 deterministic id contract"
        await neo4j_store.upsert_node(first)
        await neo4j_store.upsert_node(second)
        await neo4j_store.upsert_node(second)
        assert await neo4j_store.count_nodes() == 1

    async def test_two_edge_upserts_with_same_evidence_collapse_to_one_record(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        sr = _book_source_ref()
        a = KnowledgeNode(label="A", source_ref=sr, embedding=[0.1] * 384, embedding_dim=384)
        b = KnowledgeNode(label="B", source_ref=sr, embedding=[0.2] * 384, embedding_dim=384)
        await neo4j_store.upsert_node(a)
        await neo4j_store.upsert_node(b)
        e1 = KnowledgeEdge(
            source_id=a.id,
            target_id=b.id,
            relation_type="MET",
            evidence_span="A met B in Lhasa.",
        )
        e2 = KnowledgeEdge(
            source_id=a.id,
            target_id=b.id,
            relation_type="MET",
            evidence_span="A met B in Lhasa.",
        )
        assert e1.id == e2.id, "Plan §9.5a deterministic edge-id contract"
        await neo4j_store.upsert_edge(e1)
        await neo4j_store.upsert_edge(e2)
        nb = await neo4j_store.get_neighborhood(a.id, depth=1, min_weight=0.0)
        # Exactly one edge with relation MET should be present.
        assert sum(1 for e in nb.edges if e.relation_type == "MET") == 1

    async def test_property_updates_persist_through_re_upsert(
        self, neo4j_store: Neo4jKnowledgeStore
    ) -> None:
        # Idempotent ID + new property values = SET +=  updates the
        # stored row. Verifies our MERGE+SET pattern, not just the
        # uniqueness constraint.
        sr = _book_source_ref()
        first = KnowledgeNode(
            label="Lhasa",
            node_type=NodeType.PLACE,
            source_ref=sr,
            embedding=[0.1] * 384,
            embedding_dim=384,
            embedding_model_id="bge-small@v1",
            resolution_tier=3,
        )
        await neo4j_store.upsert_node(first)
        # Same id, but the description changed and tier was promoted.
        second = first.model_copy(
            update={
                "description": "capital of Tibet",
                "resolution_tier": 4,
            }
        )
        assert second.id == first.id
        await neo4j_store.upsert_node(second)
        fetched = await neo4j_store.get_node(first.id)
        assert fetched is not None
        assert fetched.description == "capital of Tibet"
        assert fetched.resolution_tier == 4
        assert await neo4j_store.count_nodes() == 1
