"""Tests for the Lance-backed edge dedup index (PHX-1033)."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import EdgeStore


def _edge(source: ULID, target: ULID, *, relation_descriptor: str | None = None) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=source,
        target_id=target,
        weight=1.0,
        born_at=now,
        last_fired_at=now,
        relation_descriptor=relation_descriptor,
    )


def test_dedup_key_is_deterministic_and_relation_sensitive() -> None:
    a = EdgeStore.dedup_key("S", "T", "located_in")
    assert a == EdgeStore.dedup_key("S", "T", "located_in")
    assert a != EdgeStore.dedup_key("S", "T", "capital_of")  # relation matters
    assert a != EdgeStore.dedup_key("T", "S", "located_in")  # direction matters
    assert EdgeStore.dedup_key("S", "T", None) == EdgeStore.dedup_key("S", "T", "")


def test_append_edges_populates_dedup_index(mesh_runtime: MeshRuntime) -> None:
    s, t, u = ULID(), ULID(), ULID()
    edges = [_edge(s, t, relation_descriptor="r1"), _edge(s, u, relation_descriptor="r2")]
    mesh_runtime.edges.append_edges(edges)

    keys = mesh_runtime.edges.load_dedup_keys()
    assert keys == {
        mesh_runtime.edges.dedup_key(str(s), str(t), "r1"),
        mesh_runtime.edges.dedup_key(str(s), str(u), "r2"),
    }


def test_ensure_dedup_index_backfills_legacy_workspace(mesh_runtime: MeshRuntime) -> None:
    s, t = ULID(), ULID()
    mesh_runtime.edges.append_edges([_edge(s, t, relation_descriptor="r1")])
    # Simulate a workspace whose edges predate the index.
    mesh_runtime.edges.dedup_index.delete("true")
    assert mesh_runtime.edges.load_dedup_keys() == set()

    mesh_runtime.edges._ensure_dedup_index()
    assert mesh_runtime.edges.load_dedup_keys() == {
        mesh_runtime.edges.dedup_key(str(s), str(t), "r1")
    }


def test_replace_all_edges_resyncs_dedup_index(mesh_runtime: MeshRuntime) -> None:
    s, t, u = ULID(), ULID(), ULID()
    mesh_runtime.edges.append_edges([_edge(s, t, relation_descriptor="r1")])
    mesh_runtime.edges.replace_all_edges([_edge(s, u, relation_descriptor="r2")])

    assert mesh_runtime.edges.load_dedup_keys() == {
        mesh_runtime.edges.dedup_key(str(s), str(u), "r2")
    }


def test_load_dedup_keys_empty_workspace(mesh_runtime: MeshRuntime) -> None:
    assert mesh_runtime.edges.load_dedup_keys() == set()
