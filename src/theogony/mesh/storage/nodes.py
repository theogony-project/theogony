"""Lance tables for ``chunk_nodes`` and ``consolidated_nodes``."""

from __future__ import annotations

import lancedb
import pyarrow as pa

from theogony.mesh.schemas import ChunkNode, ConsolidatedNode


def _chunk_schema(semantic_dim: int, frame_dim: int) -> pa.Schema:
    return pa.schema(
        [
            ("id", pa.string()),
            ("payload_json", pa.string()),
            ("semantic_vector", pa.list_(pa.float32(), semantic_dim)),
            ("frame_vector", pa.list_(pa.float32(), frame_dim)),
        ]
    )


def _consolidated_schema(
    semantic_dim: int,
    frame_dim: int,
    structural_dim: int,
    temporal_dim: int,
    description_dim: int,
) -> pa.Schema:
    return pa.schema(
        [
            ("id", pa.string()),
            ("payload_json", pa.string()),
            ("semantic_vector", pa.list_(pa.float32(), semantic_dim)),
            ("frame_vector", pa.list_(pa.float32(), frame_dim)),
            ("structural_vector", pa.list_(pa.float32(), structural_dim)),
            ("temporal_vector", pa.list_(pa.float32(), temporal_dim)),
            ("description_vector", pa.list_(pa.float32(), description_dim)),
        ]
    )


class MeshNodeStore:
    """Creates/opens node tables and appends rows."""

    def __init__(
        self,
        db: lancedb.DBConnection,
        *,
        semantic_dim: int,
        frame_dim: int,
        structural_dim: int = 0,
        temporal_dim: int = 0,
        description_dim: int = 0,
    ) -> None:
        self._db = db
        self.semantic_dim = semantic_dim
        self.frame_dim = frame_dim
        self.structural_dim = structural_dim
        self.temporal_dim = temporal_dim
        self.description_dim = description_dim

        c_schema = _chunk_schema(semantic_dim, frame_dim)
        if "chunk_nodes" not in db.list_tables():
            self.chunk_table = db.create_table("chunk_nodes", schema=c_schema)
        else:
            self.chunk_table = db.open_table("chunk_nodes")

        # Fixed-size optional vectors: use zero-width lists when dim is 0 (no HNSW on those).
        s_dim = structural_dim if structural_dim > 0 else 1
        t_dim = temporal_dim if temporal_dim > 0 else 1
        d_dim = description_dim if description_dim > 0 else 1
        cn_schema = _consolidated_schema(semantic_dim, frame_dim, s_dim, t_dim, d_dim)
        if "consolidated_nodes" not in db.list_tables():
            self.consolidated_table = db.create_table("consolidated_nodes", schema=cn_schema)
        else:
            self.consolidated_table = db.open_table("consolidated_nodes")

        self._struct_pad = s_dim
        self._temp_pad = t_dim
        self._desc_pad = d_dim

    def append_chunk(self, node: ChunkNode) -> None:
        if len(node.semantic_vector) != self.semantic_dim:
            raise ValueError("semantic_vector length mismatch for chunk table")
        if len(node.frame_vector) != self.frame_dim:
            raise ValueError("frame_vector length mismatch for chunk table")
        self.chunk_table.add(
            [
                {
                    "id": node.id,
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

    def consolidated_count(self) -> int:
        return int(self.consolidated_table.count_rows())

    def append_consolidated(self, node: ConsolidatedNode) -> None:
        if len(node.semantic_vector) != self.semantic_dim:
            raise ValueError("semantic_vector length mismatch")
        if len(node.frame_vector) != self.frame_dim:
            raise ValueError("frame_vector length mismatch")

        def _pad(
            v: list[float] | None,
            dim: int,
            *,
            active: bool,
        ) -> list[float]:
            if not active:
                return [0.0] * dim
            if v is None:
                return [0.0] * dim
            if len(v) != dim:
                raise ValueError("optional vector length mismatch")
            return [float(x) for x in v]

        struct_active = self.structural_dim > 0
        temp_active = self.temporal_dim > 0
        desc_active = self.description_dim > 0

        self.consolidated_table.add(
            [
                {
                    "id": node.id,
                    "payload_json": node.model_dump_json(),
                    "semantic_vector": [float(x) for x in node.semantic_vector],
                    "frame_vector": [float(x) for x in node.frame_vector],
                    "structural_vector": _pad(
                        node.structural_vector, self._struct_pad, active=struct_active
                    ),
                    "temporal_vector": _pad(
                        node.temporal_vector,
                        self._temp_pad,
                        active=temp_active,
                    ),
                    "description_vector": _pad(
                        node.description_vector, self._desc_pad, active=desc_active
                    ),
                }
            ]
        )

    def maybe_create_vector_indices(self, *, min_rows: int = 64) -> dict[str, str]:
        """Create IVF-HNSW indices when tables are large enough; otherwise skip."""
        out: dict[str, str] = {}
        for name, table, col in (
            ("chunk_nodes", self.chunk_table, "semantic_vector"),
            ("chunk_nodes_frame", self.chunk_table, "frame_vector"),
            ("consolidated_nodes", self.consolidated_table, "semantic_vector"),
        ):
            if table.count_rows() < min_rows:
                out[name + ":" + col] = "skipped_small_corpus"
                continue
            try:
                table.create_index(
                    vector_column_name=col,
                    index_type="IVF_HNSW_SQ",
                    metric="cosine",
                )
                out[name + ":" + col] = "created"
            except Exception as exc:  # noqa: BLE001 — best-effort index creation
                out[name + ":" + col] = f"failed:{exc!s}"
        return out
