#!/usr/bin/env python3
"""Oneiros 'dreaming' probe: does consolidation improve prediction without new data?

Operationalises the project's most distinctive claim — *"the Chronik grows wiser
without reading new texts"* (TARGET_ARCHITECTURE / ROADMAP) — as a falsifiable
measurement.

Protocol (test edges are NEVER seen by dreaming):
  1. Split the mesh edges into train / held-out test (same scheme as the other
     eval harnesses).
  2. Baseline: Spreading Activation on the train graph predicts the held-out
     edges → MRR_before.
  3. Dream R rounds, using ONLY the train graph:
       - fire SA from sampled seed nodes,
       - read off the top co-activated targets that are NOT already neighbours,
       - propose Hebbian edges (seed → co-activated) into the delta buffer.
     Then run the substrate's own tick functions (merge deltas → super-linear
     decay → saturation caps). Edges that are robustly co-activated across rounds
     survive; spurious ones decay — this is consolidation, not raw transitive
     closure.
  4. Re-evaluate SA on the held-out test set → MRR_after.

If MRR_after > MRR_before, the substrate reorganised its *existing* knowledge into
a form that predicts held-out truths better — emergent inference, no new data.

This runs fully in memory on the substrate's real tick functions
(`merge_edge_deltas` / `decay_edges_inplace` / `enforce_saturation`); it never
writes to the workspace.  `knn` is reported as a control: it ignores edges, so its
MRR must stay constant before/after — a sanity check that the test set is fixed.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.link_prediction import (
    build_context,
    build_csr_over_nodes,
    evaluate,
    propagate,
    split_edge_rows,
)
from theogony.mesh.eval.loader import load_mesh_eval_data
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import (
    build_csr_from_edges,
    decay_edges_inplace,
    enforce_saturation,
    merge_edge_deltas,
)


def _edges_from_rows(rows: list[tuple[str, str, float]]) -> list[Edge]:
    now = datetime.now(UTC)
    return [
        Edge(source_id=s, target_id=t, weight=w, born_at=now, last_fired_at=now)  # type: ignore[arg-type]
        for (s, t, w) in rows
    ]


def _eval_on(
    node_ids: list[str],
    edges: list[Edge],
    sem_unit: torch.Tensor,
    test_pairs: list[tuple[int, int]],
    known: dict[int, set[int]],
    *,
    hops: int,
    damping: float,
    seed: int,
) -> dict[str, float]:
    rows = [(str(e.source_id), str(e.target_id), float(e.weight)) for e in edges]
    csr = build_csr_over_nodes(node_ids, rows)
    ctx = build_context(csr, sem_unit)
    metrics = evaluate(
        ctx, test_pairs, known, rankers=("knn", "sa_raw"), hops=hops, damping=damping, seed=seed
    )
    return {name: m.mrr for name, m in metrics.items()}


def _dream_round(
    edges: list[Edge],
    node_ids: list[str],
    *,
    n_seeds: int,
    top_k: int,
    hops: int,
    damping: float,
    delta_weight: float,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Fire SA from sampled seeds; propose Hebbian deltas to top co-activated nodes."""
    rows = [(str(e.source_id), str(e.target_id), float(e.weight)) for e in edges]
    csr = build_csr_from_edges(edges)
    n = len(csr.node_ids)
    adj = torch.sparse_csr_tensor(
        csr.crow_indices, csr.col_indices, csr.values, size=(n, n), dtype=torch.float32
    )
    existing = {(s, t) for s, t, _w in rows}
    index_to_id = csr.node_ids

    seed_indices = rng.sample(range(n), min(n_seeds, n))
    deltas: list[dict[str, object]] = []
    for si in seed_indices:
        act = propagate(adj, si, n, hops=hops, damping=damping)
        act[si] = 0.0
        k = min(top_k, n)
        vals, idxs = torch.topk(act, k)
        src_id = index_to_id[si]
        for val, ti in zip(vals.tolist(), idxs.tolist(), strict=False):
            if val <= 0.0:
                continue
            tgt_id = index_to_id[int(ti)]
            if (src_id, tgt_id) in existing or src_id == tgt_id:
                continue
            deltas.append({"source_id": src_id, "target_id": tgt_id, "weight_delta": delta_weight})
    return deltas


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-wiki-v1"))
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--n-seeds", type=int, default=2000, help="Seed nodes fired per round.")
    parser.add_argument("--top-k", type=int, default=5, help="Co-activated targets per seed.")
    parser.add_argument("--delta-weight", type=float, default=0.5)
    parser.add_argument("--decay-lambda", type=float, default=0.02)
    parser.add_argument("--max-out-degree", type=int, default=64)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--max-test", type=int, default=1000)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    data = load_mesh_eval_data(args.root)
    id_to_index = data.id_to_index
    train_rows, test_rows = split_edge_rows(
        data.edge_rows, test_fraction=args.test_fraction, seed=args.seed
    )

    known: dict[int, set[int]] = {}
    for s, t, _w in data.edge_rows:
        si, ti = id_to_index.get(s), id_to_index.get(t)
        if si is not None and ti is not None:
            known.setdefault(si, set()).add(ti)
    test_pairs = [
        (id_to_index[s], id_to_index[t])
        for s, t, _w in test_rows
        if s in id_to_index and t in id_to_index
    ]
    if args.max_test and len(test_pairs) > args.max_test:
        test_pairs = random.Random(args.seed).sample(test_pairs, args.max_test)

    edges = _edges_from_rows(train_rows)
    rng = random.Random(args.seed)

    t0 = time.perf_counter()
    before = _eval_on(
        data.node_ids,
        edges,
        data.sem_unit,
        test_pairs,
        known,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
    )
    history = [
        {"round": 0, "edges": len(edges), "sa_raw_mrr": before["sa_raw"], "knn_mrr": before["knn"]}
    ]

    for r in range(1, args.rounds + 1):
        deltas = _dream_round(
            edges,
            data.node_ids,
            n_seeds=args.n_seeds,
            top_k=args.top_k,
            hops=args.hops,
            damping=args.damping,
            delta_weight=args.delta_weight,
            rng=rng,
        )
        edges = merge_edge_deltas(edges, deltas, w_max=1.0)
        decay_edges_inplace(edges, lam=args.decay_lambda, dt=1.0)
        edges = enforce_saturation(edges, max_out_degree=args.max_out_degree, w_max=1.0)
        mid = _eval_on(
            data.node_ids,
            edges,
            data.sem_unit,
            test_pairs,
            known,
            hops=args.hops,
            damping=args.damping,
            seed=args.seed,
        )
        history.append(
            {
                "round": r,
                "edges": len(edges),
                "deltas": len(deltas),
                "sa_raw_mrr": mid["sa_raw"],
                "knn_mrr": mid["knn"],
            }
        )

    after = history[-1]
    elapsed = time.perf_counter() - t0

    print("=== Oneiros dreaming probe ===")
    print(f"workspace: {args.root}  nodes: {len(data.node_ids)}  test: {len(test_pairs)} (fixed)")
    print(
        f"rounds={args.rounds} n_seeds={args.n_seeds} top_k={args.top_k} "
        f"delta_w={args.delta_weight} decay_lambda={args.decay_lambda}"
    )
    print()
    print(f"{'round':>5}{'edges':>10}{'deltas':>9}{'sa_raw MRR':>12}{'knn MRR (ctrl)':>16}")
    print("-" * 52)
    for h in history:
        print(
            f"{h['round']:>5}{h['edges']:>10}{h.get('deltas', 0):>9}"
            f"{h['sa_raw_mrr']:>12.4f}{h['knn_mrr']:>16.4f}"
        )
    delta_mrr = after["sa_raw_mrr"] - before["sa_raw"]
    print()
    print(
        f"sa_raw MRR: {before['sa_raw']:.4f} -> {after['sa_raw_mrr']:.4f}  "
        f"(Δ {delta_mrr:+.4f}, {100 * delta_mrr / max(before['sa_raw'], 1e-9):+.1f}%)"
    )
    print(f"knn control: {before['knn']:.4f} -> {after['knn_mrr']:.4f}  (must be ~constant)")
    print(f"timing: {elapsed:.1f}s")

    report = {
        "run_id": str(ULID()),
        "workspace": str(args.root),
        "params": vars(args) | {"root": str(args.root), "report_dir": str(args.report_dir)},
        "history": history,
        "sa_raw_mrr_before": before["sa_raw"],
        "sa_raw_mrr_after": after["sa_raw_mrr"],
        "delta_mrr": delta_mrr,
        "knn_mrr_before": before["knn"],
        "knn_mrr_after": after["knn_mrr"],
        "elapsed_s": elapsed,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"oneiros_dream_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
