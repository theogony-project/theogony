#!/usr/bin/env python
"""Rewrite source-anchor provenance that records a path instead of a source.

    scripts/mesh_repair_anchor_provenance.py --root data/mesh-founding \
        --anchor https://www.gutenberg.org/ebooks/348 \
        --title "Hesiod, the Homeric Hymns and Homerica" --apply

A source anchor exists to say where a claim came from. On the founding mesh all
1,219 of them said this instead:

    text: Theogony named batch_01 (/private/tmp/claude-501/-Users-jakobreinehr-
    PycharmProjects-theogony/a389241c-.../scratchpad/...)

— the directory the file happened to sit in during one session, encoding a
session id, long since deleted. The corpus was read from a working copy, which
was the right thing to do; ingestion recorded the wrong thing about it
(PHX-1084, fixed forward in `theogony mesh ingest`).

The anchors ride along in every Constellation as the provenance band (PHX-1042),
so this is on screen during the demo.

Dry-run by default. `--apply` rewrites the consolidated node table in one
overwrite, rebuilds both node indices from the result, and re-creates the Lance
indices — the overwrite drops them along with the data, and an unindexed table
answers correctly and slowly with nothing to say which one you have.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode

# "text: Theogony named batch_01 (/private/tmp/...)" ->
#   prefix "text", title "Theogony named batch_01", anchor "/private/tmp/..."
_DESCRIPTION = re.compile(r"^(?P<prefix>[^:]+):\s*(?P<title>.*?)\s*\((?P<anchor>.*)\)$", re.S)

# The batch suffix is a working title from how the corpus was fed in, not part of
# the work. "Theogony named batch_01 paragraph 3" -> ("batch_01", "paragraph 3").
_BATCH = re.compile(r"^.*?\bbatch[_ ](?P<batch>\d+)(?P<tail>.*)$", re.S)


def _rewrite(node: ConsolidatedNode, *, anchor: str, title: str) -> ConsolidatedNode | None:
    match = _DESCRIPTION.match(node.description or "")
    if match is None:
        return None
    batch = _BATCH.match(match["title"])
    if batch is None:
        new_title = title
    else:
        tail = batch["tail"].strip()
        new_title = f"{title} (batch {int(batch['batch'])})"
        if tail:
            new_title = f"{new_title} {tail}"
    return node.model_copy(
        update={
            "description": f"{match['prefix']}: {new_title} ({anchor})",
            "source_url": anchor,
        }
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--anchor", required=True, help="Stable identifier: a URL or a citation.")
    ap.add_argument("--title", required=True, help="What the work actually is.")
    ap.add_argument("--apply", action="store_true", help="Write. Without it, report only.")
    args = ap.parse_args()

    runtime = MeshRuntime.open(args.root)
    nodes = runtime.nodes.load_all_consolidated()
    anchors = [n for n in nodes if n.is_source_anchor]
    rewritten = {
        str(n.id): r for n in anchors if (r := _rewrite(n, anchor=args.anchor, title=args.title))
    }

    print(f"nodes {len(nodes)}, source anchors {len(anchors)}, rewritable {len(rewritten)}")
    unmatched = [n for n in anchors if str(n.id) not in rewritten]
    if unmatched:
        print(f"  {len(unmatched)} anchor(s) did not match the expected shape, left untouched:")
        for node in unmatched[:3]:
            print(f"    {(node.description or '')[:100]}")
    for node in list(rewritten.values())[:3]:
        print(f"  after: {node.description[:100]}")

    if not args.apply:
        print("\ndry run — pass --apply to write")
        return

    updated = [rewritten.get(str(n.id), n) for n in nodes]
    runtime.nodes.replace_all_consolidated(updated)
    runtime.invalidate_csr_cache()
    print(f"\nwrote {len(updated)} nodes; {len(rewritten)} anchors repaired")

    # `mode="overwrite"` drops the table's indices with the data. Rebuilding them
    # here rather than leaving it to the next tick, because the difference is
    # silent: an unindexed table answers correctly and slowly, and nothing in a
    # status line says which one you have.
    print(f"indices: {runtime.nodes.ensure_indices()}")


if __name__ == "__main__":
    main()
