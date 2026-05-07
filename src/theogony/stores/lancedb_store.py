"""
LanceDB implementation of the KnowledgeStore protocol.

This store is the persistent, append-only cold storage for the Neural Vector Mesh.
It stores nodes, edges, and provenance data in columnar format.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import lancedb
import pyarrow as pa

from theogony.core.model import (
    ClusterSummary,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    ScoreUpdate,
)
from theogony.core.tensor_engine import TensorMeshEngine


class LanceDBKnowledgeStore:
    """
    LanceDB-backed persistent storage for the Chronicle.
    """

    def __init__(self, db_path: Path | str, embedding_dim: int = 384):
        self.db_path = str(db_path)
        self.db = lancedb.connect(self.db_path)
        self.embedding_dim = embedding_dim

        # Define schemas
        self.node_schema = pa.schema(
            [
                ("id", pa.string()),
                ("vector", pa.list_(pa.float32(), self.embedding_dim)),
                ("payload", pa.string()),  # JSON serialized KnowledgeNode
                ("created_at", pa.timestamp("us")),
            ]
        )

        self.edge_schema = pa.schema(
            [
                ("id", pa.string()),
                ("source_id", pa.string()),
                ("target_id", pa.string()),
                ("relation_type", pa.string()),
                ("weight", pa.float32()),
                ("hebbian_strength", pa.float32()),
                ("payload", pa.string()),  # JSON serialized KnowledgeEdge
                ("created_at", pa.timestamp("us")),
            ]
        )

        # Create tables if they don't exist
        if "nodes" not in self.db.table_names():
            self.nodes_table = self.db.create_table("nodes", schema=self.node_schema)
        else:
            self.nodes_table = self.db.open_table("nodes")

        if "edges" not in self.db.table_names():
            self.edges_table = self.db.create_table("edges", schema=self.edge_schema)
        else:
            self.edges_table = self.db.open_table("edges")

    async def batch_upsert_nodes(self, nodes: Sequence[KnowledgeNode]) -> list[str]:
        """Append nodes to the store."""
        if not nodes:
            return []

        data = []
        for node in nodes:
            # Ensure embedding is the correct dimension, pad with zeros if necessary
            emb = node.embedding
            if not emb:
                emb = [0.0] * self.embedding_dim
            elif len(emb) < self.embedding_dim:
                emb = emb + [0.0] * (self.embedding_dim - len(emb))
            elif len(emb) > self.embedding_dim:
                emb = emb[: self.embedding_dim]

            data.append(
                {
                    "id": node.id,
                    "vector": emb,
                    "payload": node.model_dump_json(),
                    "created_at": node.created_at,
                }
            )

        self.nodes_table.add(data)
        return [n.id for n in nodes]

    async def batch_upsert_edges(self, edges: Sequence[KnowledgeEdge]) -> None:
        """Append edges to the store."""
        if not edges:
            return

        data = []
        for edge in edges:
            data.append(
                {
                    "id": edge.id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "relation_type": edge.relation_type,
                    "weight": edge.weight,
                    "hebbian_strength": edge.hebbian_strength,
                    "payload": edge.model_dump_json(),
                    "created_at": edge.created_at,
                }
            )

        self.edges_table.add(data)

    async def upsert_node(self, node: KnowledgeNode) -> str:
        await self.batch_upsert_nodes([node])
        return node.id

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        await self.batch_upsert_edges([edge])

    # --- Methods required by the protocol but not fully implemented for MVP ---

    async def vector_search(
        self, embedding, k=20, layer=None, node_types=None, min_confidence=None
    ):
        raise NotImplementedError("Use spreading_activation instead.")

    async def traverse(
        self, start_id, max_depth=3, min_weight=0.3, relation_types=None, *, pheromone_mode="follow"
    ):
        raise NotImplementedError("Use spreading_activation instead.")

    async def multi_hop_search(
        self, embedding, k=20, hops=3, min_weight=0.3, layer=None, *, pheromone_mode="follow"
    ):
        raise NotImplementedError("Use spreading_activation instead.")

    async def get_edges_among(self, node_ids, min_weight=0.0):
        return []

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        result = self.nodes_table.search().where(f"id = '{node_id}'").limit(1).to_list()
        if result:
            return KnowledgeNode.model_validate_json(result[0]["payload"])
        return None

    async def get_neighborhood(self, node_id, depth=2, min_weight=0.3, *, pheromone_mode="follow"):
        raise NotImplementedError("Use spreading_activation instead.")

    async def delete_node(self, node_id: str) -> None:
        pass

    async def promote(self, node_id: str) -> None:
        pass

    async def degrade(self, node_id: str) -> None:
        pass

    async def update_scores(self, node_id: str, scores: dict[str, float]) -> None:
        pass

    async def batch_update_scores(self, updates: Sequence[ScoreUpdate]) -> None:
        pass

    async def mark_self_referential(self, node_ids: Sequence[str], run_id: str) -> None:
        pass

    async def count_neighbors_in_layer(self, layer: Layer) -> dict[str, int]:
        return {}

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        return []

    async def assign_cluster(self, node_id, cluster_id, *, cluster_label=None) -> None:
        pass

    async def list_clusters(self) -> list[ClusterSummary]:
        return []

    async def get_cluster_members(self, cluster_id: str) -> AsyncIterator[str]:
        yield ""

    async def batch_bump_edges(self, edge_ids, *, delta, ts) -> None:
        pass

    async def list_aged_pheromone_edges(self, *, horizon, epsilon) -> list[tuple[str, float]]:
        return []

    async def batch_update_pheromone_deltas(self, updates) -> None:
        pass

    async def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        yield KnowledgeNode(label="dummy", source_ref=None)

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        pass

    async def list_pending_resolution(self, layer=None, limit=100) -> list[KnowledgeNode]:
        return []

    async def resolve_node(self, node_id: str, wikidata_id: str | None) -> bool:
        return False

    async def count_nodes(self, layer=None) -> int:
        return len(self.nodes_table)

    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def list_low_connectivity_nodes(
        self, *, layer, max_edges, batch_size
    ) -> list[KnowledgeNode]:
        return []

    async def find_similar_nodes_in_band(
        self, embedding, *, band_low, band_high, exclude_ids, top_k, layer=None
    ):
        return []

    async def update_depth_band(self, node_id, depth_band, *, layer=None) -> None:
        pass

    async def list_nodes_by_source_identifier(
        self, *, identifier, exclude_id=None
    ) -> list[KnowledgeNode]:
        return []

    # --- New Spreading Activation Interface ---

    def load_into_tensor_engine(self, engine: TensorMeshEngine) -> None:
        """
        Loads the entire graph from LanceDB into the PyTorch TensorMeshEngine.
        This translates the cold storage into the hot VRAM CSR format.
        """
        nodes_df = self.nodes_table.to_pandas()
        edges_df = self.edges_table.to_pandas()

        if len(nodes_df) == 0:
            engine.load_from_arrays([], [], [], [], [], [], [])
            return

        # Map UUIDs to integer indices for CSR
        node_id_to_idx = {node_id: idx for idx, node_id in enumerate(nodes_df["id"])}

        # Extract embeddings
        node_embeddings = nodes_df["vector"].tolist()

        # Build CSR arrays
        N = len(nodes_df)
        row_counts = [0] * N

        valid_edges = []
        for _, edge in edges_df.iterrows():
            src_id = edge["source_id"]
            tgt_id = edge["target_id"]
            if src_id in node_id_to_idx and tgt_id in node_id_to_idx:
                src_idx = node_id_to_idx[src_id]
                tgt_idx = node_id_to_idx[tgt_id]
                valid_edges.append(
                    (
                        src_idx,
                        tgt_idx,
                        edge["relation_type"],
                        edge["weight"],
                        edge["hebbian_strength"],
                    )
                )
                row_counts[src_idx] += 1

        # Sort edges by source index to build CSR
        valid_edges.sort(key=lambda x: x[0])

        row_ptr = [0] * (N + 1)
        for i in range(N):
            row_ptr[i + 1] = row_ptr[i] + row_counts[i]

        col_idx = [e[1] for e in valid_edges]
        base_weight = [e[3] for e in valid_edges]
        hebbian_strength = [e[4] for e in valid_edges]

        # Build a simple codebook for relation types
        unique_relations = list(set(e[2] for e in valid_edges))
        relation_to_idx = {rel: idx for idx, rel in enumerate(unique_relations)}
        edge_type_idx = [relation_to_idx[e[2]] for e in valid_edges]

        # Mock codebook embeddings (random vectors for now, should be learned)
        import random

        edge_codebook = [
            [random.uniform(-1, 1) for _ in range(self.embedding_dim)] for _ in unique_relations
        ]
        if not edge_codebook:
            edge_codebook = [[0.0] * self.embedding_dim]  # Fallback

        engine.load_from_arrays(
            row_ptr=row_ptr,
            col_idx=col_idx,
            node_embeddings=node_embeddings,
            edge_type_idx=edge_type_idx,
            edge_codebook=edge_codebook,
            base_weight=base_weight,
            hebbian_strength=hebbian_strength,
        )
