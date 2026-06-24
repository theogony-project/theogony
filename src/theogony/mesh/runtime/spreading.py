"""Single-query Spreading Activation as batched SpMV (Step S1 subset).

No diversified injection yet — that is Step S3.  This module provides a pure
pyTorch SpMV for smoke-test purposes only.
"""

from __future__ import annotations

import torch

from theogony.mesh.storage.edges import EdgeCSR

# Suppress the "CSR tensor in beta" and invariant warnings in test output.
torch.sparse.check_sparse_tensor_invariants(False)  # type: ignore[no-untyped-call]


def spreading_activation(
    csr: EdgeCSR,
    *,
    seed_index: int,
    hops: int = 3,
    damping: float = 0.5,
    device: torch.device | None = None,
) -> torch.Tensor:
    """Propagate activation from a single seed along outgoing edges.

    Each hop: ``x ← damping · Aᵀ · x`` where ``A`` is the weighted adjacency
    in CSR form (row = source, column = target).  Returns a dense vector of
    shape ``(N,)``.
    """
    if device is None:
        device = torch.device("cpu")
    n = len(csr.node_ids)
    if n == 0:
        return torch.zeros(0, dtype=torch.float32, device=device)
    adj = torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        csr.values.to(device),
        size=(n, n),
        dtype=torch.float32,
        device=device,
    )
    x = torch.zeros(n, dtype=torch.float32, device=device)
    x[seed_index] = 1.0
    for _ in range(hops):
        incoming = torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1)
        x = damping * incoming
    return x
