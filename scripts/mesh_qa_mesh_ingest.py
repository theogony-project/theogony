#!/usr/bin/env python
"""Build a mesh from a HippoRAG corpus by replaying its cached Kadmos readings.

    scripts/mesh_qa_mesh_ingest.py --dataset 2wikimultihopqa --root data/mesh-2wiki

No LLM, no network, no money: `scripts/mesh_qa_kadmos.py` already paid for one
Kadmos reading per passage and cached it; this replays those readings through
the shipped write path (`MeshParagraphReader`), so the mesh has the same linker,
identity resolution and typed edges a user's corpus gets (PHX-1110).

Prints the paragraph rate as it goes, because the founding read collapsed once
on a per-paragraph cost nobody was watching (PHX-1050).
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import time
from pathlib import Path

from theogony.mesh.eval.qa_datasets import load_dataset
from theogony.mesh.eval.qa_mesh import ingest_cached_readings, load_readings
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="2wikimultihopqa")
    ap.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    ap.add_argument(
        "--readings", type=Path, help="default: <cache-dir>/kadmos_readings_<dataset>.jsonl"
    )
    ap.add_argument("--root", type=Path, required=True, help="the mesh workspace to write")
    ap.add_argument("--max-paragraphs", type=int, default=0, help="0 = the whole corpus")
    ap.add_argument("--fresh", action="store_true", help="delete an existing workspace first")
    ap.add_argument("--every", type=int, default=200, help="progress line every N paragraphs")
    args = ap.parse_args()

    readings_path = args.readings or (args.cache_dir / f"kadmos_readings_{args.dataset}.jsonl")
    data = load_dataset(args.dataset, args.cache_dir, max_questions=1000, seed=0)
    readings = load_readings(readings_path)
    total = (
        len(data.passages)
        if not args.max_paragraphs
        else min(len(data.passages), args.max_paragraphs)
    )
    print(
        f"dataset={args.dataset} passages={len(data.passages)} readings={len(readings)} "
        f"-> {total} paragraphs"
    )

    if args.fresh and args.root.exists():
        shutil.rmtree(args.root)
    runtime = MeshRuntime.open(args.root)
    started = time.perf_counter()

    def progress(n: int) -> None:
        if n % args.every == 0 or n == total:
            elapsed = time.perf_counter() - started
            print(
                f"  {n:6d}/{total}  {elapsed / n:.3f} s/paragraph  {elapsed / 60:.1f} min",
                flush=True,
            )

    result = asyncio.run(
        ingest_cached_readings(
            runtime,
            data.passages,
            readings,
            source_identifier=args.dataset,
            title=f"HippoRAG {args.dataset}",
            max_paragraphs=args.max_paragraphs,
            on_call=progress,
        )
    )
    elapsed = time.perf_counter() - started
    rep = result.report
    print(
        f"\nparagraphs {result.paragraphs}  replayed {result.hits}  missing {result.misses}  "
        f"{elapsed / 60:.1f} min ({elapsed / max(1, result.paragraphs):.3f} s/paragraph)"
    )
    keys = [
        k for k in rep if any(t in k for t in ("nodes", "edges", "relations", "llm", "mentions"))
    ]
    for k in sorted(keys):
        print(f"  {k}: {rep[k]}")
    print(
        f"workspace {args.root}: chunks {runtime.nodes.chunk_count()} "
        f"consolidated {runtime.nodes.consolidated_count()}"
    )


if __name__ == "__main__":
    main()
