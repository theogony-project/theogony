"""Lance tables for ``chunk_nodes`` and ``consolidated_nodes``.

Per MESH_IMPLEMENTATION.md §"Nodes — LanceDB": two tables, one per node tier,
with per-vector HNSW indices on ``semantic_vector`` (default) and on populated
``frame_vector`` / ``structural_vector`` / ``description_vector`` columns.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import lancedb
import pyarrow as pa

from theogony.mesh.schemas import ChunkNode, ConsolidatedNode


def _normalize_label(label: str) -> str:
    raw = label.lower().strip()
    raw = re.sub(r"'s\b", "", raw)
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


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
        seen_ids: set[str] = set()
        out: list[ConsolidatedNode] = []
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
                node = self.get_consolidated(node_id)
                if node is None:
                    continue
                seen_ids.add(node_id)
                out.append(node)
                if len(out) >= limit:
                    return out
        return out

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
                self.consolidated_table.search(
                    vector,
                    vector_column_name=vector_column_name,
                )
                .metric("cosine")
                .limit(limit)
                .to_list()
            )
        except Exception:  # noqa: BLE001
            if vector_column_name == "semantic_vector":
                raise
            rows = (
                self.consolidated_table.search(
                    vector,
                    vector_column_name="semantic_vector",
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
