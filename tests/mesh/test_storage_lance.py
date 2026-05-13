"""Lance node/edge storage, CSR construction, and version checkout."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance
from theogony.mesh.storage.edges import build_csr_from_edges


def test_append_and_fetch_chunk(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    src = SourceProvenance(source_type="test", source_identifier="x", extracted_at=now)
    nid = ULID()
    n = ChunkNode(
        id=nid,
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.25] * 8,
        frame_vector=[0.50] * 4,
        source=src,
        raw_text_ref="ref://1",
    )
    mesh_runtime.nodes.append_chunk(n)
    got = mesh_runtime.nodes.get_chunk(str(nid))
    assert got is not None
    assert got.id == nid


def test_append_and_fetch_consolidated(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    n = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.2] * 4,
        description="test consolidated",
    )
    mesh_runtime.nodes.append_consolidated(n)
    assert mesh_runtime.nodes.consolidated_count() >= 1


def test_edge_csr_from_store(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    e1 = Edge(source_id=ULID(), target_id=ULID(), weight=1.0, born_at=now, last_fired_at=now)
    e2 = Edge(source_id=ULID(), target_id=ULID(), weight=0.5, born_at=now, last_fired_at=now)
    mesh_runtime.edges.append_edge(e1)
    mesh_runtime.edges.append_edge(e2)

    csr = build_csr_from_edges(mesh_runtime.edges.load_all_edges())
    assert len(csr.node_ids) == 4  # 4 distinct nodes
    assert csr.values.numel() == 2


def test_version_checkout(mesh_runtime: MeshRuntime) -> None:
    """Append an edge, note its version, append another, then read the old version."""
    now = datetime.now(UTC)
    e1 = Edge(source_id=ULID(), target_id=ULID(), weight=1.0, born_at=now, last_fired_at=now)
    mesh_runtime.edges.append_edge(e1)
    tbl = mesh_runtime.edges.edge_table
    vers = tbl.list_versions()
    v1 = vers[-1]["version"]

    e2 = Edge(source_id=ULID(), target_id=ULID(), weight=0.5, born_at=now, last_fired_at=now)
    mesh_runtime.edges.append_edge(e2)

    tbl.checkout(v1)
    assert tbl.count_rows() == 1
    tbl.checkout_latest()
    assert tbl.count_rows() == 2
