#!/usr/bin/env python3
"""Tonight's experiments — propagation-operator comparison + locality test.

Two MacBook-runnable studies on a seeded workspace, no training:

1. **Propagation operators (held-out link prediction, edge-split).** Compares the
   relation-agnostic propagation primitives against geometry/popularity baselines:
     - degree, knn            — popularity / pure geometry (controls)
     - sa_raw                 — Spreading Activation over raw weighted adjacency
     - sa_degnorm             — random-walk-normalised SA (hub-collapse fix)
     - sa_ppr                 — personalised PageRank (restart) — NEW
   This tells us which propagation operator should be the production default.

2. **Locality test (the fragmentation precondition).** For sampled seeds, measures
   how *concentrated* the activation energy is — participation ratio (effective
   number of active nodes) and top-K mass — under sa_raw vs sa_ppr. If PPR keeps the
   energy in a small effective set even on a small-world graph, then topic-sharded
   expert-MNLMs are viable: most of a query resolves inside one region, cross-shard
   activation is rare. This is the empirical green/red light for the "fragment the
   big MNLM into expert-MNLMs" idea.

The relation-CONDITIONED comparison (the biggest measured lever, 0.110 -> 0.254) lives
in scripts/mesh_relation_retrieval.py — run that too tonight for the full picture.

Example (tonight, on the 100k subnet):
    ./.venv/bin/python scripts/mesh_tonight_experiments.py \
        --root data/mesh-wiki-100k --max-test 1000 --locality-seeds 200
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.link_prediction import (
    build_adjacency,
    build_csr_over_nodes,
    build_normalized_adjacency,
    filtered_rank,
    in_degree_from_csr,
    propagate,
    rank_metrics,
    split_edge_rows,
)
from theogony.mesh.eval.loader import load_mesh_eval_data


def propagate_ppr(
    adj_norm: torch.Tensor, seed: int, n: int, *, iters: int, alpha: float
) -> torch.Tensor:
    """Personalised PageRank: x <- (1-alpha)*A_norm^T x + alpha*e_seed.

    Restart toward the seed keeps mass local and implicitly normalises away the
    hub-collapse of raw Spreading Activation.
    """
    device = adj_norm.device
    e = torch.zeros(n, dtype=torch.float32, device=device)
    e[seed] = 1.0
    x = e.clone()
    for _ in range(iters):
        x = (1.0 - alpha) * torch.sparse.mm(adj_norm.t(), x.unsqueeze(1)).squeeze(1) + alpha * e
    return x


def _concentration(x: torch.Tensor, seed: int) -> dict[str, float]:
    """Energy-concentration metrics for one activation vector (mass off the seed)."""
    v = x.clone()
    v[seed] = 0.0
    v = v.clamp_min(0.0)
    total = float(v.sum().item())
    if total <= 0.0:
        return {
            "participation_ratio": 0.0,
            "top10_mass": 0.0,
            "top100_mass": 0.0,
            "top1000_mass": 0.0,
        }
    # participation ratio = (sum)^2 / sum(sq) — the effective number of active nodes
    pr = float((total**2) / float((v * v).sum().item()))
    out = {"participation_ratio": pr}
    for k in (10, 100, 1000):
        topk = torch.topk(v, min(k, v.numel())).values.sum().item()
        out[f"top{k}_mass"] = float(topk) / total
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-wiki-100k"))
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--max-test", type=int, default=1000)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--ppr-alpha", type=float, default=0.15)
    parser.add_argument("--ppr-iters", type=int, default=12)
    parser.add_argument("--locality-seeds", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    data = load_mesh_eval_data(args.root)
    idx = data.id_to_index
    n = len(data.node_ids)
    print(f"workspace: {args.root}  nodes: {n}  edges: {len(data.edge_rows)}")

    # ---- Study 1: propagation operators on held-out edges ----
    train_rows, test_rows = split_edge_rows(
        data.edge_rows, test_fraction=args.test_fraction, seed=args.seed
    )
    train_csr = build_csr_over_nodes(data.node_ids, train_rows)
    device = torch.device("cpu")
    adj = build_adjacency(train_csr, device)
    adj_norm = build_normalized_adjacency(train_csr, device)
    deg = in_degree_from_csr(train_csr).to(device)
    sem = data.sem_unit.to(device)

    known: dict[int, set[int]] = {}
    for s, t, _w in data.edge_rows:
        si, ti = idx.get(s), idx.get(t)
        if si is not None and ti is not None:
            known.setdefault(si, set()).add(ti)

    test_pairs = [(idx[s], idx[t]) for s, t, _w in test_rows if s in idx and t in idx]
    if args.max_test and len(test_pairs) > args.max_test:
        test_pairs = random.Random(args.seed).sample(test_pairs, args.max_test)

    rankers = ("degree", "knn", "sa_raw", "sa_degnorm", "sa_ppr")
    ranks: dict[str, list[float]] = {r: [] for r in rankers}
    t0 = time.perf_counter()
    for hi, ti in test_pairs:
        kt = known.get(hi, set())
        scores = {
            "degree": deg,
            "knn": sem @ sem[hi],
            "sa_raw": propagate(adj, hi, n, hops=args.hops, damping=args.damping),
            "sa_degnorm": propagate(adj_norm, hi, n, hops=args.hops, damping=args.damping),
            "sa_ppr": propagate_ppr(adj_norm, hi, n, iters=args.ppr_iters, alpha=args.ppr_alpha),
        }
        for r in rankers:
            ranks[r].append(filtered_rank(scores[r], hi, ti, kt))
    study1 = {r: rank_metrics(r, ranks[r]) for r in rankers}
    s1_s = time.perf_counter() - t0

    print()
    print(f"--- Study 1: propagation operators ({len(test_pairs)} held-out edges) ---")
    print(f"{'ranker':<14}{'MRR':>9}{'Hits@1':>9}{'Hits@10':>9}{'meanRank':>10}")
    print("-" * 51)
    for m in study1.values():
        print(
            f"{m.ranker:<14}{m.mrr:>9.4f}{m.hits_at_1:>9.4f}{m.hits_at_10:>9.4f}{m.mean_rank:>10.1f}"
        )

    # ---- Study 2: locality (fragmentation precondition) ----
    full_csr = build_csr_over_nodes(data.node_ids, list(data.edge_rows))
    full_adj = build_adjacency(full_csr, device)
    full_adj_norm = build_normalized_adjacency(full_csr, device)

    rng = random.Random(args.seed + 7)
    seeds = rng.sample(range(n), min(args.locality_seeds, n))
    agg: dict[str, list[dict[str, float]]] = {"sa_raw": [], "sa_ppr": []}
    t1 = time.perf_counter()
    for si in seeds:
        x_raw = propagate(full_adj, si, n, hops=args.hops, damping=args.damping)
        x_ppr = propagate_ppr(full_adj_norm, si, n, iters=args.ppr_iters, alpha=args.ppr_alpha)
        agg["sa_raw"].append(_concentration(x_raw, si))
        agg["sa_ppr"].append(_concentration(x_ppr, si))
    s2_s = time.perf_counter() - t1

    def _mean(rows: list[dict[str, float]], key: str) -> float:
        vals = [r[key] for r in rows if r.get(key, 0.0) > 0.0 or key.startswith("top")]
        return sum(vals) / max(len(vals), 1)

    print()
    print(f"--- Study 2: locality / energy concentration ({len(seeds)} seeds) ---")
    print(f"{'operator':<12}{'eff.nodes(PR)':>15}{'top10':>9}{'top100':>10}{'top1000':>10}")
    print("-" * 56)
    locality_summary = {}
    for op in ("sa_raw", "sa_ppr"):
        pr = _mean(agg[op], "participation_ratio")
        t10 = _mean(agg[op], "top10_mass")
        t100 = _mean(agg[op], "top100_mass")
        t1000 = _mean(agg[op], "top1000_mass")
        locality_summary[op] = {
            "participation_ratio": pr,
            "top10_mass": t10,
            "top100_mass": t100,
            "top1000_mass": t1000,
            "effective_fraction_of_graph": pr / n,
        }
        print(f"{op:<12}{pr:>15.1f}{t10:>9.3f}{t100:>10.3f}{t1000:>10.3f}")
    print()
    print(
        "Read: small participation ratio + high top-K mass = energy stays in a small "
        "effective region = topic-sharded expert-MNLMs are viable. Compare sa_ppr vs sa_raw."
    )

    report = {
        "run_id": str(ULID()),
        "workspace": str(args.root),
        "nodes": n,
        "edges": len(data.edge_rows),
        "params": {
            "test_fraction": args.test_fraction,
            "max_test": len(test_pairs),
            "hops": args.hops,
            "damping": args.damping,
            "ppr_alpha": args.ppr_alpha,
            "ppr_iters": args.ppr_iters,
            "locality_seeds": len(seeds),
            "seed": args.seed,
        },
        "study1_propagation_operators": {
            m.ranker: {
                "mrr": m.mrr,
                "hits_at_1": m.hits_at_1,
                "hits_at_3": m.hits_at_3,
                "hits_at_10": m.hits_at_10,
                "mean_rank": m.mean_rank,
            }
            for m in study1.values()
        },
        "study2_locality": locality_summary,
        "timing_s": {"study1": s1_s, "study2": s2_s},
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"tonight_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out}")
    print(f"timing: study1 {s1_s:.0f}s  study2 {s2_s:.0f}s")


if __name__ == "__main__":
    main()
