"""Single-query Spreading Activation as sparse SpMV (Step S1 subset)."""

from __future__ import annotations

import torch

from theogony.mesh.storage.edges import EdgeCSR

# PyTorch CSR beta: avoid noisy invariant warnings in CI for well-formed CSR.
torch.sparse.check_sparse_tensor_invariants(False)  # type: ignore[no-untyped-call]


def spreading_activation(
    csr: EdgeCSR,
    *,
    seed_index: int,
    hops: int = 3,
    damping: float = 0.5,
    device: torch.device | None = None,
) -> torch.Tensor:
    """Propagate activation along outgoing edges for ``hops`` steps.

    Update rule per hop: ``x ← damping * (Aᵀ @ x)`` with ``A`` the weighted
    adjacency in CSR form (rows = source, columns = target). The initial vector
    is a one-hot at ``seed_index``.
    """
    if device is None:
        device = torch.device("cpu")
    n = len(csr.node_ids)
    adj = torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        csr.values.to(device),
        size=csr.size,
        dtype=torch.float32,
        device=device,
    )
    x = torch.zeros(n, dtype=torch.float32, device=device)
    x[seed_index] = 1.0
    for _ in range(hops):
        incoming = torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1)
        x = damping * incoming
    return x
