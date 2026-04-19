# E7 — Neo4jKnowledgeStore + schema + contract suite

Brief from Daedalus to Talos, 2026-04-19. Companion to Plan §3.1a (v5).

Two convention points were closed in §3.1a so this brief stays consistent with the code in `src/`:

- `Settings.neo4j: Neo4jSettings` stays **flat**. No `Settings.store.neo4j` wrapper.
- Env vars use the existing `THEOGONY_` prefix with `__` nested separator: `THEOGONY_NEO4J__URI`, etc.

## Files

```
src/theogony/stores/neo4j_store.py     NEW   Neo4jKnowledgeStore class
src/theogony/stores/_schema.py         NEW   constraint + index Cypher constants
tests/test_store_contract.py           EDIT  parametrise over both store impls
tests/test_neo4j_store_live.py         NEW   testcontainers + Neo4j 5.x
docker-compose.yml                     NEW   neo4j:5.18-community for local dev
.env.example                           EDIT  document THEOGONY_NEO4J__* vars
pyproject.toml                         EDIT  add `neo4j>=5.18`, `testcontainers[neo4j]>=4.0`
```

`src/theogony/config/settings.py` does **not** need editing. The existing `Neo4jSettings` (`uri`, `user`, `password`, `database`) is sufficient. Driver defaults handle pool size and timeouts; the vector-index dim comes from `Settings.embedding.dim` and is passed into the store explicitly.

## Classes & properties

`Neo4jKnowledgeStore(KnowledgeStore)` — implements every method of the Protocol in `src/theogony/core/store.py` against the Bolt driver. Constructor:

```python
Neo4jKnowledgeStore(
    settings: Neo4jSettings,      # from Settings.neo4j (flat, per §3.1a)
    embedding_dim: int,           # from Settings.embedding.dim; cross-check on every upsert
)
```

On `__aenter__`: open driver, run `_SCHEMA_CYPHER` (constraints + indexes + vector index from Plan §3.1a verbatim — keep them in `_schema.py` so a Cypher diff is one git command). On `__aexit__`: close driver.

Property mapping: every field listed in Plan §3.1a's two tables, with the explicit JSON-serialised columns (`source_ref_json`, `external_ids_json`, `properties_json`). The `wikidata_id` flatten + `vitality` denormalisation per §3.1a.

## Constraints + indexes

Verbatim from Plan §3.1a Cypher blocks. Two unique constraints (node `id`, relation `id`), two existence constraints (node `id`, relation `relation_type`), ten range indexes (eight on `:KnowledgeNode`, two on `[:RELATION]` — `relation_type` and `weight`), one HNSW vector index on `embedding`. All idempotent (`IF NOT EXISTS`).

## Settings (env vars)

```
THEOGONY_NEO4J__URI=bolt://localhost:7687
THEOGONY_NEO4J__USER=neo4j
THEOGONY_NEO4J__PASSWORD=...               # SecretStr; required for production
THEOGONY_NEO4J__DATABASE=neo4j
```

The vector-index dim is **not** a Neo4j env var — it lives at `THEOGONY_EMBEDDING__DIM` (default 384, BGE-small) and is read by the store constructor from `Settings.embedding.dim`. The store rejects upserts whose `node.embedding_dim` differs from this value rather than silently coercing.

## Tests

- `tests/test_store_contract.py`: parametrise existing tests over `(InMemoryKnowledgeStore, Neo4jKnowledgeStore)`. The Neo4j parametrisation is gated on `THEOGONY_TEST_NEO4J=1` and `testcontainers-python` running a Neo4j container per session (cached).
- `tests/test_neo4j_store_live.py`: schema-bootstrap idempotence (run schema twice; no errors), vector-index dim-mismatch rejection, deterministic-id idempotent-upsert (Plan §9.5).
- CI: new `neo4j` job that exports `THEOGONY_TEST_NEO4J=1` and runs the contract + live tests. Image cached; expected ~60 s overhead.

## In scope

Schema bootstrap, every `KnowledgeStore` Protocol method, vector + graph queries needed by `multi_hop_search`, batched upserts (`batch_upsert_nodes` / `batch_upsert_edges` per Plan §8 carry-over), contract suite, testcontainers integration, docker-compose for local dev, README quickstart updated with the `docker compose up neo4j` step.

## Out of scope (do not touch)

No clustering (`cluster_id` stays null). No Phoenix import/export (PHX-0022). No APOC. No Neo4j Bloom. No causal-cluster. No `Detective` / `theogony resolve` / API layer / retrieval stack — those are E8 / E9 / separate Detective etappe respectively (Plan §5 v5 split).

## Done when

The characterization slice from `tests/test_pipeline_characterization.py` ingests via `IngestionPipeline(store=Neo4jKnowledgeStore(...))` and produces the same node + edge counts as `InMemoryKnowledgeStore`. `theogony status` reports the Neo4j store reachable, schema present, embedding dim matched. CI's new `neo4j` job is green.
