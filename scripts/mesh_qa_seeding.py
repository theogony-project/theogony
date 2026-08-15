#!/usr/bin/env python3
"""Is the SA↔kNN parity structural? — the seeding-ceiling experiment.

The benchmark (docs/etappes/qa_benchmark.md) found degree-aware Spreading
Activation at parity with dense kNN, and *neither* denser bridges nor
Kadmos-grade typed edges moved it. That leaves one untested structural variable:
**seeding**. SA is seeded from the top-S passages by query cosine — i.e. it starts
inside the neighbourhood kNN already returns. A method that only re-ranks its own
seeds cannot beat the retriever that produced them, however good its edges are.

This sweeps seeding scheme × seed count and reports, beyond recall:

* **rescue rate** — of the gold passages the seeds missed, how many SA still pulls
  into its top-5. This is SA's *unique* contribution. Near zero ⇒ the graph cannot
  reach what the embedding did not already find, and parity is structural.
* **head-to-head** — gold found by SA's top-5 and not kNN's, and vice versa.
* **seed retention** — how much of SA's top-5 was already in its seed set.

Runs entirely on cached data (embeddings recomputed locally, Kadmos readings read
from the extraction cache) — **no LLM calls, no cost**.

Example:

    ./.venv/bin/python scripts/mesh_qa_seeding.py --dataset 2wikimultihopqa --construction kadmos
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from theogony.mesh.eval.qa_datasets import DATASETS, load_dataset, subsample_corpus
from theogony.mesh.eval.qa_features import (
    BGE_QUERY_INSTRUCTION,
    embed_texts,
    extract_spacy_entities,
)
from theogony.mesh.eval.qa_retrieval import (
    SeedingResult,
    build_qa_graph,
    evaluate_seeding,
    graph_inputs_from_extractions,
)


class SeedingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset: str
    construction: str
    passage_count: int
    question_count: int
    entity_node_count: int
    embedder_model_id: str
    operator: str
    hops: int
    damping: float
    knn_k: int
    seed: int
    results: list[SeedingResult] = Field(default_factory=list)
    timing_s: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


def _cache_key(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _load_readings(cache_path: Path, texts: list[str]) -> list[dict]:
    """Load cached Kadmos readings aligned to ``texts``; missing entries are empty."""
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key")
            if isinstance(key, str):
                cache[key] = row.get("reading") or {}
    return [cache.get(_cache_key(t), {}) for t in texts]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="2wikimultihopqa")
    parser.add_argument(
        "--construction",
        choices=("cheap", "kadmos"),
        default="kadmos",
        help="cheap = spaCy NER co-occurrence; kadmos = cached LLM typed relations.",
    )
    parser.add_argument("--max-questions", type=int, default=300)
    parser.add_argument("--corpus-size", type=int, default=0, help="0 = full corpus")
    parser.add_argument("--knn-k", type=int, default=10)
    parser.add_argument("--operator", choices=("ppr", "raw"), default="ppr")
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--modes", default="passage,entity,hybrid")
    parser.add_argument("--seed-counts", default="1,5,10,25,50,100")
    parser.add_argument("--embedder", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/qa_bench"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    timing: dict[str, float] = {}
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    seed_counts = [int(s) for s in args.seed_counts.split(",") if s.strip()]

    t = time.perf_counter()
    data = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    data = subsample_corpus(data, corpus_size=args.corpus_size, seed=args.seed)
    timing["load_s"] = time.perf_counter() - t
    print(f"dataset={args.dataset} passages={len(data.passages)} questions={len(data.questions)}")

    t = time.perf_counter()
    model = SentenceTransformer(args.embedder)
    passage_texts = [f"{p.title}. {p.text}" for p in data.passages]
    passage_emb = embed_texts(model, passage_texts, batch_size=args.batch_size)
    question_emb = embed_texts(
        model,
        [q.question for q in data.questions],
        batch_size=args.batch_size,
        instruction=BGE_QUERY_INSTRUCTION,
    )
    timing["embed_s"] = time.perf_counter() - t

    t = time.perf_counter()
    if args.construction == "kadmos":
        cache_path = args.cache_dir / f"kadmos_readings_{args.dataset}.jsonl"
        readings = _load_readings(cache_path, [p.text for p in data.passages])
        filled = sum(1 for r in readings if r)
        if filled == 0:
            raise SystemExit(
                f"no cached Kadmos readings at {cache_path} — run scripts/mesh_qa_kadmos.py first"
            )
        print(f"kadmos readings from cache: {filled}/{len(readings)}")
        names, per_passage, relation_pairs = graph_inputs_from_extractions(readings)
    else:
        import spacy

        nlp = spacy.load(args.spacy_model, disable=["lemmatizer", "textcat"])
        names, per_passage = extract_spacy_entities(nlp, passage_texts, batch_size=args.batch_size)
        relation_pairs = None
    entity_emb = embed_texts(model, names, batch_size=args.batch_size)
    graph = build_qa_graph(
        passage_emb,
        entity_emb,
        per_passage,
        knn_k=args.knn_k,
        seed=args.seed,
        relation_pairs=relation_pairs,
    )
    timing["build_s"] = time.perf_counter() - t

    t = time.perf_counter()
    results = evaluate_seeding(
        graph,
        passage_emb,
        question_emb,
        data.questions,
        modes=modes,
        seed_counts=seed_counts,
        operator=args.operator,
        hops=args.hops,
        damping=args.damping,
    )
    timing["evaluate_s"] = time.perf_counter() - t

    report = SeedingReport(
        run_id=str(ULID()),
        dataset=args.dataset,
        construction=args.construction,
        passage_count=len(data.passages),
        question_count=len(data.questions),
        entity_node_count=len(names),
        embedder_model_id=args.embedder,
        operator=args.operator,
        hops=args.hops,
        damping=args.damping,
        knn_k=args.knn_k,
        seed=args.seed,
        results=results,
        timing_s=timing,
        notes="Seeding-ceiling probe. rescue_rate = of gold passages absent from the "
        "seed set, the fraction SA pulls into top-5 — SA's unique contribution over "
        "the embedding ranking that seeded it. Near zero means parity is structural.",
    )
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"qa_seeding_{report.run_id}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    knn = results[0].knn_recall_at_5 if results else 0.0
    print()
    print(
        f"=== Seeding ceiling — {args.dataset} / {args.construction} "
        f"(corpus={len(data.passages)}, n={len(data.questions)}, op={args.operator}) ==="
    )
    print(f"kNN recall@5 reference: {knn:.3f}")
    print()
    header = (
        f"{'mode':>8} {'S':>4} {'sa@5':>7} {'seed@5':>7} {'rescue':>7} "
        f"{'resc/miss':>10} {'sa_only':>8} {'knn_only':>9} {'retain':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.mode:>8} {r.top_s:>4} {r.sa_recall_at_5:>7.3f} {r.seed_recall_at_5:>7.3f} "
            f"{r.rescue_rate:>7.3f} {f'{r.rescued_gold}/{r.gold_missed_by_seeds}':>10} "
            f"{r.sa_only_hits:>8} {r.knn_only_hits:>9} {r.seed_retention:>7.3f}"
        )
    print()
    print(f"report: {out}")


if __name__ == "__main__":
    main()
