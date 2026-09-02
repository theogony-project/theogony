#!/usr/bin/env python3
"""Which knob makes reinforcement able to hold an edge against decay? (PHX-1102)

    scripts/mesh_hebbian_calibration.py --root data/mesh-founding [--ticks 20]

Measured on the founding mesh: the strongest Hebbian delta a single query can
write is 2.9e-4, one tick of decay on a median-weight edge removes 4.8e-3, and
all 14 ticks the substrate has ever run drained zero reinforcement. The
substrate can only forget (PHX-1100).

Three knobs could change that, and this script simulates each against the real
weight distribution and the real firing pattern of the gold questions, so that
the choice is measured rather than argued:

    rescale   put the operator's activations on the scale the doctrine's
              alpha was written for (max-normalised, seed = 1.0)
    gate      decay only edges that did NOT fire this tick — the rule
              MESH_SUBSTRATE actually states ("edges that are not fired weaken")
    lambda    slow all forgetting

The simulation freezes each query's constellation at what the untouched mesh
returns and replays it every tick. That is a first-order approximation: real
propagation would shift as weights shift. It is enough to answer "does the
most-used edge hold, and does the never-used one still fade" — the two things a
calibration has to get right at once. The live confirmation is the heartbeat
experiment (`mesh_heartbeat.py`).

Reads only. Never writes to the workspace.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import numpy as np

from theogony.mesh.eval.corpus_qa import load_gold
from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder

W_MAX = 1.0
ALPHA = 0.01
LAMBDA = 0.05
MAX_DELTAS = 64


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--ticks", type=int, default=20)
    ap.add_argument("--k-seeds", type=int, default=1)
    ap.add_argument("--top-k", type=int, default=50)
    args = ap.parse_args()

    rt = MeshRuntime.open(args.root)
    edges = rt.edges.load_all_edges()
    n = len(edges)
    w0 = np.array([e.weight for e in edges], dtype=np.float64)
    src = [str(e.source_id) for e in edges]
    tgt = [str(e.target_id) for e in edges]
    key_pos = {
        (s, t, e.relation_descriptor): i
        for i, (s, t, e) in enumerate(zip(src, tgt, edges, strict=True))
    }
    node_ids = sorted(set(src) | set(tgt))
    node_ix = {nid: i for i, nid in enumerate(node_ids)}
    src_ix = np.array([node_ix[s] for s in src])
    tgt_ix = np.array([node_ix[t] for t in tgt])

    gold = sorted(load_gold(), key=lambda q: q.id)
    used = gold[::2]
    emb = BGESmallEnEmbedder()

    # One pass per used question against the untouched mesh: which edges fired
    # (both endpoints in the working set) and which pairs the Hebbian path would
    # credit, with raw and with max-normalised activations.
    fired_masks: list[np.ndarray] = []
    delta_pos: list[np.ndarray] = []
    delta_raw: list[np.ndarray] = []
    delta_norm: list[np.ndarray] = []
    misses = 0
    for gq in used:
        vec = asyncio.run(emb.embed_many([gq.question]))[0]
        c = retrieve(
            rt, vec, query=gq.question, top_k=args.top_k, k_seeds=args.k_seeds, record_firing=False
        ).constellation
        act = {nd.node_id: nd.activation for nd in c.nodes}
        peak = max(act.values()) if act else 1.0
        fired = np.zeros(len(node_ids), dtype=bool)
        for nid in act:
            if nid in node_ix:
                fired[node_ix[nid]] = True
        fired_masks.append(fired[src_ix] & fired[tgt_ix])

        scored = []
        for e in c.edges:
            a, b = act.get(e.source_id, 0.0), act.get(e.target_id, 0.0)
            if a <= 0 or b <= 0:
                continue
            pos = key_pos.get((e.source_id, e.target_id, e.relation_descriptor))
            if pos is None:
                misses += 1
                continue
            scored.append((a * b, (a / peak) * (b / peak), pos))
        scored.sort(reverse=True)
        top = scored[:MAX_DELTAS]
        delta_pos.append(np.array([p for _, _, p in top], dtype=int))
        delta_raw.append(np.array([r for r, _, _ in top]))
        delta_norm.append(np.array([m for _, m, _ in top]))

    fire_count = np.sum(np.stack(fired_masks), axis=0) if fired_masks else np.zeros(n, dtype=int)
    all_raw = np.concatenate(delta_raw) * ALPHA
    all_norm = np.concatenate(delta_norm) * ALPHA
    w_med = float(np.median(w0))
    n_fired = int((fire_count > 0).sum())
    n_all = int((fire_count == len(used)).sum())
    print(f"mesh: {n} edges, {len(node_ids)} nodes; {len(used)} used questions, {misses} misses")
    print(f"edges fired by >=1 used query: {n_fired} ({n_fired / n:.1%}); by all: {n_all}")
    print(f"\none tick of decay at the median weight {w_med:.4f}:  {LAMBDA * w_med**2:.2e}")
    print(
        f"delta per credited edge, raw:   max {all_raw.max():.2e}  median {np.median(all_raw):.2e}"
    )
    print(
        f"delta per credited edge, norm:  max {all_norm.max():.2e}  "
        f"median {np.median(all_norm):.2e}"
    )

    policies = {
        "A decay-all   raw   decay-all  0.05": dict(norm=False, gate=False, lam=LAMBDA),
        "B rescale     norm  decay-all  0.05": dict(norm=True, gate=False, lam=LAMBDA),
        "C gate        raw   unfired    0.05": dict(norm=False, gate=True, lam=LAMBDA),
        "D rescale+gate norm unfired    0.05": dict(norm=True, gate=True, lam=LAMBDA),
        "E lambda/10   raw   decay-all  0.005": dict(norm=False, gate=False, lam=LAMBDA / 10),
    }

    top_fired = np.argsort(-fire_count, kind="stable")[:10]
    never = fire_count == 0

    def row(label: str, w: np.ndarray) -> str:
        return (
            f"{label:38s} {w[top_fired].mean():11.4f} {w[never].mean():11.4f} "
            f"{(w >= 0.999).mean():7.1%} {(w < 0.05).mean():7.1%} {float(np.median(w)):8.4f}"
        )

    print(f"\nafter {args.ticks} ticks, one round of the {len(used)} used questions per tick:")
    print(
        f"{'policy':38s} {'top10 fired':>11s} {'never fired':>11s} "
        f"{'at cap':>7s} {'<0.05':>7s} {'median':>8s}"
    )
    print(row("start", w0))
    for name, p in policies.items():
        w = w0.copy()
        for _ in range(args.ticks):
            fired_this_tick = np.zeros(n, dtype=bool)
            for mask, pos, raw, nrm in zip(
                fired_masks, delta_pos, delta_raw, delta_norm, strict=True
            ):
                if len(pos):
                    np.add.at(w, pos, ALPHA * (nrm if p["norm"] else raw))
                fired_this_tick |= mask
            np.minimum(w, W_MAX, out=w)
            loss = p["lam"] * w**2
            if p["gate"]:
                loss[fired_this_tick] = 0.0
            w = np.maximum(0.0, w - loss)
        print(row(name, w))


if __name__ == "__main__":
    main()
