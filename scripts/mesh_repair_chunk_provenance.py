#!/usr/bin/env python
"""Rewrite chunk provenance that points at a deleted session directory (PHX-1103).

    scripts/mesh_repair_chunk_provenance.py --root data/mesh-founding \\
        --source gutenberg_348 --batch-size 100 [--apply]

Every one of the founding mesh's 1,206 chunks carries a ``raw_text_ref`` like

    /private/tmp/claude-501/…/scratchpad/fullread/batch_03.txt#p17

and a ``source.source_identifier`` naming the same file. Thirteen files in a
scratch directory of one session, none of which exists. MESH_SUBSTRATE names
``raw_text_ref`` as the pointer the immune system or an Oneiros tick uses to
re-derive a chunk off the hot path — "an identifier like gutenberg_43497#p17,
never the text it points at". On this mesh that was impossible.

PHX-1084 fixed the same defect for the source anchors and corrected ingestion
forward; the chunk tier of the existing mesh was never brought up to it. This
does that: ``batch_NN.txt#pM`` becomes ``<source>#p(NN * batch_size + M)``, the
paragraph numbering the fixed ingestion writes, and ``source_identifier``
becomes ``<source>``. Chunks already in that form are left alone, so the run is
idempotent. Measured on the founding mesh: batches 00–11 carry p1..p100 and
batch 12 carries p1..p10 — 1,210 paragraphs, which is the count the read
reported.

Dry-run by default. ``--apply`` rewrites the chunk table in one overwrite.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode

_SCRATCH = re.compile(r"batch_(\d+)\.txt#p(\d+)$")


def repaired(node: ChunkNode, *, source: str, batch_size: int) -> ChunkNode | None:
    """The node with its provenance rewritten, or None if nothing needed doing."""
    match = _SCRATCH.search(node.raw_text_ref)
    if match is None:
        return None
    paragraph = int(match.group(1)) * batch_size + int(match.group(2))
    return node.model_copy(
        update={
            "raw_text_ref": f"{source}#p{paragraph}",
            "source": node.source.model_copy(update={"source_identifier": source}),
        }
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/mesh-founding", type=Path)
    ap.add_argument("--source", default="gutenberg_348")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    chunks = list(runtime.nodes.iter_chunks(page_size=1024))
    updated: list[ChunkNode] = []
    rewritten = 0
    for node in chunks:
        fixed = repaired(node, source=args.source, batch_size=args.batch_size)
        if fixed is not None:
            rewritten += 1
        updated.append(fixed or node)
    print(f"{len(chunks)} chunks, {rewritten} with a scratch-directory ref")
    for before, after in list(zip(chunks, updated, strict=True))[:3]:
        if before is not after:
            print(f"  {before.raw_text_ref}\n    -> {after.raw_text_ref}")
    if not args.apply:
        print("dry run; pass --apply to rewrite")
        return
    if rewritten == 0:
        print("nothing to do")
        return
    runtime.nodes.replace_all_chunks(updated)
    runtime.invalidate_csr_cache()
    print(f"wrote {len(updated)} chunks; {rewritten} repaired")


if __name__ == "__main__":
    main()
