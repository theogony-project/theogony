"""Spreading Activation on a toy CSR."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import torch

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.runtime.spreading import spreading_activation
from theogony.mesh.schemas import ChunkNode, Edge, SourceProvenance
from theogony.mesh.storage.edges import build_csr_from_edges


def test_line_graph_three_hops_damping() -> None:
    """Chain 0→1→2→3 with unit weights; seed 0; damping 0.5; three hops."""
    now = datetime.now(UTC)
    edges = [
        Edge(
            source_id="n0",
            target_id="n1",
            weight=1.0,
            born_at=now,
            last_fired_at=now,
        ),
        Edge(
            source_id="n1",
            target_id="n2",
            weight=1.0,
            born_at=now,
            last_fired_at=now,
        ),
        Edge(
            source_id="n2",
            target_id="n3",
            weight=1.0,
            born_at=now,
            last_fired_at=now,
        ),
    ]
    csr = build_csr_from_edges(edges)
    assert csr.node_ids == ["n0", "n1", "n2", "n3"]
    seed = csr.id_to_index["n0"]
    x = spreading_activation(csr, seed_index=seed, hops=3, damping=0.5)
    i3 = csr.id_to_index["n3"]
    assert x[i3] == pytest.approx(0.125, rel=1e-5, abs=1e-6)
    assert x[seed] == pytest.approx(0.0, abs=1e-6)


def test_toy_mesh_size_twenty(mesh_runtime: MeshRuntime) -> None:
    """20 nodes in a ring; activation diffuses without NaNs."""
    now = datetime.now(UTC)
    sem = [0.0] * 8
    frm = [0.0] * 4
    src = SourceProvenance(
        source_type="ring",
        source_identifier="toy",
        extracted_at=now,
    )
    for i in range(20):
        mesh_runtime.nodes.append_chunk(
            ChunkNode(
                id=f"n{i:02d}",
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem,
                frame_vector=frm,
                source=src,
                raw_text_ref=f"ref://{i}",
            )
        )
    edges: list[Edge] = []
    for i in range(20):
        edges.append(
            Edge(
                source_id=f"n{i:02d}",
                target_id=f"n{(i + 1) % 20:02d}",
                weight=1.0,
                born_at=now,
                last_fired_at=now,
            )
        )
    for e in edges:
        mesh_runtime.edges.append_edge(e)
    csr = mesh_runtime.rebuild_csr()
    x = spreading_activation(csr, seed_index=csr.id_to_index["n00"], hops=3, damping=0.5)
    assert torch.isfinite(x).all()
