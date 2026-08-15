#!/usr/bin/env python3
"""Held-out link-prediction evaluation over a seeded MESH workspace.

Measures whether the substrate ranks relations it was *never told about* above
popularity and geometry baselines.  See
``theogony.mesh.eval.link_prediction`` for the protocol and ranker definitions.

Example:

    ./.venv/bin/python scripts/mesh_link_prediction_eval.py \
        --root data/mesh-smoke2-safe \
        --triplets data/raw/wikidata5m/wikidata5m_all_triplet.txt \
        --max-test 500 --scan-limit 3000000 --hops 3 --damping 0.5
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.link_prediction import (
    LinkPredictionReport,
    build_context,
    build_csr_over_nodes,
    build_heldout_testset,
    evaluate,
    split_edge_rows,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _l2_normalize_rows(matrix: torch.Tensor) -> torch.Tensor:
    norms = matrix.norm(dim=1, keepdim=True).clamp_min(1e-12)
    return matrix / norms


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-smoke2-safe"))
    parser.add_argument(
        "--mode",
        choices=("edge-split", "raw-file"),
        default="edge-split",
        help=(
            "edge-split: hide a fraction of the mesh's own edges and recover them "
            "(canonical KG-completion; works on edge-saturated seeds). "
            "raw-file: draw held-out positives from the Wikidata5m triplet file "
            "(only useful when the seed is NOT saturated over its node set)."
        ),
    )
    parser.add_argument(
        "--test-fraction",
        type=float,
        default=0.2,
        help="edge-split mode: fraction of mesh edges held out as the test set.",
    )
    parser.add_argument(
        "--triplets",
        type=Path,
        default=Path("data/raw/wikidata5m/wikidata5m_all_triplet.txt"),
    )
    parser.add_argument("--max-test", type=int, default=500)
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=3_000_000,
        help="Max lines to read from the triplet file (None-equivalent: -1 for all).",
    )
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--testset",
        type=Path,
        default=None,
        help="Cache path for the held-out test set (JSON). Reused unless --rebuild-testset.",
    )
    parser.add_argument("--rebuild-testset", action="store_true")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/run_reports/mesh_eval"),
    )
    args = parser.parse_args()

    scan_limit = None if args.scan_limit is not None and args.scan_limit < 0 else args.scan_limit

    t_load = time.perf_counter()
    rt = MeshRuntime.open(args.root.resolve())
    csr = rt.rebuild_csr()
    n = len(csr.node_ids)
    if n == 0:
        raise SystemExit("empty CSR — nothing to evaluate (seed the workspace first)")

    semantic_dim = rt.semantic_dim
    qid_to_node_id: dict[str, str] = {}
    node_id_to_qid: dict[str, str] = {}
    node_id_to_sem: dict[str, list[float]] = {}
    for node in rt.nodes.iter_consolidated():
        node_id = str(node.id)
        node_id_to_sem[node_id] = node.semantic_vector
        if node.qids:
            qid = node.qids[0].qid
            qid_to_node_id.setdefault(qid, node_id)
            node_id_to_qid[node_id] = qid

    sem = torch.zeros((n, semantic_dim), dtype=torch.float32)
    for node_id, idx in csr.id_to_index.items():
        vec = node_id_to_sem.get(node_id)
        if vec:
            sem[idx] = torch.tensor(vec[:semantic_dim], dtype=torch.float32)
    sem_unit = _l2_normalize_rows(sem)
    load_s = time.perf_counter() - t_load

    # Known tails (full mesh) for the filtered ranking protocol.
    edges = rt.edges.load_all_edges()
    known_tails_by_head: dict[int, set[int]] = {}
    for edge in edges:
        si = csr.id_to_index.get(str(edge.source_id))
        ti = csr.id_to_index.get(str(edge.target_id))
        if si is not None and ti is not None:
            known_tails_by_head.setdefault(si, set()).add(ti)

    t_testset = time.perf_counter()
    test_pairs: list[tuple[int, int]] = []
    skipped = 0

    if args.mode == "edge-split":
        edge_rows = [
            (str(e.source_id), str(e.target_id), float(e.weight) * float(e.frame_consistency))
            for e in edges
        ]
        train_rows, test_rows = split_edge_rows(
            edge_rows, test_fraction=args.test_fraction, seed=args.seed
        )
        train_csr = build_csr_over_nodes(csr.node_ids, train_rows)
        ctx = build_context(train_csr, sem_unit)
        for src_id, tgt_id, _w in test_rows:
            hi = csr.id_to_index.get(src_id)
            ti = csr.id_to_index.get(tgt_id)
            if hi is None or ti is None:
                skipped += 1
                continue
            test_pairs.append((hi, ti))
    else:
        ctx = build_context(csr, sem_unit)
        known_pairs = {
            (node_id_to_qid[str(e.source_id)], node_id_to_qid[str(e.target_id)])
            for e in edges
            if str(e.source_id) in node_id_to_qid and str(e.target_id) in node_id_to_qid
        }
        csr_qids = {q for q, nid in qid_to_node_id.items() if nid in csr.id_to_index}
        if args.testset is not None and args.testset.is_file() and not args.rebuild_testset:
            cached = json.loads(args.testset.read_text(encoding="utf-8"))
            triples: list[tuple[str, str, str]] = [tuple(row) for row in cached["triples"]]  # type: ignore[misc]
        else:
            triples = build_heldout_testset(
                args.triplets,
                csr_qids,
                known_pairs,
                max_test=args.max_test,
                seed=args.seed,
                scan_limit=scan_limit,
            )
            if args.testset is not None:
                args.testset.parent.mkdir(parents=True, exist_ok=True)
                args.testset.write_text(
                    json.dumps({"triples": [list(t) for t in triples]}, indent=2),
                    encoding="utf-8",
                )
        for head, _rel, tail in triples:
            hi = csr.id_to_index.get(qid_to_node_id.get(head, ""))
            ti = csr.id_to_index.get(qid_to_node_id.get(tail, ""))
            if hi is None or ti is None:
                skipped += 1
                continue
            test_pairs.append((hi, ti))

    testset_s = time.perf_counter() - t_testset

    if not test_pairs:
        raise SystemExit(
            "no scorable test triples resolved — for raw-file mode try a larger "
            "--scan-limit/--max-test, or use --mode edge-split"
        )

    t_eval = time.perf_counter()
    metrics = evaluate(
        ctx,
        test_pairs,
        known_tails_by_head,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
    )
    eval_s = time.perf_counter() - t_eval

    report = LinkPredictionReport(
        run_id=str(ULID()),
        workspace=str(args.root),
        mode=args.mode,
        test_fraction=args.test_fraction if args.mode == "edge-split" else None,
        triplet_source=str(args.triplets) if args.mode == "raw-file" else "(edge-split)",
        node_count=rt.nodes.consolidated_count(),
        csr_node_count=n,
        edge_count=len(edges),
        test_triples=len(test_pairs),
        skipped_endpoint_not_in_csr=skipped,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
        rankers=[metrics[r] for r in metrics],
        timing_s={
            "load_and_context": load_s,
            "build_testset": testset_s,
            "evaluate": eval_s,
        },
        notes="relation-agnostic SA (Step S1/S2.5); S3 must beat sa_degnorm.",
    )

    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / f"{report.run_id}.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print("=== mesh link-prediction eval ===")
    print(f"workspace:   {args.root}")
    print(f"mode:        {args.mode}", end="")
    print(f"  test_fraction={args.test_fraction}" if args.mode == "edge-split" else "")
    print(f"nodes:       {report.node_count}  csr_n: {n}  edges: {len(edges)}")
    print(f"test triples: {len(test_pairs)}  (skipped {skipped})")
    print(f"hops={args.hops} damping={args.damping} seed={args.seed}")
    print()
    print(f"{'ranker':<12}{'MRR':>9}{'Hits@1':>9}{'Hits@3':>9}{'Hits@10':>9}{'meanRank':>10}")
    print("-" * 58)
    for r in metrics.values():
        print(
            f"{r.ranker:<12}{r.mrr:>9.4f}{r.hits_at_1:>9.4f}"
            f"{r.hits_at_3:>9.4f}{r.hits_at_10:>9.4f}{r.mean_rank:>10.1f}"
        )
    print()
    print(f"report: {report_path}")
    print(f"timing: load={load_s:.2f}s testset={testset_s:.2f}s eval={eval_s:.2f}s")


if __name__ == "__main__":
    main()
