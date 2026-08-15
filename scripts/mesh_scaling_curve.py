#!/usr/bin/env python3
"""Edge-density scaling sweep over a seeded MESH workspace.

Holds the test set fixed and grows the amount of training structure, so the
curves answer: *does Spreading Activation pull away from geometric (kNN)
retrieval as edge density rises?*  See ``theogony.mesh.eval.scaling``.

Example:

    ./.venv/bin/python scripts/mesh_scaling_curve.py \
        --root data/mesh-smoke2-safe \
        --densities 0.05,0.1,0.2,0.4,0.7,1.0 --max-test 1000 --plot
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ulid import ULID

from theogony.mesh.eval.loader import load_mesh_eval_data
from theogony.mesh.eval.scaling import run_sweep


def _parse_densities(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def _write_csv(report, path: Path) -> None:
    ranker_names = [r.ranker for r in report.levels[0].rankers] if report.levels else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["density", "train_edges", "mean_out_degree", *[f"mrr_{r}" for r in ranker_names]]
        )
        for level in report.levels:
            mrr_by = {r.ranker: r.mrr for r in level.rankers}
            writer.writerow(
                [level.density, level.train_edges, f"{level.mean_out_degree:.4f}"]
                + [f"{mrr_by[r]:.4f}" for r in ranker_names]
            )


def _maybe_plot(report, path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    xs = [lvl.mean_out_degree for lvl in report.levels]
    ranker_names = [r.ranker for r in report.levels[0].rankers]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for ranker in ranker_names:
        ys = [next(r.mrr for r in lvl.rankers if r.ranker == ranker) for lvl in report.levels]
        style = "--" if ranker == "knn" else "-"
        ax.plot(xs, ys, style, marker="o", label=ranker)
    ax.set_xlabel("mean out-degree (training edges / node)")
    ax.set_ylabel("MRR (filtered)")
    ax.set_title(f"Spreading Activation vs geometry as density grows\n{report.workspace}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-smoke2-safe"))
    parser.add_argument("--densities", type=str, default="0.05,0.1,0.2,0.4,0.7,1.0")
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--max-test",
        type=int,
        default=1000,
        help="Subsample the fixed test set for tractable sweeps (0 = use all).",
    )
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    parser.add_argument("--plot", action="store_true", help="Also write a PNG (needs matplotlib).")
    args = parser.parse_args()

    densities = _parse_densities(args.densities)
    max_test = None if args.max_test <= 0 else args.max_test

    data = load_mesh_eval_data(args.root)
    report = run_sweep(
        run_id=str(ULID()),
        workspace=str(args.root),
        node_ids=data.node_ids,
        all_edge_rows=data.edge_rows,
        sem_unit=data.sem_unit,
        densities=densities,
        test_fraction=args.test_fraction,
        hops=args.hops,
        damping=args.damping,
        seed=args.seed,
        max_test=max_test,
    )

    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.report_dir / f"scaling_{report.run_id}.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    csv_path = args.report_dir / f"scaling_{report.run_id}.csv"
    _write_csv(report, csv_path)

    ranker_names = [r.ranker for r in report.levels[0].rankers]
    print("=== mesh edge-density scaling sweep ===")
    print(f"workspace: {report.workspace}")
    print(
        f"nodes: {report.node_count}  total_edges: {report.total_edges}  "
        f"test: {report.test_triples} (fixed)  hops={report.hops} damping={report.damping}"
    )
    print()
    header = f"{'mean_deg':>9}{'train_E':>9}" + "".join(f"{r:>11}" for r in ranker_names)
    print(header + f"{'sa-knn':>10}")
    print("-" * len(header + f"{'sa-knn':>10}"))
    for level in report.levels:
        mrr_by = {r.ranker: r.mrr for r in level.rankers}
        gap = mrr_by.get("sa_raw", 0.0) - mrr_by.get("knn", 0.0)
        row = f"{level.mean_out_degree:>9.2f}{level.train_edges:>9}"
        row += "".join(f"{mrr_by[r]:>11.4f}" for r in ranker_names)
        row += f"{gap:>+10.4f}"
        print(row)
    print()
    print(f"report: {json_path}")
    print(f"csv:    {csv_path}")

    if args.plot:
        png_path = args.report_dir / f"scaling_{report.run_id}.png"
        if _maybe_plot(report, png_path):
            print(f"plot:   {png_path}")
        else:
            print("plot:   (matplotlib not installed — pip install matplotlib for --plot)")
    print(f"timing: {report.timing_s:.1f}s")


if __name__ == "__main__":
    main()
