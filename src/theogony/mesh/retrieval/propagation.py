"""Spreading-Activation operators for mesh retrieval (Step S3a).

Canonical propagation primitives over the substrate's edge CSR. The eval harness in
``mesh/eval/`` *measures* these; this module is their production home.

Operator menu (chosen empirically — see PHX-1034, measured on the 10k/15k/100k
Wikidata5m subnets):

- ``"raw"``     — Spreading Activation over raw weighted adjacency. Sharpest top-1,
                  but hub-collapses (diffuse energy, long tail).
- ``"degnorm"`` — random-walk (row-normalised) adjacency.
- ``"ppr"``     — personalised PageRank with restart. The **relation-agnostic default**:
                  least hub-collapse, concentrates activation energy locally
                  (~4x tighter than raw on 100k), best mean-rank.

Relation conditioning — the strongest operator when a *query relation* is available —
is the masked final hop in :meth:`Propagator.relation_masked_hop` (relation-conditioned
+ symmetric-norm reached ~80% of trained RotatE on 100k, with no training). It is an
enhancement over the default, not the free-text default, because it needs a relation.

All operators support **multi-seed** injection (a weighted set of seed nodes from
diversified seeding), executed as batched sparse matrix-vector products.
"""

from __future__ import annotations

from collections.abc import Mapping

import torch

from theogony.mesh.storage.edges import EdgeCSR

# Suppress the "CSR/COO tensor in beta" + invariant warnings on the hot path.
torch.sparse.check_sparse_tensor_invariants(False)  # type: ignore[no-untyped-call]

Operator = str  # "raw" | "degnorm" | "ppr"


def _spmv(adj_t: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
    """One sparse matrix-vector product ``adj_t @ x`` (adj_t = adjacency transposed)."""
    out: torch.Tensor = torch.sparse.mm(adj_t, x.unsqueeze(1)).squeeze(1)
    return out


def build_adjacency(csr: EdgeCSR, device: torch.device) -> torch.Tensor:
    """Weighted sparse CSR adjacency (row = source, col = target)."""
    n = len(csr.node_ids)
    return torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        csr.values.to(device),
        size=(n, n),
        dtype=torch.float32,
        device=device,
    )


def row_normalized_values(csr: EdgeCSR) -> torch.Tensor:
    """Edge values divided by each source node's total out-strength (random-walk)."""
    n = len(csr.node_ids)
    counts = csr.crow_indices[1:] - csr.crow_indices[:-1]
    row_idx = torch.repeat_interleave(torch.arange(n, dtype=torch.int64), counts)
    vals = csr.values.to(torch.float32)
    row_sums = torch.zeros(n, dtype=torch.float32).scatter_add_(0, row_idx, vals)
    denom = row_sums[row_idx].clamp_min(1e-12)
    return vals / denom


def build_row_normalized_adjacency(csr: EdgeCSR, device: torch.device) -> torch.Tensor:
    """Random-walk-normalised sparse CSR adjacency."""
    n = len(csr.node_ids)
    return torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        row_normalized_values(csr).to(device),
        size=(n, n),
        dtype=torch.float32,
        device=device,
    )


def in_degree(csr: EdgeCSR) -> torch.Tensor:
    """Incoming-edge count per node."""
    n = len(csr.node_ids)
    return torch.bincount(csr.col_indices, minlength=n).to(torch.float32)


class Propagator:
    """Holds the substrate adjacency and runs Spreading Activation from seed sets."""

    def __init__(self, csr: EdgeCSR, device: torch.device | None = None) -> None:
        self.csr = csr
        self.n = len(csr.node_ids)
        self.device = device or torch.device("cpu")
        self.adj = build_adjacency(csr, self.device) if self.n else None
        self._adj_norm: torch.Tensor | None = None

    @property
    def adj_norm(self) -> torch.Tensor:
        if self._adj_norm is None:
            self._adj_norm = build_row_normalized_adjacency(self.csr, self.device)
        return self._adj_norm

    def _seed_vector(self, seeds: Mapping[int, float]) -> torch.Tensor:
        x = torch.zeros(self.n, dtype=torch.float32, device=self.device)
        for idx, weight in seeds.items():
            if 0 <= idx < self.n:
                x[idx] += float(weight)
        return x

    def propagate(
        self,
        seeds: Mapping[int, float],
        *,
        operator: Operator = "ppr",
        hops: int = 3,
        damping: float = 0.5,
        ppr_alpha: float = 0.15,
        ppr_iters: int = 12,
        degree_beta: float = 0.0,
    ) -> torch.Tensor:
        """Propagate activation from a weighted seed set; return a dense (N,) vector.

        ``degree_beta`` > 0 enables degree-aware damping (PHX-1042): after every hop,
        each node's incoming mass is divided by ``in_degree ** degree_beta``, so global
        in-hubs stop absorbing mass from every seed set. ``0.0`` (default) is the
        unchanged operator; the productive value is decided by A/B on the emergent
        judge, not hardcoded here.
        """
        if self.n == 0 or self.adj is None:
            return torch.zeros(0, dtype=torch.float32, device=self.device)
        penalty: torch.Tensor | None = None
        if degree_beta > 0.0:
            penalty = in_degree(self.csr).to(self.device).clamp_min(1.0).pow(degree_beta)
        e = self._seed_vector(seeds)
        if operator == "raw":
            adj_t = self.adj.t()
            x = e.clone()
            for _ in range(hops):
                x = _spmv(adj_t, x)
                if penalty is not None:
                    x = x / penalty
                x = damping * x
            return x
        if operator == "degnorm":
            adj_t = self.adj_norm.t()
            x = e.clone()
            for _ in range(hops):
                x = _spmv(adj_t, x)
                if penalty is not None:
                    x = x / penalty
                x = damping * x
            return x
        if operator == "ppr":
            adj_t = self.adj_norm.t()
            x = e.clone()
            for _ in range(ppr_iters):
                spread = _spmv(adj_t, x)
                if penalty is not None:
                    spread = spread / penalty
                x = (1.0 - ppr_alpha) * spread + ppr_alpha * e
            return x
        raise ValueError(f"unknown operator: {operator!r}")

    def propagate_frames(
        self,
        seeds: Mapping[int, float],
        *,
        operator: Operator = "ppr",
        hops: int = 3,
        damping: float = 0.5,
        ppr_alpha: float = 0.15,
        ppr_iters: int = 12,
    ) -> list[torch.Tensor]:
        """Like :meth:`propagate`, but return the activation vector after **every**
        iteration — the substrate's forward pass as animation frames (founding-demo
        Beat 1: watching a constellation light up hop by hop). The final frame is
        exactly what :meth:`propagate` returns for the same arguments."""
        if self.n == 0 or self.adj is None:
            return []
        e = self._seed_vector(seeds)
        frames: list[torch.Tensor] = []
        if operator in ("raw", "degnorm"):
            adj_t = (self.adj if operator == "raw" else self.adj_norm).t()
            x = e.clone()
            for _ in range(hops):
                x = damping * _spmv(adj_t, x)
                frames.append(x.clone())
            return frames
        if operator == "ppr":
            adj_t = self.adj_norm.t()
            x = e.clone()
            for _ in range(ppr_iters):
                x = (1.0 - ppr_alpha) * _spmv(adj_t, x) + ppr_alpha * e
                frames.append(x.clone())
            return frames
        raise ValueError(f"unknown operator: {operator!r}")

    def relation_masked_hop(
        self,
        activation: torch.Tensor,
        relation_adj_t: torch.Tensor,
    ) -> torch.Tensor:
        """One relation-masked hop: distribute current activation only along edges of a
        given relation. ``relation_adj_t`` is the transposed adjacency restricted to the
        query relation (row = target, col = source). The relation-conditioning win in
        PHX-1034 is *free multi-hop activation then one of these masked hops*.
        """
        return _spmv(relation_adj_t, activation)
