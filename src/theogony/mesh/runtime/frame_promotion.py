"""Entities inherit the stance of the paragraphs that speak about them (PHX-1107).

`MESH_RETRIEVAL.md` §"Implementation notes" names this in one clause: the frame
vector "is mutable by Oneiros during consolidation (when many chunks with
consistent frames consolidate, the consolidated node inherits the dominant
frame)". Nothing did it, and the reason it matters only became visible once
frames carried anything.

**The measurement that forced this.** With stances on chunks and neutral frames
on entities, the seven contradiction questions returned both sides 86% of the
time — and routing on `any`, `contradiction` and `what_is` gave *identical*
numbers. The frames were in the substrate and the retrieval could not see them,
because a Constellation is made of entities and 82% of the entities held no
stance at all. `frame_consistency` is 1.0 for a neutral node by construction,
so every profile scaled every edge by 1.0. The same shape as PHX-1104: the
substrate held something the operator had no way to read.

**What inheritance does.** Each consolidated node takes the mean of the frames
of the chunks that mention it. Mean rather than mode, because the interesting
signal is a *mixture*: a figure named in forty settled paragraphs and two
disputed ones should read as mostly settled and slightly disputed, and a mode
would erase the two. The doctrine's word is "dominant", and a centroid is the
dominant direction with the minority still in it.

Source anchors stay neutral — they are containers, not claims — and so does any
node no chunk mentions.

This is deliberately *not* folded into `run_minimal_tick`. The tick is the
substrate's hot maintenance pass and rewrites the whole node table already;
adding an inheritance step there would make every tick pay for a pass whose
input only changes when new text is read or a contradiction is found. It runs
after those, which is when it has something new to say.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from theogony.mesh.runtime.contradiction import MENTION_CONTEXTS
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge

FRAME_PROMOTION_ACTION = "mesh_frame_promotion"


@dataclass
class PromotionResult:
    nodes: int = 0
    promoted: int = 0
    unchanged: int = 0
    without_witness: int = 0
    anchors_skipped: int = 0
    audit_id: str | None = None
    elapsed_s: float = 0.0
    stance_mix: dict[str, int] = field(default_factory=dict)


def mean_frame(frames_in: Sequence[Sequence[float]], dim: int) -> list[float]:
    """Centroid of several frames, renormalised to unit length.

    An empty input, or frames that cancel exactly, yield the zero vector —
    which every consumer reads as neutral rather than as opposition.
    """
    if not frames_in:
        return [0.0] * dim
    total = [0.0] * dim
    for frame in frames_in:
        for i in range(min(dim, len(frame))):
            total[i] += float(frame[i])
    norm = sum(v * v for v in total) ** 0.5
    if norm < 1e-12:
        return [0.0] * dim
    return [v / norm for v in total]


def witnesses_by_entity(edges: Sequence[Edge]) -> dict[str, list[str]]:
    """Chunk ids that mention each entity, from the `mentions` edges."""
    out: dict[str, list[str]] = {}
    for edge in edges:
        if edge.creation_context in MENTION_CONTEXTS:
            out.setdefault(str(edge.target_id), []).append(str(edge.source_id))
    return out


def promoted_frames(
    nodes: Sequence[ConsolidatedNode],
    chunks: Mapping[str, ChunkNode],
    mentions: Mapping[str, Sequence[str]],
    *,
    dim: int,
) -> dict[str, list[float]]:
    """The frame each entity should carry, given the paragraphs about it."""
    out: dict[str, list[float]] = {}
    for node in nodes:
        if node.is_source_anchor:
            continue
        witness_frames = [
            chunks[cid].frame_vector for cid in mentions.get(str(node.id), ()) if cid in chunks
        ]
        if not witness_frames:
            continue
        out[str(node.id)] = mean_frame(witness_frames, dim)
    return out


def run_frame_promotion(
    runtime: MeshRuntime, *, apply: bool = True, log: Any = None
) -> PromotionResult:
    """Give every entity the mean stance of the paragraphs that mention it."""
    started = time.monotonic()
    say = log or (lambda _msg: None)
    dim = runtime.frame_dim
    edges = runtime.edges.load_all_edges()
    chunks = {str(c.id): c for c in runtime.nodes.iter_chunks(page_size=1024)}
    nodes = list(runtime.nodes.iter_consolidated(page_size=1024))
    mentions = witnesses_by_entity(edges)
    wanted = promoted_frames(nodes, chunks, mentions, dim=dim)

    result = PromotionResult(nodes=len(nodes))
    result.anchors_skipped = sum(1 for n in nodes if n.is_source_anchor)
    updated: list[ConsolidatedNode] = []
    for node in nodes:
        frame = wanted.get(str(node.id))
        if frame is None:
            if not node.is_source_anchor:
                result.without_witness += 1
            updated.append(node)
            continue
        if list(node.frame_vector) == frame:
            result.unchanged += 1
            updated.append(node)
            continue
        result.promoted += 1
        updated.append(node.model_copy(update={"frame_vector": frame}))

    say(
        f"{result.nodes} nodes: {result.promoted} promoted, {result.unchanged} unchanged, "
        f"{result.without_witness} without a witnessing paragraph, "
        f"{result.anchors_skipped} anchors left neutral"
    )
    if apply and result.promoted:
        runtime.nodes.replace_all_consolidated(updated)
        runtime.invalidate_csr_cache()

    result.elapsed_s = time.monotonic() - started
    result.audit_id = runtime.audit.append(
        action=FRAME_PROMOTION_ACTION,
        detail={
            "nodes": result.nodes,
            "promoted": result.promoted,
            "unchanged": result.unchanged,
            "without_witness": result.without_witness,
            "anchors_skipped": result.anchors_skipped,
            "applied": apply,
            "elapsed_s": round(result.elapsed_s, 2),
        },
    )
    return result
