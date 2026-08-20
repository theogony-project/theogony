"""Lance tables for ``chunk_nodes`` and ``consolidated_nodes``.

Per MESH_IMPLEMENTATION.md §"Nodes — LanceDB": two tables, one per node tier,
with per-vector HNSW indices on ``semantic_vector`` (default) and on populated
``frame_vector`` / ``structural_vector`` / ``description_vector`` columns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from datetime import timedelta
from typing import Any

import lancedb
import pyarrow as pa

from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, QIDTag
from theogony.stores.lance_typing import as_vector_query


def _normalize_label(label: str) -> str:
    raw = label.lower().strip()
    raw = re.sub(r"'s\b", "", raw)
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


# A referring expression is not a name. "her father" attached to Zeus as an
# alias would pull every later "her father" onto him, and in the next passage
# that is someone else entirely — the PHX-1051 attractor, rebuilt from the other
# side. Only spans that read as proper names are kept.
_REFERRING_HEAD = re.compile(
    r"^(the|a|an|his|her|its|their|this|that|these|those|one|another|"
    r"son|daughter|father|mother|brother|sister|child|children|wife|husband)\b",
    re.IGNORECASE,
)

# Descriptions arrive alongside labels at merge time and must not become tags:
# the doctrine bounds a description at a few hundred characters, a tag is a
# keyword.
_MAX_ALIAS_CHARS = 40


def _mergeable_aliases(aliases: list[str] | None, existing: list[str]) -> list[str]:
    """Aliases worth writing onto a node when a merge discovers them.

    The eager linker learns, on every merge, that some span in the text refers to
    a node it already holds. Until now that went to an in-memory registry and
    died with the run (PHX-1071), so the substrate could not match on it the next
    time it read.

    Kept only if it reads as a proper name. A merge on "the Earth-Shaker" teaches
    the mesh a genuine alias for Poseidon; a merge on "her father" teaches it
    nothing durable and would misroute the next passage that says it.
    """
    if not aliases:
        return []
    seen = {tag.strip().lower() for tag in existing}
    out: list[str] = []
    for raw in aliases:
        alias = (raw or "").strip()
        if not alias or len(alias) > _MAX_ALIAS_CHARS:
            continue
        if not alias[:1].isupper() or _REFERRING_HEAD.match(alias):
            continue
        if alias.lower() in seen:
            continue
        seen.add(alias.lower())
        out.append(alias)
    return out


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
        self,
        node_id: str,
        *,
        qids: list[QIDTag],
        node: ConsolidatedNode | None = None,
        aliases: list[str] | None = None,
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
        new_aliases = _mergeable_aliases(aliases, node.tags)
        if not new_qids and not new_aliases:
            return node
        updated = node.model_copy(
            update={
                "qids": [*node.qids, *new_qids],
                "tags": [*node.tags, *new_aliases],
            }
        )
        self.consolidated_table.delete(f'id = "{_sql_quote(node_id)}"')
        self.consolidated_table.add([self._consolidated_row(updated)])
        if new_qids:
            self.consolidated_qid_index.add(
                [{"qid": q.qid, "node_id": str(node_id)} for q in new_qids]
            )
        if new_aliases:
            self.consolidated_label_index.add(self._label_index_rows(updated))
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
        if not vector or limit <= 0:
            return []
        try:
            rows = (
                as_vector_query(
                    self.consolidated_table.search(
                        vector,
                        vector_column_name=vector_column_name,
                    )
                )
                .metric("cosine")
                .limit(limit)
                .to_list()
            )
        except Exception:  # noqa: BLE001
            if vector_column_name == "semantic_vector":
                raise
            rows = (
                as_vector_query(
                    self.consolidated_table.search(
                        vector,
                        vector_column_name="semantic_vector",
                    )
                )
                .metric("cosine")
                .limit(limit)
                .to_list()
            )
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
