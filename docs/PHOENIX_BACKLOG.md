# Phoenix Backlog (Post-MESH-Migration Catalogue)

> **Status as of 2026-05-13: post-migration.** This catalogue reflects the **post-MESH-migration** ticket space (PHX-1000+). The 51 pre-migration tickets (PHX-0001–PHX-0074) have been categorised in [`phoenix-backlog/archive/MIGRATION_AUDIT.csv`](../phoenix-backlog/archive/MIGRATION_AUDIT.csv) as **carry-forward**, **obsolete**, or **absorbed into MESH doctrine**. The legacy catalogue is preserved at [`PHOENIX_BACKLOG_LEGACY.md`](PHOENIX_BACKLOG_LEGACY.md). The binding substrate doctrine is the MESH triplet ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) + [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) + [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md)); the operative implementation plan is [`MESH_MIGRATION_PLAN.md`](MESH_MIGRATION_PLAN.md).

The gap between PHX-0074 (last legacy ticket) and PHX-1000 is deliberate — it marks the doctrine boundary. Numbers are never reused. Each carry-forward ticket from the legacy backlog has a `migrated_from: PHX-XXXX` reference.

## How to file a new ticket

See [`phoenix-backlog/README.md`](../phoenix-backlog/README.md) for lifecycle rules. In short:

1. Pick the next free PHX-1000+ number.
2. Create an entry in this catalogue.
3. Create a YAML in `phoenix-backlog/` if the ticket is active (being worked, referenced from a PR, or emitted by a RunReport).

## Catalogue

| ID | Title | Status | Priority | Notes |
|---|---|---|---|---|
| PHX-1001 | MESH migration in progress | open | critical | Meta-ticket: the Strangler-fig plan. Tracks S1–S6 completion. |

### Carry-forward tickets from the legacy backlog

Each has `migrated_from: PHX-XXXX`.

| new ID | migrated_from | Title | Status (initial) |
|---|---|---|---|
| PHX-1002 | PHX-0013 | Chronese Canonical Semantic Layer | open |
| PHX-1003 | PHX-0014 | Metis Advisory Runtime | open |
| PHX-1004 | PHX-0015 | Fast/Slow Cognition and Opposition Protocol | open |
| PHX-1005 | PHX-0017 | Sensorium: Multimodal Acquisition Adapters | open |
| PHX-1006 | PHX-0018 | Chronik-to-Model Distillation and Hardware Co-Design | open |
| PHX-1007 | PHX-0019 | Hestia: Human Flourishing Guardian | open |
| PHX-1008 | PHX-0033 | Pre-curated Wikidata subset for travel literature | open |
| PHX-1009 | PHX-0034 | Entity-resolution quality benchmark | open |
| PHX-1010 | PHX-0036 | Re-evaluate Gemini 3.1 Flash Lite once GA | open |
| PHX-1011 | PHX-0037 | LLMRateLimitError as first-class exception | open |
| PHX-1012 | PHX-0038 | AuditingLLMProvider wrapper | open |
| PHX-1013 | PHX-0039 | Token-bucket backoff inside LLMProvider | open |
| PHX-1014 | PHX-0040 | Per-stage RPM throttling in IngestionPipeline | open |
| PHX-1015 | PHX-0045 | pytest-xdist parallel test execution | open |
| PHX-1016 | PHX-0049 | AnswerSynthesizer system prompt packaging | open |
| PHX-1017 | PHX-0055 | CI smoke-test against live default LLM | open |
| PHX-1018 | PHX-0058 | Aggregated stub detection (curiosity) | open |
| PHX-1019 | PHX-0060 | Domain Clusters / Cognitive Centers | open |
| PHX-1020 | PHX-0061 | Vector-Routed Federation | open |
| PHX-1021 | PHX-0064 | Portable Constellation | open |
| PHX-1022 | PHX-0066 | Hosted Pantheon MCP Service | open |
| PHX-1023 | PHX-0067 | Eris — Adversarial Defender | open |
| PHX-1024 | PHX-0068 | Nemesis — Hybris Auditor | open |
| PHX-1025 | PHX-0069 | Hosted MCP SSE session affinity | open |
| PHX-1026 | PHX-0070 | StubLLM synthesis raises before completion | open |
| PHX-1027 | PHX-0071 | Mnemosyne — self-reflective backlog auditor | open |
| PHX-1028 | PHX-0072 | Proteus — twin-agent A/B testing | open |
| PHX-1029 | PHX-0074 | Iris — the Pantheon Cockpit | open |

### Tickets absorbed into MESH doctrine

These are **not** re-filed. Their concerns are now part of the MESH triplet. The working tickets listed here link to the MESH-triplet section that subsumes them for traceability:

| Legacy ID | Title | Absorbed by |
|---|---|---|
| PHX-0001 | Custom Knowledge Store Engine | MESH_IMPLEMENTATION.md, MESH_SUBSTRATE.md |
| PHX-0002 | Hierarchical + Heterogeneous Embedding Spaces | MESH_SUBSTRATE.md §Node anatomy |
| PHX-0016 | Non-Chronological Knowledge Topologies | MESH_SUBSTRATE.md §"No hierarchical pointer field" |
| PHX-0020 | Operative Knowledge: The Fifth Form | MESH_RETRIEVAL.md diversified injection + constellation assembly |
| PHX-0048 | KnowledgeStore.batch_update_scores | MESH_IMPLEMENTATION.md §delta buffer + CSR rebuild |
| PHX-0052 | HNSW + filter pushdown for vector_search | MESH_IMPLEMENTATION.md §"Nodes — LanceDB" |
| PHX-0056 | Activation Engine v1 | MESH_RETRIEVAL.md §"Spreading Activation as batched SpMV" |
| PHX-0057 | Edge-Pheromone trails + Slow-Path emancipation | MESH_SUBSTRATE.md §"Hebbian update" + eligibility traces + super-linear decay |
| PHX-0059 | Morpheus-as-Associator + multi-layer connectivity | MESH_IMPLEMENTATION.md §"Oneiros — implementation order" |
| PHX-0062 | Negative Knowledge / Anti-Bullshit Layer | MESH_SUBSTRATE.md §"Agent-driven cleanup" + §"Pathology and therapy" |
| PHX-0063 | Chronik-Diff | MESH_IMPLEMENTATION.md §"Audit ledger" + Lance version snapshots |
| PHX-0065 | Pantheon as Time Machine | MESH_IMPLEMENTATION.md §"Lance MVCC versioning" + checkout |
| PHX-0073 | Asklepios — Healer agent | MESH_SUBSTRATE.md §"Agent-driven cleanup" + §"Therapy" |

### Tickets declared obsolete

These are **not** re-filed. They address Gen-1 features (mostly Neo4j-specific) that the MESH substrate replaces:

| Legacy ID | Title | Reason |
|---|---|---|
| PHX-0041 | Detective default-on threshold re-evaluation | MESH has different anomaly detection (Argus pathology in S5) |
| PHX-0042 | Cypher query-plan audit for Neo4jKnowledgeStore | Neo4j-specific; MESH forbids traditional graph databases |
| PHX-0043 | Async-pipeline IngestionPipeline writes against Neo4jKnowledgeStore | Neo4j-specific |
| PHX-0044 | Read-replica readiness audit of Neo4jKnowledgeStore | Neo4j-specific |
| PHX-0046 | batch_upsert_nodes/batch_upsert_edges via UNWIND+MERGE | Neo4j-specific |
| PHX-0047 | Neo4jSettings password default | Neo4j-specific |
| PHX-0050 | ConstellationAssembler single bulk-edges Cypher | Neo4j-specific; MESH CSR provides adjacency via SpMV |
| PHX-0051 | MultiHopBreakdown.nodes_per_hop schema | Gen-1 query-result shape |
| PHX-0053 | traverse Cypher: strip embeddings | Neo4j-specific |
| PHX-0054 | Re-measure PHX-0046 batch_upsert speedup | Neo4j-specific |
