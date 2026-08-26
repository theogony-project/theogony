"""Scale edges by whether their relation resolved against a curated vocabulary.

Lives beside the substrate rather than inside `mesh.retrieval` for the same
reason `relation_pids` does: both the retrieval path and the runtime's CSR
cache need it, and importing it from `mesh.retrieval` into the runtime would
point the dependency backwards.

An edge saying `father_of` and an edge saying `co_mentions_in_paragraph` are
not the same kind of claim. The first asserts a relation and resolves to a
Wikidata property; the second records that two entities appeared in one
paragraph. Propagation treats them identically, and on the founding mesh the
second kind outnumbers the first fifteen to one.

This is the read-side dual of the distinction MESH_SUBSTRATE draws in
§"Asserted relations and observed adjacency", and close kin to frame routing
next door: that scales an edge by the epistemic consistency of its endpoints,
this scales it by the epistemic status of its relation. Neither invents a new
primitive; both re-weight an existing adjacency before Spreading Activation
runs over it.

PAIR-LEVEL, and the docstring says so because the difference is measurable.
The typing is read from :meth:`MeshRuntime.descriptor_index`, which is keyed by
node pair, so every edge between two nodes joined by a typed relation is scaled
— including the co-mention running alongside it. Boosting only the typed edge
itself scores about two entities better (91 vs 89 of 111), but needs the
descriptor as a column on the edge table rather than a JSON payload. Two
entities did not justify the migration; the numbers below are what this code
actually does, not what the better version would.

MEASURED through this lever on the founding mesh, 47 gold questions, top_k=50,
equal tick count. The genealogical/narrative split comes from the `kind` field on
each gold question (PHX-1080), not from a regex written at the point of
measurement — the previous version of this table used the latter and its split
columns did not reproduce:

    boost   total   genealogical   narrative   entities   fully answered
    1 (off)   74%            68%         86%     82/111            33/47
    3         79%            76%         86%     88/111            36/47
    10        80%            77%         86%     89/111            35/47
    30        80%            77%         86%     89/111            35/47
    100       78%            75%         86%     87/111            33/47

Narrative recall is flat at 86% across the whole range: the lever does not help
those questions and does not cost them either. Everything it buys is on the
genealogical side, +8 points at boost 3, where three questions improve and none
regress. The gain is concentrated rather than spread — the questions that move
are enumerations, where the answer is a set of siblings that typed edges connect
directly and structural edges bury: `iapetus-sons` goes 0/3 to 3/3,
`cronus-children` 3/5 to 5/5.

THREE CONTROLS, run on hand-built graphs because the lever itself cannot
express them, at an edge-level boost of 30. Aggregate only, since these predate
the checked-in kinds:

    boosting all 6,388 asserted edges       78%
    boosting 1,237 random asserted edges    76%
    boosting the 1,237 typed edges          82%

So part of the effect is merely "asserted beats structural" — but typed beats a
same-size random asserted sample by six points. The Wikidata typing carries
signal of its own.

WHY WEIGHTING RATHER THAN SELECTING. Restricting propagation to typed edges
alone scores 76% aggregate: better on genealogy, fourteen points worse on
narrative questions, because the typed subgraph reaches only 121 of 163 gold
entities. Weighting keeps every node reachable and reorders them. PHX-1066
caught a -10 narrative regression hiding under a +2 aggregate; selection walks
into that trap and weighting does not.

DEFAULT OFF, and the reason has changed. It used to be "the gold set is 66%
genealogical because the corpus is, which is exactly the shape this favours" —
a number carried over from the retired 32-question set (PHX-1073 corrected the
set five days before this file quoted it). The checked-in labelling says 55% by
question, 68% by entity, and narrative is untouched rather than traded away, so
the bias argument does not carry the decision on its own.

What does: this has been measured on one corpus, one gold set, and it moves
exactly one question kind. A default that helps genealogy and does nothing else
is a default tuned to Hesiod. It ships as a lever with its measurements
attached, like ``degree_beta`` and ``hub_mask_top_n`` (PHX-1042, PHX-1070).
"""

from __future__ import annotations

import torch

from theogony.mesh.relation_pids import pid_for
from theogony.mesh.storage.edges import EdgeCSR


def typed_edge_mask(csr: EdgeCSR, descriptors: dict[tuple[str, str], str | None]) -> torch.Tensor:
    """Boolean mask over ``csr`` edge positions: does this edge resolve to a P-ID?

    ``descriptors`` is :meth:`MeshRuntime.descriptor_index`, which is cached on
    the edge mutation generation — a filtered metadata query costs ~194 ms and
    this must not pay it per call.
    """
    n = len(csr.node_ids)
    if n == 0 or csr.col_indices.numel() == 0:
        return torch.zeros(0, dtype=torch.bool)
    counts = csr.crow_indices[1:] - csr.crow_indices[:-1]
    src_of_edge = torch.repeat_interleave(torch.arange(n, dtype=torch.int64), counts).tolist()
    tgt_of_edge = csr.col_indices.tolist()
    ids = csr.node_ids
    return torch.tensor(
        [
            pid_for(descriptors.get((ids[s], ids[t]))) is not None
            for s, t in zip(src_of_edge, tgt_of_edge, strict=True)
        ],
        dtype=torch.bool,
    )


def build_typed_boosted_csr(
    csr: EdgeCSR,
    descriptors: dict[tuple[str, str], str | None],
    *,
    boost: float,
) -> EdgeCSR:
    """Return a copy of ``csr`` with P-ID-carrying edges scaled by ``boost``.

    ``boost=1.0`` is the identity transform and is returned unchanged, so the
    lever costs nothing while it is off.
    """
    if boost == 1.0 or len(csr.node_ids) == 0 or csr.col_indices.numel() == 0:
        return csr
    mask = typed_edge_mask(csr, descriptors)
    scale = torch.where(mask, torch.tensor(float(boost)), torch.tensor(1.0))
    return EdgeCSR(
        crow_indices=csr.crow_indices,
        col_indices=csr.col_indices,
        values=csr.values.to(torch.float32) * scale,
        node_ids=csr.node_ids,
        id_to_index=csr.id_to_index,
    )
