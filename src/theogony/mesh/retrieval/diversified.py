"""Diversified injection for mesh retrieval (Step S3b).

Seed selection is the first defence against the failure mode the substrate exists to
avoid: a query that lands on one dense hub, floods activation into that hub's
neighbourhood, and returns a monotonous, biased working set. MESH_RETRIEVAL §"Diversified
injection" prescribes two mechanisms, both implemented here as pure, tested functions:

1. **Maximum Marginal Relevance (MMR)** — pick seeds that are each relevant to the query
   *and* mutually dissimilar, so the injected set spans the query's semantic neighbourhood
   instead of clustering on its single closest match.
2. **Weight-class stratification** — bucket candidate seeds by node potential (in-strength)
   and cap how many seeds may come from the top "hub" class, so a few giant nodes cannot
   monopolise the injection.

:func:`select_seeds` combines both and returns a ``{csr_index: weight}`` map ready for
:meth:`theogony.mesh.retrieval.propagation.Propagator.propagate`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch

from theogony.mesh.stratification import WeightClasses, class_seats


@dataclass(frozen=True)
class SeedCandidate:
    """A retrieval seed candidate (one ANN hit mapped onto the edge CSR)."""

    index: int  # CSR row index
    node_id: str
    vector: Sequence[float]  # semantic / description vector
    potential: float = 0.0  # weight-class signal (in-strength)
    qid: str | None = None


def _normalized_matrix(rows: Sequence[Sequence[float]]) -> torch.Tensor:
    mat = torch.tensor([list(r) for r in rows], dtype=torch.float32)
    if mat.ndim == 1:
        mat = mat.unsqueeze(0)
    norms = mat.norm(dim=1, keepdim=True).clamp_min(1e-12)
    normalized: torch.Tensor = mat / norms
    return normalized


def mmr_order(
    query_vector: Sequence[float],
    candidate_vectors: Sequence[Sequence[float]],
    *,
    lambda_: float = 0.6,
) -> list[int]:
    """Return candidate positions in Maximum Marginal Relevance order.

    Score of an unselected candidate ``i`` given already-selected ``S`` is
    ``lambda_ * rel(i) - (1 - lambda_) * max_{j in S} sim(i, j)``. Higher ``lambda_``
    favours relevance; lower favours diversity.
    """
    if not candidate_vectors:
        return []
    cand = _normalized_matrix(candidate_vectors)
    query = _normalized_matrix([query_vector])[0]
    relevance = cand @ query  # (M,)
    pair_sim = cand @ cand.t()  # (M, M)
    m = cand.shape[0]
    selected: list[int] = []
    remaining = set(range(m))
    while remaining:
        if not selected:
            nxt = int(torch.argmax(relevance).item())
        else:
            sel_idx = torch.tensor(selected, dtype=torch.int64)
            max_redundancy = pair_sim[:, sel_idx].max(dim=1).values  # (M,)
            mmr = lambda_ * relevance - (1.0 - lambda_) * max_redundancy
            mmr_masked = mmr.clone()
            mmr_masked[sel_idx] = float("-inf")
            nxt = int(torch.argmax(mmr_masked).item())
        selected.append(nxt)
        remaining.discard(nxt)
    return selected


def weight_classes(potentials: Sequence[float], *, n_classes: int = 4) -> list[int]:
    """Assign each candidate a weight class 0..n_classes-1 by quantile of node potential.

    Class ``n_classes - 1`` is the "hub" class (highest potential).
    """
    if not potentials:
        return []
    if n_classes <= 1 or len(potentials) == 1:
        return [0] * len(potentials)
    vals = torch.tensor(list(potentials), dtype=torch.float32)
    qs = torch.tensor([i / n_classes for i in range(1, n_classes)], dtype=torch.float32)
    edges = torch.quantile(vals, qs)
    classes: list[int] = []
    for v in vals:
        cls = int(torch.searchsorted(edges, v, right=True).item())
        classes.append(min(cls, n_classes - 1))
    return classes


def select_seeds(
    query_vector: Sequence[float],
    candidates: Sequence[SeedCandidate],
    *,
    k: int = 8,
    lambda_: float = 0.6,
    n_classes: int = 4,
    max_hub_fraction: float = 0.5,
    weight_classes_global: WeightClasses | None = None,
    min_per_class: int = 1,
) -> dict[int, float]:
    """Pick up to ``k`` diversified, weight-stratified seeds.

    Returns ``{csr_index: weight}`` where weight is the query-cosine relevance
    (floored to a small positive), so closer seeds inject more activation.

    With ``weight_classes_global`` this is stratification as the doctrine
    describes it: classes are a property of the substrate and each one present in
    the pool is guaranteed ``min_per_class`` seats. Without it, the old behaviour
    — quantiles over whichever candidates the ANN returned, and a cap on the
    class that happened to land highest. That fallback exists for callers with no
    runtime to ask, and it is not stratification: measured on the founding mesh
    the pool's median p25 is 3.71 against a global 1.16 (PHX-1091).
    """
    if not candidates or k <= 0:
        return {}

    vectors = [c.vector for c in candidates]
    order = mmr_order(query_vector, vectors, lambda_=lambda_)
    classes = (
        [weight_classes_global.of(c.potential) for c in candidates]
        if weight_classes_global is not None
        else weight_classes([c.potential for c in candidates], n_classes=n_classes)
    )

    query = _normalized_matrix([query_vector])[0]
    cand_mat = _normalized_matrix(vectors)
    relevance = (cand_mat @ query).tolist()

    chosen = class_seats(
        classes,
        order,
        k=k,
        min_per_class=min_per_class if weight_classes_global is not None else 0,
        hub_class=n_classes - 1,
        max_hub_fraction=max_hub_fraction,
    )
    seeds: dict[int, float] = {}
    for pos in chosen:
        seeds[candidates[pos].index] = max(float(relevance[pos]), 1e-3)
    return seeds
