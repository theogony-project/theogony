#!/usr/bin/env python
"""Read finished answer runs by the dataset's question type (PHX-1127).

    scripts/mesh_qa_by_type.py RUN.json [RUN.json ...] [--cache-dir data/raw/qa_bench] \
        [--pairs constellation_typed:passages,constellation_typed:vector_only] [--json out.json]

`scripts/mesh_qa_constellation.py` reports one exact match per arm, and by the
shape of the gold answer. 2WikiMultihopQA also labels what each question asks
for — compositional, inference, comparison, bridge_comparison — and read by
that, the tie with passage retrieval is a lead of 6.5 to 9.0 points on the
questions that do not name their answer and a deficit on plain comparisons,
which the model answers right 62% of the time with no material at all.

Prints, per run: exact match, how often the answer stood in the material and
the exact match where it did, by type and pool; then every pair by type and
pool, and each pool once more by which arm found the answer and by the shape
of the gold.

No model is called and nothing is written but --json. A run whose rows carry no
`question_type` (every run before PHX-1127) takes the types from the dataset
file under --cache-dir; if that is not on disk, the run cannot be read by type
and the script says so instead of fetching it. The pairs default to the ones the
harness reports (`qa_mesh.QA_PAIRS`), restricted to the arms the run has.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from theogony.mesh.eval.qa_datasets import POOLED_TYPES, question_types
from theogony.mesh.eval.qa_mesh import (
    BY_TYPE_TABLES,
    QA_PAIRS,
    by_type_lines,
    by_type_report,
    pair_by_type_lines,
    results_from_run,
)


def read_run(
    run: dict[str, Any], cache_dir: Path, pairs: tuple[tuple[str, str], ...]
) -> dict[str, Any]:
    """The by-type summary and pairings of one run file's answer rows."""
    dataset = str(run.get("dataset", ""))
    results = results_from_run(run, question_types=question_types(dataset, cache_dir))
    untyped = sorted({r.qid for r in results if not r.question_type})
    if untyped:
        raise SystemExit(
            f"{len(untyped)} question(s) of this run have no question type: the rows carry "
            f"none and the dataset file for {dataset!r} under {cache_dir} does not give one "
            "(not on disk, or the release labels no types)"
        )
    return {
        "model": run.get("model"),
        "mesh": run.get("mesh"),
        "dataset": dataset,
        "arms": sorted({r.arm for r in results}),
        **by_type_report(results, pooled=POOLED_TYPES.get(dataset), pairs=pairs),
    }


def _print(path: Path, read: dict[str, Any]) -> None:
    print(f"\n== {path}  model={read['model']}  mesh={read['mesh']}  dataset={read['dataset']}")
    for metric, label in BY_TYPE_TABLES:
        print(f"\n{label}")
        print("\n".join(by_type_lines(read["by_type"], read["arms"], metric=metric)))
    for pair, table in read["paired_by_type"].items():
        print(f"\n{pair}  (exact match better / worse, exact sign test)")
        print("\n".join(pair_by_type_lines(table, read["paired_in_pool"][pair])))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="run files of mesh_qa_constellation.py")
    ap.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    ap.add_argument(
        "--pairs", default="", help="arm:baseline,arm:baseline (default: the harness's pairs)"
    )
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    pairs: tuple[tuple[str, str], ...] = QA_PAIRS
    if args.pairs:
        wanted = [tuple(p.split(":")) for p in args.pairs.split(",") if p.strip()]
        if any(len(p) != 2 for p in wanted):
            sys.exit("--pairs takes arm:baseline, separated by commas")
        pairs = tuple((a.strip(), b.strip()) for a, b in wanted)

    out: dict[str, Any] = {}
    for path in args.runs:
        read = read_run(json.loads(path.read_text(encoding="utf-8")), args.cache_dir, pairs)
        out[str(path)] = read
        _print(path, read)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwritten: {args.json}")


if __name__ == "__main__":
    main()
