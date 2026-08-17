"""Constellation assembly reads in batches, and its caches invalidate on writes.

Assembly was 92% of a warm query (395 ms of 430 ms) — not because of the work it
does but because of how it asked for it: one Lance query per activated node, and a
filtered metadata query per call. Both are now batched, taking a warm query to
~57 ms with an identical result.

The risk that buys is staleness, so the invalidation is what these tests pin.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge


def _node(runtime: MeshRuntime, description: str) -> ConsolidatedNode:
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * runtime.semantic_dim,
        frame_vector=[0.0] * runtime.frame_dim,
        description=description,
        description_vector=[0.1] * runtime.semantic_dim,
    )
    runtime.nodes.append_consolidated(node)
    return node


def _edge(src: str, tgt: str, relation: str) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=src,  # type: ignore[arg-type]
        target_id=tgt,  # type: ignore[arg-type]
        weight=0.5,
        born_at=now,
        last_fired_at=now,
        relation_descriptor=relation,
    )


def test_batched_node_fetch_matches_individual_fetches(mesh_runtime: MeshRuntime) -> None:
    nodes = [_node(mesh_runtime, f"node {i}") for i in range(5)]
    ids = [str(n.id) for n in nodes]

    batched = mesh_runtime.nodes.get_consolidated_many(ids)
    assert set(batched) == set(ids)
    for nid in ids:
        one = mesh_runtime.nodes.get_consolidated(nid)
        assert one is not None
        assert batched[nid].description == one.description


def test_batched_node_fetch_tolerates_unknown_ids(mesh_runtime: MeshRuntime) -> None:
    known = _node(mesh_runtime, "known")
    result = mesh_runtime.nodes.get_consolidated_many([str(known.id), str(ULID())])
    assert list(result) == [str(known.id)]
    assert mesh_runtime.nodes.get_consolidated_many([]) == {}


def test_descriptor_index_returns_every_relation(mesh_runtime: MeshRuntime) -> None:
    a, b = str(ULID()), str(ULID())
    mesh_runtime.edges.append_edges([_edge(a, b, "mentions"), _edge(b, a, "cited_by")])
    index = mesh_runtime.descriptor_index()
    assert index[(a, b)] == "mentions"
    assert index[(b, a)] == "cited_by"


def test_descriptor_cache_is_reused_until_edges_change(mesh_runtime: MeshRuntime) -> None:
    """The cache must be a cache — and must not outlive the data it describes."""
    a, b, c = str(ULID()), str(ULID()), str(ULID())
    mesh_runtime.edges.append_edges([_edge(a, b, "mentions")])

    first = mesh_runtime.descriptor_index()
    assert mesh_runtime.descriptor_index() is first  # same object: no rebuild

    mesh_runtime.edges.append_edges([_edge(b, c, "follows")])
    rebuilt = mesh_runtime.descriptor_index()
    assert rebuilt is not first, "a write must invalidate the descriptor cache"
    assert rebuilt[(b, c)] == "follows"


def test_invalidate_csr_cache_also_drops_descriptors(mesh_runtime: MeshRuntime) -> None:
    """Out-of-band mutations invalidate through the one documented entry point."""
    a, b = str(ULID()), str(ULID())
    mesh_runtime.edges.append_edges([_edge(a, b, "mentions")])
    first = mesh_runtime.descriptor_index()

    mesh_runtime.invalidate_csr_cache()
    assert mesh_runtime.descriptor_index() is not first
