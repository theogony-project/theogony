#!/usr/bin/env python3
"""Kadmos-grade vs cheap construction on the QA-retrieval benchmark.

The first-cut benchmark (`scripts/mesh_qa_retrieval.py`, docs/etappes/qa_benchmark.md)
found degree-aware Spreading Activation at **parity** with dense kNN and **no
density crossover** — and localised the open question: the entity bridges were
cheap spaCy-NER co-occurrence, which is noisy (every pair of entities sharing a
passage gets bridged, related or not). This script tests the follow-up hypothesis:

    Do **clean, typed relational edges** — Kadmos v2's own LLM extraction — carry
    the multi-hop signal that noisy co-occurrence bridges do not?

Design: **one corpus, one question set, two graphs.** Same passages, same
embeddings, same passage-kNN backbone, same BM25, same bridge capping — the *only*
difference is where entity↔entity bridges come from. That isolates the variable.

Extraction reuses the real Kadmos `SYSTEM_PROMPT` and `ParagraphReadingOutput`
schema, so this measures the substrate's actual reading contract, not a bespoke
prompt. Readings are cached to JSONL keyed by passage text, so re-runs are free
and an interrupted run resumes.

Example:

    THEOGONY_LLM__PROVIDER=deepseek ./.venv/bin/python scripts/mesh_qa_kadmos.py \\
        --dataset 2wikimultihopqa --max-questions 150 --corpus-size 1500

Cost is reported per run; deepseek-chat runs ~0.0002 EUR/passage.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import torch
from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider
from theogony.config.settings import Settings
from theogony.mesh.eval.qa_datasets import DATASETS, load_dataset, subsample_corpus
from theogony.mesh.eval.qa_features import (
    BGE_QUERY_INSTRUCTION,
    embed_texts,
    extract_spacy_entities,
)
from theogony.mesh.eval.qa_retrieval import (
    BM25,
    QAGraph,
    QAMethodMetrics,
    QAPassage,
    QAQuestion,
    _tokenize,
    build_qa_graph,
    density_sweep,
    evaluate_methods,
    graph_inputs_from_extractions,
    normalize_reading_payload,
)
from theogony.mesh.ingestion.kadmos_v2 import SYSTEM_PROMPT
from theogony.mesh.ingestion.reading_schemas import ParagraphReadingOutput

# Providers differ in how strictly they honour a JSON schema; DeepSeek in
# particular returns `name`/`wikidata_id`/`subject`/`object`. Naming the exact keys
# is a provider-compatibility shim, not a change to the extraction task — the
# schema, the concepts asked for, and the relation semantics are Kadmos's own.
_FIELD_NAME_APPENDIX = """

Use exactly these JSON keys:
{"concepts": [{"label": str, "entity_type": str, "tags": [str], "description": str}],
 "relations": [{"source": str, "target": str, "relation_descriptor": str, "relation_kind": str}],
 "paragraph_concept": {"label": str, "description": str, "tags": [str]} | null}
"source" and "target" must be exact "label" strings from your own concepts list."""


class ExtractionStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passages: int = 0
    from_cache: int = 0
    llm_calls: int = 0
    failures: int = 0
    cost_eur: float = 0.0
    wall_s: float = 0.0
    model_id: str = ""


class ConstructionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    construction: str
    entity_nodes: int
    entity_bridges: int
    methods: list[QAMethodMetrics] = Field(default_factory=list)
    density_levels: list[dict[str, float]] = Field(default_factory=list)


class KadmosComparisonReport(BaseModel):
    """A/B of cheap vs Kadmos-grade construction on one shared corpus."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset: str
    passage_count: int
    question_count: int
    gold_coverage: float
    embedder_model_id: str
    knn_k: int
    seed_top_s: int
    hops: int
    damping: float
    seed: int
    extraction: ExtractionStats
    constructions: list[ConstructionResult] = Field(default_factory=list)
    timing_s: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Kadmos extraction with an on-disk cache
# ---------------------------------------------------------------------------


def _cache_key(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn last line from an interrupted run is skipped, not fatal
        key = row.get("key")
        if isinstance(key, str):
            cache[key] = row.get("reading") or {}
    return cache


async def extract_readings(
    passages: list[QAPassage],
    llm: LLMProvider,
    *,
    cache_path: Path,
    concurrency: int,
    timeout_s: float,
) -> tuple[list[dict[str, Any]], ExtractionStats]:
    """Read every passage with Kadmos's prompt+schema, caching results to JSONL.

    Concurrency is bounded by a semaphore (the LLMProvider protocol guarantees
    asyncio-safety). Each completed reading is appended to the cache immediately,
    so an interrupted run resumes instead of re-paying for work already done.

    A failed or schema-violating reading is recorded as an empty reading and
    counted — honest-failure: the passage stays retrievable via its embedding, it
    just contributes no bridges.
    """
    cache = _load_cache(cache_path)
    stats = ExtractionStats(passages=len(passages), model_id=getattr(llm, "model_id", ""))
    todo = [p for p in passages if _cache_key(p.text) not in cache]
    stats.from_cache = len(passages) - len(todo)

    if todo:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        started = time.perf_counter()
        done = 0

        async def _one(passage: QAPassage) -> None:
            nonlocal done
            async with sem:
                prompt = (
                    f"PARAGRAPH:\n{passage.title}. {passage.text}\n\n"
                    "Extract the concepts, relations, and paragraph concept."
                )
                reading: dict[str, Any] = {}
                try:
                    result = await llm.complete(
                        prompt=prompt,
                        system=SYSTEM_PROMPT + _FIELD_NAME_APPENDIX,
                        json_schema=ParagraphReadingOutput.model_json_schema(),
                        temperature=0.1,
                        timeout_s=timeout_s,
                    )
                    stats.cost_eur += float(result.cost_eur)
                    payload = normalize_reading_payload(json.loads(result.text))
                    reading = ParagraphReadingOutput.model_validate(payload).model_dump()
                except Exception:  # noqa: BLE001 — any failure degrades to an empty reading
                    stats.failures += 1
                stats.llm_calls += 1
                async with lock:
                    with cache_path.open("a", encoding="utf-8") as fh:
                        fh.write(
                            json.dumps({"key": _cache_key(passage.text), "reading": reading}) + "\n"
                        )
                    cache[_cache_key(passage.text)] = reading
                    done += 1
                    if done % 50 == 0 or done == len(todo):
                        rate = done / max(1e-9, time.perf_counter() - started)
                        eta = (len(todo) - done) / max(1e-9, rate)
                        print(
                            f"  extracted {done}/{len(todo)}  "
                            f"{rate:.1f}/s  eta {eta / 60:.1f} min  "
                            f"cost {stats.cost_eur:.3f} EUR  fail {stats.failures}",
                            flush=True,
                        )

        await asyncio.gather(*(_one(p) for p in todo))
        stats.wall_s = time.perf_counter() - started

    readings = [cache.get(_cache_key(p.text), {}) for p in passages]
    return readings, stats


# ---------------------------------------------------------------------------
# Evaluation of one construction
# ---------------------------------------------------------------------------


def _evaluate_construction(
    name: str,
    graph: QAGraph,
    passage_emb: torch.Tensor,
    question_emb: torch.Tensor,
    bm25: BM25,
    questions: list[QAQuestion],
    entity_count: int,
    *,
    args: argparse.Namespace,
    fractions: list[float],
) -> ConstructionResult:
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
    levels = density_sweep(
        graph,
        passage_emb,
        question_emb,
        questions,
        fractions=fractions,
        hops=args.hops,
        damping=args.damping,
        seed_top_s=args.seed_top_s,
    )
    return ConstructionResult(
        construction=name,
        entity_nodes=entity_count,
        entity_bridges=len(graph.entity_edges) // 2,
        methods=methods,
        density_levels=[lvl.model_dump() for lvl in levels],
    )


def _print_construction(res: ConstructionResult) -> None:
    print(f"--- {res.construction}: {res.entity_nodes} entities, {res.entity_bridges} bridges")
    print(f"{'method':>7} {'recall@2':>9} {'recall@5':>9} {'mrr@10':>8}")
    for m in res.methods:
        print(f"{m.method:>7} {m.recall_at_2:>9.3f} {m.recall_at_5:>9.3f} {m.mrr_at_10:>8.3f}")
    print(f"{'ent_frac':>9} {'sa_ppr@5':>9} {'knn@5':>7} {'ppr-knn':>8}")
    for lvl in res.density_levels:
        print(
            f"{lvl['entity_edge_fraction']:>9.2f} {lvl['sa_ppr_recall_at_5']:>9.3f} "
            f"{lvl['knn_recall_at_5']:>7.3f} {lvl['sa_ppr_minus_knn_at_5']:>+8.3f}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="2wikimultihopqa")
    parser.add_argument("--max-questions", type=int, default=150)
    parser.add_argument("--corpus-size", type=int, default=1500)
    parser.add_argument("--knn-k", type=int, default=10)
    parser.add_argument("--seed-top-s", type=int, default=10)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--embedder", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--spacy-model", default="en_core_web_sm")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--llm-timeout", type=float, default=90.0)
    parser.add_argument("--densities", default="0.0,0.25,0.5,1.0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Run extraction (populating the cache) and stop — for cost pilots.",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/qa_bench"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    import spacy
    from sentence_transformers import SentenceTransformer

    timing: dict[str, float] = {}
    fractions = [float(x) for x in args.densities.split(",") if x.strip()]

    t = time.perf_counter()
    data = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    data = subsample_corpus(data, corpus_size=args.corpus_size, seed=args.seed)
    timing["load_s"] = time.perf_counter() - t
    print(
        f"dataset={args.dataset} passages={len(data.passages)} "
        f"questions={len(data.questions)} gold_coverage={data.gold_coverage:.3f}"
    )

    # --- Kadmos-grade extraction (the only paid step) ----------------------
    settings = Settings()
    llm = build_llm_from_settings(settings)
    cache_path = args.cache_dir / f"kadmos_readings_{args.dataset}.jsonl"
    print(f"extracting with {getattr(llm, 'model_id', '?')} (cache: {cache_path})")
    readings, ex_stats = asyncio.run(
        extract_readings(
            data.passages,
            llm,
            cache_path=cache_path,
            concurrency=args.concurrency,
            timeout_s=args.llm_timeout,
        )
    )
    timing["extract_s"] = ex_stats.wall_s
    print(
        f"extraction: {ex_stats.from_cache} cached, {ex_stats.llm_calls} calls, "
        f"{ex_stats.failures} failures, {ex_stats.cost_eur:.3f} EUR, {ex_stats.wall_s / 60:.1f} min"
    )
    if args.extract_only:
        print("--extract-only: stopping after extraction.")
        return

    # --- shared features ---------------------------------------------------
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
    bm25 = BM25(docs=[_tokenize(t_) for t_ in passage_texts])
    timing["embed_s"] = time.perf_counter() - t

    # --- construction A: cheap (spaCy NER + co-occurrence) -----------------
    t = time.perf_counter()
    nlp = spacy.load(args.spacy_model, disable=["lemmatizer", "textcat"])
    cheap_names, cheap_per_passage = extract_spacy_entities(
        nlp, passage_texts, batch_size=args.batch_size
    )
    cheap_emb = embed_texts(model, cheap_names, batch_size=args.batch_size)
    cheap_graph = build_qa_graph(
        passage_emb, cheap_emb, cheap_per_passage, knn_k=args.knn_k, seed=args.seed
    )
    timing["cheap_build_s"] = time.perf_counter() - t

    # --- construction B: Kadmos-grade (LLM concepts + typed relations) -----
    t = time.perf_counter()
    kad_names, kad_per_passage, relation_pairs = graph_inputs_from_extractions(readings)
    kad_emb = embed_texts(model, kad_names, batch_size=args.batch_size)
    kad_graph = build_qa_graph(
        passage_emb,
        kad_emb,
        kad_per_passage,
        knn_k=args.knn_k,
        seed=args.seed,
        relation_pairs=relation_pairs,
    )
    timing["kadmos_build_s"] = time.perf_counter() - t

    t = time.perf_counter()
    results = [
        _evaluate_construction(
            "cheap (spaCy NER + co-occurrence)",
            cheap_graph,
            passage_emb,
            question_emb,
            bm25,
            data.questions,
            len(cheap_names),
            args=args,
            fractions=fractions,
        ),
        _evaluate_construction(
            "kadmos (LLM concepts + typed relations)",
            kad_graph,
            passage_emb,
            question_emb,
            bm25,
            data.questions,
            len(kad_names),
            args=args,
            fractions=fractions,
        ),
    ]
    timing["evaluate_s"] = time.perf_counter() - t

    report = KadmosComparisonReport(
        run_id=str(ULID()),
        dataset=args.dataset,
        passage_count=len(data.passages),
        question_count=len(data.questions),
        gold_coverage=data.gold_coverage,
        embedder_model_id=args.embedder,
        knn_k=args.knn_k,
        seed_top_s=args.seed_top_s,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
        extraction=ex_stats,
        constructions=results,
        timing_s=timing,
        notes="A/B on ONE shared subsampled corpus: identical passages, embeddings, "
        "kNN backbone, BM25 and bridge capping; only the entity-entity bridge source "
        "differs (passage co-occurrence vs LLM-asserted typed relations). Absolute "
        "recall is not comparable to the full-corpus run (smaller corpus is easier); "
        "the cheap-vs-kadmos contrast and the kNN anchor are.",
    )
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"qa_kadmos_{report.run_id}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print()
    print(
        f"=== Kadmos-grade vs cheap — {args.dataset} "
        f"(corpus={len(data.passages)}, n={len(data.questions)}) ==="
    )
    for res in results:
        _print_construction(res)
    print(f"report: {out}")


if __name__ == "__main__":
    main()
