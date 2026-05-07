#!/usr/bin/env python3
"""
Monkey-1 comparison script (nous_implementation_brief §4 E5, §6).

Reads a NousRunReport and an IngestRunReport for the same article and
prints a comparison Markdown table to stdout.

Usage:
    python scripts/monkey1_compare.py \\
        --nous  data/run_reports/nous/<ulid>.json \\
        --ingest data/run_reports/ingest/<ulid>.json

Or with --cold to skip Chronicle-hit columns when comparing against a
cold-store run (i.e. chronicle_seeded=False in the NousRunReport).

The script does NOT run either pipeline.  It reads already-written reports.
To generate the reports first:

    # Seed the Chronicle (requires Neo4j running):
    theogony ingest 43497 --sentences 500

    # Run the topology_parser baseline on the same article:
    theogony ingest --url https://en.wikipedia.org/wiki/Trans-Himalaya

    # Run Nous:
    theogony nous read "Trans-Himalaya"

    # Compare:
    python scripts/monkey1_compare.py \\
        --nous  data/run_reports/nous/<ulid>.json \\
        --ingest data/run_reports/ingest/<ulid>.json

Chronicle precondition note:
    Running Monkey 1 on a cold store will show chronicle_hits_used=0 and
    new connections to Hedin nodes=0.  This is expected.  The
    NousRunReport.chronicle_seeded field documents this condition.

    See: docs/etappes/nous_hesiod_brief.md §9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    result: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return result


def _edge_to_node_ratio(nodes: int, edges: int) -> str:
    if nodes == 0:
        return "—"
    return f"{edges / nodes:.2f}"


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    return str(value)


def _print_table(rows: list[tuple[str, str, str]]) -> None:
    col1 = max(len(r[0]) for r in rows)
    col2 = max(len(r[1]) for r in rows)
    col3 = max(len(r[2]) for r in rows)

    sep = f"| {'-' * col1} | {'-' * col2} | {'-' * col3} |"
    header = f"| {'Metric':<{col1}} | {'topology_parser':<{col2}} | {'Nous':<{col3}} |"
    print(header)
    print(sep)
    for label, parser_val, nous_val in rows:
        print(f"| {label:<{col1}} | {parser_val:<{col2}} | {nous_val:<{col3}} |")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monkey-1: compare topology_parser vs Nous metrics."
    )
    parser.add_argument("--nous", required=True, help="Path to NousRunReport JSON file.")
    parser.add_argument("--ingest", required=True, help="Path to IngestRunReport JSON file.")
    parser.add_argument(
        "--cold",
        action="store_true",
        help="Skip Chronicle-hit columns (expected when chronicle_seeded=False).",
    )
    args = parser.parse_args()

    nous_data = _load_json(args.nous)
    ingest_data = _load_json(args.ingest)

    if nous_data.get("report_type") != "nous":
        print(
            f"WARNING: --nous file has report_type={nous_data.get('report_type')!r},"
            " expected 'nous'.",
            file=sys.stderr,
        )

    if ingest_data.get("report_type") != "ingest":
        print(
            f"WARNING: --ingest file has report_type={ingest_data.get('report_type')!r},"
            " expected 'ingest'.",
            file=sys.stderr,
        )

    # Nous metrics
    nous_nodes = nous_data.get("nodes_written", 0)
    nous_edges = nous_data.get("edges_written", 0)
    nous_hints_offered = nous_data.get("chronicle_hits_offered", 0)
    nous_hints_used = nous_data.get("chronicle_hits_used", 0)
    nous_seeded = nous_data.get("chronicle_seeded", False)

    # topology_parser metrics (from IngestRunReport)
    store_data = ingest_data.get("store", {})
    parser_nodes = store_data.get("nodes_upserted", 0)
    parser_edges = store_data.get("edges_upserted", 0)

    print()
    print("## Monkey-1 Comparison: topology_parser vs Nous")
    print()

    chronicle_note = (
        "(chronicle_seeded=False — Chronicle-hit metrics expected zero)"
        if not nous_seeded
        else "(chronicle_seeded=True)"
    )
    print(f"Chronicle state: {chronicle_note}")
    print()

    rows: list[tuple[str, str, str]] = [
        ("Nodes produced", _fmt(parser_nodes), _fmt(nous_nodes)),
        ("Edges produced", _fmt(parser_edges), _fmt(nous_edges)),
        (
            "Edge-to-node ratio",
            _edge_to_node_ratio(parser_nodes, parser_edges),
            _edge_to_node_ratio(nous_nodes, nous_edges),
        ),
        ("Cross-level diagonal edges", "0 (tree)", "see AnnotatedReading"),
        (
            "Chronicle hits offered",
            "0 (no retrieval)",
            _fmt(nous_hints_offered) if not args.cold else "—",
        ),
        (
            "Chronicle hits used",
            "0 (no retrieval)",
            _fmt(nous_hints_used) if not args.cold else "—",
        ),
    ]

    _print_table(rows)

    print()
    print("Nous verdict:", nous_data.get("verdict", "—"))
    print("Parser verdict:", ingest_data.get("verdict", "—"))

    # Monkey-1 threshold check (brief §6)
    nous_ratio = nous_edges / max(nous_nodes, 1)
    parser_ratio = parser_edges / max(parser_nodes, 1)

    print()
    if nous_ratio > parser_ratio:
        print(f"✓ Nous edge-to-node ratio > topology_parser: {nous_ratio:.2f} > {parser_ratio:.2f}")
    else:
        print(
            f"✗ Nous edge-to-node ratio NOT > topology_parser:"
            f" {nous_ratio:.2f} <= {parser_ratio:.2f}"
        )

    if nous_seeded and nous_hints_used > 0:
        print(f"✓ Chronicle hits used: {nous_hints_used} / {nous_hints_offered} offered")
    elif not nous_seeded:
        print("— Chronicle seeded=False; Chronicle-hit comparison not applicable.")
    else:
        print("✗ No Chronicle hits used (check: is the Chronicle seeded?)")


if __name__ == "__main__":
    main()
