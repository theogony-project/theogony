"""
KnowledgeStore protocol — the abstract interface to the Chronik's storage layer.

All access to the Chronik goes through this interface. This allows the storage
backend to be replaced (Neo4j today, custom engine tomorrow) without changing
any other part of the system.

Implementations must live in src/theogony/stores/.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from theogony.core.model import (
    Constellation,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
)


class ScoredNode(BaseModel):
    """Result of a similarity search: a node plus its (normalised) score.

    Concrete pydantic class rather than a typing.Protocol — every store
    implementation returns the same shape, so a single value type is
    simpler to reason about than a structural promise. Tests assert
    structure here once, not per-backend.
    """

    node: KnowledgeNode
    score: float = Field(ge=-1.0, le=1.0)


class Path(BaseModel):
    """A single path through the graph, returned by :meth:`KnowledgeStore.traverse`.

    ``nodes[0]`` is the start node. ``nodes[i+1]`` is reached from
    ``nodes[i]`` via ``edges[i]``. ``total_weight`` is the product of
    the edges' weights — paths whose product falls below
    ``min_weight^len(edges)`` should not be returned by traversal.
    """

    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    total_weight: float = Field(ge=0.0, le=1.0)


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

    async def batch_upsert_nodes(self, nodes: Sequence[KnowledgeNode]) -> list[str]:
        """Insert or update a batch of nodes. Returns the node IDs in order.

        PHX-0046 perf path: backends with bulk-write APIs (Neo4j UNWIND
        + MERGE; future DuckDB COPY) override this for one-round-trip
        semantics. The InMemory backend implements it as a per-node
        ``upsert_node`` loop — same ordering, same idempotency, just
        no perf win.

        Pipelines (``IngestionPipeline.run``) chunk their final node
        list into batches of ``Settings.store.batch_size`` and call
        this method once per chunk; on Neo4j that collapses N
        round-trips to ⌈N/batch_size⌉.
        """
        ...

    async def batch_upsert_edges(self, edges: Sequence[KnowledgeEdge]) -> None:
        """Insert or update a batch of edges. PHX-0046 perf path; see batch_upsert_nodes."""
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

    def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        """Export all nodes in a given memory layer. Used by the Phoenix process.

        This is an **async generator** — implementations are
        ``async def export_layer(...) -> AsyncIterator[KnowledgeNode]``
        with ``yield`` in the body. Callers do NOT ``await``;
        they iterate via ``async for n in store.export_layer(...)``.
        The Protocol declaration is intentionally a sync ``def``
        because that is what mypy sees from outside an async
        generator (the function returns the iterator immediately).
        """
        ...

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        """Bulk-import nodes. Used by the Phoenix process after distillation."""
        ...

    # -------------------------------------------------------------------------
    # Resolution-honesty queries (Plan §9.6)
    # -------------------------------------------------------------------------

    async def list_pending_resolution(
        self,
        layer: Layer | None = None,
        limit: int = 100,
    ) -> list[KnowledgeNode]:
        """
        Nodes with ``manual_resolution_needed=True``.

        Backs ``theogony resolve --list``: the human-in-the-loop surface
        for the §3.4 honest-failure path. Implementations MUST NOT
        return tier-1+ nodes — the model invariant guarantees those
        cannot have ``manual_resolution_needed=True``, but stores SHOULD
        filter explicitly rather than rely on the invariant.

        Ordering: most-recently created first, so newly-failed mentions
        bubble up for review.
        """
        ...

    async def resolve_node(
        self,
        node_id: str,
        wikidata_id: str | None,
    ) -> bool:
        """Resolve one ``manual_resolution_needed=True`` node by hand.

        Used by ``theogony resolve <mention>`` (Plan §3.4) to record an
        operator's pick after the automated five-stage resolver fell
        through to tier 0. Two effects on the node, applied atomically
        from the store's perspective (one upsert / one Cypher SET):

        * If ``wikidata_id`` is non-empty: set
          ``external_ids["wikidata"] = wikidata_id`` and bump
          ``resolution_tier`` to 1 (operator-confirmed). Clear
          ``manual_resolution_needed``.
        * If ``wikidata_id`` is None or empty string: keep the node at
          tier 0 (operator confirmed "none of the candidates fit"),
          but still clear ``manual_resolution_needed`` so it stops
          showing up in the resolve queue.

        Returns ``True`` when the node existed and was updated;
        ``False`` when the id was unknown (silent no-op semantics
        matching ``promote`` / ``update_scores``).
        """
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
