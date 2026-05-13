"""Spreading Activation propagation on toy CSR meshes.

All IDs in this test are plain strings (the CSR builder compares strings, not
ULIDs).  Since ``Edge.source_id`` / ``.target_id`` are typed as ``ULID`` in the
schema we create ULIDs and keep a mapping to short labels for readability.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import torch
from ulid import ULID

from theogony.mesh.runtime.spreading import spreading_activation
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import build_csr_from_edges


def test_line_graph_three_hops() -> None:
    """Chain 0→1→2→3 with unit weights; seed 0; damping 0.5; 3 hops."""
    now = datetime.now(UTC)
    # Four ULIDs sorted lexicographically match the chain order.
    ids = sorted(str(ULID()) for _ in range(4))
    edges = [
        Edge(source_id=ids[0], target_id=ids[1], weight=1.0, born_at=now, last_fired_at=now),
        Edge(source_id=ids[1], target_id=ids[2], weight=1.0, born_at=now, last_fired_at=now),
        Edge(source_id=ids[2], target_id=ids[3], weight=1.0, born_at=now, last_fired_at=now),
    ]
    csr = build_csr_from_edges(edges)
    x = spreading_activation(csr, seed_index=csr.id_to_index[ids[0]], hops=3, damping=0.5)
    target = csr.id_to_index[ids[3]]
    # x_3 = 0.5 ^ 3 = 0.125
    assert x[target] == pytest.approx(0.125, rel=1e-5)
    assert x[csr.id_to_index[ids[0]]] == pytest.approx(0.0, abs=1e-6)


def test_no_nans_empty_graph() -> None:
    """Edge-less CSR; activation stays zero."""
    csr = build_csr_from_edges([])
    x = spreading_activation(csr, seed_index=0, hops=3, damping=0.5)
    assert x.numel() == 0


def test_twenty_node_ring(mesh_runtime) -> None:
    """20-node ring built on the fixture runtime; activation diffuses without NaNs."""
    from theogony.mesh.schemas import ChunkNode, SourceProvenance

    now = datetime.now(UTC)
    src = SourceProvenance(source_type="ring", source_identifier="toy", extracted_at=now)
    nids: list[str] = []
    for i in range(20):
        nid = str(ULID())
        nids.append(nid)
        mesh_runtime.nodes.append_chunk(
            ChunkNode(
                id=nid,
                born_at=now,
                last_fired_at=now,
                semantic_vector=[0.0] * 8,
                frame_vector=[0.0] * 4,
                source=src,
                raw_text_ref=f"ref://{i}",
            )
        )
    for i in range(20):
        mesh_runtime.edges.append_edge(
            Edge(
                source_id=nids[i],
                target_id=nids[(i + 1) % 20],
                weight=1.0,
                born_at=now,
                last_fired_at=now,
            )
        )
    csr = mesh_runtime.rebuild_csr()
    x = spreading_activation(csr, seed_index=csr.id_to_index[nids[0]], hops=3, damping=0.5)
    assert torch.isfinite(x).all()
