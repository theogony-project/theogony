"""Lance tables for ``chunk_nodes`` and ``consolidated_nodes``.

Per MESH_IMPLEMENTATION.md §"Nodes — LanceDB": two tables, one per node tier,
with per-vector HNSW indices on ``semantic_vector`` (default) and on populated
``frame_vector`` / ``structural_vector`` / ``description_vector`` columns.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import lancedb
import pyarrow as pa

from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, QIDTag
from theogony.stores.lance_typing import as_vector_query


def _normalize_label(label: str) -> str:
    raw = label.lower().strip()
    raw = re.sub(r"'s\b", "", raw)
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


def _create_scalar_index(table: Any, column: str) -> None:
    """Build a scalar index, preferring the current API over the deprecated one.

    lancedb replaced `create_scalar_index(col)` with `create_index(col,
    config=BTree())` in 0.25. This repo has already been bitten once by lancedb
    moving an API between the version installed locally and the one CI resolves
    (PHX-1057), so both spellings are supported rather than pinning to either.
    """
    try:
        from lancedb.index import BTree

        table.create_index(column, config=BTree())
    except (ImportError, TypeError):
        table.create_scalar_index(column)


# Below this row count a full scan beats an index, and IVF cannot train
# partitions. Chosen so test-sized workspaces never pay for indexing.
# Re-rank this many times ``limit`` PQ candidates against their true vectors
# before returning. Without it the IVF-PQ index is not an approximation of the
# nearest neighbours, it is a different answer: measured on the founding mesh
# (5,002 nodes, 384-d), the indexed top-64 overlapped the exact top-64 by a
# **median of 22%**, minimum 9% (PHX-1085).
#
#     refine_factor   overlap (median / min)   median ms
#     none                  22% /  9%             9.40
#     5                     52% / 31%            10.32
#     10                    72% / 45%            11.11
#     20                    89% / 72%            11.80
#     30                    97% / 80%            12.09
#     50                   100% / 94%            12.22
#     no index at all      100% / 100%           12.38
#
# `nprobes` does nothing here — 22% at 20 and at 64 — so the loss is the product
# quantiser (8 sub-vectors for a 384-d vector), not partition coverage. Only
# re-ranking against the stored vectors recovers it.
#
# 50 costs 2.8 ms on this mesh and buys back the whole candidate set. It re-ranks
# `50 * limit` rows, so on a 5,002-node mesh it is very nearly exhaustive — which
# is why it matches the unindexed scan in both accuracy and time. On a large mesh
# the same setting re-ranks a small fraction and the index does the work it was
# built for. That half is reasoned rather than measured: this repo has no large
# mesh carrying a vector index to check it on (`data/mesh-wiki-100k` has none,
# and its vectors are 1024-d).
_VECTOR_REFINE_FACTOR = 50

_MIN_ROWS_FOR_INDEX = 512

# A Lance index covers only the rows that existed when it was built; later
# appends land in an unindexed fragment that every query scans on top of the
# index. Refresh once this many rows have accumulated outside it — below that,
# scanning the tail is cheaper than folding it in.
_MAX_UNINDEXED_ROWS = 512

# How much Lance version history a maintenance pass keeps. These are
# storage-level snapshots, one per write, not the substrate's own record: the
# doctrinal history lives in the `mesh_audit` table and the RunReports, and
# nothing in this codebase reads an old Lance version (there is no `checkout`,
# `restore` or `as_of` anywhere). Retaining them is expensive — measured on a
# 2,325-node mesh, appends cost 83.3 ms against 2.6 ms for the same rows written
# without the version pile-up, and pruning 1,893 versions to 13 restored
# 40.8 -> 2.7 ms for 1.9 s of work (PHX-1060).
#
# Zero keeps the current version only. Callers that want history kept pass a
# window; `run_minimal_tick` threads one through.
_DEFAULT_VERSION_RETENTION = timedelta(0)


def _unindexed_rows(table: Any) -> int:
    """Rows the least up-to-date index on this table does not cover."""
    worst = 0
    for idx in table.list_indices():
        try:
            stats = table.index_stats(idx.name)
        except Exception:  # noqa: BLE001 - stats are advisory, never load-bearing
            continue
        worst = max(worst, int(getattr(stats, "num_unindexed_rows", 0) or 0))
    return worst


def _refresh_indices(table: Any, *, max_unindexed: int = _MAX_UNINDEXED_ROWS) -> str:
    """Fold rows appended since the last build into this table's indices.

    Building an index is not a one-time act, which is the half of PHX-1059 the
    first fix missed. Measured on a mesh whose indices were built at 831 rows
    and then grown to 2,300 (64% of rows outside the index):

        label lookup   88.4 ms  ->  3.3 ms
        get_consolidated 48.6 ms ->  1.2 ms
        ANN              41.7 ms ->  5.2 ms

    for 2.5 s of refresh. Without this the index lowers the growth curve but
    does not flatten it: the unindexed tail grows with every ingest, so the
    scan it forces grows too.
    """
    stale = _unindexed_rows(table)
    if stale < max_unindexed:
        return f"fresh ({stale} rows unindexed)"
    try:
        table.optimize(cleanup_older_than=timedelta(days=3650))
    except Exception as exc:  # noqa: BLE001 - a stale index only costs speed
        return f"refresh failed: {exc}"
    return f"refreshed ({stale} rows folded in)"


def _sql_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _have_table(db: lancedb.DBConnection, name: str) -> bool:
    resp = db.list_tables()
    return name in (resp.tables or [])


_QID_INDEX_SCHEMA = pa.schema(
    [
        ("qid", pa.string()),
        ("node_id", pa.string()),
    ]
)

_LABEL_INDEX_SCHEMA = pa.schema(
    [
        ("label", pa.string()),
        ("node_id", pa.string()),
    ]
)


class NodeFiringBuffer:
    """Append path for node firings, folded into the node tables at each Oneiros tick.

    `fired_total` and `fired_recent` are declared on both node schemas and were
    **0 on every node of every mesh this repo has built** — nothing wrote them.
    Four mechanisms read them: tier promotion (`MESH_SUBSTRATE.md` §"Consolidation,
    splits, and tier promotion" gates on "number of distinct activation contexts,
    age, breadth of incoming references"), tier-modulated decay through
    `decay_tier`, Oneiros' replay of structurally important edges, and the
    eligibility traces of three-factor RL. All four were reading a history nobody
    recorded (PHX-1100, PHX-1101).

    **Buffered, because reading must not write.** `MESH_IMPLEMENTATION.md`
    §"What is forbidden" names "reads that mutate the version they read from" and
    says the write-back goes through a buffer instead. A firing is recorded on the
    query path and applied by the tick; no Lance version moves during a read.

    **One append per pass, not one per node** — the same section requires it in as
    many words: "The flush is a single append batch, not many small appends." The
    edge delta buffer next door does the opposite, one file open per delta under
    the lock, measured at 3.05 ms for a single query's 64 deltas. A pass here
    records ~50 nodes for ~0.1 ms.

    Nothing on the query path reads this file. `EdgeDeltaBuffer.pending()` reparses
    its whole sidecar and is reached from the CSR cache fingerprint, so its cost
    grows with the backlog on every query; this buffer is written by readers and
    read only by the tick.
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
                # A torn final line from a killed process costs one pass, not the tick.
                continue
        return rows

    def append_firing(self, node_ids: Iterable[str], *, at: datetime | None = None) -> int:
        """Record that these nodes fired together in one pass. Returns how many."""
        ids = sorted({str(node_id) for node_id in node_ids})
        if not ids:
            return 0
        row = {"at": (at or datetime.now(UTC)).isoformat(), "node_ids": ids}
        with self._lock:
            if self._path is None:
                self._rows.append(row)
                return len(ids)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        return len(ids)

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out = self._rows
            self._rows = []
            if self._path is not None:
                out = out + self._persisted()
                self._path.unlink(missing_ok=True)
            return out

    def pending_passes(self) -> int:
        """Recorded passes not yet folded in. **Not for the query path** — this
        reparses the sidecar, and its cost grows with the backlog."""
        with self._lock:
            return len(self._rows) + len(self._persisted())


class MeshNodeStore:
    """Creates/opens node tables and provides append/query methods."""

    def __init__(
        self,
        db: lancedb.DBConnection,
        *,
        semantic_dim: int,
        frame_dim: int,
    ) -> None:
        self._db = db
        self.semantic_dim = semantic_dim
        self.frame_dim = frame_dim

        chunk_schema = pa.schema(
            [
                ("id", pa.string()),
                ("payload_json", pa.string()),
                ("semantic_vector", pa.list_(pa.float32(), semantic_dim)),
                ("frame_vector", pa.list_(pa.float32(), frame_dim)),
            ]
        )
        if _have_table(db, "chunk_nodes"):
            self.chunk_table = db.open_table("chunk_nodes")
        else:
            self.chunk_table = db.create_table("chunk_nodes", schema=chunk_schema)

        consolidated_schema = pa.schema(
            [
                ("id", pa.string()),
                ("payload_json", pa.string()),
                ("semantic_vector", pa.list_(pa.float32(), semantic_dim)),
                ("frame_vector", pa.list_(pa.float32(), frame_dim)),
                ("description_vector", pa.list_(pa.float32(), semantic_dim)),
            ]
        )
        if _have_table(db, "consolidated_nodes"):
            self.consolidated_table = db.open_table("consolidated_nodes")
        else:
            self.consolidated_table = db.create_table(
                "consolidated_nodes", schema=consolidated_schema
            )
        self._consolidated_has_description_vector = (
            self.consolidated_table.schema.get_field_index("description_vector") >= 0
        )
        if _have_table(db, "consolidated_qid_index"):
            self.consolidated_qid_index = db.open_table("consolidated_qid_index")
        else:
            self.consolidated_qid_index = db.create_table(
                "consolidated_qid_index", schema=_QID_INDEX_SCHEMA
            )
        if _have_table(db, "consolidated_label_index"):
            self.consolidated_label_index = db.open_table("consolidated_label_index")
        else:
            self.consolidated_label_index = db.create_table(
                "consolidated_label_index", schema=_LABEL_INDEX_SCHEMA
            )
        self._ensure_consolidated_indexes()

    # ---- chunk nodes ----

    def _chunk_row(self, node: ChunkNode) -> dict[str, object]:
        assert len(node.semantic_vector) == self.semantic_dim
        assert len(node.frame_vector) == self.frame_dim
        return {
            "id": str(node.id),
            "payload_json": node.model_dump_json(),
            "semantic_vector": [float(x) for x in node.semantic_vector],
            "frame_vector": [float(x) for x in node.frame_vector],
        }

    def append_chunk(self, node: ChunkNode) -> None:
        self.append_chunks([node])

    def append_chunks(self, nodes: list[ChunkNode]) -> None:
        if not nodes:
            return
        self.chunk_table.add([self._chunk_row(node) for node in nodes])

    def get_chunk(self, node_id: str) -> ChunkNode | None:
        rows = self.chunk_table.search().where(f'id = "{node_id}"').limit(1).to_list()
        if not rows:
            return None
        return ChunkNode.model_validate_json(rows[0]["payload_json"])

    def chunk_count(self) -> int:
        return int(self.chunk_table.count_rows())

    # ---- consolidated nodes ----

    def _consolidated_row(self, node: ConsolidatedNode) -> dict[str, object]:
        assert len(node.semantic_vector) == self.semantic_dim
        assert len(node.frame_vector) == self.frame_dim
        if node.description_vector is not None:
            assert len(node.description_vector) == self.semantic_dim
        row: dict[str, object] = {
            "id": str(node.id),
            "payload_json": node.model_dump_json(),
            "semantic_vector": [float(x) for x in node.semantic_vector],
            "frame_vector": [float(x) for x in node.frame_vector],
        }
        if self._consolidated_has_description_vector:
            row["description_vector"] = (
                [float(x) for x in node.description_vector]
                if node.description_vector is not None
                else None
            )
        return row

    @staticmethod
    def _qid_index_rows(node: ConsolidatedNode) -> list[dict[str, object]]:
        node_id = str(node.id)
        seen: set[str] = set()
        rows: list[dict[str, object]] = []
        for qid_tag in node.qids:
            if qid_tag.qid in seen:
                continue
            seen.add(qid_tag.qid)
            rows.append({"qid": qid_tag.qid, "node_id": node_id})
        return rows

    @staticmethod
    def _label_index_rows(node: ConsolidatedNode) -> list[dict[str, object]]:
        node_id = str(node.id)
        raw_labels: list[str] = []
        if node.description:
            raw_labels.append(node.description)
        raw_labels.extend(node.tags)
        seen: set[str] = set()
        rows: list[dict[str, object]] = []
        for raw_label in raw_labels:
            normalized = _normalize_label(raw_label)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            rows.append({"label": normalized, "node_id": node_id})
        return rows

    def _ensure_consolidated_indexes(self) -> None:
        if self.consolidated_table.count_rows() == 0:
            return
        qid_count = self.consolidated_qid_index.count_rows()
        label_count = self.consolidated_label_index.count_rows()
        if qid_count > 0 and label_count > 0:
            return
        qid_rows: list[dict[str, object]] = []
        label_rows: list[dict[str, object]] = []
        for node in self.iter_consolidated(page_size=1024):
            if qid_count == 0:
                qid_rows.extend(self._qid_index_rows(node))
            if label_count == 0:
                label_rows.extend(self._label_index_rows(node))
            if len(qid_rows) >= 4096:
                self.consolidated_qid_index.add(qid_rows)
                qid_rows = []
            if len(label_rows) >= 4096:
                self.consolidated_label_index.add(label_rows)
                label_rows = []
        if qid_rows:
            self.consolidated_qid_index.add(qid_rows)
        if label_rows:
            self.consolidated_label_index.add(label_rows)

    def append_consolidated(self, node: ConsolidatedNode) -> None:
        self.append_consolidated_many([node])

    def append_consolidated_many(self, nodes: list[ConsolidatedNode]) -> None:
        if not nodes:
            return
        self.consolidated_table.add([self._consolidated_row(node) for node in nodes])
        qid_rows = [row for node in nodes for row in self._qid_index_rows(node)]
        if qid_rows:
            self.consolidated_qid_index.add(qid_rows)
        label_rows = [row for node in nodes for row in self._label_index_rows(node)]
        if label_rows:
            self.consolidated_label_index.add(label_rows)

    def replace_all_consolidated(self, nodes: list[ConsolidatedNode]) -> None:
        """Rewrite the consolidated table and both its indices from ``nodes``.

        The store is otherwise append-only, which is right: the substrate's
        history is its record. This exists for repairs that must not leave a
        stale row behind — see `scripts/mesh_repair_anchor_provenance.py`, which
        corrects provenance that recorded a filesystem path instead of a source
        (PHX-1084).

        One overwrite per table rather than delete-then-add, for the reason
        :meth:`EdgeStore.replace_all_edges` gives: the delete-then-add form left
        every table empty when the add raised (PHX-1082).
        """
        if not nodes:
            self.consolidated_table.delete("true")
            self.consolidated_qid_index.delete("true")
            self.consolidated_label_index.delete("true")
            return

        self.consolidated_table.add(
            [self._consolidated_row(node) for node in nodes], mode="overwrite"
        )
        qid_rows = [row for node in nodes for row in self._qid_index_rows(node)]
        if qid_rows:
            self.consolidated_qid_index.add(qid_rows, mode="overwrite")
        else:
            self.consolidated_qid_index.delete("true")
        label_rows = [row for node in nodes for row in self._label_index_rows(node)]
        if label_rows:
            self.consolidated_label_index.add(label_rows, mode="overwrite")
        else:
            self.consolidated_label_index.delete("true")

    def get_consolidated(self, node_id: str) -> ConsolidatedNode | None:
        rows = self.consolidated_table.search().where(f'id = "{node_id}"').limit(1).to_list()
        if not rows:
            return None
        return ConsolidatedNode.model_validate_json(rows[0]["payload_json"])

    def get_consolidated_many(self, node_ids: Iterable[str]) -> dict[str, ConsolidatedNode]:
        """Fetch many consolidated nodes in one query, keyed by id.

        Constellation assembly needs every activated node at once. Fetching them
        one at a time costs one Lance query each — measured at 4.3 ms, so ~171 ms
        for a 30-node working set, against ~5 ms for the same nodes in a single
        filtered read. Missing ids are simply absent from the result.
        """
        ids = [str(n) for n in node_ids]
        if not ids:
            return {}
        quoted = ",".join(f'"{_sql_quote(i)}"' for i in ids)
        rows = self.consolidated_table.search().where(f"id IN ({quoted})").to_list()
        out: dict[str, ConsolidatedNode] = {}
        for row in rows:
            node = ConsolidatedNode.model_validate_json(row["payload_json"])
            out[str(node.id)] = node
        return out

    def ensure_indices(
        self,
        *,
        min_rows: int = _MIN_ROWS_FOR_INDEX,
        max_unindexed: int = _MAX_UNINDEXED_ROWS,
    ) -> dict[str, str]:
        """Create the Lance indices this store's own query patterns depend on.

        The substrate created **no indices at all**, so every lookup was a full
        scan whose cost grew with the table. Measured on a 2,436-node mesh:

            get_consolidated            57.7 ms  ->   5.2 ms
            find_consolidated_by_labels 213.7 ms ->  16.2 ms
            get_consolidated_by_qid      56.0 ms ->   3.7 ms
            ANN over description_vector  61.9 ms ->   8.4 ms

        Batching the reads (PHX-1057 and its follow-up) cut how *many* queries ran;
        this cuts what each one costs, and — more importantly — stops it growing
        linearly with the mesh. Ingestion resolution cost was scaling roughly with
        the square of the node count because both the number of lookups and the
        cost of each were rising together.

        Indices are also *refreshed* here, not only created: Lance leaves rows
        appended after a build outside the index, so an index built once and never
        maintained lowers the growth curve without flattening it. See
        :func:`_refresh_indices`.

        Indexing is skipped below ``min_rows``: IVF needs enough vectors to train
        partitions, and on a small workspace a scan is faster than an index anyway.
        Returns a map of index name to status for the caller's run report.
        """
        result: dict[str, str] = {}
        rows = self.consolidated_table.count_rows()
        if rows < min_rows:
            return {"skipped": f"only {rows} consolidated rows (<{min_rows})"}

        existing = {idx.name for idx in self.consolidated_table.list_indices()}
        for column in ("id",):
            if any(column in name for name in existing):
                result[f"consolidated.{column}"] = "present"
                continue
            try:
                _create_scalar_index(self.consolidated_table, column)
                result[f"consolidated.{column}"] = "created"
            except Exception as exc:  # noqa: BLE001 - indexing is best-effort
                result[f"consolidated.{column}"] = f"failed: {exc}"

        # Partition count follows the row count: too many partitions on a small
        # table trains poorly, too few degrades recall on a large one.
        partitions = max(1, min(256, int(rows**0.5)))
        for column in ("semantic_vector", "description_vector"):
            if any(column in name for name in existing):
                result[f"consolidated.{column}"] = "present"
                continue
            try:
                self.consolidated_table.create_index(
                    metric="cosine",
                    vector_column_name=column,
                    index_type="IVF_PQ",
                    num_partitions=partitions,
                    num_sub_vectors=max(1, min(8, self.semantic_dim // 8)),
                    replace=True,
                )
                result[f"consolidated.{column}"] = "created"
            except Exception as exc:  # noqa: BLE001 - a missing index only costs speed
                result[f"consolidated.{column}"] = f"failed: {exc}"

        result["consolidated.refresh"] = _refresh_indices(
            self.consolidated_table, max_unindexed=max_unindexed
        )

        for table, column, key in (
            (self.consolidated_label_index, "label", "label_index.label"),
            (self.consolidated_qid_index, "qid", "qid_index.qid"),
        ):
            if table.count_rows() < min_rows:
                result[key] = "skipped: too few rows"
                continue
            if any(column in idx.name for idx in table.list_indices()):
                result[key] = "present"
            else:
                try:
                    _create_scalar_index(table, column)
                    result[key] = "created"
                except Exception as exc:  # noqa: BLE001
                    result[key] = f"failed: {exc}"
                    continue
            result[f"{key}.refresh"] = _refresh_indices(table, max_unindexed=max_unindexed)
        return result

    def prune_history(self, *, retention: timedelta = _DEFAULT_VERSION_RETENTION) -> dict[str, int]:
        """Discard Lance version snapshots older than ``retention``.

        Every write creates a version, and the substrate writes one node at a
        time across three tables, so a single 124-paragraph batch leaves roughly
        four thousand of them. That history is not free: it is what makes an
        append cost 83.3 ms on a grown mesh against 2.6 ms for the same rows
        written without the pile-up (PHX-1060). The node count is not the driver
        — a mesh with *more* index rows and the same nodes appends in 2.6 ms when
        it has 13 versions instead of 1,871.

        This removes storage snapshots, not the substrate's memory. What the mesh
        did and when is recorded in the `mesh_audit` table and the RunReports;
        the Lance version chain has no reader in this codebase. Callers that want
        it kept anyway pass a longer ``retention``.

        Returns versions removed per table, for the caller's run report.
        """
        removed: dict[str, int] = {}
        for name, table in (
            ("consolidated_nodes", self.consolidated_table),
            ("chunk_nodes", self.chunk_table),
            ("consolidated_label_index", self.consolidated_label_index),
            ("consolidated_qid_index", self.consolidated_qid_index),
        ):
            try:
                before = len(table.list_versions())
                table.optimize(cleanup_older_than=retention)
                # Compaction commits a version of its own, so a run that prunes
                # nothing can end up one or two ahead. Report removals only.
                removed[name] = max(0, before - len(table.list_versions()))
            except Exception:  # noqa: BLE001 - pruning is best-effort upkeep
                removed[name] = 0
        return removed

    def merge_identity_evidence(
        self, node_id: str, *, qids: list[QIDTag], node: ConsolidatedNode | None = None
    ) -> ConsolidatedNode | None:
        """Persist identity evidence acquired at merge time (PHX-1053).

        When the eager linker merges a reference into an existing node, the
        reference may carry Q-IDs the stored node does not have yet (measured
        live: Aphrodite Q35500 merged into a hymn concept and the Q-ID
        evaporated with the process). Appending them here makes the identity
        durable and Q-ID-addressable for every later read and ingest.

        Pass ``node`` when the caller already holds it — the eager linker always
        does, having just matched it. Re-fetching costs a filtered Lance query
        (68.7 ms on a 2.4k-node mesh) on *every* merge, including the common case
        where the reference carries no Q-ID the node lacks and the function
        returns immediately."""
        node = node or self.get_consolidated(node_id)
        if node is None:
            return None
        known = {q.qid for q in node.qids}
        new_qids = [q for q in qids if q.qid not in known]
        if not new_qids:
            return node
        updated = node.model_copy(update={"qids": [*node.qids, *new_qids]})
        self.consolidated_table.delete(f'id = "{_sql_quote(node_id)}"')
        self.consolidated_table.add([self._consolidated_row(updated)])
        self.consolidated_qid_index.add([{"qid": q.qid, "node_id": str(node_id)} for q in new_qids])
        return updated

    def get_consolidated_id_by_qid(self, qid: str) -> str | None:
        """Return node_id for a Q-ID without loading the full node payload.

        Used by the wikidata5m seed path (PHX-1030) so bulk imports do not
        materialise 1024-d vectors into the resolver cache.
        """
        rows = (
            self.consolidated_qid_index.search()
            .where(f'qid = "{_sql_quote(qid)}"')
            .limit(1)
            .to_list()
        )
        if not rows:
            return None
        return str(rows[0]["node_id"])

    def get_consolidated_by_qid(self, qid: str) -> ConsolidatedNode | None:
        node_id = self.get_consolidated_id_by_qid(qid)
        if node_id is None:
            return None
        return self.get_consolidated(node_id)

    def get_consolidated_by_label(self, label: str) -> ConsolidatedNode | None:
        normalized = _normalize_label(label)
        if not normalized:
            return None
        rows = (
            self.consolidated_label_index.search()
            .where(f'label = "{_sql_quote(normalized)}"')
            .limit(1)
            .to_list()
        )
        if not rows:
            return None
        return self.get_consolidated(str(rows[0]["node_id"]))

    def find_consolidated_by_labels(
        self,
        labels: list[str],
        *,
        limit: int = 32,
    ) -> list[ConsolidatedNode]:
        if limit <= 0:
            return []

        # Candidate *selection* is unchanged: one index read per label, in the
        # caller's priority order, stopping at `limit` — the eager linker's
        # scoring depends on which candidates it sees, so this must stay exact.
        # Only the hydration is batched. Fetching each matching node with its own
        # query was the expensive half (~595 ms for one concept on a 2.4k-node
        # mesh); collecting the ids first and reading them in one go removes it
        # without touching semantics.
        #
        # A combined `label IN (...)` read was tried and rejected: it is faster
        # still, but changes which candidates survive truncation when a generic
        # tag matches more nodes than `limit` (measured: 15 differing sets out of
        # 60 real label/tag combinations). Identity resolution is not a place to
        # trade exactness for latency.
        seen_ids: set[str] = set()
        ordered_ids: list[str] = []
        for label in labels:
            normalized = _normalize_label(label)
            if not normalized:
                continue
            rows = (
                self.consolidated_label_index.search()
                .where(f'label = "{_sql_quote(normalized)}"')
                .limit(limit)
                .to_list()
            )
            for row in rows:
                node_id = str(row["node_id"])
                if node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                ordered_ids.append(node_id)
                if len(ordered_ids) >= limit:
                    break
            if len(ordered_ids) >= limit:
                break

        hydrated = self.get_consolidated_many(ordered_ids)
        return [hydrated[nid] for nid in ordered_ids if nid in hydrated]

    def search_consolidated_by_vector(
        self,
        vector: list[float],
        *,
        vector_column_name: str = "description_vector",
        limit: int = 16,
    ) -> list[ConsolidatedNode]:
        """Nearest consolidated nodes by cosine, re-ranked against their true vectors.

        See :data:`_VECTOR_REFINE_FACTOR` for why the re-ranking is not optional:
        without it this returns a median of 22% of the actual nearest neighbours.
        """
        if not vector or limit <= 0:
            return []

        def _search(column: str) -> list[dict[str, Any]]:
            query = as_vector_query(
                self.consolidated_table.search(vector, vector_column_name=column)
            ).metric("cosine")
            # Unsupported on a table with no vector index — there is nothing to
            # refine there, the search is already exact.
            with contextlib.suppress(Exception):
                query = query.refine_factor(_VECTOR_REFINE_FACTOR)
            return cast("list[dict[str, Any]]", query.limit(limit).to_list())

        try:
            rows = _search(vector_column_name)
        except Exception:  # noqa: BLE001
            if vector_column_name == "semantic_vector":
                raise
            rows = _search("semantic_vector")
        return [ConsolidatedNode.model_validate_json(row["payload_json"]) for row in rows]

    def iter_consolidated(self, *, page_size: int = 1000) -> Iterator[ConsolidatedNode]:
        offset = 0
        while True:
            rows = self.consolidated_table.search().limit(page_size).offset(offset).to_list()
            if not rows:
                return
            for row in rows:
                yield ConsolidatedNode.model_validate_json(row["payload_json"])
            offset += len(rows)

    def load_all_consolidated(self, limit: int | None = None) -> list[ConsolidatedNode]:
        if limit is not None:
            rows = self.consolidated_table.search().limit(limit).to_list()
            return [ConsolidatedNode.model_validate_json(row["payload_json"]) for row in rows]
        return list(self.iter_consolidated())

    def consolidated_count(self) -> int:
        return int(self.consolidated_table.count_rows())


# How much of `fired_recent` survives a tick. `MESH_SUBSTRATE.md` calls the field
# a "rolling window counter" and never says how long the window is, so this is a
# free parameter with no measurement behind it — stated rather than buried,
# because 1/(1-γ) ticks is the effective window and the tick itself has no
# schedule (PHX-1100: `run_minimal_tick`'s only caller is the CLI).
#
# Nothing reads `fired_recent` yet. What unblocks tier promotion is `fired_total`,
# which has no window and no free parameter. This exists because the field is in
# the doctrine's schema and leaving it at 0 while writing its sibling would be a
# second version of the gap PHX-1101 closes.
DEFAULT_FIRED_RECENT_DECAY = 0.9


def merge_node_firings(
    nodes: list[ConsolidatedNode],
    rows: list[dict[str, Any]],
    *,
    recent_decay: float = DEFAULT_FIRED_RECENT_DECAY,
) -> tuple[list[ConsolidatedNode], int, int]:
    """Fold recorded passes into the firing counters. Returns (nodes, touched, passes).

    The dual of :func:`merge_edge_deltas` for nodes, and deliberately the same
    shape: a pure function over a list, so the arithmetic is testable without a
    store and the IO stays in the tick.

    ``fired_total`` counts passes in which the node reached the working set.
    ``fired_recent`` is the same count under exponential forgetting, applied to
    **every** node and not only the ones that fired — otherwise a node that stops
    firing keeps its old recency for ever, which is the opposite of what a rolling
    window means.

    ``last_fired_at`` moves only for nodes that actually fired, and only forward:
    passes can be drained out of order, and a stale sidecar must not walk a
    timestamp backwards.
    """
    counts: dict[str, int] = {}
    latest: dict[str, datetime] = {}
    for row in rows:
        try:
            at = datetime.fromisoformat(str(row.get("at")))
        except (TypeError, ValueError):
            at = datetime.now(UTC)
        for node_id in row.get("node_ids") or []:
            key = str(node_id)
            counts[key] = counts.get(key, 0) + 1
            if key not in latest or at > latest[key]:
                latest[key] = at

    touched = 0
    out: list[ConsolidatedNode] = []
    for node in nodes:
        fired = counts.get(str(node.id), 0)
        update: dict[str, Any] = {
            "fired_total": node.fired_total + fired,
            # **Floor, not round.** The schema types this as an int, and an
            # integer cannot carry the tail of an exponential: with the default
            # decay, `round(1 * 0.9)` is 1, so a node that fired once would sit at
            # `fired_recent = 1` for ever and the field would never forget
            # anything — the exact failure it exists to avoid. Flooring makes the
            # decay terminate: 45 reaches 0 in about forty ticks, 1 in one.
            "fired_recent": int(node.fired_recent * recent_decay) + fired,
        }
        if fired:
            touched += 1
            when = latest[str(node.id)]
            if when > node.last_fired_at:
                update["last_fired_at"] = when
        if (
            update["fired_total"] == node.fired_total
            and update["fired_recent"] == node.fired_recent
        ):
            out.append(node)
            continue
        out.append(node.model_copy(update=update))
    return out, touched, len(rows)
