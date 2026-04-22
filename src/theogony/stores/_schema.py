"""
Cypher constants for :class:`Neo4jKnowledgeStore` (Plan §3.1a).

Single source of truth for the Neo4j schema. Every statement is
**verbatim** from Plan §3.1a's Cypher blocks — copying, not
paraphrasing, was Daedalus' explicit instruction in the E7 brief.
A future schema change is one git diff in this file.

Schema is **Edition-agnostic** (runs on Neo4j Community + Enterprise).
Property-existence constraints (``REQUIRE … IS NOT NULL``) are
intentionally absent — they are Enterprise-only and Pydantic-enforced
one layer up (Plan §3.1a edition note, §9.5/§9.5a deterministic IDs:
``compute_node_id`` and ``compute_edge_id`` post-validators on
``KnowledgeNode`` / ``KnowledgeEdge`` guarantee non-empty IDs;
``KnowledgeEdge.relation_type`` is a required field). Hesiod
escalation 2026-04-19 → Option A.

Statement order matters: constraints first (so indexes attach to a
constraint-backed property where applicable), then range indexes,
then the HNSW vector index. Every statement is idempotent
(``IF NOT EXISTS``) so reconnecting against an existing database
is a clean no-op — see :meth:`Neo4jKnowledgeStore._ensure_schema`.

The ``vector.dimensions`` value in the HNSW index is templated from
``Settings.embedding.dim`` (passed to the store constructor) so a
future BGE-large or OpenAI 3-small swap is a one-line change. The
template is intentionally a Python f-string interpolation, not a
Cypher parameter — Neo4j's ``CREATE INDEX`` syntax does not accept
parameters in the ``OPTIONS`` block.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constraints + range indexes — verbatim from Plan §3.1a
# ---------------------------------------------------------------------------

#: Uniqueness constraints. One per label. Property-existence constraints
#: live one layer up (Pydantic validators) — see module docstring.
CONSTRAINT_CYPHER: tuple[str, ...] = (
    """
    CREATE CONSTRAINT knowledge_node_id_unique IF NOT EXISTS
      FOR (n:KnowledgeNode) REQUIRE n.id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT relation_id_unique IF NOT EXISTS
      FOR ()-[r:RELATION]-() REQUIRE r.id IS UNIQUE
    """,
)


#: Range indexes — ten on :KnowledgeNode, three on [:RELATION] = thirteen total
#: (Plan §3.1a + cluster + pheromone indexes). Each has one named consumer documented in
#: the Plan's table comments above the Cypher block.
RANGE_INDEX_CYPHER: tuple[str, ...] = (
    # Node side — 10 indexes.
    """
    CREATE INDEX knowledge_node_label IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.label)
    """,
    """
    CREATE INDEX knowledge_node_node_type IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.node_type)
    """,
    """
    CREATE INDEX knowledge_node_layer IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.layer)
    """,
    """
    CREATE INDEX knowledge_node_wikidata IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.wikidata_id)
    """,
    """
    CREATE INDEX knowledge_node_resolution_tier IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.resolution_tier)
    """,
    """
    CREATE INDEX knowledge_node_manual_resolution IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.manual_resolution_needed)
    """,
    """
    CREATE INDEX knowledge_node_vitality IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.vitality)
    """,
    """
    CREATE INDEX knowledge_node_last_accessed IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.last_accessed)
    """,
    """
    CREATE INDEX knowledge_node_cluster_id IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.cluster_id)
    """,
    """
    CREATE INDEX knowledge_node_cluster_label IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.cluster_label)
    """,
    # Edge side — 3 indexes.
    """
    CREATE INDEX relation_relation_type IF NOT EXISTS
      FOR ()-[r:RELATION]-() ON (r.relation_type)
    """,
    """
    CREATE INDEX relation_weight IF NOT EXISTS
      FOR ()-[r:RELATION]-() ON (r.weight)
    """,
    """
    CREATE INDEX relation_last_traversed IF NOT EXISTS
      FOR ()-[r:RELATION]-() ON (r.last_traversed)
    """,
)


# ---------------------------------------------------------------------------
# HNSW vector index — templated from embedding_dim (Plan §3.1a)
# ---------------------------------------------------------------------------


def vector_index_cypher(embedding_dim: int) -> str:
    """Render the HNSW vector-index DDL with the configured dimension.

    Verbatim from Plan §3.1a except the integer ``vector.dimensions``,
    which is interpolated from the constructor argument so a future
    embedding-model swap (BGE-large / OpenAI 3-small / PHX-0005) is
    a single integer change. ``cosine`` is hard-coded because BGE-small
    is cosine-trained — Plan §3.1a explicitly calls an ``ip``-similarity
    index against a cosine-normalised model "a foot-gun".
    """
    if embedding_dim <= 0:
        raise ValueError(f"embedding_dim must be positive; got {embedding_dim}")
    return f"""
    CREATE VECTOR INDEX knowledge_node_embedding IF NOT EXISTS
      FOR (n:KnowledgeNode) ON (n.embedding)
      OPTIONS {{
        indexConfig: {{
          `vector.dimensions`: {embedding_dim},
          `vector.similarity_function`: 'cosine'
        }}
      }}
    """


# ---------------------------------------------------------------------------
# Bootstrap helper — what _ensure_schema executes in order
# ---------------------------------------------------------------------------


def all_schema_statements(embedding_dim: int) -> tuple[str, ...]:
    """Return every DDL statement, in execution order, for one bootstrap call.

    Order: constraints → range indexes → vector index. Statement order
    is documented at module top: constraints first so any property
    backed by a constraint exists before its index targets it.
    """
    return (
        *CONSTRAINT_CYPHER,
        *RANGE_INDEX_CYPHER,
        vector_index_cypher(embedding_dim),
    )


__all__ = [
    "CONSTRAINT_CYPHER",
    "RANGE_INDEX_CYPHER",
    "all_schema_statements",
    "vector_index_cypher",
]
