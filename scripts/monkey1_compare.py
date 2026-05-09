#!/usr/bin/env python3
"""
Monkey-1 comparison script.

Reads a KadmosRunReport and an IngestRunReport for the same article and
prints a comparison Markdown table to stdout.

Usage:
    python scripts/monkey1_compare.py \\
        --kadmos data/run_reports/kadmos/<ulid>.json \\
        --ingest data/run_reports/ingest/<ulid>.json

Or with --nous for legacy NousRunReport files.

Chronicle precondition note:
    The Chronik should be seeded with prior ingests for the cross-document
    connection comparison to be meaningful. See docs/etappes/nous_hesiod_brief.md §9.
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


def _print_table(rows: list[tuple[str, str, str]], header3: str = "Kadmos v2") -> None:
    col1 = max(len(r[0]) for r in rows)
    col2 = max(len(r[1]) for r in rows)
    col3 = max(len(r[2]) for r in rows)

    sep = f"| {'-' * col1} | {'-' * col2} | {'-' * col3} |"
    header = f"| {'Metric':<{col1}} | {'topology_parser':<{col2}} | {header3:<{col3}} |"
    print(header)
    print(sep)
    for label, parser_val, kadmos_val in rows:
        print(f"| {label:<{col1}} | {parser_val:<{col2}} | {kadmos_val:<{col3}} |")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monkey-1: compare topology_parser vs Kadmos v2 metrics."
    )
    parser.add_argument(
        "--kadmos",
        "--nous",
        dest="kadmos",
        required=True,
        help="Path to KadmosRunReport (or legacy NousRunReport) JSON file.",
    )
    parser.add_argument("--ingest", required=True, help="Path to IngestRunReport JSON file.")
    args = parser.parse_args()

    kadmos_data = _load_json(args.kadmos)
    ingest_data = _load_json(args.ingest)

    report_type = kadmos_data.get("report_type", "unknown")
    if report_type not in ("kadmos", "nous"):
        print(
            f"WARNING: --kadmos file has report_type={report_type!r}, expected 'kadmos' or 'nous'.",
            file=sys.stderr,
        )

    if ingest_data.get("report_type") != "ingest":
        print(
            f"WARNING: --ingest file has report_type={ingest_data.get('report_type')!r},"
            " expected 'ingest'.",
            file=sys.stderr,
        )

    # Kadmos metrics — support both KadmosRunReport and legacy NousRunReport field names
    if report_type == "kadmos":
        kadmos_concepts = kadmos_data.get("total_concepts", 0)
        kadmos_edges_explicit = kadmos_data.get("total_edges", 0)
        kadmos_syntheses = kadmos_data.get("total_syntheses", 0)
        kadmos_revisions = kadmos_data.get("total_revisions", 0)
        kadmos_llm_calls = kadmos_data.get("total_llm_calls", 0)
        kadmos_cost = kadmos_data.get("total_llm_cost_eur", 0.0)
    else:
        # Legacy NousRunReport
        kadmos_concepts = kadmos_data.get("nodes_written", 0)
        kadmos_edges_explicit = kadmos_data.get("edges_written", 0)
        kadmos_syntheses = kadmos_data.get("synthesis_events", 0)
        kadmos_revisions = kadmos_data.get("repair_events", 0)
        kadmos_llm_calls = kadmos_data.get("llm_calls", 0)
        kadmos_cost = kadmos_data.get("llm_cost_eur", 0.0)

    # topology_parser metrics (from IngestRunReport)
    store_data = ingest_data.get("store", {})
    parser_nodes = store_data.get("nodes_upserted", 0)
    parser_edges = store_data.get("edges_upserted", 0)
    parser_cost = ingest_data.get("relations", {}).get("llm_cost_eur", 0.0)

    print()
    print("## Monkey-1 Comparison: topology_parser vs Kadmos v2")
    print()

    rows: list[tuple[str, str, str]] = [
        ("Concepts/Nodes produced", _fmt(parser_nodes), _fmt(kadmos_concepts)),
        ("Explicit edges (LLM-recognised)", _fmt(parser_edges), _fmt(kadmos_edges_explicit)),
        (
            "Edge-to-node ratio (explicit only)",
            _edge_to_node_ratio(parser_nodes, parser_edges),
            _edge_to_node_ratio(kadmos_concepts, kadmos_edges_explicit),
        ),
        ("Synthesis nodes", "0 (flat)", _fmt(kadmos_syntheses)),
        ("Revision events", "0 (stateless)", _fmt(kadmos_revisions)),
        (
            "LLM calls",
            _fmt(ingest_data.get("relations", {}).get("attempted", "?")),
            _fmt(kadmos_llm_calls),
        ),
        ("LLM cost (EUR)", f"€{parser_cost:.4f}", f"€{kadmos_cost:.4f}"),
    ]

    _print_table(rows)

    print()
    print("Kadmos verdict:", kadmos_data.get("verdict", "—"))
    print("Parser verdict:", ingest_data.get("verdict", "—"))

    # Monkey-1 threshold checks
    print()
    parser_ratio = parser_edges / max(parser_nodes, 1)
    kadmos_explicit_ratio = kadmos_edges_explicit / max(kadmos_concepts, 1)

    if kadmos_explicit_ratio > parser_ratio:
        print(
            f"✓ Explicit edge-to-node ratio > parser: "
            f"{kadmos_explicit_ratio:.2f} > {parser_ratio:.2f}"
        )
    else:
        print(
            f"✗ Explicit edge-to-node ratio NOT > parser: "
            f"{kadmos_explicit_ratio:.2f} <= {parser_ratio:.2f}"
        )

    if kadmos_syntheses > 0:
        print(f"✓ Synthesis nodes created: {kadmos_syntheses}")
    else:
        print("✗ No synthesis nodes created")


if __name__ == "__main__":
    main()
