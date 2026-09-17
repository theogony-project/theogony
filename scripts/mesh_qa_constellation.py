#!/usr/bin/env python
"""Does the graph help answering where the model does not know the corpus? (PHX-1110)

    scripts/mesh_qa_constellation.py --root data/mesh-2wiki --dataset 2wikimultihopqa \
        [--limit 300] [--arms closed_book,passages,vector_only,constellation] [--out report.json]

Four arms, one model, one scorer (SQuAD EM / F1, PHX-1089's):

    closed_book          no material — the prior; 24.8% EM on 2Wiki
    passages             top-k passages by cosine — plain RAG, the published bridge
    vector_only          top-k mesh entities by cosine, as their descriptions
    constellation        the same kind of entities plus the relations among them
    constellation_typed  the same, without the structural descriptors (60% of the list)

`constellation` against `vector_only` is the graph's own contribution; against
`passages` it is whether the substrate's rendering competes with plain RAG at
all. The founding corpus could not ask either question (PHX-1098: prior 86%).

Costs real money. Prints the model, the tick count and every setting with the
results, because none of it is reproducible without them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import numpy as np

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.eval.qa_answers import summarise_qa_answers
from theogony.mesh.eval.qa_datasets import load_dataset
from theogony.mesh.eval.qa_mesh import (
    DEFAULT_PASSAGE_K,
    QA_ARMS,
    answer_qa_set,
    paired_qa,
    paragraph_of,
    summarise_by_kind,
    unit_rows,
)
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--dataset", default="2wikimultihopqa")
    ap.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    ap.add_argument("--max-questions", type=int, default=1000, help="the sampled question set")
    ap.add_argument("--seed", type=int, default=0, help="sampling seed, as in mesh_qa_answers.py")
    ap.add_argument(
        "--limit", type=int, default=0, help="first N of the sampled questions (0 = all)"
    )
    ap.add_argument("--arms", default=",".join(QA_ARMS))
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="entities for the mesh arms")
    ap.add_argument("--passage-k", type=int, default=DEFAULT_PASSAGE_K)
    ap.add_argument("--seeds", type=int, default=None, help="k_seeds for the constellation arm")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--passage-vectors", type=Path, help="default: <root>/passage_vectors.npy")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    settings = Settings()
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    data = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    questions = data.questions[: args.limit] if args.limit else data.questions
    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()

    vectors_path = args.passage_vectors or (args.root / "passage_vectors.npy")
    if "passages" in arms:
        if vectors_path.exists():
            passage_vectors = np.load(vectors_path)
        else:
            t = time.perf_counter()
            texts = [paragraph_of(p) for p in data.passages]
            rows = asyncio.run(embedder.embed_many(texts, batch_size=64))
            passage_vectors = unit_rows(np.asarray(rows, dtype=np.float32))
            np.save(vectors_path, passage_vectors)
            print(
                f"embedded {len(texts)} passages in {time.perf_counter() - t:.0f} s "
                f"-> {vectors_path}"
            )
    else:
        passage_vectors = None

    # Embedded up front, in one batch: the answer loop runs inside an event loop
    # of its own, and an `asyncio.run` inside it is an error, not a slowdown.
    texts = [q.question for q in questions]
    cache = dict(zip(texts, asyncio.run(embedder.embed_many(texts, batch_size=64)), strict=True))

    def embed(text: str) -> list[float]:
        return cache[text]

    llm = build_llm_from_settings(settings)
    k_seeds = args.seeds if args.seeds is not None else DEFAULT_K_SEEDS
    retrieve_kwargs = {"k_seeds": args.seeds} if args.seeds is not None else {}
    print(
        f"model={settings.llm.provider}/{settings.llm.model_id or '<default>'} mesh={args.root} "
        f"ticks={runtime.tick_count()} questions={len(questions)} arms={','.join(arms)} "
        f"top_k={args.top_k} passage_k={args.passage_k} k_seeds={k_seeds} "
        f"-> {len(questions) * len(arms)} calls"
    )
    t = time.perf_counter()
    results = asyncio.run(
        answer_qa_set(
            runtime,
            embed,
            llm,
            questions,
            data.passages,
            passage_vectors,
            arms=arms,
            top_k=args.top_k,
            passage_k=args.passage_k,
            concurrency=args.concurrency,
            **retrieve_kwargs,
        )
    )
    elapsed = time.perf_counter() - t
    summary = summarise_qa_answers(results)

    print(f"\n{'arm':14s} {'EM':>7s} {'F1':>7s} {'gold in ctx':>12s} {'empty':>6s}")
    for arm in arms:
        s = summary[arm]
        print(
            f"{arm:14s} {s['exact_match']:7.1%} {s['f1']:7.1%} "
            f"{s['gold_in_context']:12.1%} {s['empty_answers']:6.0f}"
        )

    by_kind = summarise_by_kind(results)
    print(f"\n{'exact match by answer kind':28s} " + " ".join(f"{a[:12]:>12s}" for a in arms))
    for kind in ("entity", "yes_no", "date"):
        if kind in by_kind:
            n = int(next(iter(by_kind[kind].values()))["questions"])
            cells = " ".join(
                f"{by_kind[kind].get(a, {}).get('exact_match', float('nan')):12.1%}" for a in arms
            )
            print(f"{kind + f' (n={n})':28s} {cells}")

    paired: dict[str, dict[str, float]] = {}
    for arm, base in (
        ("constellation", "vector_only"),
        ("constellation", "passages"),
        ("constellation", "closed_book"),
        ("constellation_typed", "constellation"),
        ("constellation_typed", "vector_only"),
        ("constellation_typed", "passages"),
        ("vector_only", "closed_book"),
        ("passages", "closed_book"),
    ):
        if arm in summary and base in summary:
            p = paired_qa(results, arm=arm, baseline=base)
            paired[f"{arm}_vs_{base}"] = p
            d_em = summary[arm]["exact_match"] - summary[base]["exact_match"]
            d_f1 = summary[arm]["f1"] - summary[base]["f1"]
            print(
                f"\n{arm} vs {base}: EM {d_em:+.1%}  F1 {d_f1:+.1%}   "
                f"EM better/worse/equal {p['em_better']:.0f}/{p['em_worse']:.0f}"
                f"/{p['em_equal']:.0f} "
                f"(p={p['p_em']:.3g})   F1 better/worse {p['f1_better']:.0f}/{p['f1_worse']:.0f} "
                f"(p={p['p_f1']:.3g})"
            )
    print(f"\n{elapsed / 60:.1f} min")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "model": f"{settings.llm.provider}/{settings.llm.model_id or 'default'}",
                    "mesh": str(args.root),
                    "ticks": runtime.tick_count(),
                    "dataset": args.dataset,
                    "questions": len(questions),
                    "top_k": args.top_k,
                    "passage_k": args.passage_k,
                    "k_seeds": k_seeds,
                    "summary": summary,
                    "by_kind": by_kind,
                    "paired": paired,
                    "answers": [
                        {
                            "qid": r.qid,
                            "arm": r.arm,
                            "question": r.question,
                            "gold": r.gold,
                            "answer": r.answer,
                            "em": r.em,
                            "f1": r.f1,
                            "gold_in_context": r.gold_in_context,
                        }
                        for r in results
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
