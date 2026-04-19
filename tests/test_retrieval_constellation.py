"""
ConstellationAssembler unit tests (Plan §3.8 layer 5 + 6).

Asserts the assembler:
- projects retrieved nodes to slim ``ConstellationNode`` (no embedding leak);
- collects edges via depth-1 ``get_neighborhood`` probes per seed and
  deduplicates by ``(source_id, target_id, relation_type)``;
- identifies both Plan §9.1 gap kinds:
    * ``"orphan_target:<id>"`` for an edge endpoint absent from the
      retrieved set;
    * ``"no_strong_match"`` when the top-1 score is below
      ``STRONG_MATCH_THRESHOLD``;
- populates ``suggested_sources`` deduped on ``(source_type, identifier)``;
- always sets ``path="fast"``.

The "snapshot" tests use explicit dict literals rather than ``syrupy`` —
the brief calls for snapshot-on-structure; an inline literal makes the
expected shape visible at the point of assertion and avoids dragging in
a new dev dependency for a single use site. (PR body documents this
deviation.)
"""

from __future__ import annotations

from theogony.core.model import (
    KnowledgeEdge,
    KnowledgeNode,
    NodeType,
    SourceRef,
)
from theogony.core.store import ScoredNode
from theogony.retrieval.constellation import (
    GAP_NO_STRONG_MATCH,
    GAP_ORPHAN_PREFIX,
    ConstellationAssembler,
)
from theogony.retrieval.multi_hop import MultiHopResult
from theogony.stores import InMemoryKnowledgeStore


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="43497", location=loc, language="en")


def _node(label: str, *, node_type: NodeType = NodeType.PERSON) -> KnowledgeNode:
    """Construct a uniquely-located KnowledgeNode for assembler tests.

    Embeddings are intentionally empty: the assembler does not look at
    them, and leaving them off makes the slim-DTO contract assertion
    (``"embedding"`` absent from the dump) tighter.
    """
    return KnowledgeNode(
        label=label,
        node_type=node_type,
        source_ref=_src(f"loc:{label}"),
    )


async def _populate(
    store: InMemoryKnowledgeStore,
    nodes: list[KnowledgeNode],
    edges: list[KnowledgeEdge] | None = None,
) -> None:
    for n in nodes:
        await store.upsert_node(n)
    for e in edges or []:
        await store.upsert_edge(e)


# ---------------------------------------------------------------- projection


class TestConstellationProjection:
    async def test_nodes_are_slim_dtos_without_embeddings(self) -> None:
        store = InMemoryKnowledgeStore()
        n = _node("Hedin")
        await _populate(store, [n])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(scored_nodes=[ScoredNode(node=n, score=0.9)], seed_count=1)
        constellation = await assembler.assemble("Wer war Sven Hedin?", result)
        assert len(constellation.nodes) == 1
        slim = constellation.nodes[0]
        assert slim.id == n.id
        assert slim.label == "Hedin"
        # Slim DTO must not carry an embedding field at all (§9.1).
        dump = slim.model_dump()
        assert "embedding" not in dump
        assert "embedding_dim" not in dump

    async def test_node_order_preserves_retrieval_score_order(self) -> None:
        store = InMemoryKnowledgeStore()
        a, b, c = _node("A"), _node("B"), _node("C")
        await _populate(store, [a, b, c])
        assembler = ConstellationAssembler(store)
        scored = [
            ScoredNode(node=a, score=0.95),
            ScoredNode(node=b, score=0.81),
            ScoredNode(node=c, score=0.42),
        ]
        result = MultiHopResult(scored_nodes=scored, seed_count=3)
        constellation = await assembler.assemble("query", result)
        assert [n.label for n in constellation.nodes] == ["A", "B", "C"]


# ---------------------------------------------------------------- edges


class TestEdgeCollectionAndDedup:
    async def test_collects_edges_among_retrieved_nodes(self) -> None:
        store = InMemoryKnowledgeStore()
        hedin, tibet = _node("Hedin"), _node("Tibet", node_type=NodeType.PLACE)
        edge = KnowledgeEdge(
            source_id=hedin.id,
            target_id=tibet.id,
            relation_type="REACHED",
            evidence_span="Hedin reached Tibet",
        )
        await _populate(store, [hedin, tibet], [edge])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(
            scored_nodes=[
                ScoredNode(node=hedin, score=0.9),
                ScoredNode(node=tibet, score=0.7),
            ],
            seed_count=2,
        )
        constellation = await assembler.assemble("Hedin Tibet", result)
        assert len(constellation.edges) == 1
        slim = constellation.edges[0]
        assert (slim.source_id, slim.target_id, slim.relation_type) == (
            hedin.id,
            tibet.id,
            "REACHED",
        )

    async def test_deduplicates_edges_seen_via_multiple_seeds(self) -> None:
        # The same edge will be returned both from Hedin's depth-1
        # neighbourhood and from Tibet's. The assembler must collapse it
        # to a single ConstellationEdge (Plan §9.1 — slim DTOs, no dups).
        store = InMemoryKnowledgeStore()
        hedin, tibet = _node("Hedin"), _node("Tibet", node_type=NodeType.PLACE)
        edge = KnowledgeEdge(
            source_id=hedin.id,
            target_id=tibet.id,
            relation_type="REACHED",
            evidence_span="Hedin reached Tibet.",
        )
        await _populate(store, [hedin, tibet], [edge])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(
            scored_nodes=[
                ScoredNode(node=hedin, score=0.9),
                ScoredNode(node=tibet, score=0.85),
            ],
            seed_count=2,
        )
        constellation = await assembler.assemble("query", result)
        assert len(constellation.edges) == 1


# ---------------------------------------------------------------- gaps


class TestGapDetection:
    async def test_orphan_target_gap_unreachable_under_bulk_edges_semantics(self) -> None:
        # PHX-0050: the previous implementation surfaced an
        # "orphan_target:<id>" gap whenever a retrieved node had an
        # edge to a non-retrieved node. The bulk get_edges_among
        # Cypher only returns within-set edges by definition, so the
        # cross-set edge is invisible to the assembler here — and the
        # orphan gap can never fire. This test pins that semantic
        # change so any future re-introduction of orphan detection
        # has to update the test too.
        store = InMemoryKnowledgeStore()
        hedin, tibet = _node("Hedin"), _node("Tibet", node_type=NodeType.PLACE)
        edge = KnowledgeEdge(
            source_id=hedin.id,
            target_id=tibet.id,
            relation_type="REACHED",
            evidence_span="Hedin reached Tibet.",
        )
        await _populate(store, [hedin, tibet], [edge])
        assembler = ConstellationAssembler(store)
        # Only Hedin in the retrieved set; Tibet is "out of view".
        result = MultiHopResult(scored_nodes=[ScoredNode(node=hedin, score=0.9)], seed_count=1)
        constellation = await assembler.assemble("Hedin", result)
        # No edges in the constellation (the (Hedin → Tibet) edge is
        # not "among" the retrieved set), so no orphan gap either.
        assert constellation.edges == []
        assert all(not g.startswith(GAP_ORPHAN_PREFIX) for g in constellation.gaps)

    async def test_no_strong_match_gap_when_top_score_below_threshold(self) -> None:
        store = InMemoryKnowledgeStore()
        n = _node("WeakMatch")
        await _populate(store, [n])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(scored_nodes=[ScoredNode(node=n, score=0.1)], seed_count=1)
        constellation = await assembler.assemble("weak query", result, query_embedding=[1.0, 0.0])
        assert GAP_NO_STRONG_MATCH in constellation.gaps

    async def test_no_strong_match_skipped_without_embedding(self) -> None:
        store = InMemoryKnowledgeStore()
        n = _node("WeakMatch")
        await _populate(store, [n])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(scored_nodes=[ScoredNode(node=n, score=0.05)], seed_count=1)
        constellation = await assembler.assemble("weak", result, query_embedding=None)
        assert GAP_NO_STRONG_MATCH not in constellation.gaps

    async def test_no_gaps_when_strong_matches_and_no_orphans(self) -> None:
        store = InMemoryKnowledgeStore()
        n = _node("StrongMatch")
        await _populate(store, [n])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(scored_nodes=[ScoredNode(node=n, score=0.95)], seed_count=1)
        constellation = await assembler.assemble("query", result, query_embedding=[1.0, 0.0])
        assert constellation.gaps == []


# ---------------------------------------------------------------- sources


class TestSuggestedSources:
    async def test_dedupes_by_source_type_and_identifier(self) -> None:
        # Two nodes from the same Gutenberg book should produce one
        # suggested source, not two.
        store = InMemoryKnowledgeStore()
        a = _node("A")
        b = _node("B")
        await _populate(store, [a, b])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(
            scored_nodes=[ScoredNode(node=a, score=0.9), ScoredNode(node=b, score=0.8)],
            seed_count=2,
        )
        constellation = await assembler.assemble("query", result)
        assert len(constellation.suggested_sources) == 1
        assert constellation.suggested_sources[0].identifier == "43497"


# ---------------------------------------------------------------- snapshot


class TestSnapshotShape:
    async def test_constellation_structure_matches_expected_shape(self) -> None:
        # Snapshot-style structural assertion (PR body documents the
        # decision to use an inline literal rather than syrupy).
        store = InMemoryKnowledgeStore()
        hedin = _node("Hedin")
        tibet = _node("Tibet", node_type=NodeType.PLACE)
        edge = KnowledgeEdge(
            source_id=hedin.id,
            target_id=tibet.id,
            relation_type="REACHED",
            evidence_span="Hedin reached Tibet.",
        )
        await _populate(store, [hedin, tibet], [edge])
        assembler = ConstellationAssembler(store)
        result = MultiHopResult(
            scored_nodes=[
                ScoredNode(node=hedin, score=0.95),
                ScoredNode(node=tibet, score=0.82),
            ],
            seed_count=2,
        )
        constellation = await assembler.assemble("Hedin Tibet", result)

        # Compare a structural projection (ids, labels, types, edge tuples).
        node_shape = [(n.label, n.node_type.value) for n in constellation.nodes]
        edge_shape = [
            (e.source_id == hedin.id, e.target_id == tibet.id, e.relation_type)
            for e in constellation.edges
        ]
        assert node_shape == [("Hedin", "person"), ("Tibet", "place")]
        assert edge_shape == [(True, True, "REACHED")]
        assert constellation.path == "fast"
        assert constellation.gaps == []
        assert len(constellation.suggested_sources) == 1
