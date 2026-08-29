"""Single-query retrieval orchestrator (Step S3).

Wires the S3 pieces into one call: a query **vector** in, a :class:`Constellation` out.

    query vector
      -> ANN seeds (vector search over consolidated nodes)
      -> diversified injection (MMR + weight-class stratification)   [S3b]
      -> [optional] frame routing (masked SpMV)                      [S3c]
      -> Spreading Activation (PPR default)                          [S3a]
      -> Constellation assembly                                      [S3c]

The orchestrator is embedder-agnostic: callers pass a query vector already in the
workspace's semantic space (the ``theogony mesh ask`` CLI does the text->vector step).
No synthesis, no LLM.

Retrieval is **read-only by default**. Passing ``hebbian=True`` additionally credits
the traversed edges into the delta buffer, closing the query -> reinforcement ->
tick -> denser-mesh loop; see :func:`append_hebbian_deltas` for what that does and,
importantly, what it is not (one-factor Hebbian, not the doctrine's three-factor RL).
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import torch

from theogony.mesh.retrieval.constellation import (
    Constellation,
    ConstellationNode,
    assemble_constellation,
)
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
from theogony.mesh.retrieval.diversified import SeedCandidate, select_seeds
from theogony.mesh.retrieval.frame_routing import build_frame_routed_csr
from theogony.mesh.retrieval.propagation import Propagator, in_degree
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode
from theogony.mesh.storage.edges import EdgeCSR, in_strength


@dataclass
class RetrievalResult:
    """Constellation plus the operational metadata a RunReport needs."""

    constellation: Constellation
    seed_node_ids: list[str]
    operator: str
    frame_routed: bool
    ann_hit_count: int
    timings_ms: dict[str, float] = field(default_factory=dict)
    hebbian_deltas: int = 0


def append_hebbian_deltas(
    runtime: MeshRuntime,
    constellation: Constellation,
    *,
    learning_rate: float = 0.01,
    max_deltas: int = 64,
) -> int:
    """Reinforce the edges this query actually traversed. Returns the delta count.

    "Fire together, wire together": each edge in the returned Constellation is
    credited in proportion to the product of its endpoints' activation, so the
    paths that carried the answer strengthen and incidental ones barely move. The
    deltas land in the append-only :class:`EdgeDeltaBuffer`; nothing is written to
    Lance here. They are merged, decayed and saturated by the next Oneiros tick
    (``theogony mesh tick``), which is where the substrate's dynamics belong.

    Bounded by ``max_deltas`` (highest co-activation first) so a single broad query
    cannot flood the buffer — the tick's cost is linear in what it drains.

    **This is one-factor Hebbian learning, not the three-factor rule the doctrine
    specifies.** MESH_RETRIEVAL requires a consumer-feedback signal and a rater
    distinct from the consumer; neither exists yet. Reinforcing on co-activation
    alone rewards what the substrate already believed, so it will amplify existing
    structure — including wrong structure. That is why this is opt-in, and why the
    honest description is "the loop is closeable", not "the loop is correct".
    """
    activation = {n.node_id: n.activation for n in constellation.nodes}
    scored: list[tuple[float, str, str, str | None]] = []
    for edge in constellation.edges:
        source_act = activation.get(edge.source_id, 0.0)
        target_act = activation.get(edge.target_id, 0.0)
        if source_act <= 0.0 or target_act <= 0.0:
            continue
        scored.append(
            (source_act * target_act, edge.source_id, edge.target_id, edge.relation_descriptor)
        )

    scored.sort(key=lambda row: row[0], reverse=True)
    written = 0
    for product, source_id, target_id, relation in scored[:max_deltas]:
        runtime.edges.delta.append_hebbian_delta(
            source_id=source_id,
            target_id=target_id,
            weight_delta=learning_rate * product,
            relation_descriptor=relation,
        )
        written += 1
    return written


def _aligned_node_frames(runtime: MeshRuntime, csr: EdgeCSR) -> torch.Tensor:
    """Build a (N, frame_dim) tensor of node frame vectors aligned to CSR order.

    Only invoked when frame routing is requested (opt-in); on the structural seed all
    frames are zero, so the default path never pays this scan.
    """
    dim = runtime.frame_dim
    frames = torch.zeros((len(csr.node_ids), dim), dtype=torch.float32)
    for node in runtime.nodes.load_all_consolidated():
        idx = csr.id_to_index.get(str(node.id))
        if idx is not None and node.frame_vector:
            frames[idx] = torch.tensor(node.frame_vector[:dim], dtype=torch.float32)
    return frames


def _vector_only_constellation(
    runtime: MeshRuntime,
    query_vector: Sequence[float],
    hits: list[ConsolidatedNode],
    *,
    top_k: int,
    operator: str,
    query: str | None,
) -> Constellation:
    """Degenerate fallback when the mesh has no edges: rank ANN hits by cosine."""
    q = torch.tensor(list(query_vector), dtype=torch.float32)
    q = q / q.norm().clamp_min(1e-12)
    scored: list[tuple[float, ConsolidatedNode]] = []
    for h in hits:
        vec = h.semantic_vector
        if not vec:
            continue
        v = torch.tensor(vec, dtype=torch.float32)
        cos = float((v @ q / v.norm().clamp_min(1e-12)).item())
        scored.append((cos, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    nodes = []
    for cos, h in scored[:top_k]:
        qid = h.qids[0].qid if h.qids else None
        name = h.description or (h.tags[0] if h.tags else (qid or str(h.id)))
        nodes.append(
            ConstellationNode(
                node_id=str(h.id),
                name=name,
                qid=qid,
                tags=h.tags[:8],
                description=h.description,
                tier=h.consolidation_tier,
                activation=max(cos, 0.0),
                is_source_anchor=h.is_source_anchor,
            )
        )
    return Constellation(
        query=query,
        operator=operator,
        nodes=nodes,
        gaps=["no edges in mesh — vector-only retrieval (no Spreading Activation)"],
    )


# Words that open a question and are capitalised for that reason alone. Without
# this, "Who" and "What" would be looked up as entity names on every query.
_QUESTION_WORDS = frozenset(
    {
        "who",
        "what",
        "which",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "did",
        "does",
        "do",
        "is",
        "are",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "from",
        "by",
        "for",
        "with",
        "many",
        "much",
    }
)

# A query names a handful of things, not dozens. The cap keeps a long question
# from flooding the seed set and drowning the ANN's contribution.
_MAX_NAME_ANCHORS = 8


def _name_anchor_seeds(
    runtime: MeshRuntime,
    query: str,
    csr: EdgeCSR,
    *,
    max_anchors: int = _MAX_NAME_ANCHORS,
) -> dict[int, float]:
    """Seeds for entities the query names outright.

    Vector search finds nodes that resemble the *question*; the answer to a
    question usually does not resemble it. "What children did Themis bear to
    Zeus?" is answered by Eunomia, Dike and Eirene, which rank 2345, 2578 and
    2764 by cosine because they have nothing in common with the words of the
    question — they are related to something *in* it. Measured on the founding
    gold set, every expected entity sits exactly one hop from an entity the
    question names, against a 6.6% chance baseline (PHX-1068).

    So the entity named in the question is looked up by name, in the index the
    substrate already maintains, and injected as a seed at full strength: an
    exact name match is stronger evidence than any cosine.

    Only capitalised spans are considered — trying every n-gram would match
    common nouns that happen to be node names. This is an English heuristic on an
    English corpus, and it is the honest limitation of this approach rather than
    a hidden one.

    (The original reason given here was cost: "a label read each — 14.5 ms
    indexed, so ~390 ms on a ten-word question". Re-measured 2026-08-26 it is
    **1.61 ms**, and the gold questions produce a median of four capitalised
    spans and seven at worst. The indices arrived after that sentence was
    written. Cost is no longer the argument; ambiguity is.)
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", query or "")
    spans: list[str] = []
    for size in (3, 2, 1):
        for start in range(len(tokens) - size + 1):
            window = tokens[start : start + size]
            if not window[0][:1].isupper():
                continue
            if all(word.lower() in _QUESTION_WORDS for word in window):
                continue
            spans.append(" ".join(window))
    if not spans:
        return {}

    # Narrowest span first. A label matching one node is a name; one matching
    # eighteen is a category, and the two were being served in the order the
    # spans happened to be generated — longest n-gram first. So "In Greek
    # mythology, who is the father of Zeus?" gave `greek mythology` (18 nodes)
    # the whole budget and never looked `Zeus` up at all: two differently-worded
    # questions returned the identical eight anchors, none of them the subject
    # (PHX-1081).
    #
    # Ordering rather than a cut-off, because the cut-off is not there to make:
    # across the 47 gold questions the widest real name is `Hermes` at 11 nodes
    # and the narrowest category word is `mythology` at 15. A threshold would sit
    # in a four-node gap. And rather than a per-span quota, which fixed the broad
    # case by breaking the narrow one — "Who is the father of Zeus?" fell from six
    # anchors to three, because Zeus legitimately answers to six nodes.
    #
    # Costs one label read per span instead of stopping early: 1.61 ms each,
    # median four spans per gold question and seven at worst, so ~6-11 ms.
    matches: list[tuple[int, int, str, list[int]]] = []
    for order, span in enumerate(spans):
        indices = [
            index
            for node in runtime.nodes.find_consolidated_by_labels([span], limit=32)
            if not node.is_source_anchor
            and (index := csr.id_to_index.get(str(node.id))) is not None
        ]
        if indices:
            # Ties broken by the generation order, which is longest n-gram first:
            # between two equally narrow labels the more specific phrase wins.
            matches.append((len(indices), order, span, indices))
    matches.sort(key=lambda m: (m[0], m[1]))

    seeds: dict[int, float] = {}
    for _fanout, _order, _span, indices in matches:
        for index in indices:
            seeds[index] = 1.0
            if len(seeds) >= max_anchors:
                return seeds
    return seeds


# Re-exported so `from ...retrieve import DEFAULT_TOP_K` keeps working; the
# constant and its justification live in `defaults.py` beside its siblings.
DEFAULT_TOP_K = DEFAULT_TOP_K


def retrieve(
    runtime: MeshRuntime,
    query_vector: Sequence[float],
    *,
    operator: str = "ppr",
    top_k: int = DEFAULT_TOP_K,
    k_seeds: int = DEFAULT_K_SEEDS,
    ann_limit: int = 64,
    mmr_lambda: float = 0.6,
    hops: int = 3,
    damping: float = 0.5,
    ppr_alpha: float = 0.15,
    ppr_iters: int = 12,
    degree_beta: float = 0.0,
    hub_mask_top_n: int = 0,
    typed_edge_boost: float = 1.0,
    query_frame: Sequence[float] | None = None,
    frame_threshold: float = 0.0,
    vector_column: str = "semantic_vector",
    name_anchors: bool = True,
    query: str | None = None,
    csr: EdgeCSR | None = None,
    propagator: Propagator | None = None,
    hebbian: bool = False,
    hebbian_learning_rate: float = 0.01,
    hebbian_max_deltas: int = 64,
) -> RetrievalResult:
    """Run one diversified-injection + Spreading-Activation query; return a Constellation.

    ``csr`` / ``propagator`` may be supplied pre-built (and cached by the caller) to skip
    the per-query CSR rebuild — the dominant cost at scale (PHX-1041). When omitted they
    are built from ``runtime``. A supplied ``propagator`` is ignored when frame routing is
    active (the routed adjacency requires a fresh one).

    Two default-off hub-bias levers (PHX-1042), to be tuned by A/B on the emergent judge:
    ``degree_beta`` enables degree-aware damping inside the propagation operator;
    ``hub_mask_top_n`` > 0 zeroes the activation of the top-N global in-degree nodes
    before Constellation assembly (seeds are never masked — they were chosen by
    query-relevant ANN + MMR, not by degree).

    A third, also default-off: ``typed_edge_boost`` > 1.0 scales edges whose relation
    resolves to a Wikidata property, so asserted relations conduct more strongly than
    observed adjacency. On the founding gold set a boost of 3 takes recall 74% -> 79%
    (82 -> 88 of 111 entities, 33 -> 36 questions answered in full) while regressing
    no question at all; higher values buy one more entity and start costing individual
    questions. Weighting rather than *selecting* those edges is what keeps the
    narrative questions whole. See :mod:`theogony.mesh.typed_edges` for the curve, the
    controls, and why it is not on by default (PHX-1070).
    """
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    if csr is None:
        # An explicitly supplied csr is used as given: the caller may already have
        # applied a re-weighting, and silently boosting it again would compound.
        csr = runtime.typed_boosted_csr(typed_edge_boost)
    timings["csr_ms"] = (time.perf_counter() - t0) * 1000.0
    n = len(csr.node_ids)

    t1 = time.perf_counter()
    hits = runtime.nodes.search_consolidated_by_vector(
        list(query_vector), vector_column_name=vector_column, limit=ann_limit
    )
    timings["ann_ms"] = (time.perf_counter() - t1) * 1000.0

    if n == 0:
        constellation = _vector_only_constellation(
            runtime, query_vector, hits, top_k=top_k, operator=operator, query=query
        )
        return RetrievalResult(
            constellation=constellation,
            seed_node_ids=[],
            operator=operator,
            frame_routed=False,
            ann_hit_count=len(hits),
            timings_ms=timings,
        )

    strength = in_strength(csr)
    candidates: list[SeedCandidate] = []
    for h in hits:
        node_id = str(h.id)
        idx = csr.id_to_index.get(node_id)
        if idx is None:
            continue
        vec = h.description_vector if vector_column == "description_vector" else None
        if not vec:
            vec = h.semantic_vector
        if not vec:
            continue
        candidates.append(
            SeedCandidate(
                index=idx,
                node_id=node_id,
                vector=vec,
                potential=float(strength[idx].item()),
                qid=h.qids[0].qid if h.qids else None,
            )
        )
    # Global class boundaries, cached on the runtime by CSR generation. Without
    # them `select_seeds` takes quantiles over whichever candidates the ANN
    # returned, so a node's weight class depended on who else was retrieved
    # (PHX-1091).
    seeds = dict(
        select_seeds(
            list(query_vector),
            candidates,
            k=k_seeds,
            lambda_=mmr_lambda,
            weight_classes_global=runtime.weight_classes(),
        )
    )
    if name_anchors and query:
        t_anchor = time.perf_counter()
        for index, weight in _name_anchor_seeds(runtime, query, csr).items():
            seeds[index] = max(seeds.get(index, 0.0), weight)
        timings["name_anchor_ms"] = (time.perf_counter() - t_anchor) * 1000.0

    active_csr = csr
    frame_routed = False
    if query_frame is not None and any(abs(float(x)) > 0.0 for x in query_frame):
        node_frames = _aligned_node_frames(runtime, csr)
        active_csr = build_frame_routed_csr(
            csr, node_frames, query_frame, threshold=frame_threshold
        )
        frame_routed = True
        propagator = Propagator(active_csr)

    if propagator is None:
        propagator = Propagator(active_csr)

    t2 = time.perf_counter()
    activation = propagator.propagate(
        seeds,
        operator=operator,
        hops=hops,
        damping=damping,
        ppr_alpha=ppr_alpha,
        ppr_iters=ppr_iters,
        degree_beta=degree_beta,
    )
    timings["propagate_ms"] = (time.perf_counter() - t2) * 1000.0

    if hub_mask_top_n > 0 and activation.numel() > 0:
        deg = in_degree(active_csr).to(activation.device)
        top_n = min(hub_mask_top_n, activation.numel())
        hub_indices = torch.topk(deg, top_n).indices.tolist()
        seed_set = set(seeds)
        masked = [int(i) for i in hub_indices if int(i) not in seed_set]
        if masked:
            activation = activation.clone()
            activation[masked] = 0.0

    t3 = time.perf_counter()
    constellation = assemble_constellation(
        runtime,
        activation,
        csr,
        top_k=top_k,
        seed_indices=set(seeds),
        operator=operator,
        query=query,
        frame_routed=frame_routed,
    )
    timings["assemble_ms"] = (time.perf_counter() - t3) * 1000.0

    # Opt-in by design: a query that silently mutates the substrate would make every
    # evaluation non-reproducible and quietly contaminate the retrieval benchmarks.
    deltas = 0
    if hebbian:
        t4 = time.perf_counter()
        deltas = append_hebbian_deltas(
            runtime,
            constellation,
            learning_rate=hebbian_learning_rate,
            max_deltas=hebbian_max_deltas,
        )
        timings["hebbian_ms"] = (time.perf_counter() - t4) * 1000.0

    return RetrievalResult(
        constellation=constellation,
        seed_node_ids=[csr.node_ids[i] for i in seeds if 0 <= i < n],
        operator=operator,
        frame_routed=frame_routed,
        ann_hit_count=len(hits),
        timings_ms=timings,
        hebbian_deltas=deltas,
    )
