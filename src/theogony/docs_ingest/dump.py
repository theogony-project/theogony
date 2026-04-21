"""
JSONL.gz round-trip for a docs-ingest Chronicle dump.

Format: a single gzipped JSON-Lines file. Each line is one record:

```json
{"kind": "node", "data": {... KnowledgeNode JSON ...}}
{"kind": "edge", "data": {... KnowledgeEdge JSON ...}}
```

Properties:

- **Atomic.** A consumer can stream the file and ingest as it reads;
  no out-of-order references because nodes are written before edges.
- **Diffable.** Plain JSON, one record per line, sorted writes (see
  :func:`write_dump`'s ordering pass) — git diffs are meaningful.
- **Compact.** Gzip brings a chronicle of a few hundred nodes with
  embeddings down to roughly the size of the raw embedding floats.
- **Honest.** Every node carries its ``embedding_model_id`` so a
  consumer can decide whether to re-embed instead of importing
  vectors from a different model than its own.

Companion helpers:

- :func:`write_dump` (file path or stream)
- :func:`read_dump` (file path or stream)
- :func:`dump_metadata` — a small header dict that consumers can use
  to verify embedding-model compatibility before importing
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest.extractors import ExtractedChronicle

#: Schema version for the dump format. Bump when the on-disk shape
#: changes incompatibly so older consumers fail loudly rather than
#: silently mis-parsing.
DUMP_SCHEMA_VERSION = 1


class DumpError(RuntimeError):
    """Raised when a Chronicle dump cannot be parsed."""


def write_dump(
    chronicle: ExtractedChronicle,
    path: Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write ``chronicle`` to ``path`` as a gzipped JSONL file.

    Records are written in deterministic order: header first, then
    nodes sorted by id, then edges sorted by id. Two runs against the
    same chronicle therefore produce byte-identical files (modulo the
    header's ``written_at`` timestamp).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes_sorted = sorted(chronicle.nodes, key=lambda n: n.id)
    edges_sorted = sorted(chronicle.edges, key=lambda e: e.id)

    header = {
        "kind": "header",
        "schema_version": DUMP_SCHEMA_VERSION,
        "written_at": datetime.now(UTC).isoformat(),
        "node_count": len(nodes_sorted),
        "edge_count": len(edges_sorted),
        "embedding_model_id": _detect_embedding_model_id(nodes_sorted),
        "embedding_dim": _detect_embedding_dim(nodes_sorted),
        "metadata": dict(metadata or {}),
    }

    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write(json.dumps(header, separators=(",", ":")) + "\n")
        for node in nodes_sorted:
            fh.write(_record("node", node.model_dump(mode="json")) + "\n")
        for edge in edges_sorted:
            fh.write(_record("edge", edge.model_dump(mode="json")) + "\n")


def read_dump(
    path: Path,
) -> tuple[dict[str, Any], list[KnowledgeNode], list[KnowledgeEdge]]:
    """Read a gzipped JSONL Chronicle dump from ``path``.

    Returns ``(header, nodes, edges)``. Raises :class:`DumpError` when
    the file is unreadable, missing the header, or contains records
    with unknown ``kind`` values.
    """
    nodes: list[KnowledgeNode] = []
    edges: list[KnowledgeEdge] = []
    header: dict[str, Any] | None = None

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DumpError(f"line {line_no}: invalid JSON: {exc}") from exc
            kind = rec.get("kind")
            if kind == "header":
                header = rec
            elif kind == "node":
                nodes.append(KnowledgeNode.model_validate(rec["data"]))
            elif kind == "edge":
                edges.append(KnowledgeEdge.model_validate(rec["data"]))
            else:
                raise DumpError(f"line {line_no}: unknown record kind: {kind!r}")

    if header is None:
        raise DumpError("missing header record")
    if header.get("schema_version") != DUMP_SCHEMA_VERSION:
        raise DumpError(
            f"unsupported schema_version: {header.get('schema_version')!r} "
            f"(this build expects {DUMP_SCHEMA_VERSION})"
        )
    return header, nodes, edges


def dump_metadata(path: Path) -> dict[str, Any]:
    """Return the header of a dump without reading the body.

    Useful for ``theogony seed --info`` to verify embedding-model
    compatibility before paying for the full parse.
    """
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        first_line = fh.readline().strip()
    if not first_line:
        raise DumpError("empty dump")
    rec: dict[str, Any] = json.loads(first_line)
    if rec.get("kind") != "header":
        raise DumpError(f"first record is not a header (kind={rec.get('kind')!r})")
    return rec


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _record(kind: str, data: dict[str, Any]) -> str:
    return json.dumps(
        {"kind": kind, "data": data},
        separators=(",", ":"),
        sort_keys=True,
    )


def _detect_embedding_model_id(nodes: list[KnowledgeNode]) -> str | None:
    for n in nodes:
        if n.embedding_model_id:
            return n.embedding_model_id
    return None


def _detect_embedding_dim(nodes: list[KnowledgeNode]) -> int | None:
    for n in nodes:
        if n.embedding:
            return len(n.embedding)
    return None


def iter_records(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Stream raw ``(kind, data)`` records from a dump.

    Useful for tooling that wants to inspect a dump without the
    KnowledgeNode / KnowledgeEdge model overhead (e.g. a quick
    ``jq``-style pretty-printer).
    """
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            yield rec.get("kind", "?"), rec.get("data", rec)


__all__ = [
    "DUMP_SCHEMA_VERSION",
    "DumpError",
    "dump_metadata",
    "iter_records",
    "read_dump",
    "write_dump",
]


# Suppress "imported but unused" if mypy strips the IO re-export later.
_: type = IO
