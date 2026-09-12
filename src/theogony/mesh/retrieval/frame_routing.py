"""Frame routing for mesh retrieval (Step S3c).

MESH_RETRIEVAL §"Frame-sensitive resonance" requires that propagation be conditioned on
the *frame* of a query — its polarity / stance / register — so that a query in one frame
does not freely activate edges that only make sense in an incompatible frame (the
refutation / sarcasm / hypothetical failure mode). The mechanism is a **masked SpMV**:
edge values are scaled by how consistent each edge's endpoints are with the active query
frame, before Spreading Activation runs.

This module produces a frame-routed :class:`EdgeCSR` (same structure, reweighted values)
that any :class:`~theogony.mesh.retrieval.propagation.Propagator` can consume unchanged.

**The signal arrived with PHX-1107.** For most of this project the frames were a
salted SHA-256 projection of the node label — 5,002 nodes, 4,977 distinct
vectors, no epistemic content — so routing on them would have masked edges by a
hash, and this module said so. `mesh/frames.py` now supplies real stances:
Kadmos declares one per paragraph and per relation, chunks carry it, entities
and source anchors are neutral (they assert nothing). A neutral frame still
scores ``1.0`` — an absent stance never suppresses propagation — so the
structural seed, which writes zero frames, is unaffected.

**Reachable from outside since PHX-1107** via ``theogony mesh ask
--frame-profile``; before that no caller in `src/` or `scripts/` passed a
``query_frame`` and there was no flag to set one. The profiles live in
`frames.QUERY_PROFILES`; `contradiction` is the one that could not be written
before, because it needs stances the substrate had no way to record.
"""

from __future__ import annotations

from collections.abc import Sequence

import torch

from theogony.mesh.storage.edges import EdgeCSR


def frame_consistency(
    node_frames: torch.Tensor,
    query_frame: Sequence[float],
) -> torch.Tensor:
    """Per-node cosine consistency with the query frame, in ``[0, 1]``.

    Zero-norm frames (query or node) yield ``1.0`` (neutral): an absent frame never
    suppresses propagation. Negative cosines clamp to ``0.0`` (an opposed frame fully
    attenuates rather than flipping sign).
    """
    n = node_frames.shape[0]
    q = torch.tensor(list(query_frame), dtype=torch.float32)
    q_norm = float(q.norm().item())
    if q_norm < 1e-12 or n == 0:
        return torch.ones(n, dtype=torch.float32)
    q = q / q_norm
    node_norms = node_frames.norm(dim=1)
    cos = (node_frames @ q) / node_norms.clamp_min(1e-12)
    cos = cos.clamp(min=0.0, max=1.0)
    # Nodes with a zero frame are neutral (consistency 1.0), not suppressed.
    cos = torch.where(node_norms < 1e-12, torch.ones_like(cos), cos)
    return cos


def build_frame_routed_csr(
    csr: EdgeCSR,
    node_frames: torch.Tensor,
    query_frame: Sequence[float],
    *,
    threshold: float = 0.0,
) -> EdgeCSR:
    """Return a copy of ``csr`` with edge values scaled by endpoint frame consistency.

    Each edge ``s -> t`` is scaled by ``min(consistency[s], consistency[t])`` (an edge is
    only as frame-consistent as its less-consistent endpoint). Edges whose scale falls
    below ``threshold`` are zeroed (hard mask). With an absent query frame this is the
    identity transform.
    """
    n = len(csr.node_ids)
    if n == 0 or csr.col_indices.numel() == 0:
        return csr
    consistency = frame_consistency(node_frames, query_frame)

    counts = csr.crow_indices[1:] - csr.crow_indices[:-1]
    src_of_edge = torch.repeat_interleave(torch.arange(n, dtype=torch.int64), counts)
    tgt_of_edge = csr.col_indices
    edge_scale = torch.minimum(consistency[src_of_edge], consistency[tgt_of_edge])
    if threshold > 0.0:
        edge_scale = torch.where(edge_scale < threshold, torch.zeros_like(edge_scale), edge_scale)
    new_values = csr.values.to(torch.float32) * edge_scale
    return EdgeCSR(
        crow_indices=csr.crow_indices,
        col_indices=csr.col_indices,
        values=new_values,
        node_ids=csr.node_ids,
        id_to_index=csr.id_to_index,
    )
