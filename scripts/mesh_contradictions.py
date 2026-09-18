#!/usr/bin/env python
"""Find what the corpus disagrees with itself about, and record it (PHX-1107).

    scripts/mesh_contradictions.py --root data/mesh-founding-framed [--apply]
    scripts/mesh_contradictions.py --root ... --replay findings.json --apply

Candidates are structural — two relations competing for the same slot, witnessed
by different paragraphs — and each is judged by one small LLM call: can both be
true at once? Confirmed ones get `contradicts` edges between the witnessing
chunks and move those chunks to the `disputed` stance, which is what makes them
reachable by a contradiction-framed query.

Dry by default. `--apply` writes. `--replay` re-uses a previous run's verdicts
so a measurement can be repeated without spending again.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.runtime.contradiction import (
    DEFAULT_MAX_GROUP,
    ContradictionAdjudicator,
    LLMContradictionAdjudicator,
    ReplayAdjudicator,
    run_contradiction_pass,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _say(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default=Path("data/mesh-founding-framed"), type=Path)
    ap.add_argument(
        "--max-group",
        default=DEFAULT_MAX_GROUP,
        type=int,
        help="Groups wider than this are hubs, not disagreements.",
    )
    ap.add_argument("--limit", default=0, type=int, help="Judge at most N candidates (0 = all).")
    ap.add_argument("--apply", action="store_true", help="Write the edges and the frames.")
    ap.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="A previous run's JSON; replays its verdicts instead of asking the model.",
    )
    ap.add_argument("--out", type=Path, help="Write the findings as JSON here.")
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    adjudicator: ContradictionAdjudicator
    if args.replay is not None:
        previous = json.loads(args.replay.read_text(encoding="utf-8"))
        adjudicator = ReplayAdjudicator.from_findings(previous["findings"])
    else:
        adjudicator = LLMContradictionAdjudicator(build_llm_from_settings(Settings()))

    result = asyncio.run(
        run_contradiction_pass(
            runtime,
            adjudicator,
            max_group=args.max_group,
            limit=args.limit,
            apply=args.apply,
            log=_say,
        )
    )

    _say("")
    _say(
        f"Mesh {args.root}   Adjudicator {result.adjudicator_model}   "
        f"max_group {args.max_group}   {'written' if args.apply else 'dry run'}"
    )
    _say(
        f"Candidates {result.candidates}   confirmed {result.confirmed}   "
        f"compatible {result.compatible}   uncertain {result.uncertain}   "
        f"({result.elapsed_s:.0f}s)"
    )
    if args.apply:
        _say(f"Edges written {result.edges_written}   paragraphs marked {result.chunks_marked}")

    confirmed = [f for f in result.findings if f["verdict"] == "CONTRADICTION"]
    if confirmed:
        _say("")
        _say("Confirmed contradictions:")
        for f in confirmed:
            left = f"{f['left_name']} {f['descriptor']} {f['shared_name']}"
            right = f"{f['right_name']} {f['descriptor']} {f['shared_name']}"
            if f["axis"] == "source":
                left = f"{f['shared_name']} {f['descriptor']} {f['left_name']}"
                right = f"{f['shared_name']} {f['descriptor']} {f['right_name']}"
            _say(f"  {left}   /   {right}")
            if f["reason"]:
                _say(f"      {f['reason'][:150]}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "root": str(args.root),
                    "adjudicator_model": result.adjudicator_model,
                    "max_group": args.max_group,
                    "applied": args.apply,
                    "candidates": result.candidates,
                    "confirmed": result.confirmed,
                    "compatible": result.compatible,
                    "uncertain": result.uncertain,
                    "edges_written": result.edges_written,
                    "chunks_marked": result.chunks_marked,
                    "audit_id": result.audit_id,
                    "findings": result.findings,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _say(f"\nDetail written: {args.out}")


if __name__ == "__main__":
    main()
