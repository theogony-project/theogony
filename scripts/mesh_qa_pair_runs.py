#!/usr/bin/env python
"""Pair two answer runs of scripts/mesh_qa_constellation.py question for question.

    scripts/mesh_qa_pair_runs.py --a off.json --b on.json [--json out.json]

The script's own sign tests compare arms within one run. The question of
PHX-1118 is the same arm on two meshes — accrual off against accrual on — so
the two runs are read together: for every arm both ran, how often B beats A on
exact match and on F1, the exact sign test on the discordant questions, and the
same by answer kind and by question type (PHX-1127; a run written before its
rows carried the type takes it from the dataset file under --cache-dir, when
that is on disk). Two runs with different models are refused: the alias has
drifted nine points between months, and only pairs from one sitting are read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from theogony.mesh.eval.qa_datasets import POOLED_TYPES, question_types
from theogony.mesh.eval.qa_mesh import paired_by_kind, paired_by_type, paired_qa, results_from_run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=Path, required=True, help="the baseline run (accrual off)")
    ap.add_argument("--b", type=Path, required=True, help="the run to compare (accrual on)")
    ap.add_argument(
        "--cache-dir",
        default=Path("data/raw/qa_bench"),
        type=Path,
        help="where the dataset file lies, for the question types of older runs",
    )
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (args.a, args.b))
    # Runs written before 2026-10-25 carry no `seed`; they were sampled with the
    # script's default, and the question sets below are the hard check.
    defaults: dict[str, object] = {"seed": 0}
    for key in ("model", "dataset", "questions", "top_k", "passage_k", "k_seeds", "seed"):
        missing = [name for name, run in (("A", a), ("B", b)) if key not in run]
        if missing and key in defaults:
            print(
                f"warning: '{key}' missing from {' and '.join(missing)}; assuming the default "
                f"{defaults[key]!r} (an older run)",
                file=sys.stderr,
            )
        va, vb = a.get(key, defaults.get(key)), b.get(key, defaults.get(key))
        if va != vb:
            sys.exit(f"{key} differs: {va} vs {vb}; the two runs are not one sitting")
    # A run that names one model and was answered by another is not a run of
    # the named model (PHX-1123); runs written before 2026-11-08 do not say
    # who answered, and cannot be checked.
    for name, run in (("A", a), ("B", b)):
        named = str(run["model"]).split("/", 1)[-1]
        others = {
            m: n for m, n in (run.get("answered_by") or {}).items() if m not in (named, "none")
        }
        if others:
            sys.exit(f"{name} names {named} but was answered by {others}; not a run of {named}")
        failed = (run.get("answered_by") or {}).get("none", 0)
        if failed:
            print(
                f"warning: {failed} calls of {name} failed and score as empty answers",
                file=sys.stderr,
            )
    qids_a, qids_b = ({x["qid"] for x in run["answers"]} for run in (a, b))
    if qids_a != qids_b:
        sys.exit(
            f"question sets differ ({len(qids_a ^ qids_b)} qids not in both); "
            "same --seed and --limit required"
        )
    types = question_types(a["dataset"], args.cache_dir)
    pooled = POOLED_TYPES.get(a["dataset"])
    results = results_from_run(a, question_types=types, arm_suffix="@a") + results_from_run(
        b, question_types=types, arm_suffix="@b"
    )
    arms = sorted({x["arm"] for x in a["answers"]} & {x["arm"] for x in b["answers"]})
    out: dict = {"a": str(args.a), "b": str(args.b), "model": a["model"], "arms": {}}
    print(f"model {a['model']}  A={a['mesh']}  B={b['mesh']}")
    for arm in arms:
        pair = paired_qa(results, arm=f"{arm}@b", baseline=f"{arm}@a")
        kinds = paired_by_kind(results, arm=f"{arm}@b", baseline=f"{arm}@a")
        by_type = paired_by_type(results, arm=f"{arm}@b", baseline=f"{arm}@a", pooled=pooled)
        em_a, em_b = a["summary"][arm]["exact_match"], b["summary"][arm]["exact_match"]
        out["arms"][arm] = {
            "em_a": em_a,
            "em_b": em_b,
            "paired": pair,
            "by_kind": kinds,
            "by_type": by_type,
        }
        print(
            f"\n{arm}: paired {pair['questions']:.0f}  "
            f"EM {em_a:.1%} -> {em_b:.1%} ({em_b - em_a:+.1%})  "
            f"better/worse {pair['em_better']:.0f}/{pair['em_worse']:.0f} (p={pair['p_em']:.3g})  "
            f"F1 better/worse {pair['f1_better']:.0f}/{pair['f1_worse']:.0f}"
        )
        for group, pk in (*kinds.items(), *by_type.items()):
            print(
                f"    {group:17s} n={pk['questions']:.0f}  better/worse "
                f"{pk['em_better']:.0f}/{pk['em_worse']:.0f} (p={pk['p_em']:.3g})"
            )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwritten: {args.json}")


if __name__ == "__main__":
    main()
