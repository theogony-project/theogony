#!/usr/bin/env python3
"""Relation-conditioned Spreading Activation — the empirical kernel of S3.

All four prior experiments triangulate on one lever: the gap between
relation-agnostic SA and relation-aware trained KGE (RotatE). MESH_RETRIEVAL's
'frame routing' is exactly the mechanism to close it — a masked SpMV that
conditions propagation on edge semantics. This script implements the minimal,
measurable version of that idea and tests, on the *same split* as the KGE
baseline, whether conditioning on the query relation closes the SA -> RotatE gap.

This is NOT the full S3 module (MMR + weight-class + sub-mesh + constellation +
`mesh ask`); that is a separate doctrine-defined PR. This is the falsifiable
proof-of-lever that justifies building it.

Rankers (predict tail t given head h and query relation r):
  * sa_raw       — relation-agnostic SA over all edges (the current primitive).
  * sa_sym       — degree-symmetric-normalised SA (D^-1/2 A D^-1/2): hub-collapse
                   correction, relation-agnostic.
  * sa_rel       — relation-conditioned: free multi-hop activation from h for
                   hops-1, then ONE relation-r-masked hop (masked SpMV / frame
                   routing). Uses r, like KGE does.
  * sa_rel_sym   — sa_rel on the symmetric-normalised free-propagation graph.

The trained KGE numbers (TransE / RotatE) come from mesh_kge_baseline.py on the
identical split and are quoted in the writeup for comparison.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.link_prediction import filtered_rank, propagate, rank_metrics
from theogony.mesh.eval.loader import load_mesh_eval_data
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _labeled_triples(root: Path) -> list[tuple[str, str, str]]:
    rt = MeshRuntime.open(root.resolve())
    out = []
    for e in rt.edges.load_all_edges():
        out.append(
            (
                str(e.source_id),
                e.relation_descriptor or e.relation_kind or "related",
                str(e.target_id),
            )
        )
    return out


def _split(triples, *, test_fraction, seed, max_test):
    """Identical protocol to mesh_kge_baseline._split_triples (comparable numbers)."""
    order = list(range(len(triples)))
    random.Random(seed).shuffle(order)
    n_test = int(round(len(order) * test_fraction))
    test_raw = [triples[i] for i in order[:n_test]]
    train = [triples[i] for i in order[n_test:]]
    ent = {h for h, _r, _t in train} | {t for _h, _r, t in train}
    rel = {r for _h, r, _t in train}
    test = [(h, r, t) for (h, r, t) in test_raw if h in ent and t in ent and r in rel]
    if max_test and len(test) > max_test:
        test = random.Random(seed + 1).sample(test, max_test)
    return train, test


def _sym_normalize(
    rows: torch.Tensor, cols: torch.Tensor, vals: torch.Tensor, n: int
) -> torch.Tensor:
    """Return values scaled by D^-1/2 (out) and D^-1/2 (in) — symmetric normalisation."""
    out_deg = torch.zeros(n, dtype=torch.float32).scatter_add_(0, rows, vals)
    in_deg = torch.zeros(n, dtype=torch.float32).scatter_add_(0, cols, vals)
    d_out = out_deg.clamp_min(1e-12).rsqrt()
    d_in = in_deg.clamp_min(1e-12).rsqrt()
    return vals * d_out[rows] * d_in[cols]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-wiki-v1"))
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--max-test", type=int, default=2000)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    data = load_mesh_eval_data(args.root)
    idx = data.id_to_index
    n = len(data.node_ids)

    triples = _labeled_triples(args.root)
    train, test = _split(
        triples, test_fraction=args.test_fraction, seed=args.seed, max_test=args.max_test
    )
    print(
        f"workspace: {args.root}  nodes: {n}  triples: {len(triples)}  "
        f"train: {len(train)}  test: {len(test)}"
    )

    # full (relation-agnostic) train adjacency
    tr = [(idx[h], idx[t]) for h, _r, t in train if h in idx and t in idx]
    rows = torch.tensor([a for a, _b in tr], dtype=torch.int64)
    cols = torch.tensor([b for _a, b in tr], dtype=torch.int64)
    vals = torch.ones(len(tr), dtype=torch.float32)
    adj = torch.sparse_coo_tensor(torch.stack([rows, cols]), vals, (n, n)).coalesce()
    sym_vals = _sym_normalize(rows, cols, vals, n)
    adj_sym = torch.sparse_coo_tensor(torch.stack([rows, cols]), sym_vals, (n, n)).coalesce()

    # per-relation edge arrays for the masked final hop
    rel_edges: dict[str, list[tuple[int, int]]] = {}
    for h, r, t in train:
        if h in idx and t in idx:
            rel_edges.setdefault(r, []).append((idx[h], idx[t]))
    rel_rows = {r: torch.tensor([a for a, _ in e], dtype=torch.int64) for r, e in rel_edges.items()}
    rel_cols = {r: torch.tensor([b for _, b in e], dtype=torch.int64) for r, e in rel_edges.items()}

    known: dict[int, set[int]] = {}
    for h, _r, t in train + test:
        if h in idx and t in idx:
            known.setdefault(idx[h], set()).add(idx[t])

    def masked_hop(a: torch.Tensor, r: str) -> torch.Tensor:
        score = torch.zeros(n, dtype=torch.float32)
        score.index_add_(0, rel_cols[r], a[rel_rows[r]])
        return score

    ranks: dict[str, list[float]] = {k: [] for k in ("sa_raw", "sa_sym", "sa_rel", "sa_rel_sym")}
    t0 = time.perf_counter()
    for h, r, t in test:
        hi, ti = idx[h], idx[t]
        kt = known.get(hi, set())

        a_full = propagate(adj, hi, n, hops=args.hops, damping=args.damping)
        a_sym = propagate(adj_sym, hi, n, hops=args.hops, damping=args.damping)
        a_free = propagate(adj, hi, n, hops=max(1, args.hops - 1), damping=args.damping)
        a_free_sym = propagate(adj_sym, hi, n, hops=max(1, args.hops - 1), damping=args.damping)

        ranks["sa_raw"].append(filtered_rank(a_full, hi, ti, kt))
        ranks["sa_sym"].append(filtered_rank(a_sym, hi, ti, kt))
        ranks["sa_rel"].append(filtered_rank(masked_hop(a_free, r), hi, ti, kt))
        ranks["sa_rel_sym"].append(filtered_rank(masked_hop(a_free_sym, r), hi, ti, kt))

    elapsed = time.perf_counter() - t0
    metrics = {name: rank_metrics(name, rs) for name, rs in ranks.items()}

    print()
    print(f"{'ranker':<14}{'MRR':>9}{'Hits@1':>9}{'Hits@3':>9}{'Hits@10':>9}{'meanRank':>10}")
    print("-" * 60)
    for m in metrics.values():
        print(
            f"{m.ranker:<14}{m.mrr:>9.4f}{m.hits_at_1:>9.4f}{m.hits_at_3:>9.4f}{m.hits_at_10:>9.4f}{m.mean_rank:>10.1f}"
        )
    print()
    print("reference (same split, mesh_kge_baseline.py): TransE MRR 0.145, RotatE MRR 0.285")
    print(f"timing: {elapsed:.1f}s")

    report = {
        "run_id": str(ULID()),
        "workspace": str(args.root),
        "test_triples": len(test),
        "hops": args.hops,
        "damping": args.damping,
        "seed": args.seed,
        "rankers": {
            m.ranker: {
                "mrr": m.mrr,
                "hits_at_1": m.hits_at_1,
                "hits_at_3": m.hits_at_3,
                "hits_at_10": m.hits_at_10,
                "mean_rank": m.mean_rank,
            }
            for m in metrics.values()
        },
        "kge_reference": {"TransE_mrr": 0.145, "RotatE_mrr": 0.285},
        "elapsed_s": elapsed,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"relation_retrieval_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
