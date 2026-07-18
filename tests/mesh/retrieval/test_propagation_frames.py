"""propagate_frames (founding-demo Beat 1): the SA forward pass as frames.

The animation must be *honest*: the final frame has to be exactly what
``propagate`` returns for the same arguments, frame count must follow the
operator's iteration count, and an empty mesh yields no frames.
"""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import build_csr_from_edges


def _chain(n: int):
    now = datetime.now(UTC)
    ids = sorted(str(ULID()) for _ in range(n))
    edges = [
        Edge(source_id=ids[i], target_id=ids[i + 1], weight=1.0, born_at=now, last_fired_at=now)
        for i in range(n - 1)
    ]
    return ids, build_csr_from_edges(edges)


def test_last_frame_equals_propagate_for_every_operator() -> None:
    ids, csr = _chain(5)
    prop = Propagator(csr)
    seeds = {csr.id_to_index[ids[0]]: 1.0}
    for operator in ("raw", "degnorm", "ppr"):
        frames = prop.propagate_frames(seeds, operator=operator)
        final = prop.propagate(seeds, operator=operator)
        assert frames, operator
        assert torch.allclose(frames[-1], final, atol=1e-6), operator


def test_frame_count_follows_iterations() -> None:
    ids, csr = _chain(4)
    prop = Propagator(csr)
    seeds = {csr.id_to_index[ids[0]]: 1.0}
    assert len(prop.propagate_frames(seeds, operator="raw", hops=2)) == 2
    assert len(prop.propagate_frames(seeds, operator="ppr", ppr_iters=7)) == 7


def test_activation_spreads_hop_by_hop() -> None:
    """The demo moment itself: a node two hops out is dark in frame 1 and lit
    in frame 2."""
    ids, csr = _chain(4)
    prop = Propagator(csr)
    frames = prop.propagate_frames({csr.id_to_index[ids[0]]: 1.0}, operator="raw", hops=3)
    two_hops_out = csr.id_to_index[ids[2]]
    assert float(frames[0][two_hops_out]) == 0.0
    assert float(frames[1][two_hops_out]) > 0.0


def test_empty_mesh_yields_no_frames() -> None:
    prop = Propagator(build_csr_from_edges([]))
    assert prop.propagate_frames({0: 1.0}) == []
