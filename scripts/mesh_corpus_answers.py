#!/usr/bin/env python
"""Ask the founding gold set three ways and score the answers.

    scripts/mesh_corpus_answers.py --root data/mesh-founding [--top-k 50] [--limit N]

Three arms, same model, same questions:

    closed_book    no context — what the model already knows
    vector_only    top-k nodes by cosine, as plain text
    constellation  the same nodes plus the relations among them

The closed-book arm is the one that makes the others readable. The corpus is
Hesiod and the model has read Hesiod, so a constellation arm scoring well proves
nothing on its own. Every claim here is about the difference between arms.

Costs real money. Prints the model and the tick count with the results, because
neither is reproducible without them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.eval.corpus_answers import ARMS, answer_gold_set, summarise_answers
from theogony.mesh.eval.corpus_qa import load_gold
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--top-k", default=DEFAULT_TOP_K, type=int)
    ap.add_argument("--limit", type=int, default=0, help="First N questions only (0 = all).")
    ap.add_argument(
        "--seeds",
        type=int,
        default=None,
        help="k_seeds for the constellation arm (default: the library default).",
    )
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", type=Path, help="Write per-answer detail as JSON here.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    settings = Settings()
    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()
    llm = build_llm_from_settings(settings)

    gold = load_gold()
    if args.limit:
        gold = gold[: args.limit]

    def embed(text: str) -> list[float]:
        return asyncio.run(embedder.embed_many([text]))[0]

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    results = answer_gold_set(runtime, embed, llm, arms=arms, gold=gold, top_k=args.top_k)
    summary = summarise_answers(results)

    print(
        f"Modell {settings.llm.provider}/{settings.llm.model_id or '<default>'}   "
        f"Ticks {runtime.tick_count()}   top_k {args.top_k}   Fragen {len(gold)}"
    )
    print()
    print(f"{'Arm':16s} {'Antwort-Recall':>15s} {'vollstaendig':>13s} {'verweigert':>11s}")
    for arm in arms:
        s = summary.get(arm)
        if not s:
            continue
        print(
            f"{arm:16s} {s['answer_recall']:14.0%} "
            f"{s['complete_answers']:8.0f}/{s['questions']:.0f} "
            f"{s['declined']:10.0f}"
        )

    if "constellation" in summary and "vector_only" in summary:
        delta = summary["constellation"]["answer_recall"] - summary["vector_only"]["answer_recall"]
        print(f"\nGraph gegen reine Vektorsuche: {delta:+.0%}")
    if "constellation" in summary and "closed_book" in summary:
        delta = summary["constellation"]["answer_recall"] - summary["closed_book"]["answer_recall"]
        print(f"Graph gegen Vorwissen:        {delta:+.0%}")

    if args.verbose:
        print()
        by_id: dict[str, dict[str, object]] = {}
        for r in results:
            by_id.setdefault(r.id, {})[r.arm] = r
        for qid, per_arm in by_id.items():
            print(f"\n{qid}")
            for arm in arms:
                r = per_arm.get(arm)
                if r:
                    print(f"   {arm:14s} {len(r.found)}/{len(r.expected)}  {r.answer[:90]}")

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "model": f"{settings.llm.provider}/{settings.llm.model_id or 'default'}",
                    "ticks": runtime.tick_count(),
                    "top_k": args.top_k,
                    "summary": summary,
                    "answers": [
                        {
                            "id": r.id,
                            "arm": r.arm,
                            "kind": r.kind,
                            "expected": r.expected,
                            "answer": r.answer,
                            "found": r.found,
                            "missed": r.missed,
                        }
                        for r in results
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nDetail geschrieben: {args.out}")


if __name__ == "__main__":
    main()
