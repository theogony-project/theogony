#!/usr/bin/env python3
"""Does a substrate that is used answer better on what it was used for? (PHX-1102)

    scripts/mesh_heartbeat.py --root data/mesh-founding --rounds 10

The first falsifiable claim of "the mesh is alive", as a protocol:

    split the gold questions in two halves, used and held-out
    measure retrieval recall on both
    R rounds of: ask every used question (firing recorded) -> tick
    measure both again

If recall on the used half rises while the held-out half does not fall, the
substrate learned from use without narrowing. If both fall, decay is winning and
the calibration is wrong. If used rises and held-out falls, use is crowding out
the rest — the hub pathology the doctrine's saturation rules exist for.

Runs on a COPY of the workspace — one per policy — and deletes nothing you
did not pass in. No LLM, no network, no money: retrieval recall only, because
the answer instrument cannot resolve differences this size (PHX-1096/1097).
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import statistics
from pathlib import Path

from theogony.mesh.eval.corpus_qa import _name_index, _normalise, evaluate, load_gold, summarise
from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--work", default="data/mesh-heartbeat", type=Path, help="copies go here")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--k-seeds", type=int, default=1)
    ap.add_argument("--policies", default="shipped,gate,grow")
    ap.add_argument("--alpha", type=float, default=0.1, help="Hebbian alpha for the grow policy")
    ap.add_argument("--no-normalize", action="store_true", help="grow policy: raw activations")
    args = ap.parse_args()

    emb = BGESmallEnEmbedder()
    cache: dict[str, list[float]] = {}

    def embed(text: str) -> list[float]:
        if text not in cache:
            cache[text] = asyncio.run(emb.embed_many([text]))[0]
        return cache[text]

    gold = sorted(load_gold(), key=lambda q: q.id)
    used, held = gold[::2], gold[1::2]
    print(f"{len(used)} used / {len(held)} held-out questions, k_seeds={args.k_seeds}")

    def recall(rt: MeshRuntime, qs: list) -> tuple[float, int]:
        s = summarise(evaluate(rt, embed, gold=qs, k_seeds=args.k_seeds))
        return s["recall_given_coverage"], int(s["questions_fully_answered"])

    def gold_rank(rt: MeshRuntime, qs: list) -> float:
        """Mean rank of each gold entity's best node within a 200-node working set.

        Recall at top-50 is coarse: it moves only when an entity crosses the
        budget. Rank moves as soon as the activation order does, which is what
        the weight dynamics change first. An entity absent from the mesh counts
        as 201 — constant across rounds, so deltas are unaffected; the founding
        gold set has 100% coverage, so here it never happens.
        """
        names = _name_index(rt)
        ranks: list[float] = []
        for gq in qs:
            c = retrieve(
                rt,
                embed(gq.question),
                query=gq.question,
                k_seeds=args.k_seeds,
                top_k=200,
                record_firing=False,
            ).constellation
            order = {n.node_id: i + 1 for i, n in enumerate(c.nodes)}
            for name in gq.expect:
                ids = names.get(_normalise(name), set())
                ranks.append(min((order.get(i, 201) for i in ids), default=201))
        return statistics.mean(ranks)

    def weights(rt: MeshRuntime) -> tuple[float, float]:
        ws = [e.weight for e in rt.edges.load_all_edges()]
        return statistics.median(ws), max(ws)

    def line(
        r: object,
        u: float,
        uf: int,
        ru: float,
        h: float,
        hf: int,
        rh: float,
        m: float,
        x: float,
        spared: object,
    ) -> str:
        return (
            f"{str(r):>7s} {u:7.1%} {uf:7d} {ru:7.1f} {h:7.1%} {hf:7d} {rh:7.1f} "
            f"{m:7.4f} {x:7.4f} {str(spared):>7s}"
        )

    for policy in args.policies.split(","):
        gate = policy in ("gate", "grow")
        grow = policy == "grow"
        root = args.work / policy
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(args.root, root)
        rt = MeshRuntime.open(root)

        u0, uf0 = recall(rt, used)
        h0, hf0 = recall(rt, held)
        r0u, r0h = gold_rank(rt, used), gold_rank(rt, held)
        m0, x0 = weights(rt)
        extra = f", alpha={args.alpha}, normalize={not args.no_normalize}" if grow else ""
        print(f"\n== {policy}  (decay_gate={gate}, hebbian={grow}{extra}) ==")
        head = ("round", "used", "full", "rank", "held", "full", "rank", "w med", "w max", "spared")
        print(" ".join(f"{h:>7s}" for h in head))
        print(line(0, u0, uf0, r0u, h0, hf0, r0h, m0, x0, "-"))
        for r in range(1, args.rounds + 1):
            for gq in used:
                retrieve(
                    rt,
                    embed(gq.question),
                    query=gq.question,
                    k_seeds=args.k_seeds,
                    hebbian=grow,
                    hebbian_learning_rate=args.alpha,
                    hebbian_normalize=not args.no_normalize,
                )
            res = rt.run_minimal_tick(decay_gate=gate)
            if r in (1, 2, 3, 5, args.rounds):
                u, uf = recall(rt, used)
                h, hf = recall(rt, held)
                ru, rh = gold_rank(rt, used), gold_rank(rt, held)
                m, x = weights(rt)
                print(line(r, u, uf, ru, h, hf, rh, m, x, res.edges_spared_from_decay))


if __name__ == "__main__":
    main()
