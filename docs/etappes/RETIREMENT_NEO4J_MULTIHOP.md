# Retirement: Neo4j + multi-hop retrieval (spreading-only direction)

**Status:** Operational note for contributors — **Neo4j is no longer a Chronicle core backend**; **multi-hop retrieval strategies** (the F3 family) are **removed**. Queries run through **spreading activation** (`TensorMeshEngine`) on graph data exported from the store.

**Binding target:** [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md).

---

## What was removed / will not be extended

| Area | Decision |
|------|----------|
| `Neo4jKnowledgeStore` | **Deleted** — no Bolt, no Cypher on the product path. |
| `MultiHopRetriever` + `retrieval/strategies/*` | **Deleted** — no `multi_hop_search` as primary retrieval. |
| CLI `--store neo4j` | **Invalid** — only `memory` (and later explicitly `lancedb`, once fully wired). |

---

## What replaces it

- **`SpreadingActivationRetriever`** (`src/theogony/retrieval/spreading_activation_retrieval.py`): builds a `TensorMeshEngine` from `InMemoryKnowledgeStore` (or LanceDB via `load_into_tensor_engine`), runs `spreading_activation`, maps back to `ScoredNode` / `MultiHopResult` carriers for existing reports.
- **Default runtime store:** `InMemoryKnowledgeStore` (API, MCP without seed, cockpit standalone, CLI helpers) so CI and local runs work **without Docker**.

---

## Known gaps (Talos / follow-up)

- `LanceDBKnowledgeStore` does not yet implement the full `KnowledgeStore` protocol — production persistence and all write paths (pheromone, relevance, …) must be completed or consciously trimmed.
- Older docs / wave briefs still mention Neo4j or multi-hop — **update** them or point to this document.
- `QueryRunReport.multi_hop` is still named for history; renaming to `spreading` is optional (schema break).

---

*Short-lived document — once everything is consolidated, link or fold it into INDEX / Glossary.*
