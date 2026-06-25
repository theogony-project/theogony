#!/usr/bin/env python3
"""Trained KGE baseline (pykeen) vs Spreading Activation on an identical split.

Closes the rigor gap in the link-prediction story: our SA numbers were only
compared against *untrained* baselines (degree, kNN). This script trains a
standard knowledge-graph-embedding model (TransE / RotatE / DistMult) on the
mesh's own edges and evaluates it with the filtered MRR/Hits@k protocol — then
runs our SA rankers on the *exact same* held-out test set.

Honest framing of the comparison:
- KGE is **relation-aware and trained** (sees (h, r, t), learns embeddings).
- SA (`sa_raw`) is **relation-agnostic and untrained** (propagates over weighted
  adjacency, never sees the relation type).
So KGE is an *upper-reference*. The question is how much of the gap an untrained,
relation-blind structural primitive already closes — and how much head-room a
relation-conditioned retrieval (migration step S3) would unlock.

Example:

    ./venv/bin/python scripts/mesh_kge_baseline.py \
        --root data/mesh-wiki-v1 --model TransE --epochs 150 --dim 128
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
from ulid import ULID

from theogony.mesh.eval.link_prediction import (
    build_context,
    build_csr_over_nodes,
    evaluate,
)
from theogony.mesh.eval.loader import load_mesh_eval_data
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _load_labeled_triples(root: Path) -> list[tuple[str, str, str]]:
    """Mesh edges as (head_node_id, relation, tail_node_id) label triples."""
    rt = MeshRuntime.open(root.resolve())
    triples: list[tuple[str, str, str]] = []
    for edge in rt.edges.load_all_edges():
        rel = edge.relation_descriptor or edge.relation_kind or "related"
        triples.append((str(edge.source_id), rel, str(edge.target_id)))
    return triples


def _split_triples(
    triples: list[tuple[str, str, str]],
    *,
    test_fraction: float,
    seed: int,
    max_test: int | None = None,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Deterministic split, then filter test so every h/r/t is seen in train.

    The train-vocabulary filter is what makes the comparison fair: both KGE and
    SA are scored only on test edges whose endpoints (and, for KGE, relation)
    exist in the training graph.
    """
    order = list(range(len(triples)))
    random.Random(seed).shuffle(order)
    n_test = int(round(len(order) * test_fraction))
    test_raw = [triples[i] for i in order[:n_test]]
    train = [triples[i] for i in order[n_test:]]

    train_entities = {h for h, _r, _t in train} | {t for _h, _r, t in train}
    train_relations = {r for _h, r, _t in train}
    test = [
        (h, r, t)
        for (h, r, t) in test_raw
        if h in train_entities and t in train_entities and r in train_relations
    ]
    if max_test is not None and len(test) > max_test:
        test = random.Random(seed + 1).sample(test, max_test)
    return train, test


def _run_kge(
    train: list[tuple[str, str, str]],
    test: list[tuple[str, str, str]],
    *,
    model: str,
    dim: int,
    epochs: int,
    batch_size: int,
    seed: int,
    device: str,
) -> dict[str, float]:
    from pykeen.pipeline import pipeline
    from pykeen.triples import TriplesFactory

    train_arr = np.array(train, dtype=str)
    test_arr = np.array(test, dtype=str)
    train_tf = TriplesFactory.from_labeled_triples(triples=train_arr)
    test_tf = TriplesFactory.from_labeled_triples(
        triples=test_arr,
        entity_to_id=train_tf.entity_to_id,
        relation_to_id=train_tf.relation_to_id,
    )
    result = pipeline(
        training=train_tf,
        testing=test_tf,
        model=model,
        model_kwargs={"embedding_dim": dim},
        training_kwargs={
            "num_epochs": epochs,
            "batch_size": batch_size,
            "use_tqdm": False,
        },
        random_seed=seed,
        device=device,
    )
    return {
        "mrr": float(result.get_metric("inverse_harmonic_mean_rank")),
        "hits_at_1": float(result.get_metric("hits_at_1")),
        "hits_at_3": float(result.get_metric("hits_at_3")),
        "hits_at_10": float(result.get_metric("hits_at_10")),
    }


def _run_sa(
    root: Path,
    train: list[tuple[str, str, str]],
    test: list[tuple[str, str, str]],
    *,
    hops: int,
    damping: float,
    seed: int,
) -> dict[str, dict[str, float]]:
    """Relation-agnostic SA / geometry rankers on the identical split."""
    data = load_mesh_eval_data(root)
    id_to_index = data.id_to_index

    train_rows = [(h, t, 1.0) for (h, _r, t) in train if h in id_to_index and t in id_to_index]
    train_csr = build_csr_over_nodes(data.node_ids, train_rows)
    ctx = build_context(train_csr, data.sem_unit)

    known_tails_by_head: dict[int, set[int]] = {}
    for h, _r, t in train + test:
        hi, ti = id_to_index.get(h), id_to_index.get(t)
        if hi is not None and ti is not None:
            known_tails_by_head.setdefault(hi, set()).add(ti)

    test_pairs = [
        (id_to_index[h], id_to_index[t])
        for (h, _r, t) in test
        if h in id_to_index and t in id_to_index
    ]
    metrics = evaluate(
        ctx,
        test_pairs,
        known_tails_by_head,
        rankers=("degree", "knn", "sa_raw", "sa_degnorm"),
        hops=hops,
        damping=damping,
        seed=seed,
    )
    return {
        name: {
            "mrr": m.mrr,
            "hits_at_1": m.hits_at_1,
            "hits_at_3": m.hits_at_3,
            "hits_at_10": m.hits_at_10,
        }
        for name, m in metrics.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-wiki-v1"))
    parser.add_argument("--model", type=str, default="TransE", help="TransE / RotatE / DistMult")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument(
        "--max-test",
        type=int,
        default=2000,
        help="Cap the shared test set (KGE + SA score the same triples). 0 = all.",
    )
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu", help="cpu / mps / cuda")
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    triples = _load_labeled_triples(args.root)
    max_test = None if args.max_test <= 0 else args.max_test
    train, test = _split_triples(
        triples, test_fraction=args.test_fraction, seed=args.seed, max_test=max_test
    )
    print(
        f"workspace: {args.root}  triples: {len(triples)}  "
        f"train: {len(train)}  test (train-vocab filtered): {len(test)}"
    )
    if not test:
        raise SystemExit("no scorable test triples after vocab filter")

    t_sa = time.perf_counter()
    sa = _run_sa(args.root, train, test, hops=args.hops, damping=args.damping, seed=args.seed)
    sa_s = time.perf_counter() - t_sa

    t_kge = time.perf_counter()
    kge = _run_kge(
        train,
        test,
        model=args.model,
        dim=args.dim,
        epochs=args.epochs,
        batch_size=args.batch_size,
        seed=args.seed,
        device=args.device,
    )
    kge_s = time.perf_counter() - t_kge

    rows = {
        "degree (untrained, popularity)": sa["degree"],
        "knn (untrained, geometry)": sa["knn"],
        "sa_raw (untrained, relation-agnostic)": sa["sa_raw"],
        "sa_degnorm (untrained, relation-agnostic)": sa["sa_degnorm"],
        f"{args.model} (TRAINED, relation-aware)": kge,
    }

    print()
    print(f"{'method':<44}{'MRR':>9}{'Hits@1':>9}{'Hits@3':>9}{'Hits@10':>9}")
    print("-" * 80)
    for name, m in rows.items():
        print(
            f"{name:<44}{m['mrr']:>9.4f}{m['hits_at_1']:>9.4f}"
            f"{m['hits_at_3']:>9.4f}{m['hits_at_10']:>9.4f}"
        )
    print()
    print(f"timing: SA {sa_s:.1f}s  KGE({args.model}, {args.epochs}ep) {kge_s:.1f}s")

    report = {
        "run_id": str(ULID()),
        "workspace": str(args.root),
        "model": args.model,
        "dim": args.dim,
        "epochs": args.epochs,
        "test_fraction": args.test_fraction,
        "seed": args.seed,
        "triples_total": len(triples),
        "train_triples": len(train),
        "test_triples": len(test),
        "results": rows,
        "timing_s": {"sa": sa_s, "kge": kge_s},
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"kge_baseline_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
