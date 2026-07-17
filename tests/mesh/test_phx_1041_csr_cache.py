"""PHX-1041: columnar CSR build + MeshRuntime query-path cache."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import build_csr_from_columns, build_csr_from_edges


def test_build_csr_from_columns_matches_edge_builder() -> None:
    now = datetime.now(UTC)
    a, b, c = ULID(), ULID(), ULID()
    edges = [
        Edge(
            source_id=a,
            target_id=b,
            weight=1.0,
            frame_consistency=0.5,
            born_at=now,
            last_fired_at=now,
        ),
        Edge(
            source_id=b,
            target_id=c,
            weight=2.0,
            frame_consistency=1.0,
            born_at=now,
            last_fired_at=now,
        ),
    ]
    from_edges = build_csr_from_edges(edges)
    from_cols = build_csr_from_columns(
        [str(a), str(b)],
        [str(b), str(c)],
        [1.0, 2.0],
        [0.5, 1.0],
    )
    assert from_cols.node_ids == from_edges.node_ids
    assert from_cols.crow_indices.tolist() == from_edges.crow_indices.tolist()
    assert from_cols.col_indices.tolist() == from_edges.col_indices.tolist()
    assert from_cols.values.tolist() == pytest.approx(from_edges.values.tolist())


def test_csr_from_store_uses_columns_not_payload(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    source, target = ULID(), ULID()
    mesh_runtime.edges.append_edge(
        Edge(
            source_id=source,
            target_id=target,
            weight=0.75,
            frame_consistency=0.8,
            born_at=now,
            last_fired_at=now,
            relation_descriptor="test_edge",
        )
    )
    csr = mesh_runtime.edges.csr_from_store()
    assert len(csr.node_ids) == 2
    assert csr.values.numel() == 1
    assert float(csr.values[0]) == pytest.approx(0.6)


def test_rebuild_csr_reuses_cache_until_graph_changes(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    mesh_runtime.edges.append_edge(
        Edge(source_id=ULID(), target_id=ULID(), weight=1.0, born_at=now, last_fired_at=now)
    )

    first = mesh_runtime.rebuild_csr()
    second = mesh_runtime.rebuild_csr()
    assert first is second

    mesh_runtime.edges.append_edge(
        Edge(source_id=ULID(), target_id=ULID(), weight=0.5, born_at=now, last_fired_at=now)
    )
    third = mesh_runtime.rebuild_csr()
    assert third is not first
    assert third.values.numel() == 2


def test_invalidate_csr_cache_and_force_rebuild(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    mesh_runtime.edges.append_edge(
        Edge(source_id=ULID(), target_id=ULID(), weight=1.0, born_at=now, last_fired_at=now)
    )
    cached = mesh_runtime.rebuild_csr()
    mesh_runtime.invalidate_csr_cache()
    rebuilt = mesh_runtime.rebuild_csr()
    assert rebuilt is not cached
    forced = mesh_runtime.rebuild_csr(force=True)
    assert forced is not rebuilt


def test_delta_pending_invalidates_csr_cache(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    a, b = ULID(), ULID()
    mesh_runtime.edges.append_edge(
        Edge(source_id=a, target_id=b, weight=1.0, born_at=now, last_fired_at=now)
    )
    before = mesh_runtime.rebuild_csr()
    mesh_runtime.edges.delta.append_hebbian_delta(
        source_id=str(a), target_id=str(b), weight_delta=0.1
    )
    after = mesh_runtime.rebuild_csr()
    assert after is not before


def test_mutation_generation_bumps_on_append(mesh_runtime: MeshRuntime) -> None:
    now = datetime.now(UTC)
    gen0 = mesh_runtime.edges.mutation_generation
    mesh_runtime.edges.append_edge(
        Edge(source_id=ULID(), target_id=ULID(), weight=1.0, born_at=now, last_fired_at=now)
    )
    assert mesh_runtime.edges.mutation_generation == gen0 + 1
    first = mesh_runtime.rebuild_csr()
    second = mesh_runtime.rebuild_csr()
    assert first is second
    assert mesh_runtime.rebuild_csr() is first
