"""Edge storage: Lance ``mesh_edges`` table, COO delta buffer, CSR builder.

Per MESH_IMPLEMENTATION.md §"Edges — PyTorch sparse + delta buffer + Lance
metadata table":

1. **Stable CSR sparse tensor** – built at Oneiros tick boundaries.
2. **COO delta buffer** – lock-free append path for Hebbian updates.
3. **Lance edge-metadata table** – off-hot-path rich descriptors (parallel).

Edge insertion at S1 writes to both the quantitative Lance table and (when
metadata is present) the metadata table. At Oneiros tick time the delta buffer
is drained, merged, decayed, saturating the CSR is rebuilt, the quantitative
table is atomically replaced, and the metadata table is resynced.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
import torch

from theogony.mesh.schemas import Edge, EdgeMetadata


def _have_table(db: lancedb.DBConnection, name: str) -> bool:
    resp = db.list_tables()
    return name in (resp.tables or [])


# ---- Lance schemas ----

_EDGE_SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("target_id", pa.string()),
        ("weight", pa.float32()),
        ("decay_tier", pa.int32()),
        ("frame_consistency", pa.float32()),
        ("eligibility", pa.float32()),
        ("feedback_modulated_strength", pa.float32()),
        ("born_at", pa.timestamp("us")),
        ("last_fired_at", pa.timestamp("us")),
        ("payload_json", pa.string()),
    ]
)

_METADATA_SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("target_id", pa.string()),
        ("payload_json", pa.string()),
    ]
)

# Edge-identity index for O(1) deduplication without materialising Edge objects
# (PHX-1033). One short hashed key per directed (source, target, relation)
# edge — the lightweight analogue of MeshNodeStore's consolidated_qid_index.
_DEDUP_INDEX_SCHEMA = pa.schema([("dedup_key", pa.string())])


# ---- CSR container ----


@dataclass(frozen=True)
class EdgeCSR:
    """CSR adjacency for outgoing edges (row = source, col = target)."""

    crow_indices: torch.Tensor  # int64  (N+1,)
    col_indices: torch.Tensor  # int64  (E,)
    values: torch.Tensor  # float32  (E,)
    node_ids: list[str]
    id_to_index: dict[str, int]


# ---- Delta buffer ----


class EdgeDeltaBuffer:
    """Append path for Hebbian updates, merged into the CSR at each Oneiros tick.

    When ``path`` is given the buffer is **durable**: each delta is also appended to
    a JSONL sidecar, so reinforcement written by one process (``theogony mesh ask
    --hebbian``) is drained by the tick in another (``theogony mesh tick``). Without
    it the buffer is process-local, which makes the whole query -> reinforcement ->
    tick loop inert across CLI invocations — the deltas die at process exit.

    The sidecar lives beside the Lance directory rather than inside it: it is
    scratch state with a different lifecycle (truncated on every drain), not a
    versioned table.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._rows: list[dict[str, Any]] = []
        self._path = path

    def _persisted(self) -> list[dict[str, Any]]:
        if self._path is None or not self._path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A torn final line from a killed process costs one delta, not the tick.
                continue
        return rows

    def append_hebbian_delta(
        self,
        *,
        source_id: str,
        target_id: str,
        weight_delta: float,
    ) -> None:
        row = {
            "source_id": source_id,
            "target_id": target_id,
            "weight_delta": weight_delta,
        }
        with self._lock:
            if self._path is None:
                self._rows.append(row)
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out = self._rows
            self._rows = []
            if self._path is not None:
                out = out + self._persisted()
                self._path.unlink(missing_ok=True)
            return out

    def pending(self) -> int:
        with self._lock:
            return len(self._rows) + len(self._persisted())


# ---- Merging helpers ----


def merge_edge_deltas(
    base: list[Edge], deltas: list[dict[str, Any]], *, w_max: float
) -> list[Edge]:
    """Apply weight deltas to existing edges; create synthetic edges for new pairs."""

    def _key(e: Edge) -> tuple[str, str]:
        return (str(e.source_id), str(e.target_id))

    by_key: dict[tuple[str, str], Edge] = {}
    for e in base:
        by_key[_key(e)] = e.model_copy(deep=True)

    for d in deltas:
        s = str(d["source_id"])
        t = str(d["target_id"])
        dw = float(d["weight_delta"])
        if dw <= 0:
            continue
        k = (s, t)
        if k in by_key:
            cur = by_key[k]
            nw = min(w_max, cur.weight + dw)
            by_key[k] = cur.model_copy(update={"weight": nw})
        else:
            now = datetime.now(UTC)
            by_key[k] = Edge(
                source_id=s,  # type: ignore[arg-type]
                target_id=t,  # type: ignore[arg-type]
                weight=min(w_max, dw),
                born_at=now,
                last_fired_at=now,
            )
    return list(by_key.values())


def decay_edges_inplace(edges: list[Edge], *, lam: float = 0.05, dt: float = 1.0) -> None:
    """Discrete super-linear decay ``Δw = -λ · dt · w^k``, tier-modulated *k*.
    Default: ``k = 2`` (tier 0), ``k = 1.5`` (tier 1), ``k = 1.2`` (tier 2+).
    """

    def _k(tier: int) -> float:
        if tier <= 0:
            return 2.0
        if tier == 1:
            return 1.5
        return 1.2

    for e in edges:
        k = _k(e.decay_tier)
        w = float(e.weight)
        delta = lam * dt * (w**k)
        e.weight = max(0.0, w - delta)


def enforce_saturation(
    edges: list[Edge], *, max_out_degree: int = 64, w_max: float = 1.0
) -> list[Edge]:
    """Per-source-node cap on outgoing count; drop lowest-weight edges first."""
    by_source: dict[str, list[Edge]] = {}
    for e in edges:
        key = str(e.source_id)
        by_source.setdefault(key, []).append(e)

    survivors: list[Edge] = []
    for out_list in by_source.values():
        sorted_out = sorted(out_list, key=lambda x: x.weight, reverse=True)
        kept = sorted_out[:max_out_degree]
        survivors.extend(kept)

    for e in survivors:
        e.weight = min(e.weight, w_max)
    return survivors


def build_csr_from_columns(
    source_ids: Iterable[str],
    target_ids: Iterable[str],
    weights: Iterable[float],
    frame_consistencies: Iterable[float] | None = None,
) -> EdgeCSR:
    """Build a PyTorch CSR tensor where conductance = weight × frame_consistency.

    Prefer this over :func:`build_csr_from_edges` on the query hot path — it
    consumes columnar Lance fields and avoids per-edge JSON deserialization
    (PHX-1041).
    """
    sources = [str(s) for s in source_ids]
    targets = [str(t) for t in target_ids]
    weight_list = [float(w) for w in weights]
    if frame_consistencies is None:
        frame_list = [1.0] * len(weight_list)
    else:
        frame_list = [float(f) for f in frame_consistencies]
    if not (len(sources) == len(targets) == len(weight_list) == len(frame_list)):
        raise ValueError(
            "source_ids, target_ids, weights, and frame_consistencies must have equal length"
        )

    # Node index space includes every endpoint — even a node whose only edge is a
    # dropped self-loop — so seed / constellation node→index mapping stays stable.
    endpoints: set[str] = set(sources)
    endpoints.update(targets)
    ordered = sorted(endpoints)
    id_to_index = {nid: i for i, nid in enumerate(ordered)}
    n = len(ordered)

    # Drop self-loops (source == target). Activation cannot propagate from a node
    # to itself, and PPR / PageRank zero the diagonal by construction, so a stored
    # self-loop carries no Spreading-Activation signal — it only inflates a node's
    # out-degree and clones itself into every Constellation. Filtering here (rather
    # than at write time) also self-heals meshes that accumulated self-loops before
    # this guard: e.g. the founding mesh's identity-attractor `fed_with` self-loops
    # on the poem hub (PHX-1051), which dominated the induced sub-graph of a query.
    triples = [
        (s, t, w, f)
        for s, t, w, f in zip(sources, targets, weight_list, frame_list, strict=True)
        if s != t
    ]

    row_counts = [0] * n
    for source, _t, _w, _f in triples:
        row_counts[id_to_index[source]] += 1
    crow = [0]
    for count in row_counts:
        crow.append(crow[-1] + count)
    nnz = crow[-1]
    col = [0] * nnz
    val = [0.0] * nnz
    write = crow[:-1].copy()

    for source, target, weight, frame in triples:
        si = id_to_index[source]
        pos = write[si]
        col[pos] = id_to_index[target]
        val[pos] = weight * frame
        write[si] += 1

    return EdgeCSR(
        crow_indices=torch.tensor(crow, dtype=torch.int64),
        col_indices=torch.tensor(col, dtype=torch.int64),
        values=torch.tensor(val, dtype=torch.float32),
        node_ids=ordered,
        id_to_index=id_to_index,
    )


def build_csr_from_edges(edges: list[Edge]) -> EdgeCSR:
    """Build a PyTorch CSR tensor where conductance = weight × frame_consistency."""
    return build_csr_from_columns(
        (str(edge.source_id) for edge in edges),
        (str(edge.target_id) for edge in edges),
        (edge.weight for edge in edges),
        (edge.frame_consistency for edge in edges),
    )


# ---- Lance-backed edge store ----


class EdgeStore:
    """Lance ``mesh_edges`` table + parallel ``edge_metadata`` table + delta buffer."""

    def __init__(self, db: lancedb.DBConnection, *, delta_path: Path | None = None) -> None:
        self._db = db
        self.delta = EdgeDeltaBuffer(delta_path)
        # Cheap write-clock for CSR cache invalidation (PHX-1041). Listing Lance
        # versions is O(version_count) and can take tens of seconds on busy
        # workspaces; this counter is O(1) and sufficient for single-process
        # query loops (CLI / cockpit).
        self._mutation_generation: int = 0

        if _have_table(db, "mesh_edges"):
            self.edge_table = db.open_table("mesh_edges")
        else:
            self.edge_table = db.create_table("mesh_edges", schema=_EDGE_SCHEMA)

        if _have_table(db, "edge_metadata"):
            self.meta_table = db.open_table("edge_metadata")
        else:
            self.meta_table = db.create_table("edge_metadata", schema=_METADATA_SCHEMA)

        if _have_table(db, "edge_dedup_index"):
            self.dedup_index = db.open_table("edge_dedup_index")
        else:
            self.dedup_index = db.create_table("edge_dedup_index", schema=_DEDUP_INDEX_SCHEMA)
        self._ensure_dedup_index()

    @property
    def mutation_generation(self) -> int:
        return self._mutation_generation

    def _bump_mutation_generation(self) -> None:
        self._mutation_generation += 1

    @staticmethod
    def dedup_key(source_id: str, target_id: str, relation_descriptor: str | None) -> str:
        """Stable 128-bit hash identifying a directed (source, target, relation) edge.

        Hashing keeps the index key fixed-width, control-character-free, and
        safe to compare, regardless of what a free-form ``relation_descriptor``
        contains.  Collisions are astronomically unlikely; a collision would at
        worst skip one legitimate edge as a duplicate (a benign, audited loss).
        """
        raw = f"{source_id}\x1f{target_id}\x1f{relation_descriptor or ''}".encode()
        return hashlib.blake2b(raw, digest_size=16).hexdigest()

    def _dedup_rows(self, edges: list[Edge]) -> list[dict[str, str]]:
        return [
            {
                "dedup_key": self.dedup_key(
                    str(edge.source_id), str(edge.target_id), edge.relation_descriptor
                )
            }
            for edge in edges
        ]

    def _iter_existing_dedup_keys(self, *, page_size: int = 4096) -> Iterator[str]:
        """Yield dedup keys for already-stored edges without building Edge objects."""
        offset = 0
        while True:
            rows = self.edge_table.search().limit(page_size).offset(offset).to_list()
            if not rows:
                return
            for row in rows:
                relation_descriptor: str | None = None
                payload = row.get("payload_json")
                if payload:
                    try:
                        relation_descriptor = json.loads(payload).get("relation_descriptor")
                    except (ValueError, TypeError):
                        relation_descriptor = None
                yield self.dedup_key(
                    str(row["source_id"]), str(row["target_id"]), relation_descriptor
                )
            offset += len(rows)

    def _ensure_dedup_index(self) -> None:
        """Backfill the dedup index for a workspace whose edges predate it (once)."""
        if self.edge_table.count_rows() == 0:
            return
        if self.dedup_index.count_rows() > 0:
            return
        batch: list[dict[str, str]] = []
        for key in self._iter_existing_dedup_keys():
            batch.append({"dedup_key": key})
            if len(batch) >= 4096:
                self.dedup_index.add(batch)
                batch = []
        if batch:
            self.dedup_index.add(batch)

    def load_dedup_keys(self) -> set[str]:
        """Return all stored edge dedup keys — the cheap replacement for a
        ``load_all_edges()`` scan when only edge identity is needed."""
        arrow = self.dedup_index.search().to_arrow()
        if arrow.num_rows == 0:
            return set()
        return set(arrow.column("dedup_key").to_pylist())

    @staticmethod
    def _edge_row(edge: Edge) -> dict[str, Any]:
        return {
            "source_id": str(edge.source_id),
            "target_id": str(edge.target_id),
            "weight": float(edge.weight),
            "decay_tier": int(edge.decay_tier),
            "frame_consistency": float(edge.frame_consistency),
            "eligibility": float(edge.eligibility),
            "feedback_modulated_strength": float(edge.feedback_modulated_strength),
            "born_at": edge.born_at,
            "last_fired_at": edge.last_fired_at,
            "payload_json": edge.model_dump_json(),
        }

    @staticmethod
    def _metadata_row(edge: Edge) -> dict[str, Any] | None:
        meta = EdgeMetadata(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_descriptor=edge.relation_descriptor,
            relation_kind=edge.relation_kind,
            description=edge.description,
            pids=edge.pids,
            creation_context=edge.creation_context,
        )
        if not any(
            [
                meta.relation_descriptor,
                meta.relation_kind,
                meta.description,
                meta.pids,
                meta.creation_context,
            ]
        ):
            return None
        return {
            "source_id": str(meta.source_id),
            "target_id": str(meta.target_id),
            "payload_json": meta.model_dump_json(),
        }

    def append_edge(self, edge: Edge) -> None:
        """Write one edge to the quantitative table + optionally metadata."""
        self.append_edges([edge])

    def append_edges(self, edges: list[Edge]) -> None:
        """Write many edges to the quantitative table + optional metadata."""
        if not edges:
            return
        self.edge_table.add([self._edge_row(edge) for edge in edges])
        meta_rows = [row for edge in edges if (row := self._metadata_row(edge)) is not None]
        if meta_rows:
            self.meta_table.add(meta_rows)
        self.dedup_index.add(self._dedup_rows(edges))
        self._bump_mutation_generation()

    def load_all_edges(self) -> list[Edge]:
        arrow = self.edge_table.search().to_arrow()
        out: list[Edge] = []
        for row in arrow.to_pylist():
            out.append(Edge.model_validate_json(row["payload_json"]))
        return out

    def load_metadata_for_sources(
        self, source_ids: Iterable[str]
    ) -> dict[tuple[str, str], EdgeMetadata]:
        """Load edge descriptors for a small set of source nodes (Constellation enrichment).

        Keyed by ``(source_id, target_id)``. Used by retrieval to attach
        ``relation_descriptor`` to the edges of an activated sub-graph without scanning
        the full metadata table. ULIDs are alphanumeric, so they inline safely in the
        Lance filter (same pattern as :meth:`neighbor_ids`).
        """
        ids = {str(s) for s in source_ids}
        if not ids:
            return {}
        quoted = ",".join(f'"{sid}"' for sid in ids)
        rows = self.meta_table.search().where(f"source_id IN ({quoted})").to_list()
        out: dict[tuple[str, str], EdgeMetadata] = {}
        for row in rows:
            meta = EdgeMetadata.model_validate_json(row["payload_json"])
            out[(str(meta.source_id), str(meta.target_id))] = meta
        return out

    def replace_all_edges(self, edges: list[Edge]) -> None:
        """Atomically replace the quantitative and metadata tables (Oneiros commit)."""
        self.edge_table.delete("true")
        self.meta_table.delete("true")
        self.dedup_index.delete("true")
        if not edges:
            self._bump_mutation_generation()
            return
        self.edge_table.add([self._edge_row(edge) for edge in edges])
        meta_rows = [row for edge in edges if (row := self._metadata_row(edge)) is not None]
        if meta_rows:
            self.meta_table.add(meta_rows)
        self.dedup_index.add(self._dedup_rows(edges))
        self._bump_mutation_generation()

    def count_rows(self) -> int:
        return int(self.edge_table.count_rows())

    def neighbor_ids(self, node_id: str) -> set[str]:
        outgoing = self.edge_table.search().where(f'source_id = "{node_id}"').to_list()
        incoming = self.edge_table.search().where(f'target_id = "{node_id}"').to_list()
        neighbours = {str(row["target_id"]) for row in outgoing}
        neighbours.update(str(row["source_id"]) for row in incoming)
        return neighbours

    def adjacency_index(self) -> dict[str, set[str]]:
        """Undirected neighbour sets for every node, from one columnar scan.

        :meth:`neighbor_ids` costs two filtered scans of the whole edge table —
        measured at ~597 ms on a 27.8k-edge mesh. Callers that score many
        candidates (the eager linker checks up to 24 per concept) pay that per
        candidate, which is what actually collapses ingestion throughput as a mesh
        grows. One full scan of the same table costs ~1.07 s, so building the whole
        index is cheaper than asking about two nodes.

        Reads only the two id columns — no payload_json, no Edge construction.
        """
        arrow = self.edge_table.search().select(["source_id", "target_id"]).to_arrow()
        sources = arrow.column("source_id").to_pylist()
        targets = arrow.column("target_id").to_pylist()
        index: dict[str, set[str]] = {}
        for source, target in zip(sources, targets, strict=True):
            src, tgt = str(source), str(target)
            index.setdefault(src, set()).add(tgt)
            index.setdefault(tgt, set()).add(src)
        return index

    def csr_from_store(self) -> EdgeCSR:
        """Build CSR from quantitative Lance columns (no ``payload_json`` parse)."""
        arrow = self.edge_table.search().to_arrow()
        if arrow.num_rows == 0:
            return build_csr_from_columns([], [], [], [])
        return build_csr_from_columns(
            arrow.column("source_id").to_pylist(),
            arrow.column("target_id").to_pylist(),
            arrow.column("weight").to_pylist(),
            arrow.column("frame_consistency").to_pylist(),
        )
