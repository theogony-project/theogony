#!/usr/bin/env python3
"""End-to-end answers on the HippoRAG trio — does retrieval reach the answer?

    scripts/mesh_qa_answers.py --dataset 2wikimultihopqa --max-questions 1000

PHX-1087 measured the answer for the first time, on the founding corpus, and
could not settle anything: 47 questions, a two-to-three point noise floor, and a
corpus of canonical Greek mythology the model answers at 50% with no context at
all. This is the measurement that can settle it — 1,000 questions per dataset,
gold answers, and corpora the model has not memorised as canon.

Four arms over one shared corpus: `closed_book`, `bm25`, `knn`, `sa_ppr`.
Scored with SQuAD exact match and token F1, the metrics the multi-hop QA
literature reports, so these numbers can sit beside published ones.

Everything but the answering runs offline. The answering costs money; the run
prints the model and the arm count before it starts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import spacy
import torch
from sentence_transformers import SentenceTransformer

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.eval.qa_answers import (
    ARMS,
    answer_dataset,
    summarise_qa_answers,
)
from theogony.mesh.eval.qa_datasets import DATASETS, load_dataset
from theogony.mesh.eval.qa_features import (
    BGE_QUERY_INSTRUCTION,
    embed_texts,
    extract_spacy_entities,
)
from theogony.mesh.eval.qa_retrieval import BM25, build_qa_graph, rank_methods


def _tok(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", text.lower())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=sorted(DATASETS), default="2wikimultihopqa")
    ap.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    ap.add_argument("--max-questions", type=int, default=1000)
    ap.add_argument("--top-k", type=int, default=5, help="Passages handed to the model.")
    ap.add_argument("--knn-k", type=int, default=10)
    # The seeding ceiling, and the reason this is a flag rather than a constant.
    # Spreading Activation's advantage over kNN on 2Wiki exists only at *narrow*
    # seeding: at S=5 it merely re-ranks kNN's own hits (rescue 0.000), and the
    # published +0.102 recall@5 was measured at S=2. Running the answer benchmark
    # at the default 10 measures SA at the configuration where it is known to add
    # nothing (PHX-1089).
    ap.add_argument("--seed-top-s", type=int, default=10)
    ap.add_argument("--seed-mode", choices=("passage", "entity", "hybrid"), default="passage")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--embedder", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--spacy-model", default="en_core_web_sm")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    settings = Settings()
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    timing: dict[str, float] = {}

    t = time.perf_counter()
    data = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    passages, questions = data.passages, data.questions
    timing["load_s"] = time.perf_counter() - t
    print(
        f"dataset={args.dataset} passages={len(passages)} questions={len(questions)} "
        f"gold_coverage={data.gold_coverage:.3f}"
    )
    print(
        f"model={settings.llm.provider}/{settings.llm.model_id or '<default>'} "
        f"arms={','.join(arms)} top_k={args.top_k} "
        f"seeding={args.seed_mode}/S={args.seed_top_s} "
        f"-> {len(questions) * len(arms)} calls"
    )

    t = time.perf_counter()
    model = SentenceTransformer(args.embedder)
    passage_emb = embed_texts(
        model, [f"{p.title}. {p.text}" for p in passages], batch_size=args.batch_size
    )
    question_emb = embed_texts(
        model,
        [q.question for q in questions],
        batch_size=args.batch_size,
        instruction=BGE_QUERY_INSTRUCTION,
    )
    timing["embed_s"] = time.perf_counter() - t

    t = time.perf_counter()
    nlp = spacy.load(args.spacy_model, disable=["lemmatizer", "textcat"])
    entity_names, entities_per_passage = extract_spacy_entities(
        nlp, [f"{p.title}. {p.text}" for p in passages], batch_size=args.batch_size
    )
    entity_emb = (
        embed_texts(model, entity_names, batch_size=args.batch_size)
        if entity_names
        else torch.zeros((0, passage_emb.shape[1]), dtype=torch.float32)
    )
    graph = build_qa_graph(
        passage_emb, entity_emb, entities_per_passage, knn_k=args.knn_k, seed=args.seed
    )
    bm25 = BM25(docs=[_tok(f"{p.title}. {p.text}") for p in passages])
    timing["build_s"] = time.perf_counter() - t
    print(f"entities={len(entity_names)} graph_nodes={len(graph.node_ids)}")

    t = time.perf_counter()
    rankings = rank_methods(
        graph,
        passage_emb,
        question_emb,
        bm25,
        questions,
        top_k=max(args.top_k, 5),
        entity_emb=entity_emb,
        seed_mode=args.seed_mode,
        seed_top_s=args.seed_top_s,
    )
    timing["rank_s"] = time.perf_counter() - t

    t = time.perf_counter()
    results = asyncio.run(
        answer_dataset(
            build_llm_from_settings(settings),
            questions,
            passages,
            rankings,
            arms=arms,
            top_k=args.top_k,
            concurrency=args.concurrency,
        )
    )
    timing["answer_s"] = time.perf_counter() - t
    summary = summarise_qa_answers(results)

    print()
    print(f"{'arm':14s} {'EM':>7s} {'F1':>7s} {'gold in context':>16s} {'empty':>7s}")
    for arm in arms:
        s = summary.get(arm)
        if s:
            print(
                f"{arm:14s} {s['exact_match']:6.1%} {s['f1']:6.1%} "
                f"{s['gold_in_context']:15.1%} {s['empty_answers']:7.0f}"
            )
    print(f"\nanswering took {timing['answer_s']:.0f}s")

    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "dataset": args.dataset,
                    "model": f"{settings.llm.provider}/{settings.llm.model_id or 'default'}",
                    "questions": len(questions),
                    "passages": len(passages),
                    "top_k": args.top_k,
                    "seed_top_s": args.seed_top_s,
                    "seed_mode": args.seed_mode,
                    "timing_s": timing,
                    "summary": summary,
                    "answers": [
                        {
                            "qid": r.qid,
                            "arm": r.arm,
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
        print(f"detail written: {args.out}")


if __name__ == "__main__":
    main()
