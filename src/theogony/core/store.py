"""
KnowledgeStore protocol — the abstract interface to the Chronik's storage layer.

All access to the Chronik goes through this interface. This allows the storage
backend to be replaced (Neo4j today, custom engine tomorrow) without changing
any other part of the system.

Implementations must live in src/theogony/stores/.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from theogony.core.model import (
    Constellation,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
)


class ScoredNode(Protocol):
    node: KnowledgeNode
    score: float


class Path(Protocol):
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    total_weight: float


@runtime_checkable
class KnowledgeStore(Protocol):
    """
    Abstract interface for the Chronik's storage layer.

    Implementations must support:
    - vector similarity search across embeddings
    - graph traversal along weighted, typed edges
    - combined multi-hop vector+graph search (the core retrieval operation)
    - node and edge CRUD with full provenance
    - lifecycle management (promote, degrade, delete)
    - cluster management for hierarchical organization
    - bulk export/import for the Phoenix process
    """

    # -------------------------------------------------------------------------
    # Vector search
    # -------------------------------------------------------------------------

    async def vector_search(
        self,
        embedding: list[float],
        k: int = 20,
        layer: Layer | None = None,
        node_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> list[ScoredNode]:
        """Find the k nodes most semantically similar to the given embedding."""
        ...

    # -------------------------------------------------------------------------
    # Graph traversal
    # -------------------------------------------------------------------------

    async def traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        min_weight: float = 0.3,
        relation_types: list[str] | None = None,
    ) -> list[Path]:
        """Traverse the graph from a starting node, following edges above the weight threshold."""
        ...

    # -------------------------------------------------------------------------
    # Combined retrieval — the core operation
    # -------------------------------------------------------------------------

    async def multi_hop_search(
        self,
        embedding: list[float],
        k: int = 20,
        hops: int = 3,
        min_weight: float = 0.3,
        layer: Layer | None = None,
    ) -> list[ScoredNode]:
        """
        Recursive vector+graph search.

        1. Find top-k nodes by vector similarity.
        2. From each hit, traverse the graph to depth `hops`, following
           edges above `min_weight`.
        3. From each newly discovered node, run another similarity search.
        4. Deduplicate and rank by combined score.

        This is the primary retrieval operation of the Chronik.
        """
        ...

    # -------------------------------------------------------------------------
    # Node and edge access
    # -------------------------------------------------------------------------

    async def upsert_node(self, node: KnowledgeNode) -> str:
        """Insert or update a node. Returns the node ID."""
        ...

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        """Insert or update an edge."""
        ...

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        """Retrieve a single node by ID."""
        ...

    async def get_neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        min_weight: float = 0.3,
    ) -> Constellation:
        """
        Retrieve the local graph neighborhood of a node.

        This is the foundation of the Hover-Lupe: given a node that appeared
        in an answer, return its connected context.
        """
        ...

    async def delete_node(self, node_id: str) -> None:
        """Delete a node and all its edges."""
        ...

    # -------------------------------------------------------------------------
    # Lifecycle management
    # -------------------------------------------------------------------------

    async def promote(self, node_id: str) -> None:
        """Promote a node from Ephemera to Mneme."""
        ...

    async def degrade(self, node_id: str) -> None:
        """Degrade a Mneme node back toward Ephemera or mark it for archival."""
        ...

    async def update_scores(self, node_id: str, scores: dict[str, float]) -> None:
        """Update the lifecycle scores for a node."""
        ...

    # -------------------------------------------------------------------------
    # Cluster management
    # -------------------------------------------------------------------------

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        """Return the centroid embedding for a knowledge cluster."""
        ...

    async def assign_cluster(self, node_id: str, cluster_id: str) -> None:
        """Assign a node to a knowledge cluster."""
        ...

    # -------------------------------------------------------------------------
    # Bulk operations — for the Phoenix process
    # -------------------------------------------------------------------------

    async def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        """Export all nodes in a given memory layer. Used by the Phoenix process."""
        ...

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        """Bulk-import nodes. Used by the Phoenix process after distillation."""
        ...

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    async def count_nodes(self, layer: Layer | None = None) -> int:
        """Return the number of nodes, optionally filtered by layer."""
        ...

    async def health(self) -> dict[str, object]:
        """Return a health status dict for the store."""
        ...
