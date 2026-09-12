#!/usr/bin/env python
"""Does a disputed question return both sides? (PHX-1107)

    scripts/mesh_contradiction_eval.py --root data/mesh-founding-framed \
        --profiles any,contradiction [--out detail.json]

Seven questions whose correct answer is "both": the corpus says Night bore the
Fates and it says Themis did. A question scores only when the Constellation
carries an entity from each side. Run per frame profile on the same mesh, so
the difference is the routing and nothing else.

Costs no money — retrieval only, no LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.mesh import frames
from theogony.mesh.eval.contradiction_recall import (
    evaluate_contradictions,
    load_contradictions,
    summarise,
)
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def _say(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default=Path("data/mesh-founding-framed"), type=Path)
    ap.add_argument("--profiles", default="any,contradiction")
    ap.add_argument("--top-k", default=DEFAULT_TOP_K, type=int)
    ap.add_argument("--seeds", default=None, type=int, help="k_seeds (default: the library's).")
    ap.add_argument("--frame-threshold", default=0.0, type=float)
    ap.add_argument("--out", type=Path, help="Write per-question detail as JSON here.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()

    def embed(text: str) -> list[float]:
        return asyncio.run(embedder.embed_many([text]))[0]

    gold = load_contradictions()
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    retrieve_kwargs = {"k_seeds": args.seeds} if args.seeds is not None else {}

    _say(
        f"Mesh {args.root}   Knoten {runtime.nodes.consolidated_count()}   "
        f"Chunks {runtime.nodes.chunk_count()}   Kanten {runtime.edges.count_rows()}   "
        f"Fragen {len(gold)}   top_k {args.top_k}   "
        f"k_seeds {args.seeds if args.seeds is not None else DEFAULT_K_SEEDS}"
    )
    _say("")
    _say(f"{'Profil':16s} {'beide Seiten':>13s} {'eine Seite':>11s} {'Seiten Ø':>9s}")

    everything: dict[str, list[dict[str, object]]] = {}
    summaries: dict[str, dict[str, float]] = {}
    for profile in profiles:
        results = evaluate_contradictions(
            runtime,
            embed,
            profile=profile,
            gold=gold,
            top_k=args.top_k,
            frame_threshold=args.frame_threshold,
            **retrieve_kwargs,
        )
        s = summarise(results)
        summaries[profile] = s
        _say(f"{profile:16s} {s['both_sides']:12.0%} {s['any_side']:10.0%} {s['sides_mean']:9.2f}")
        everything[profile] = [
            {
                "id": r.id,
                "question": r.question,
                "both_sides": r.both_sides,
                "nodes": r.nodes,
                "contradiction_edges": r.contradiction_edges,
                "sides": [
                    {"label": s_.label, "expect": s_.expect, "found": s_.found} for s_ in r.sides
                ],
            }
            for r in results
        ]

    if args.verbose:
        for profile in profiles:
            _say("")
            _say(f"== {profile}")
            for row in everything[profile]:
                mark = "BEIDE" if row["both_sides"] else "     "
                _say(f"  {mark} {row['id']:24s} ({row['nodes']} Knoten)")
                for side in row["sides"]:  # type: ignore[union-attr]
                    got = ", ".join(side["found"]) or "—"
                    _say(f"        {side['label'][:46]:46s} {got}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "root": str(args.root),
                    "top_k": args.top_k,
                    "k_seeds": args.seeds if args.seeds is not None else DEFAULT_K_SEEDS,
                    "profiles": {p: frames.QUERY_PROFILES[p][0] for p in profiles},
                    "summaries": summaries,
                    "results": everything,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _say(f"\nDetail geschrieben: {args.out}")


if __name__ == "__main__":
    main()
