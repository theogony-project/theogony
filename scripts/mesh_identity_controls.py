#!/usr/bin/env python
"""The identity controls of PHX-1118, read-only, on one mesh workspace.

    scripts/mesh_identity_controls.py --root data/mesh-2wiki-off [--json out.json]

A description that grows at re-mention changes the surface the linker matches
on, and the one attractor this substrate has had (PHX-1051) absorbed entities
into generic hubs through exactly that surface. So the same counts are read on
both arms before the answers are compared: how many entity nodes there are and
how many are candidates, how mentions distribute over them, how long the
descriptions are, how many carry provenance, and how many distinct nodes carry
each gold answer's name.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from theogony.mesh.eval.qa_datasets import load_dataset
from theogony.mesh.eval.qa_mesh import answer_kind
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.storage.nodes import _normalize_label  # the label index's own normaliser


def _label(node) -> str:
    text = node.description or ""
    return text.split(" — ", 1)[0][:60] if text else (node.tags[0] if node.tags else str(node.id))


def controls(root: Path, dataset: str | None, cache_dir: Path) -> dict:
    runtime = MeshRuntime.open(root)
    nodes = runtime.nodes.load_all_consolidated()
    entities = [n for n in nodes if not n.is_source_anchor]
    lengths = sorted(len(n.description or "") for n in entities)
    by_id = {str(n.id): n for n in nodes}

    edges = runtime.edges.load_all_edges()
    mentions = [e for e in edges if e.creation_context == "kadmos_mentions"]
    sources_of: dict[str, set[str]] = defaultdict(set)
    for e in mentions:
        sources_of[str(e.target_id)].add(str(e.source_id))
    in_degree = Counter(str(e.target_id) for e in mentions)

    # Audit rows by action. The log has no public group-by; one column scan.
    actions = Counter(
        row["action"] for row in runtime.audit._table.search().select(["action"]).to_list()
    )

    out: dict = {
        "root": str(root),
        "consolidated": len(nodes),
        "source_anchors": sum(n.is_source_anchor for n in nodes),
        "entity_nodes": len(entities),
        "is_candidate": sum(n.is_candidate for n in entities),
        "mention_edges": len(mentions),
        "mentioned_nodes": len(sources_of),
        "mentioned_from_2_plus": sum(len(s) >= 2 for s in sources_of.values()),
        "mentioned_from_3_plus": sum(len(s) >= 3 for s in sources_of.values()),
        "description_chars": {
            "median": lengths[len(lengths) // 2] if lengths else 0,
            "mean": round(statistics.fmean(lengths), 1) if lengths else 0,
            "p90": lengths[int(len(lengths) * 0.9)] if lengths else 0,
            "max": lengths[-1] if lengths else 0,
            "in_band_200_500": sum(200 <= x <= 500 for x in lengths),
        },
        "with_description_source_chunks": sum(bool(n.description_source_chunks) for n in entities),
        "with_description_generated_at": sum(
            n.description_generated_at is not None for n in entities
        ),
        "audit_rows_by_action": dict(sorted(actions.items())),
        "top_in_degree": [
            {"label": _label(by_id[nid]) if nid in by_id else nid, "mentions": k}
            for nid, k in in_degree.most_common(20)
        ],
        "ticks": runtime.tick_count(),
    }
    if dataset:
        data = load_dataset(dataset, cache_dir, max_questions=1000, seed=0)
        # The label index holds a row per tag and one for the whole description,
        # so a name matches nodes *tagged* with it as well as nodes *named* it.
        # The identity control is the named ones (the head before " — "); the
        # tag-only carriers are reported beside them.
        named_hits: list[int] = []
        tag_only_hits: list[int] = []
        for q in data.questions:
            if answer_kind(q.answer) != "entity":
                continue
            names = [q.answer, *q.answer_aliases]
            wanted = {_normalize_label(x) for x in names}
            wanted.discard("")  # a non-Latin alias normalises to nothing
            found = [
                n
                for n in runtime.nodes.find_consolidated_by_labels(names, limit=10_000)
                if not n.is_source_anchor and "paragraph_concept" not in n.tags
            ]
            # Named: the description head before " — ", or the label the reader
            # stored first in `tags` (a bare-name description gains ". sentence"
            # on the accrual arm and has no " — ").
            heads = {
                str(n.id)
                for n in found
                if _normalize_label((n.description or "").split(" — ", 1)[0]) in wanted
                or _normalize_label(n.tags[0] if n.tags else "") in wanted
            }
            named_hits.append(len(heads))
            tag_only_hits.append(len({str(n.id) for n in found} - heads))
        found_named = [h for h in named_hits if h]
        out["gold_names"] = {
            "entity_questions": len(named_hits),
            "named_on_no_node": sum(h == 0 for h in named_hits),
            "named_on_one_node": sum(h == 1 for h in named_hits),
            "named_on_2_plus_nodes": sum(h >= 2 for h in named_hits),
            "named_mean_among_found": round(statistics.fmean(found_named), 2) if found_named else 0,
            "named_max": max(named_hits) if named_hits else 0,
            "tag_only_carriers_total": sum(tag_only_hits),
            "tag_only_carriers_max": max(tag_only_hits) if tag_only_hits else 0,
        }
    return out


def mention_diff(root_a: Path, root_b: Path, *, top: int = 12) -> dict:
    """Where the mentions went: the same chunk's `kadmos_mentions` on two meshes
    built from the same passages, joined by the chunk's `raw_text_ref` and the
    target's label (node ids are not shared between builds).

    The entity count and the top-20 in-degree cannot see a mention that moved
    from one existing node to another; this can. It says how many of the
    mentions changed node and which labels gained or lost most. Whether a move
    is better or worse placed is not judged here.
    """

    def mentions_by_chunk(root: Path) -> dict[str, list[str]]:
        runtime = MeshRuntime.open(root)
        # Join on the label the reader stored first in `tags`: the description
        # head grows on the accrual arm for a bare-name node, the tag does not.
        label = {
            str(n.id): (n.tags[0] if n.tags else _label(n))
            for n in runtime.nodes.load_all_consolidated()
        }
        chunk_ref = {str(c.id): str(c.raw_text_ref) for c in runtime.nodes.iter_chunks()}
        out: dict[str, list[str]] = defaultdict(list)
        for e in runtime.edges.load_all_edges():
            if e.creation_context == "kadmos_mentions":
                out[chunk_ref.get(str(e.source_id), str(e.source_id))].append(
                    label.get(str(e.target_id), str(e.target_id))
                )
        return out

    a, b = mentions_by_chunk(root_a), mentions_by_chunk(root_b)
    moved = 0
    for ref in set(a) | set(b):
        ca, cb = Counter(a.get(ref, [])), Counter(b.get(ref, []))
        moved += sum((ca - cb).values())
    in_a = Counter(x for labels in a.values() for x in labels)
    in_b = Counter(x for labels in b.values() for x in labels)
    delta = {lab: in_b[lab] - in_a[lab] for lab in set(in_a) | set(in_b)}
    changed = sum(1 for d in delta.values() if d)
    gainers = sorted(delta.items(), key=lambda kv: -kv[1])[:top]
    losers = sorted(delta.items(), key=lambda kv: kv[1])[:top]
    return {
        "a": str(root_a),
        "b": str(root_b),
        "mentions": sum(in_a.values()),
        "mentions_that_changed_node": moved,
        "labels_whose_count_changed": changed,
        "gainers": [{"label": lab, "a": in_a[lab], "b": in_b[lab]} for lab, _ in gainers],
        "losers": [{"label": lab, "a": in_a[lab], "b": in_b[lab]} for lab, _ in losers],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument(
        "--against",
        type=Path,
        help="a second mesh built from the same passages: report where the mentions moved",
    )
    ap.add_argument("--dataset", default="2wikimultihopqa", help="'' to skip the gold-name control")
    ap.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    ap.add_argument("--json", type=Path, help="also write the controls here")
    args = ap.parse_args()
    out = controls(args.root, args.dataset or None, args.cache_dir)
    if args.against:
        out["against"] = mention_diff(args.root, args.against)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
