#!/usr/bin/env python
"""Run the founding-corpus gold set against a mesh.

    scripts/mesh_corpus_qa.py [--root data/mesh-founding] [--top-k 30]

Prints coverage and recall separately. Read them separately: low coverage is a
reading problem, low recall on covered entities is a retrieval problem, and the
end-to-end number cannot tell you which you have.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.mesh.eval.corpus_qa import evaluate, summarise
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--top-k", default=30, type=int)
    ap.add_argument("--json", action="store_true", help="emit the summary as JSON")
    ap.add_argument("--verbose", action="store_true", help="one line per question")
    ap.add_argument("--curve", action="store_true", help="recall as a function of top_k")
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()

    def embed(text: str) -> list[float]:
        return asyncio.run(embedder.embed_many([text]))[0]

    results = evaluate(runtime, embed, top_k=args.top_k)
    summary = summarise(results)

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
