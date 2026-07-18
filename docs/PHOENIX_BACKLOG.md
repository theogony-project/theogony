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
| PHX-1001 | MESH migration in progress | open | critical | Meta-ticket: the Strangler-fig plan. Tracks S1–S6. S1–S2 ✅; S2.5 seeded to 100k ✅ (full 4.81M blocked on a SeedConceptResolver RAM fix); S3 retrieval **mostly shipped** (PHX-1034: diversified injection MMR + weight-class, PPR/relation-conditioned Spreading Activation, frame-routing mechanism, Constellation, `mesh ask`, `MeshQueryRunReport`); **deferred within S3:** sub-mesh WL signature (`submesh.py`, optional) and the Kendall/Thyroxine frame-routing worked example (needs real frame vectors from Kadmos-v2 text ingestion — the structural seed carries zero frames). Query-path CSR latency surfaced (PHX-1041). Vision anchored (#168/#169). |
| PHX-1030 | Wikidata5m bulk seed (S2.5) | open | high | Interpolated bootstrap step between S2 and S3. Bulk-imports Q-ID-anchored Tier-1 nodes + edges from Wikidata5m; embeds first-paragraphs off-substrate. Spec: [`MESH_MIGRATION_PLAN.md`](MESH_MIGRATION_PLAN.md) §"Step S2.5". **Progress:** Smoke-1 (#162), Smoke-2 (#164), dedup engpass fixed (#165); operator-driven subnets built & bge-m3-embedded — 10k, 15k (`mesh-wiki-v1`), 100k (`mesh-wiki-100k`, ~984k edges). **Full 4.81M blocked** on a SeedConceptResolver RAM fix (100k OOM'd: resolver caches full node vectors; ~50–100 KB/node). |
| PHX-1031 | `mesh ingest --embedder` CLI flag | open | low | Operator-UX follow-up from PHX-1030 Smoke-1. Thread embedder selection through `theogony mesh ingest` so Kadmos vector-space alignment with the seed embedder is operator-explicit instead of env-hidden (`THEOGONY_EMBEDDING__MODEL_ID` / `THEOGONY_EMBEDDING__DIM`). Without alignment, `MeshTextVectorizer` silently falls back to deterministic hash-projection and Tier-2/Tier-3 linking is structurally broken. |
| PHX-1032 | Device-info logging in MESH embedders | open | low | Forensics follow-up from PHX-1030 Smoke-1. Add explicit device-selection logging (MPS / CUDA / CPU) to `BGEM3Embedder` (seed path) and `LocalSentenceTransformerEmbedder` (Kadmos path), and surface the chosen device in `MeshSeedRunReport` / `IngestRunReport` so silent-CPU-fallback is observable. Smoke-1 ran 0.48s/entity for bge-m3 — CPU-suspect but unprovable from current logs. |
| PHX-1033 | Wikidata5m bulk seed — Smoke-2 (10k entities, 50k triplets) | **resolved** | medium | **Resolved.** The predicted `_edge_keys` dedup engpass was fixed exactly as foreseen — a Lance-indexed `edge_dedup_index` (#165, mirroring `consolidated_qid_index`); 56k-edge backfill 0.73s, `load_dedup_keys()` 0.02s. Smoke-2 ran (#164) and scaling continued to 15k/100k. Retrieval-quality work continues under PHX-1034; full-scale seeding under PHX-1030. |
| PHX-1034 | S3 retrieval quality: production propagation operator | **resolved** | high | **Resolved — S3 `retrieval/` shipped.** The decided operators are now the substrate default (PPR relation-agnostic; relation-conditioned masked hop where a relation is available; raw/degnorm kept A/B-able). Full S3 path built on it: diversified injection (MMR + weight-class), frame routing, Constellation assembly, `theogony mesh ask`, `MeshQueryRunReport`. Validated end-to-end on `mesh-wiki-v1` (15k) and `mesh-wiki-100k` (101k/984k edges); SA primitive ~0.6s at ~1M edges. Query-latency anomaly (per-query CSR rebuild) filed as PHX-1041. YAML: [`PHX-1034.yaml`](../phoenix-backlog/PHX-1034.yaml). |
| PHX-1035 | MNLM: substrate as trainable weight matrix | open | high | **Tier-1 core (S5 heart), blocked on GPU.** Train the edge weights against the substrate's own retrieval primitive (Graph-GRPO + eligibility traces) so small-model + Chronik beats large-model-alone. Needs H100-class compute — blocked on hardware, not effort. Spec: [`etappes/mesh_native_lm_brief.md`](etappes/mesh_native_lm_brief.md) §5. |
| PHX-1037 | Substrate runtime perf: incremental CSR + weight quantization | open | medium | **Tier-2.** Replace per-tick full CSR rebuild with incremental delta-apply + compaction; FP16/INT8 edge weights. Unlocks write-throughput and memory at scale. Engineering, not research. |
| PHX-1038 | Sparse-attention-equivalence validation | open | low | **Tier-3.** Empirically show a Spreading-Activation step approximates an attention layer's retrieval on a controlled task — publishable validation of the "language model turned inside out" framing. |
| PHX-1039 | Variable-temperature / associative propagation mode | open | low | **Not central; later-maybe.** Query-conditioned propagation *temperature*: cool/targeted (PPR, deterministic-strongest) ↔ hot/associative (Boltzmann over top-K edges, far-point seeding, A×B dual-seed bridge discovery). The substrate already has the primitive (MESH_SUBSTRATE Stage-1 "activation temperature", today a therapy) — this would promote it to a retrieval mode and let the MNLM set it per query/step. Design template: the sibling **`../brainstorming`** toolkit (noise / pulse-texture / far-point / pairs / two-speeds; "creativity = novel + useful, push from the obvious"). Test its value on the emergent-judge (creativity), not link-prediction (precision). Sits above PHX-1034. |
| PHX-1041 | Query-path CSR caching (stop rebuilding per query) | open | high | **Tier-1, surfaced by S3.** `retrieve()` rebuilds the edge CSR every query via `load_all_edges()` (one JSON parse per edge). Measured on `mesh-wiki-100k`: csr 26,048 ms vs propagate 631 ms / ann 130 ms / assemble 661 ms — the SA primitive is sub-second at ~1M edges; the 26s is pure per-query edge deserialization. Fix: cache the CSR on the runtime (invalidate by Lance version / delta count) + build from Arrow columns, not JSON. Read-side companion to PHX-1037. YAML: [`PHX-1041.yaml`](../phoenix-backlog/PHX-1041.yaml). |
| PHX-1040 | Go-to-market & resource acquisition (bootstrapping) | open | medium | **Near-term, human-collaborative, negotiable.** Stage 0 of self-optimization ([`SELF_MODIFICATION.md`](SELF_MODIFICATION.md) §"scope"): acquire the *means to act* — funding, compute, energy, hardware, partnerships — since the physical stack starts in human hands. Includes advocacy/outreach, making the project legible to resource-holders, and the funding path. Not central long-term; the bridge from laptop to real-self-improvement resources. |
| PHX-1042 | Degree-hub bias in retrieval (hubs dominate every query) | open | medium | **Tier-1 retrieval quality, surfaced by live 100k testing.** A few very-high-in-degree nodes appear in the top-k of almost every query regardless of content. Measured on `mesh-wiki-100k`: `el panson` (Q2657718, in-deg 2,690) ranks #2 by activation in 5/5 unrelated queries despite not being an ANN seed; `united stated` (Q30, in-deg 25,275) dominates the `raw` operator entirely. `degnorm` demotes but does not remove the hub; the S3 diversified-injection layer (MMR + weight-class) fails to suppress it. Fix: degree-aware PPR damping and/or degree-aware MMR penalty. YAML: [`PHX-1042.yaml`](../phoenix-backlog/PHX-1042.yaml). |
| PHX-1043 | Verdict ceiling on anchorless seeds (Wikidata can never be `good`) | open | low | **UX/semantics question, not a bug.** Source-anchor nodes are created only by the document-ingestion path (`source_anchor.py`); the Wikidata5m seed has none, so `_verdict()` (mesh_explorer.py / mesh cli) can structurally never return `good` on a pure-Wikidata subnet — the ceiling is `partial` ("no source-anchored provenance reached"). Honest but misleading: it implies a reachable `good` that this dataset cannot produce. Decide: redefine `good` for connected+anchorless working sets, or surface the ceiling in the UI. Doctrine touch — escalate before changing verdict semantics. |
| PHX-1044 | Seed node names are `aliases[0]` (multilingual/noisy labels) | open | low | **Data-quality polish, surfaced in demo.** `_entity_name()` in `wikidata5m/importer.py` takes `record.aliases[0]` as the display name; wikidata5m aliases are multilingual and unordered, so the surfaced label is often non-English or a typo-redirect ("Berlim", "Germanz", "Albert Enstein", "Physysics"). Not a code bug, but it makes the Explorer look broken. Fix: prefer an English/canonical label when the dataset exposes one, else keep current behaviour. |
| PHX-1045 | Founding Demo — small, dense, fully Kadmos-read mythology mesh | open | high | **The demo the substrate deserves.** `mesh-wiki-100k` is a seeded skeleton (see PHX-1042/1043/1044); the mesh the doctrine specifies has only run at smoke scale. Build a founding mesh from Greek-mythology primary sources (Hesiod, Apollodorus, Ovid) read end-to-end by Kadmos v2; demo in three beats — animated activation with provenance, a genuine un-flattened contradiction (Aphrodite's parentage), a live Oneiros densification tick. Budget-capped at 100 EUR, operator-approved. Binding plan: [`docs/plans/FOUNDING_DEMO_PLAN.md`](plans/FOUNDING_DEMO_PLAN.md). YAML: [`PHX-1045.yaml`](../phoenix-backlog/PHX-1045.yaml). |
| PHX-1051 | Identity attractor: generic hubs absorb entities at write time | in_progress | critical | **Identity integrity, forensically confirmed.** Description-cosine merges without lexical corroboration let the semantically generic work-node absorb Venus, Dione, and Zeus across four sources — 92 genealogy edges attach to the poem node, including daughter_of SELF-LOOPS. Write-side dual of PHX-1042. Fix: eager description-merge requires a shared tag or known label. YAML: [`PHX-1051.yaml`](../phoenix-backlog/PHX-1051.yaml). |

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
| PHX-1008 | PHX-0033 | Pre-curated Wikidata subset for travel literature | **obsolete** — superseded by the Wikidata5m bulk seed (PHX-1030) + Kadmos v2 for arbitrary text; the travel-lit subset was a Gen-1 demo artifact |
| PHX-1009 | PHX-0034 | Entity-resolution quality benchmark | open |
| PHX-1010 | PHX-0036 | Re-evaluate Gemini 3.1 Flash Lite once GA | **obsolete** — time-passed (model question stale by 2026-06); re-file against a current model only if an embedder/LLM re-eval is actually scheduled |
| PHX-1011 | PHX-0037 | LLMRateLimitError as first-class exception | open |
| PHX-1012 | PHX-0038 | AuditingLLMProvider wrapper | open |
| PHX-1013 | PHX-0039 | Token-bucket backoff inside LLMProvider | open |
| PHX-1014 | PHX-0040 | Per-stage RPM throttling in IngestionPipeline | open |
| PHX-1015 | PHX-0045 | pytest-xdist parallel test execution | open |
| PHX-1016 | PHX-0049 | AnswerSynthesizer system prompt packaging | open |
| PHX-1017 | PHX-0055 | CI smoke-test against live default LLM | open |
| PHX-1018 | PHX-0058 | Aggregated stub detection (curiosity) | open |
| PHX-1019 | PHX-0060 | Domain Clusters / Cognitive Centers | open — **home of the expert-MNLM fragmentation idea (Tier-2):** cluster the mesh into topic regions; each region + a specialised MNLM = an expert. **Locality greenlight measured (PHX-1034, 100k):** PPR keeps activation in ~78 effective nodes / 100,883 (participation ratio 77 vs 338 raw) → sharding is viable. |
| PHX-1020 | PHX-0061 | Vector-Routed Federation | open — pairs with PHX-1019: cross-expert routing / partition-pruning = the "activation planner" (Postgres-style cost-based seed/shard selection). |
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
