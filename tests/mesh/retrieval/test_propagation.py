"""Propagation operators (S3a) on toy CSR meshes.

These pin the substrate's production Spreading-Activation operators:
- ``raw`` must reproduce the legacy single-seed ``spreading_activation`` exactly,
- ``ppr`` must keep activation local (more mass on/near the seed than ``raw``),
- multi-seed injection must be additive,
- unknown operators must fail loudly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import torch
from ulid import ULID

from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.runtime.spreading import spreading_activation
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import build_csr_from_edges


def _chain(n: int) -> tuple[list[str], object]:
    now = datetime.now(UTC)
    ids = sorted(str(ULID()) for _ in range(n))
    edges = [
        Edge(source_id=ids[i], target_id=ids[i + 1], weight=1.0, born_at=now, last_fired_at=now)
        for i in range(n - 1)
    ]
    return ids, build_csr_from_edges(edges)


def test_raw_matches_legacy_spreading_activation() -> None:
    """The S3 ``raw`` operator must equal the proven single-seed SpMV."""
    ids, csr = _chain(4)
    prop = Propagator(csr)
    x = prop.propagate({csr.id_to_index[ids[0]]: 1.0}, operator="raw", hops=3, damping=0.5)
    legacy = spreading_activation(csr, seed_index=csr.id_to_index[ids[0]], hops=3, damping=0.5)
    assert torch.allclose(x, legacy, atol=1e-6)
    assert x[csr.id_to_index[ids[3]]] == pytest.approx(0.125, rel=1e-5)


def test_degnorm_equals_raw_on_outdegree_one_chain() -> None:
    """On a chain every source has out-degree 1, so row-normalisation is a no-op."""
    ids, csr = _chain(4)
    prop = Propagator(csr)
    raw = prop.propagate({csr.id_to_index[ids[0]]: 1.0}, operator="raw", hops=3, damping=0.5)
    deg = prop.propagate({csr.id_to_index[ids[0]]: 1.0}, operator="degnorm", hops=3, damping=0.5)
    assert torch.allclose(raw, deg, atol=1e-6)


def test_ppr_keeps_mass_local() -> None:
    """PPR with restart retains seed mass and decays with distance (anti-hub-collapse)."""
    ids, csr = _chain(5)
    prop = Propagator(csr)
    seed = csr.id_to_index[ids[0]]
    x = prop.propagate({seed: 1.0}, operator="ppr", ppr_alpha=0.15, ppr_iters=30)
    assert torch.isfinite(x).all()
    # Restart keeps the seed the most-activated node, and activation falls along the chain.
    assert x[seed] >= 0.15
    order = [csr.id_to_index[i] for i in ids]
    vals = [float(x[i]) for i in order]
    assert vals == sorted(vals, reverse=True)


def test_multi_seed_injection_is_additive() -> None:
    ids, csr = _chain(5)
    prop = Propagator(csr)
    a = csr.id_to_index[ids[0]]
    b = csr.id_to_index[ids[2]]
    xa = prop.propagate({a: 1.0}, operator="raw", hops=2, damping=0.5)
    xb = prop.propagate({b: 1.0}, operator="raw", hops=2, damping=0.5)
    xab = prop.propagate({a: 1.0, b: 1.0}, operator="raw", hops=2, damping=0.5)
    assert torch.allclose(xab, xa + xb, atol=1e-6)


def test_empty_mesh_returns_empty_vector() -> None:
    csr = build_csr_from_edges([])
    prop = Propagator(csr)
    x = prop.propagate({0: 1.0}, operator="ppr")
    assert x.numel() == 0


def test_unknown_operator_raises() -> None:
    _, csr = _chain(3)
    prop = Propagator(csr)
    with pytest.raises(ValueError, match="unknown operator"):
        prop.propagate({0: 1.0}, operator="nonsense")
