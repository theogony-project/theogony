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
from theogony.mesh.eval.corpus_answers import (
    ARMS,
    AnswerResult,
    answer_gold_set,
    paired_against,
    summarise_answers,
)
from theogony.mesh.eval.corpus_qa import load_gold
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
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
    ap.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="ask the same prompts N times; the summary then reports the spread",
    )
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
    # `--seeds` was declared and never passed. Two runs were reported as
    # "k_seeds=1" that were the library default, and nothing said otherwise —
    # an argparse flag that reaches nothing is indistinguishable, from the
    # outside, from one that works (PHX-1097).
    retrieve_kwargs = {"k_seeds": args.seeds} if args.seeds is not None else {}
    results = answer_gold_set(
        runtime,
        embed,
        llm,
        arms=arms,
        gold=gold,
        top_k=args.top_k,
        repeat=args.repeat,
        **retrieve_kwargs,
    )
    summary = summarise_answers(results)

    print(
        f"Modell {settings.llm.provider}/{settings.llm.model_id or '<default>'}   "
        f"Ticks {runtime.tick_count()}   top_k {args.top_k}   "
        f"k_seeds {args.seeds if args.seeds is not None else DEFAULT_K_SEEDS}   "
        f"Fragen {len(gold)}   Laeufe {args.repeat}"
    )
    print()
    print(f"{'Arm':16s} {'Antwort-Recall':>15s} {'vollstaendig':>13s} {'verweigert':>11s}")
    for arm in arms:
        s = summary.get(arm)
        if not s:
            continue
        spread = (
            f"  [{s['answer_recall_min']:.0%}-{s['answer_recall_max']:.0%}]"
            if s["runs"] > 1
            else ""
        )
        print(
            f"{arm:16s} {s['answer_recall']:14.0%} "
            f"{s['complete_answers']:8.1f}/{s['questions']:.0f} "
            f"{s['declined']:10.1f}{spread}"
        )

    if "constellation" in summary and "vector_only" in summary:
        delta = summary["constellation"]["answer_recall"] - summary["vector_only"]["answer_recall"]
        print(f"\nGraph gegen reine Vektorsuche: {delta:+.0%}")
    if "constellation" in summary and "closed_book" in summary:
        delta = summary["constellation"]["answer_recall"] - summary["closed_book"]["answer_recall"]
        print(f"Graph gegen Vorwissen:        {delta:+.0%}")

    # Paired, because the totals above are the wrong comparison when the control
    # is this noisy: both arms' totals move with the model's mood, the pairing
    # does not. And the slice is where the arms can differ at all — the corpus is
    # Hesiod, and on the questions the model answers from memory every arm ties.
    for arm in arms:
        if arm == "closed_book" or "closed_book" not in summary:
            continue
        pair = paired_against(results, arm=arm)
        print(
            f"\n{arm} gegen closed_book, Frage fuer Frage: "
            f"{pair['better']:.0f} besser / {pair['worse']:.0f} schlechter / "
            f"{pair['equal']:.0f} gleich"
        )
        print(
            f"  auf den {pair['slice_questions']:.0f} Fragen, die closed_book nicht "
            f"vollstaendig beantwortet: {pair['slice_recall']:.0%}"
        )

    if args.verbose:
        print()
        by_question: dict[str, dict[str, AnswerResult]] = {}
        for row in results:
            by_question.setdefault(row.id, {})[row.arm] = row
        for qid, per_arm in by_question.items():
            print(f"\n{qid}")
            for arm in arms:
                shown = per_arm.get(arm)
                if shown is not None:
                    print(
                        f"   {arm:14s} {len(shown.found)}/{len(shown.expected)}  "
                        f"{shown.answer[:90]}"
                    )

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
                            "run": r.run,
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
