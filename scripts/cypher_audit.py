"""
PHX-0042 — Cypher query-plan audit harness for Neo4jKnowledgeStore hot paths.

Loads a synthetic ~2000-node fixture into a running Neo4j (the
docker-compose default at ``localhost:7687`` works), runs PROFILE on
each of the five Plan §3.1a hot paths the read-side cares about,
and prints a Markdown-shaped report fragment to stdout. Talos pipes
the output into ``docs/cypher_audit/<date>_post_e9.md`` with one
manual verdict per section.

Run-once script. Not part of the test suite — the audit is the
artefact, the script is just the harness that produces it.

Usage:
    docker compose up -d neo4j
    python scripts/cypher_audit.py > /tmp/cypher_audit_raw.md
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from theogony.config.settings import Neo4jSettings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, NodeType, SourceRef
from theogony.stores import Neo4jKnowledgeStore

EMBEDDING_DIM = 384
NODE_COUNT = 2000
EDGES_PER_NODE = 2  # ~4000 edges total


def _src(loc: str) -> SourceRef:
    return SourceRef(source_type="gutenberg", identifier="audit", location=loc, language="en")


def _node(idx: int) -> KnowledgeNode:
    """Synthetic node with the production embedding shape.

    Embedding direction varies along the index so multi_hop / vector_search
    has a non-trivial ranking to compute.
    """
    vec = [0.0] * EMBEDDING_DIM
    vec[idx % EMBEDDING_DIM] = 1.0
    layer_choice = "ephemera" if idx % 3 != 0 else "mneme"
    type_choice = (
        NodeType.PERSON
        if idx % 4 == 0
        else NodeType.PLACE
        if idx % 4 == 1
        else NodeType.ORGANIZATION
        if idx % 4 == 2
        else NodeType.OTHER
    )
    node = KnowledgeNode(
        label=f"audit-{idx}",
        node_type=type_choice,
        source_ref=_src(f"loc:{idx}"),
        embedding=vec,
        embedding_dim=EMBEDDING_DIM,
        embedding_model_id="audit@v1",
        external_ids={"wikidata": f"Q{idx}"},
        manual_resolution_needed=(idx % 50 == 0),
        resolution_tier=4 if idx % 50 != 0 else 0,
    )
    if layer_choice == "mneme":
        from theogony.core.model import Layer

        node.layer = Layer.MNEME
    return node


async def _populate(store: Neo4jKnowledgeStore) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    nodes = [_node(i) for i in range(NODE_COUNT)]
    await store.batch_upsert_nodes(nodes)
    edges: list[KnowledgeEdge] = []
    for i, n in enumerate(nodes):
        for offset in range(1, EDGES_PER_NODE + 1):
            target_idx = (i + offset * 7) % NODE_COUNT
            if target_idx == i:
                continue
            edges.append(
                KnowledgeEdge(
                    source_id=n.id,
                    target_id=nodes[target_idx].id,
                    relation_type="LINKS_TO" if offset % 2 == 0 else "REFERS_TO",
                    weight=0.5 + (i % 10) * 0.05,
                    evidence_span=f"audit edge {i}-{offset}",
                )
            )
    await store.batch_upsert_edges(edges)
    return nodes, edges


async def _profile(
    store: Neo4jKnowledgeStore, name: str, cypher: str, params: dict[str, Any]
) -> None:
    """Run PROFILE and print a Markdown section with the results."""
    print(f"\n## {name}\n")
    print("```cypher")
    # PROFILE prefix forces query-plan + db-hit collection.
    profiled = "PROFILE " + cypher.strip()
    print(profiled)
    print("```\n")
    print(f"Parameters: `{params}`\n")
    async with store._session() as session:  # noqa: SLF001 — audit harness
        result = await session.run(profiled, **params)
        records = await result.data()
        summary = await result.consume()
    plan = summary.profile
    if plan is None:
        print("**No profile returned** — Cypher executed but driver did not")
        print("attach profile data. Likely a server-side EXPLAIN/PROFILE option")
        print("toggle. Investigate manually via cypher-shell.\n")
        return

    total_db_hits = _walk_db_hits(plan)
    n_records = len(records) if records is not None else 0
    per_record = total_db_hits / max(n_records, 1)
    used_indexes = sorted(_walk_index_usage(plan))
    print(f"- Records returned: **{n_records}**")
    print(f"- Total db hits: **{total_db_hits:,}**")
    print(f"- db hits per record: **{per_record:.1f}**")
    print(f"- Indexes used: {', '.join(f'`{i}`' for i in used_indexes) or '(none)'}")
    print("- Plan operator tree (top 6 by db hits):")
    print()
    print("```")
    for op_name, hits in _top_operators(plan, n=6):
        print(f"  {hits:>8,} db hits  —  {op_name}")
    print("```")


def _walk_db_hits(plan: Any) -> int:
    """Sum dbHits across the plan tree.

    The neo4j-driver Python ``summary.profile`` is a dict (not the
    wrapper object older docs imply); keys are camelCase
    (``dbHits``, ``operatorType``, ``children``).
    """
    total = int(plan.get("dbHits", 0) or 0)
    for child in plan.get("children", []) or []:
        total += _walk_db_hits(child)
    return total


def _walk_index_usage(plan: Any) -> set[str]:
    """Collect index names referenced anywhere in the plan."""
    seen: set[str] = set()
    args = plan.get("args", {}) or {}
    details = str(args.get("Details", "") or "")
    if "knowledge_node" in details or "relation_" in details:
        # The Details string carries indexed-property and index-name hints;
        # we surface the whole string so the verdict-writer sees the context.
        seen.add(details.strip("` "))
    op_name = str(plan.get("operatorType", "") or "").lower()
    if "index" in op_name:
        seen.add(op_name)
    for child in plan.get("children", []) or []:
        seen |= _walk_index_usage(child)
    return seen


def _top_operators(plan: Any, n: int = 6) -> list[tuple[str, int]]:
    """Flatten the plan tree, return top-n operators by dbHits."""
    flat: list[tuple[str, int]] = []

    def _walk(p: Any) -> None:
        op = str(p.get("operatorType", "?")).split("@")[0]
        details = str(p.get("args", {}).get("Details", ""))
        label = f"{op}  {details}".strip() if details else op
        flat.append((label, int(p.get("dbHits", 0) or 0)))
        for c in p.get("children", []) or []:
            _walk(c)

    _walk(plan)
    flat.sort(key=lambda kv: kv[1], reverse=True)
    return flat[:n]


async def main() -> int:
    print("# Cypher PROFILE audit\n")
    print(
        f"Synthetic fixture: {NODE_COUNT} nodes, ~{NODE_COUNT * EDGES_PER_NODE} edges, "
        f"{EMBEDDING_DIM}-dim embeddings.\n"
    )
    print("Each section: PROFILE Cypher + parameters + db-hit summary + ")
    print("top-N operators. Verdict added manually in `docs/cypher_audit/...md`.\n")
    settings = Neo4jSettings()
    async with Neo4jKnowledgeStore(settings, embedding_dim=EMBEDDING_DIM) as store:
        async with store._session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        nodes, _edges = await _populate(store)
        sample_id = nodes[0].id
        sample_layer = "ephemera"
        # Build a query embedding aligned with one of the indexed axes.
        query_emb = [0.0] * EMBEDDING_DIM
        query_emb[42] = 1.0

        # 1. vector_search — uses HNSW + WHERE filter on layer/type/conf
        await _profile(
            store,
            name=(
                "1. vector_search (k=20, layer=EPHEMERA, "
                "node_types=[PERSON,PLACE], min_confidence=0.5)"
            ),
            cypher="""
            CALL db.index.vector.queryNodes('knowledge_node_embedding', 20, $embedding)
            YIELD node, score
            WHERE node.layer = $layer
              AND node.node_type IN $types
              AND node.confidence >= $min_conf
            RETURN node.id AS id, score
            """,
            params={
                "embedding": query_emb,
                "layer": sample_layer,
                "types": ["person", "place"],
                "min_conf": 0.5,
            },
        )

        # 2. traverse — variable-length match with weight + type filter
        await _profile(
            store,
            name=(
                "2. traverse (start=AKA-…, max_depth=3, min_weight=0.3, relation_types=[LINKS_TO])"
            ),
            cypher="""
            MATCH path = (start:KnowledgeNode {id: $start_id})
              -[r:RELATION*1..3]->(other:KnowledgeNode)
            WHERE all(rel IN r WHERE rel.weight >= $min_weight
                                   AND rel.relation_type IN $rel_types)
            RETURN path
            LIMIT 50
            """,
            params={
                "start_id": sample_id,
                "min_weight": 0.3,
                "rel_types": ["LINKS_TO"],
            },
        )

        # 3. get_neighborhood — undirected variable-length depth=1
        await _profile(
            store,
            name="3. get_neighborhood (start=AKA-…, depth=1, min_weight=0.3)",
            cypher="""
            MATCH (start:KnowledgeNode {id: $node_id})
            OPTIONAL MATCH (start)-[r:RELATION*1..1]-(other:KnowledgeNode)
            WHERE r IS NULL OR all(rel IN r WHERE rel.weight >= $min_weight)
            WITH start, collect(DISTINCT other) AS others, collect(r) AS rel_lists
            RETURN start.id AS start_id, [n IN others WHERE n IS NOT NULL | n.id] AS others
            """,
            params={"node_id": sample_id, "min_weight": 0.3},
        )

        # 4. multi_hop_search — full server-side: vector seed + traverse for k=10 nodes
        # The store implementation actually issues vector_search + per-seed
        # traverse client-side. For audit purposes we PROFILE one
        # representative variant: the seed CALL, since per-seed traverses
        # are covered by section 2.
        await _profile(
            store,
            name=(
                "4. multi_hop_search seed "
                "(vector_search variant covered above; traverse covered in §2)"
            ),
            cypher="""
            CALL db.index.vector.queryNodes('knowledge_node_embedding', 10, $embedding)
            YIELD node, score
            RETURN node.id AS id, score
            """,
            params={"embedding": query_emb},
        )

        # 5. list_pending_resolution
        await _profile(
            store,
            name="5. list_pending_resolution (manual_resolution_needed=true, limit=20)",
            cypher="""
            MATCH (n:KnowledgeNode {manual_resolution_needed: true})
            RETURN n.id AS id, n.label AS label
            ORDER BY n.created_at DESC
            LIMIT 20
            """,
            params={},
        )

    print("\n---\n")
    print("End of automated audit. Manual verdicts go in the docs/cypher_audit Markdown.\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - one-shot script
    sys.exit(asyncio.run(main()))
