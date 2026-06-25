"""Frame routing (S3c): masked-SpMV reweighting by query-frame consistency."""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.retrieval.frame_routing import build_frame_routed_csr, frame_consistency
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import build_csr_from_edges


def _triangle() -> tuple[list[str], object]:
    now = datetime.now(UTC)
    ids = sorted(str(ULID()) for _ in range(3))
    edges = [
        Edge(source_id=ids[0], target_id=ids[1], weight=1.0, born_at=now, last_fired_at=now),
        Edge(source_id=ids[1], target_id=ids[2], weight=1.0, born_at=now, last_fired_at=now),
    ]
    return ids, build_csr_from_edges(edges)


def test_zero_query_frame_is_neutral() -> None:
    frames = torch.tensor([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    cons = frame_consistency(frames, [0.0, 0.0])
    assert torch.allclose(cons, torch.ones(3))


def test_zero_node_frame_is_neutral() -> None:
    frames = torch.tensor([[1.0, 0.0], [0.0, 0.0]])  # node 1 has no frame
    cons = frame_consistency(frames, [1.0, 0.0])
    assert cons[0] > 0.99
    assert cons[1] == 1.0  # absent frame never suppresses


def test_opposing_frame_clamps_to_zero() -> None:
    frames = torch.tensor([[1.0, 0.0], [-1.0, 0.0]])
    cons = frame_consistency(frames, [1.0, 0.0])
    assert cons[0] > 0.99
    assert cons[1] == 0.0


def test_zero_query_frame_keeps_csr_identical() -> None:
    """No query frame -> frame routing is the identity transform (current-seed no-op)."""
    ids, csr = _triangle()
    frames = torch.tensor([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    routed = build_frame_routed_csr(csr, frames, [0.0, 0.0])
    assert torch.allclose(routed.values, csr.values)


def test_hard_threshold_zeros_inconsistent_edges() -> None:
    ids, csr = _triangle()
    # Node 0 aligned with query frame; nodes 1,2 opposed.
    frames = torch.tensor([[1.0, 0.0], [-1.0, 0.0], [-1.0, 0.0]])
    routed = build_frame_routed_csr(csr, frames, [1.0, 0.0], threshold=0.5)
    # Edge 1->2 connects two opposed nodes -> scale 0 -> masked.
    idx_1 = csr.id_to_index[ids[1]]
    start = int(csr.crow_indices[idx_1].item())
    end = int(csr.crow_indices[idx_1 + 1].item())
    assert float(routed.values[start:end].sum().item()) == 0.0
