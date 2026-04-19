"""
In-memory KnowledgeStore implementation.

Used for tests and dev runs. All nodes/edges live in dicts keyed by id;
no persistence, no on-disk indexes, no concurrency control beyond
asyncio's single-event-loop guarantee.

Per Plan §2.2 this is the **architectural lever** of Generation 1: it
lets the upper layers (extraction, retrieval, OneirosWorker) be
developed and tested without a Neo4j container running, and it forces
the ``KnowledgeStore`` Protocol to be a real contract — the
parametrised contract suite in ``tests/test_store_contract.py``
exercises both stores with the same assertions.

Suitable scale: a single Project Gutenberg book (~10k nodes, ~10k
edges). Vector search is O(n) cosine over all embeddings, traversal
is BFS — both fine for that range.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import AsyncIterator, Sequence

from theogony.core.model import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    KnowledgeEdge,
    KnowledgeNode,
    Layer,
    ScoreUpdate,
)
from theogony.core.store import Path, ScoredNode


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity with safe fallback to 0.0.

    Returns 0.0 (rather than raising) when either vector is empty,
    when dimensions disagree, or when either norm is zero. Storing
    nodes without embeddings is a legitimate state during ingest;
    a similarity query against them should miss, not crash.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryKnowledgeStore:
    """Pure-Python ``KnowledgeStore`` for tests and small dev runs.

    Concurrency: safe for single-event-loop async use. Concurrent
    mutation from multiple threads is undefined behaviour; not a Gen 1
    concern (Plan §3.5: pure asyncio, no threads).
    """

    def __init__(self) -> None:
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        self._outgoing: dict[str, set[str]] = {}  # node_id -> outgoing edge_ids
        self._incoming: dict[str, set[str]] = {}  # node_id -> incoming edge_ids
        self._clusters: dict[str, set[str]] = {}  # cluster_id -> node_ids

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
        candidates: list[tuple[float, KnowledgeNode]] = []
        for node in self._nodes.values():
            # Nodes without embeddings cannot be similarity-ranked, so
            # they never appear in vector_search results — matches the
            # Neo4j HNSW semantic (only indexed nodes are returned).
            # The contract suite asserts this exclusion across both
            # backends.
            if not node.embedding:
                continue
            if layer is not None and node.layer != layer:
                continue
            if node_types is not None and node.node_type not in node_types:
                continue
            if min_confidence is not None and node.scores.confidence < min_confidence:
                continue
            score = _cosine(embedding, node.embedding)
            candidates.append((score, node))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [ScoredNode(node=n, score=s) for s, n in candidates[:k]]

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
        if start_id not in self._nodes:
            return []
        paths: list[Path] = []
        # Each queue entry: (current_id, accumulated_nodes, accumulated_edges,
        # total_weight, depth). Cycle prevention via the per-path node-set.
        queue: deque[tuple[str, list[KnowledgeNode], list[KnowledgeEdge], float, int]] = deque()
        queue.append((start_id, [self._nodes[start_id]], [], 1.0, 0))
        while queue:
            current_id, path_nodes, path_edges, total_weight, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge_id in self._outgoing.get(current_id, set()):
                edge = self._edges[edge_id]
                if edge.weight < min_weight:
                    continue
                if relation_types is not None and edge.relation_type not in relation_types:
                    continue
                target_id = edge.target_id
                if target_id not in self._nodes:
                    continue
                if any(n.id == target_id for n in path_nodes):
                    continue
                new_nodes = [*path_nodes, self._nodes[target_id]]
                new_edges = [*path_edges, edge]
                new_weight = total_weight * edge.weight
                paths.append(Path(nodes=new_nodes, edges=new_edges, total_weight=new_weight))
                queue.append((target_id, new_nodes, new_edges, new_weight, depth + 1))
        return paths

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
        """Vector seed + graph expansion + dedupe (Plan §4.2).

        Algorithm:
            1. Vector search for k seeds (filtered by `layer`).
            2. For each seed, traverse up to `hops` steps following
               edges with weight >= `min_weight`.
            3. Score each discovered node as
               `seed_similarity * product_of_path_weights`.
            4. Dedupe by node id, keeping the maximum score.
            5. Return top-k.

        This is intentionally simple. The plan calls out richer
        re-ranking (vector similarity at each hop) as a Gen 2 concern.
        """
        seeds = await self.vector_search(embedding, k=k, layer=layer)
        scored: dict[str, float] = {sn.node.id: sn.score for sn in seeds}
        for seed in seeds:
            paths = await self.traverse(seed.node.id, max_depth=hops, min_weight=min_weight)
            for path in paths:
                if not path.nodes:
                    continue
                last = path.nodes[-1]
                if layer is not None and last.layer != layer:
                    continue
                discounted = seed.score * path.total_weight
                if last.id not in scored or scored[last.id] < discounted:
                    scored[last.id] = discounted
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [
            ScoredNode(node=self._nodes[node_id], score=score)
            for node_id, score in ranked[:k]
            if node_id in self._nodes
        ]

    # -------------------------------------------------------------------------
    # Node and edge access
    # -------------------------------------------------------------------------

    async def upsert_node(self, node: KnowledgeNode) -> str:
        existing = self._nodes.get(node.id)
        if existing is not None and existing.cluster_id and existing.cluster_id != node.cluster_id:
            self._clusters.get(existing.cluster_id, set()).discard(existing.id)
        self._nodes[node.id] = node
        if node.cluster_id:
            self._clusters.setdefault(node.cluster_id, set()).add(node.id)
        self._outgoing.setdefault(node.id, set())
        self._incoming.setdefault(node.id, set())
        return node.id

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        existing = self._edges.get(edge.id)
        if existing is not None:
            self._outgoing.get(existing.source_id, set()).discard(existing.id)
            self._incoming.get(existing.target_id, set()).discard(existing.id)
        self._edges[edge.id] = edge
        self._outgoing.setdefault(edge.source_id, set()).add(edge.id)
        self._incoming.setdefault(edge.target_id, set()).add(edge.id)

    async def batch_upsert_nodes(self, nodes: Sequence[KnowledgeNode]) -> list[str]:
        # PHX-0046: InMemory has no per-call I/O, so a per-node loop is
        # already optimal — the contract is identical to the Neo4j
        # UNWIND override (idempotent, ordered, returns ids in input
        # order). Tests in tests/test_store_contract.py exercise both
        # backends through the same assertions.
        return [await self.upsert_node(n) for n in nodes]

    async def batch_upsert_edges(self, edges: Sequence[KnowledgeEdge]) -> None:
        for edge in edges:
            await self.upsert_edge(edge)

    async def get_edges_among(
        self,
        node_ids: Sequence[str],
        min_weight: float = 0.0,
    ) -> list[KnowledgeEdge]:
        # PHX-0050: in-memory has no I/O cost, a set-membership filter
        # over self._edges is already optimal. The contract — return
        # only edges where both endpoints are in node_ids and
        # weight >= min_weight — is identical to the Neo4j override.
        if not node_ids:
            return []
        ids = set(node_ids)
        return [
            e
            for e in self._edges.values()
            if e.source_id in ids and e.target_id in ids and e.weight >= min_weight
        ]

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        return self._nodes.get(node_id)

    async def get_neighborhood(
        self,
        node_id: str,
        depth: int = 2,
        min_weight: float = 0.3,
    ) -> Constellation:
        """BFS in both directions, collecting slim DTOs per Plan §9.1."""
        if node_id not in self._nodes:
            return Constellation(query=f"node:{node_id}")
        visited_nodes: set[str] = {node_id}
        visited_edges: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge_id in self._outgoing.get(current_id, set()):
                edge = self._edges[edge_id]
                if edge.weight < min_weight:
                    continue
                visited_edges.add(edge.id)
                if edge.target_id not in visited_nodes and edge.target_id in self._nodes:
                    visited_nodes.add(edge.target_id)
                    queue.append((edge.target_id, current_depth + 1))
            for edge_id in self._incoming.get(current_id, set()):
                edge = self._edges[edge_id]
                if edge.weight < min_weight:
                    continue
                visited_edges.add(edge.id)
                if edge.source_id not in visited_nodes and edge.source_id in self._nodes:
                    visited_nodes.add(edge.source_id)
                    queue.append((edge.source_id, current_depth + 1))
        nodes = [
            ConstellationNode.from_knowledge_node(self._nodes[nid])
            for nid in visited_nodes
            if nid in self._nodes
        ]
        edges = [ConstellationEdge.from_knowledge_edge(self._edges[eid]) for eid in visited_edges]
        suggested = [self._nodes[nid].source_ref for nid in visited_nodes if nid in self._nodes]
        return Constellation(
            query=f"node:{node_id}",
            nodes=nodes,
            edges=edges,
            suggested_sources=suggested,
        )

    async def delete_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            return
        node = self._nodes.pop(node_id)
        if node.cluster_id and node.cluster_id in self._clusters:
            self._clusters[node.cluster_id].discard(node_id)
        for edge_id in list(self._outgoing.get(node_id, set())):
            edge = self._edges.pop(edge_id, None)
            if edge is not None:
                self._incoming.get(edge.target_id, set()).discard(edge.id)
        for edge_id in list(self._incoming.get(node_id, set())):
            edge = self._edges.pop(edge_id, None)
            if edge is not None:
                self._outgoing.get(edge.source_id, set()).discard(edge.id)
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)

    # -------------------------------------------------------------------------
    # Lifecycle management
    # -------------------------------------------------------------------------

    async def promote(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].layer = Layer.MNEME

    async def degrade(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].layer = Layer.EPHEMERA

    async def update_scores(self, node_id: str, scores: dict[str, float]) -> None:
        if node_id not in self._nodes:
            return
        node_scores = self._nodes[node_id].scores
        for key, value in scores.items():
            if hasattr(node_scores, key):
                setattr(node_scores, key, value)

    async def batch_update_scores(self, updates: Sequence[ScoreUpdate]) -> None:
        # PHX-0048: in-process per-node loop. Same partial-update
        # semantics as the Neo4j override (only non-None fields are
        # written), missing-id silent no-op (matches update_scores).
        #
        # ``vitality`` is a derived value on NodeScores (computed by
        # ``NodeScores.vitality()`` from the four component scores).
        # The Neo4j store carries a denormalised ``vitality`` column
        # which the bulk write also updates — InMemory has no such
        # column; the four component scores are the source of truth
        # and ``vitality()`` recomputes on read. We therefore accept
        # ``upd.vitality`` for cross-backend symmetry but do nothing
        # with it: any downstream consumer that needs the vitality
        # number calls ``node.scores.vitality()`` and gets the
        # canonical value.
        for upd in updates:
            node = self._nodes.get(upd.node_id)
            if node is None:
                continue
            for field in ("confidence", "relevance", "connectivity", "freshness"):
                value = getattr(upd, field)
                if value is not None:
                    setattr(node.scores, field, value)

    async def count_neighbors_in_layer(self, layer: Layer) -> dict[str, int]:
        # PHX-0050 / E8.5: bulk degree map. The InMemory store keeps
        # outgoing/incoming sets per node id (E1), so this is a
        # constant-time lookup per node — same answer the Neo4j
        # ``OPTIONAL MATCH`` would give. Cross-layer edges count
        # toward the in-layer node's degree (Plan §5 E8.5
        # ``connectivity is symmetric``).
        result: dict[str, int] = {}
        for node_id, node in self._nodes.items():
            if node.layer != layer:
                continue
            outgoing = len(self._outgoing.get(node_id, set()))
            incoming = len(self._incoming.get(node_id, set()))
            result[node_id] = outgoing + incoming
        return result

    # -------------------------------------------------------------------------
    # Cluster management
    # -------------------------------------------------------------------------

    async def get_cluster_centroid(self, cluster_id: str) -> list[float]:
        members = self._clusters.get(cluster_id, set())
        embeddings = [
            self._nodes[mid].embedding
            for mid in members
            if mid in self._nodes and self._nodes[mid].embedding
        ]
        if not embeddings:
            return []
        dim = len(embeddings[0])
        if any(len(e) != dim for e in embeddings):
            return []
        n = len(embeddings)
        return [sum(e[i] for e in embeddings) / n for i in range(dim)]

    async def assign_cluster(self, node_id: str, cluster_id: str) -> None:
        if node_id not in self._nodes:
            return
        node = self._nodes[node_id]
        if node.cluster_id and node.cluster_id in self._clusters:
            self._clusters[node.cluster_id].discard(node_id)
        node.cluster_id = cluster_id
        self._clusters.setdefault(cluster_id, set()).add(node_id)

    # -------------------------------------------------------------------------
    # Bulk operations
    # -------------------------------------------------------------------------

    async def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]:
        for node in list(self._nodes.values()):
            if node.layer == layer:
                yield node

    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None:
        async for node in nodes:
            await self.upsert_node(node)

    # -------------------------------------------------------------------------
    # Resolution-honesty queries (Plan §9.6)
    # -------------------------------------------------------------------------

    async def list_pending_resolution(
        self,
        layer: Layer | None = None,
        limit: int = 100,
    ) -> list[KnowledgeNode]:
        candidates = [
            n
            for n in self._nodes.values()
            if n.manual_resolution_needed and (layer is None or n.layer == layer)
        ]
        candidates.sort(key=lambda n: n.created_at, reverse=True)
        return candidates[:limit]

    async def resolve_node(
        self,
        node_id: str,
        wikidata_id: str | None,
    ) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if wikidata_id:
            node.external_ids = {**node.external_ids, "wikidata": wikidata_id}
            node.resolution_tier = 1
        node.manual_resolution_needed = False
        return True

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    async def count_nodes(self, layer: Layer | None = None) -> int:
        if layer is None:
            return len(self._nodes)
        return sum(1 for n in self._nodes.values() if n.layer == layer)

    async def health(self) -> dict[str, object]:
        return {
            "backend": "in_memory",
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "clusters": len(self._clusters),
            "ephemera_nodes": sum(1 for n in self._nodes.values() if n.layer == Layer.EPHEMERA),
            "mneme_nodes": sum(1 for n in self._nodes.values() if n.layer == Layer.MNEME),
            "pending_resolution": sum(
                1 for n in self._nodes.values() if n.manual_resolution_needed
            ),
        }
