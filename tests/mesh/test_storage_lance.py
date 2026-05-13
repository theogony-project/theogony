"""Lance node/edge storage and versioning smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, Edge, SourceProvenance
from theogony.mesh.storage.edges import MeshEdgeStore, build_csr_from_edges


def test_append_chunk_and_fetch(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    src = SourceProvenance(
        source_type="test",
        source_identifier="x",
        extracted_at=now,
    )
    n = ChunkNode(
        id="01HZX8QZ7QZ7QZ7QZ7QZ7QZ7Q",
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.25] * 8,
        frame_vector=[0.5] * 4,
        source=src,
        raw_text_ref="ref://1",
    )
    mesh_runtime.nodes.append_chunk(n)
    got = mesh_runtime.nodes.get_chunk(n.id)
    assert got is not None
    assert got.id == n.id


def test_edge_csr_and_version_pin(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    store = mesh_runtime.edges
    assert isinstance(store, MeshEdgeStore)
    e = Edge(
        source_id="n0",
        target_id="n1",
        weight=1.0,
        born_at=now,
        last_fired_at=now,
    )
    store.append_edge(e)
    csr = build_csr_from_edges(store.load_edges())
    assert csr.size[0] == 2
    assert csr.values.numel() == 1

    tbl = store.edge_table
    versions_after_first = tbl.list_versions()
    v_one_edge = versions_after_first[-1]["version"]
    e2 = Edge(
        source_id="n1",
        target_id="n2",
        weight=0.5,
        born_at=now,
        last_fired_at=now,
    )
    store.append_edge(e2)
    tbl.checkout(v_one_edge)
    assert tbl.count_rows() == 1
    tbl.checkout_latest()
    assert tbl.count_rows() == 2
