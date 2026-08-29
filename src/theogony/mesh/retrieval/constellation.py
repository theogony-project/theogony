"""Constellation assembly for mesh retrieval (Step S3c).

A **Constellation** is the substrate's answer shape: not raw text, but the activated
sub-graph — the nodes Spreading Activation lit up, the edges among them, the provenance
anchors that ground them, and the *gaps* the substrate is honest about (no source anchor
reached, unconsolidated candidates in the working set, disconnected activation). A
consumer (an agent, the Cockpit, an MNLM) reasons over this structured working set.

This is the read-side dual of MESH_RETRIEVAL §"What a query returns". It carries no
synthesis and no LLM — assembly is pure substrate bookkeeping over an activation vector.
"""

from __future__ import annotations

import torch
from pydantic import BaseModel, ConfigDict, Field

from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.storage.edges import EdgeCSR, descriptor_rank


class ConstellationNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str
    qid: str | None = None
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    tier: int = 1
    activation: float = 0.0
    is_source_anchor: bool = False
    is_candidate: bool = False
    is_seed: bool = False


class ConstellationEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    source_name: str
    target_name: str
    weight: float
    relation_descriptor: str | None = None


class Constellation(BaseModel):
    """Structured working set returned by a single query."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    operator: str = "ppr"
    frame_routed: bool = False
    seed_node_ids: list[str] = Field(default_factory=list)
    nodes: list[ConstellationNode] = Field(default_factory=list)
    edges: list[ConstellationEdge] = Field(default_factory=list)
    source_anchor_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


def _display_name(node_id: str, description: str | None, tags: list[str], qid: str | None) -> str:
    if description:
        return description
    if tags:
        return tags[0]
    if qid:
        return qid
    return node_id


# How far past `top_k` to look so that anchors displaced from the answer budget
# can be replaced by content. Six anchors in a top-30 was the worst case measured.
_ANCHOR_HEADROOM = 16

# Anchors kept for provenance once they no longer compete for answer slots. The
# gap report needs at least one; a few give redundancy without crowding.
_PROVENANCE_ANCHORS = 3


def assemble_constellation(
    runtime: MeshRuntime,
    activation: torch.Tensor,
    csr: EdgeCSR,
    *,
    top_k: int = DEFAULT_TOP_K,
    seed_indices: set[int] | None = None,
    operator: str = "ppr",
    query: str | None = None,
    frame_routed: bool = False,
    max_edges: int = 200,
) -> Constellation:
    """Turn an activation vector into a structured Constellation."""
    seed_indices = seed_indices or set()
    n = len(csr.node_ids)
    if n == 0 or activation.numel() == 0:
        return Constellation(
            query=query,
            operator=operator,
            frame_routed=frame_routed,
            gaps=["empty mesh — no nodes or no edges to activate"],
        )

    # Over-fetch, because source anchors must not eat the answer budget. Every
    # entity in a paragraph is wired to that paragraph's anchor, so anchors are
    # the highest-degree nodes in the mesh and propagation floods them — on the
    # founding mesh they took 33 of 240 top-30 slots across eight questions
    # (13.8%) while carrying nothing to read: "text paragraph: Theogony
    # batch_01". They are provenance, and stay for it; they just ride along
    # outside `top_k` rather than inside it (PHX-1042).
    #
    # ---
    #
    # `MESH_IMPLEMENTATION` §"Damping and stop conditions" specifies a
    # minimum-activation threshold "default ≈ 0.05" per node, and says correctness
    # comes from damping plus that threshold. **There is no threshold here**: nodes
    # are kept on `v > 0.0` and cut by `top_k`.
    #
    # Adding the documented one would not be a fix. Measured over the 47 gold
    # questions: a median of 9 nodes clear 0.05 (min 5, max 23) against a budget of
    # 50, the 50th-ranked activation is 0.0106, and the peak is 0.1903. The figure
    # is calibrated for `x_{t+1} = damping · A · x_t + injection`, where activation
    # accumulates; what runs is PPR — mass-preserving, alpha 0.15, 12 iterations —
    # on a different scale entirely. The budget is doing the stopping, and doing it
    # on the right scale (PHX-1095).
    k = min(top_k + _ANCHOR_HEADROOM, n)
    top_vals, top_idx = torch.topk(activation, k)
    prelim = [
        (int(i), float(v))
        for i, v in zip(top_idx.tolist(), top_vals.tolist(), strict=True)
        if v > 0.0
    ]
    prelim_ids = [csr.node_ids[i] for i, _ in prelim]
    prelim_hydrated = runtime.nodes.get_consolidated_many(prelim_ids)

    content: list[tuple[int, float]] = []
    anchors: list[tuple[int, float]] = []
    for idx, act in prelim:
        cn = prelim_hydrated.get(csr.node_ids[idx])
        (anchors if (cn is not None and cn.is_source_anchor) else content).append((idx, act))
    keep = content[:top_k] + anchors[:_PROVENANCE_ANCHORS]
    if not keep:
        return Constellation(
            query=query,
            operator=operator,
            frame_routed=frame_routed,
            seed_node_ids=[csr.node_ids[i] for i in seed_indices if 0 <= i < n],
            gaps=["no activation — seeds did not reach any connected node"],
        )

    topk_set = {i for i, _ in keep}
    # Already hydrated above in one read: per-node fetches cost a Lance query
    # each (4.3 ms measured), which dominated assembly for no structural reason.
    hydrated = prelim_hydrated

    nodes: list[ConstellationNode] = []
    candidate_count = 0
    for idx, act in keep:
        node_id = csr.node_ids[idx]
        cn = hydrated.get(node_id)
        if cn is None:
            nodes.append(
                ConstellationNode(
                    node_id=node_id, name=node_id, activation=act, is_seed=idx in seed_indices
                )
            )
            continue
        qid = cn.qids[0].qid if cn.qids else None
        if cn.is_candidate:
            candidate_count += 1
        nodes.append(
            ConstellationNode(
                node_id=node_id,
                name=_display_name(node_id, cn.description, cn.tags, qid),
                qid=qid,
                tags=cn.tags[:8],
                description=cn.description,
                tier=cn.consolidation_tier,
                activation=act,
                is_source_anchor=cn.is_source_anchor,
                is_candidate=cn.is_candidate,
                is_seed=idx in seed_indices,
            )
        )

    name_by_id = {node.node_id: node.name for node in nodes}
    # Cached on the edge mutation generation, like the CSR: building the index
    # costs 290 ms on the founding mesh, and it must not be paid per query. See
    # `EdgeStore.descriptor_index` for the measured breakdown — the dominant cost
    # is the JSON parse, not the filter, which is the opposite of what the note
    # here used to claim.
    descriptors = runtime.descriptor_index()

    # One row per node PAIR, not per CSR position. Two nodes may be joined by
    # several distinct relations — `Theogony -> Homer` carries nine on the
    # founding mesh — and the CSR holds a position for each. The descriptor index
    # is keyed by pair, so emitting a row per position printed the pair's single
    # winning descriptor once per position: "Theogony was jealous of Homer", four
    # times in one Constellation, spending four slots to say one thing. Measured
    # across single-seed constellations, 28-50% of the edge budget went to such
    # repetitions (PHX-1088).
    activation_by_index = {idx: act for idx, act in keep}
    best: dict[tuple[int, int], float] = {}
    for src_idx, _ in keep:
        start = int(csr.crow_indices[src_idx].item())
        end = int(csr.crow_indices[src_idx + 1].item())
        for pos in range(start, end):
            tgt_idx = int(csr.col_indices[pos].item())
            if tgt_idx not in topk_set:
                continue
            key = (src_idx, tgt_idx)
            value = float(csr.values[pos].item())
            if value > best.get(key, 0.0):
                best[key] = value

    # Ordered by how strongly the query activated the *endpoints*, not by edge
    # weight. The CSR value sums a pair's parallel edges, so weight ranks pairs by
    # how many ways they are connected rather than by how much they bear on the
    # question. `Theogony -> Homer` summed to 6.382 across nine relations and
    # outranked `Theia -> Helius` at 0.859 — on a query asking which children
    # Theia bore, whose answer is exactly that edge. Activation is what the query
    # produced; weight is what the corpus happened to repeat.
    def _claim(src: int, tgt: int) -> int:
        """How much the relation between two nodes claims (PHX-1078's ranking)."""
        return descriptor_rank(descriptors.get((csr.node_ids[src], csr.node_ids[tgt])))

    # One row per *unordered* pair, keeping the direction that claims more. Both
    # directions are stored and both are real, but they describe the same join:
    # `Theia --was subject in love to--> Hyperion` and `Hyperion
    # --co_mentions_in_paragraph--> Theia` sat next to each other at the top of a
    # Constellation, the second saying nothing the first had not.
    undirected: dict[tuple[int, int], tuple[int, int, float]] = {}
    for (src, tgt), weight in best.items():
        key = (src, tgt) if src <= tgt else (tgt, src)
        held = undirected.get(key)
        if held is None or (_claim(src, tgt), weight) > (_claim(held[0], held[1]), held[2]):
            undirected[key] = (src, tgt, weight)

    # Ordered by how strongly the query activated the endpoints, then by how much
    # the relation claims, then by weight.
    def _edge_key(edge: tuple[int, int, float]) -> tuple[float, int, float]:
        src, tgt, weight = edge
        return (
            min(activation_by_index.get(src, 0.0), activation_by_index.get(tgt, 0.0)),
            _claim(src, tgt),
            weight,
        )

    raw_edges = sorted(undirected.values(), key=_edge_key, reverse=True)

    edges: list[ConstellationEdge] = []
    for src_idx, tgt_idx, weight in raw_edges[:max_edges]:
        sid = csr.node_ids[src_idx]
        tid = csr.node_ids[tgt_idx]
        descriptor = descriptors.get((sid, tid))
        edges.append(
            ConstellationEdge(
                source_id=sid,
                target_id=tid,
                source_name=name_by_id.get(sid, sid),
                target_name=name_by_id.get(tid, tid),
                weight=weight,
                relation_descriptor=descriptor,
            )
        )

    source_anchor_ids = [node.node_id for node in nodes if node.is_source_anchor]

    gaps: list[str] = []
    if not source_anchor_ids:
        gaps.append("no source-anchored provenance reached in this working set")
    if candidate_count:
        gaps.append(f"{candidate_count} unconsolidated candidate node(s) in working set")
    if not edges:
        gaps.append("activated nodes are not directly connected (multi-hop activation only)")

    return Constellation(
        query=query,
        operator=operator,
        frame_routed=frame_routed,
        seed_node_ids=[csr.node_ids[i] for i in seed_indices if 0 <= i < n],
        nodes=nodes,
        edges=edges,
        source_anchor_ids=source_anchor_ids,
        gaps=gaps,
    )
