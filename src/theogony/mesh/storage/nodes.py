"""Lance tables for ``chunk_nodes`` and ``consolidated_nodes``.

Per MESH_IMPLEMENTATION.md §"Nodes — LanceDB": two tables, one per node tier,
with per-vector HNSW indices on ``semantic_vector`` (default) and on populated
``frame_vector`` / ``structural_vector`` / ``description_vector`` columns.
"""

from __future__ import annotations

import lancedb
import pyarrow as pa

from theogony.mesh.schemas import ChunkNode, ConsolidatedNode


def _have_table(db: lancedb.DBConnection, name: str) -> bool:
    resp = db.list_tables()
    return name in (resp.tables or [])


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

    # ---- chunk nodes ----

    def append_chunk(self, node: ChunkNode) -> None:
        assert len(node.semantic_vector) == self.semantic_dim
        assert len(node.frame_vector) == self.frame_dim
        self.chunk_table.add(
            [
                {
                    "id": str(node.id),
                    "payload_json": node.model_dump_json(),
                    "semantic_vector": [float(x) for x in node.semantic_vector],
                    "frame_vector": [float(x) for x in node.frame_vector],
                }
            ]
        )

    def get_chunk(self, node_id: str) -> ChunkNode | None:
        rows = self.chunk_table.search().where(f'id = "{node_id}"').limit(1).to_list()
        if not rows:
            return None
        return ChunkNode.model_validate_json(rows[0]["payload_json"])

    def chunk_count(self) -> int:
        return int(self.chunk_table.count_rows())

    # ---- consolidated nodes ----

    def append_consolidated(self, node: ConsolidatedNode) -> None:
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
        self.consolidated_table.add([row])

    def get_consolidated(self, node_id: str) -> ConsolidatedNode | None:
        rows = self.consolidated_table.search().where(f'id = "{node_id}"').limit(1).to_list()
        if not rows:
            return None
        return ConsolidatedNode.model_validate_json(rows[0]["payload_json"])

    def load_all_consolidated(self, limit: int | None = None) -> list[ConsolidatedNode]:
        search = self.consolidated_table.search()
        if limit is not None:
            search = search.limit(limit)
        rows = search.to_arrow().to_pylist()
        return [ConsolidatedNode.model_validate_json(row["payload_json"]) for row in rows]

    def consolidated_count(self) -> int:
        return int(self.consolidated_table.count_rows())
