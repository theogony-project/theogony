#!/usr/bin/env python
"""Run the founding-corpus gold set against a mesh.

    scripts/mesh_corpus_qa.py [--root data/mesh-founding] [--top-k 50] [--curve]

Prints coverage and recall separately. Read them separately: low coverage is a
reading problem, low recall on covered entities is a retrieval problem, and the
end-to-end number cannot tell you which you have.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.mesh.eval.corpus_qa import evaluate, recall_curve, summarise, summarise_by_kind
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--top-k", default=DEFAULT_TOP_K, type=int)
    ap.add_argument("--json", action="store_true", help="emit the summary as JSON")
    ap.add_argument("--verbose", action="store_true", help="one line per question")
    ap.add_argument("--curve", action="store_true", help="recall as a function of top_k")
    ap.add_argument(
        "--seed-sweep",
        action="store_true",
        help="recall as a function of k_seeds — the seeding ceiling, on this corpus.",
    )
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()

    def embed(text: str) -> list[float]:
        return asyncio.run(embedder.embed_many([text]))[0]

    if args.seed_sweep:
        # The seeding ceiling. On HippoRAG, Spreading Activation's entire
        # advantage lives at narrow seeding: +5.0 exact match end-to-end at S=2
        # and nothing at S=10 (PHX-1089). The same shape holds here — and the
        # shipped default sits on the wrong side of it (PHX-1090).
        print(f"Ticks auf diesem Mesh: {runtime.tick_count()}\n")
        print(f"{'k_seeds':>8s} {'Recall':>8s} {'voll':>8s}")
        for k in (1, 2, 3, 5, 8, 16, 32):
            s_ = summarise(evaluate(runtime, embed, top_k=args.top_k, k_seeds=k))
            marker = "  <- Default" if k == DEFAULT_K_SEEDS else ""
            print(
                f"{k:8d} {s_['recall_given_coverage']:7.0%} "
                f"{s_['questions_fully_answered']:5.0f}/{s_['questions']:.0f}{marker}"
            )
        return

    if args.curve:
        print(f"Ticks auf diesem Mesh: {runtime.tick_count()}\n")
        curve = recall_curve(runtime, embed)
        print(f"{'top_k':>6s}  {'Recall':>7s}")
        for k, recall in curve.items():
            print(f"{k:6d}  {recall:6.0%}")
        return

    results = evaluate(runtime, embed, top_k=args.top_k)
    summary = summarise(results)
    # Recall is only comparable at equal tick count: a tick costs ~777 units of
    # edge weight against ~0.1 returned by reinforcement (PHX-1077), so a mesh
    # that has been ticked more scores lower for reasons unrelated to retrieval.
    # Reported beside every number rather than left for the reader to remember
    # (PHX-1074).
    summary["ticks"] = float(runtime.tick_count())

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    if args.verbose:
        print(f"{'id':22s} {'cov':>5s} {'rec':>5s}  missing / not retrieved")
        for r in results:
            gap = [n for n in r.present if n not in r.retrieved]
            note = []
            if r.missing:
                note.append("nicht im Mesh: " + ", ".join(r.missing))
            if gap:
                note.append("nicht abgerufen: " + ", ".join(gap))
            print(f"{r.id:22s} {r.coverage:5.2f} {r.recall:5.2f}  {' | '.join(note)}")
        print()

    by_kind = summarise_by_kind(results)
    print(f"{'':28s} {'Fragen':>7s} {'Abdeckung':>10s} {'Recall':>8s} {'voll':>8s}")
    for kind in [k for k in by_kind if k != "all"] + ["all"]:
        s_ = by_kind[kind]
        print(
            f"{kind:28s} {s_['questions']:7.0f} {s_['coverage']:9.0%} "
            f"{s_['recall_given_coverage']:8.0%} {s_['questions_fully_answered']:5.0f}"
            f"/{s_['questions']:.0f}"
        )
    print()
    print(
        f"Ticks auf diesem Mesh        {summary['ticks']:.0f}"
        f"   (Recall ist nur bei gleicher Tick-Zahl vergleichbar)"
    )
    print(f"Fragen                       {summary['questions']:.0f}")
    print(f"erwartete Entitaeten         {summary['entities_expected']:.0f}")
    print(
        f"davon im Mesh vorhanden      {summary['entities_in_mesh']:.0f}"
        f"   (Abdeckung {summary['coverage']:.0%})"
    )
    print(
        f"davon abgerufen              {summary['entities_retrieved']:.0f}"
        f"   (Recall {summary['recall_given_coverage']:.0%})"
    )
    print(f"Ende-zu-Ende                 {summary['end_to_end']:.0%}")
    print(
        f"vollstaendig beantwortet     {summary['questions_fully_answered']:.0f}"
        f" von {summary['questions']:.0f}"
    )


if __name__ == "__main__":
    main()
