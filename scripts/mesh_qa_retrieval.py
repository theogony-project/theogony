#!/usr/bin/env python3
"""Multi-hop QA passage-retrieval benchmark driver — SA vs kNN vs BM25.

Operationalises README empirical question 2 on the standard trio
(MuSiQue / 2WikiMultihopQA / HotpotQA) + single-hop controls (PopQA), using the
HippoRAG_v2 shared-corpus protocol (passage recall@2 / @5). The compute lives in
``theogony.mesh.eval.qa_retrieval``; this driver does the I/O: fetch the dataset,
embed locally (BGE), extract entities locally (spaCy), build the cheap LLM-free
graph, run the methods + the edge-density ablation, and write a run report.

Everything runs **offline after a one-time dataset fetch** and needs **no paid
LLM** — the graph is spaCy-NER entities + embedding-kNN edges (the LinearRAG /
SPRIG "cheap construction" first-cut). Kadmos-grade LLM extraction is a
documented fidelity upgrade, not a prerequisite.

Example:

    ./.venv/bin/python scripts/mesh_qa_retrieval.py \
        --dataset 2wikimultihopqa --max-questions 300 --knn-k 10

Datasets: 2wikimultihopqa | musique | hotpotqa | popqa (single-hop control).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.qa_retrieval import (
    BM25,
    QAPassage,
    QAQuestion,
    QARetrievalReport,
    build_qa_graph,
    density_sweep,
    evaluate_methods,
)

HF_BASE = "https://huggingface.co/datasets/osunlp/HippoRAG_v2/resolve/main"

DATASETS: dict[str, tuple[str, str]] = {
    "2wikimultihopqa": ("2wikimultihopqa.json", "2wikimultihopqa_corpus.json"),
    "musique": ("musique.json", "musique_corpus.json"),
    "hotpotqa": ("hotpotqa.json", "hotpotqa_corpus.json"),
    "popqa": ("popqa.json", "popqa_corpus.json"),
}

# spaCy entity labels worth keeping as graph nodes (drop CARDINAL/ORDINAL/PERCENT…).
_KEEP_LABELS = {
    "PERSON",
    "NORP",
    "FAC",
    "ORG",
    "GPE",
    "LOC",
    "PRODUCT",
    "EVENT",
    "WORK_OF_ART",
    "LAW",
    "LANGUAGE",
}

# bge-small-en-v1.5 recommends this instruction on the query side only.
_BGE_QUERY_INSTR = "Represent this sentence for searching relevant passages: "


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url} → {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "theogony-bench/1.0"})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as fh:  # noqa: S310 (fixed HF host)
        fh.write(resp.read())


def _norm_title(title: str) -> str:
    return title.strip().lower()


def load_dataset(
    name: str, cache_dir: Path, *, max_questions: int, seed: int
) -> tuple[list[QAPassage], list[QAQuestion], float]:
    """Fetch + parse a HippoRAG_v2 dataset. Returns (passages, questions, gold_coverage)."""
    import random

    query_file, corpus_file = DATASETS[name]
    query_path = cache_dir / query_file
    corpus_path = cache_dir / corpus_file
    _download(f"{HF_BASE}/{query_file}", query_path)
    _download(f"{HF_BASE}/{corpus_file}", corpus_path)

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    passages = [
        QAPassage(idx=i, title=str(p.get("title", "")), text=str(p.get("text", "")))
        for i, p in enumerate(corpus)
    ]
    title_to_idx: dict[str, int] = {}
    for p in passages:
        title_to_idx.setdefault(_norm_title(p.title), p.idx)

    raw_q = json.loads(query_path.read_text(encoding="utf-8"))
    questions: list[QAQuestion] = []
    matched_gold = 0
    total_gold = 0
    for q in raw_q:
        gold: set[int] = set()
        # Gold = the titles of supporting passages, matched to the shared corpus by
        # title. HippoRAG_v2 ships the HotpotQA-native `supporting_facts` ([title,
        # sent_id] pairs) for the multi-hop trio; the `paragraphs`/`is_supporting`
        # shape is a fallback for datasets that use it.
        gold_titles: set[str] = set()
        for fact in q.get("supporting_facts", []):
            if isinstance(fact, (list, tuple)) and fact:
                gold_titles.add(_norm_title(str(fact[0])))
        for para in q.get("paragraphs", []):
            if para.get("is_supporting"):
                gold_titles.add(_norm_title(str(para.get("title", ""))))
        for gt in gold_titles:
            total_gold += 1
            idx = title_to_idx.get(gt)
            if idx is not None:
                gold.add(idx)
                matched_gold += 1
        if not gold:
            continue
        ans = q.get("answer")
        if isinstance(ans, list):
            ans = ans[0] if ans else ""
        questions.append(
            QAQuestion(
                qid=str(q.get("_id") or q.get("id") or ""),
                question=str(q.get("question", "")),
                answer=str(ans),
                gold_idxs=gold,
            )
        )
    if max_questions and len(questions) > max_questions:
        questions = random.Random(seed).sample(questions, max_questions)
    coverage = matched_gold / max(1, total_gold)
    return passages, questions, coverage


def _embed(model, texts: list[str], *, batch_size: int, instruction: str = "") -> torch.Tensor:
    payload = [instruction + t for t in texts] if instruction else texts
    vecs = model.encode(
        payload,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=True,
    )
    return torch.tensor(vecs, dtype=torch.float32)


def _extract_entities(
    nlp, passages: list[QAPassage], *, batch_size: int
) -> tuple[list[str], list[set[int]]]:
    """spaCy NER → global unique entity list + per-passage entity-index sets."""
    entity_to_idx: dict[str, int] = {}
    per_passage: list[set[int]] = []
    texts = [f"{p.title}. {p.text}" for p in passages]
    for doc in nlp.pipe(texts, batch_size=batch_size):
        ents: set[int] = set()
        for ent in doc.ents:
            if ent.label_ not in _KEEP_LABELS:
                continue
            key = ent.text.strip().lower()
            if len(key) < 2:
                continue
            ei = entity_to_idx.get(key)
            if ei is None:
                ei = len(entity_to_idx)
                entity_to_idx[key] = ei
            ents.add(ei)
        per_passage.append(ents)
    entity_names = [""] * len(entity_to_idx)
    for name, ei in entity_to_idx.items():
        entity_names[ei] = name
    return entity_names, per_passage


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="2wikimultihopqa")
    parser.add_argument("--max-questions", type=int, default=300)
    parser.add_argument("--knn-k", type=int, default=10, help="passage-passage kNN edges per node")
    parser.add_argument("--seed-top-s", type=int, default=10, help="query→passage seeds for SA")
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--embedder", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--densities",
        type=str,
        default="0.0,0.25,0.5,1.0",
        help="comma-separated entity-edge fractions for the ablation",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/qa_bench"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    import spacy
    from sentence_transformers import SentenceTransformer

    timing: dict[str, float] = {}

    t = time.perf_counter()
    passages, questions, coverage = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    timing["load_s"] = time.perf_counter() - t
    print(
        f"dataset={args.dataset} passages={len(passages)} questions={len(questions)} "
        f"gold_coverage={coverage:.3f}"
    )

    t = time.perf_counter()
    model = SentenceTransformer(args.embedder)
    passage_emb = _embed(
        model, [f"{p.title}. {p.text}" for p in passages], batch_size=args.batch_size
    )
    question_emb = _embed(
        model,
        [q.question for q in questions],
        batch_size=args.batch_size,
        instruction=_BGE_QUERY_INSTR,
    )
    timing["embed_passages_questions_s"] = time.perf_counter() - t

    t = time.perf_counter()
    nlp = spacy.load(args.spacy_model, disable=["lemmatizer", "textcat"])
    entity_names, entities_per_passage = _extract_entities(
        nlp, passages, batch_size=args.batch_size
    )
    entity_emb = (
        _embed(model, entity_names, batch_size=args.batch_size)
        if entity_names
        else torch.zeros((0, passage_emb.shape[1]), dtype=torch.float32)
    )
    timing["ner_and_entity_embed_s"] = time.perf_counter() - t
    print(f"entities={len(entity_names)}")

    t = time.perf_counter()
    graph = build_qa_graph(
        passage_emb, entity_emb, entities_per_passage, knn_k=args.knn_k, seed=args.seed
    )
    timing["build_graph_s"] = time.perf_counter() - t

    bm25 = BM25(docs=[_tok(f"{p.title}. {p.text}") for p in passages])

    t = time.perf_counter()
    methods = evaluate_methods(
        graph,
        passage_emb,
        question_emb,
        bm25,
        questions,
        hops=args.hops,
        damping=args.damping,
        seed_top_s=args.seed_top_s,
    )
    timing["evaluate_s"] = time.perf_counter() - t

    fractions = [float(x) for x in args.densities.split(",") if x.strip()]
    t = time.perf_counter()
    density_levels = density_sweep(
        graph,
        passage_emb,
        question_emb,
        questions,
        fractions=fractions,
        hops=args.hops,
        damping=args.damping,
        seed_top_s=args.seed_top_s,
    )
    timing["density_sweep_s"] = time.perf_counter() - t

    report = QARetrievalReport(
        run_id=str(ULID()),
        dataset=args.dataset,
        construction="spacy-ner entities + embedding co-occurrence/kNN edges (LLM-free first-cut)",
        embedder_model_id=args.embedder,
        passage_count=len(passages),
        entity_node_count=len(entity_names),
        question_count=len(questions),
        gold_coverage=coverage,
        knn_k=args.knn_k,
        seed_top_s=args.seed_top_s,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
        methods=methods,
        density_levels=density_levels,
        timing_s=timing,
        notes="Cheap LLM-free construction (LinearRAG/SPRIG-style). SA/kNN/BM25 over the "
        "shared corpus; recall@k = fraction of gold retrieved. Density ablation sweeps the "
        "entity-bridge edge fraction with the geometric backbone fixed; kNN is the flat reference.",
    )

    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"qa_retrieval_{report.run_id}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print()
    print(f"=== QA retrieval — {args.dataset} (n={len(questions)}) ===")
    print(f"{'method':>7} {'recall@2':>9} {'recall@5':>9} {'mrr@10':>8}")
    for m in methods:
        print(f"{m.method:>7} {m.recall_at_2:>9.3f} {m.recall_at_5:>9.3f} {m.mrr_at_10:>8.3f}")
    print()
    print(
        f"{'ent_frac':>9} {'edges':>9} {'sa_raw@5':>9} {'sa_ppr@5':>9} {'knn@5':>7} {'ppr-knn':>8}"
    )
    for lvl in density_levels:
        print(
            f"{lvl.entity_edge_fraction:>9.2f} {lvl.total_edges:>9} "
            f"{lvl.sa_raw_recall_at_5:>9.3f} {lvl.sa_ppr_recall_at_5:>9.3f} "
            f"{lvl.knn_recall_at_5:>7.3f} {lvl.sa_ppr_minus_knn_at_5:>+8.3f}"
        )
    print()
    print(f"report: {out}")


def _tok(text: str) -> list[str]:
    from theogony.mesh.eval.qa_retrieval import _tokenize

    return _tokenize(text)


if __name__ == "__main__":
    main()
