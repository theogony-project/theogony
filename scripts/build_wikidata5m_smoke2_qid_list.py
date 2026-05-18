#!/usr/bin/env python3
"""Build the wikidata5m Smoke-2 Q-ID selection (degree threshold in triplet graph)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def _compute_degrees(triplet_path: Path) -> Counter[str]:
    degree: Counter[str] = Counter()
    with triplet_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            subject_qid, _predicate_pid, object_qid = parts
            degree[subject_qid] += 1
            degree[object_qid] += 1
    return degree


def _write_selection(
    *,
    degree: Counter[str],
    min_degree: int,
    output_path: Path,
    manifest_path: Path,
    triplet_path: Path,
) -> None:
    selected = [(qid, count) for qid, count in degree.items() if count >= min_degree]
    selected.sort(key=lambda item: (-item[1], item[0]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    header = (
        f"# wikidata5m Smoke-2 entity selection\n"
        f"# source: {triplet_path.name}\n"
        f"# rule: undirected degree >= {min_degree}\n"
        f"# generated_at: {generated_at}\n"
        f"# qid_count: {len(selected)}\n"
    )
    if selected:
        header += f"# min_degree_in_file: {selected[-1][1]}\n"
        header += f"# max_degree_in_file: {selected[0][1]}\n"

    lines = [header.rstrip(), ""]
    lines.extend(f"{qid}\t{count}" for qid, count in selected)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    induced_triplets = 0
    selected_qids = {qid for qid, _ in selected}
    with triplet_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.strip().split("\t")
            if len(parts) != 3:
                continue
            subject_qid, _predicate_pid, object_qid = parts
            if subject_qid in selected_qids and object_qid in selected_qids:
                induced_triplets += 1

    manifest = {
        "generated_at": generated_at,
        "triplet_source": str(triplet_path),
        "min_degree": min_degree,
        "qid_count": len(selected),
        "min_degree_in_file": selected[-1][1] if selected else None,
        "max_degree_in_file": selected[0][1] if selected else None,
        "sum_degrees": sum(count for _, count in selected),
        "induced_triplets": induced_triplets,
        "output_path": str(output_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/raw/wikidata5m"),
        help="Directory containing wikidata5m_all_triplet.txt",
    )
    parser.add_argument(
        "--min-degree",
        type=int,
        default=150,
        help="Minimum undirected triplet degree (default: 150).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Q-ID list path (default: <data-root>/wikidata5m_smoke2_qids_min_degree150.txt).",
    )
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    triplet_path = data_root / "wikidata5m_all_triplet.txt"
    if not triplet_path.is_file():
        raise SystemExit(f"missing triplet file: {triplet_path}")

    output_path = (
        args.output.resolve()
        if args.output is not None
        else data_root / f"wikidata5m_smoke2_qids_min_degree{args.min_degree}.txt"
    )
    manifest_path = output_path.with_suffix(".manifest.json")

    degree = _compute_degrees(triplet_path)
    _write_selection(
        degree=degree,
        min_degree=args.min_degree,
        output_path=output_path,
        manifest_path=manifest_path,
        triplet_path=triplet_path,
    )
    print(json.dumps(json.loads(manifest_path.read_text(encoding="utf-8")), indent=2))


if __name__ == "__main__":
    main()
