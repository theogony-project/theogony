> **# Phoenix Backlog (LEGACY catalogue — pre-MESH)**
>
> This is a copy of the pre-MESH-migration catalogue, preserved for historical reference.
> The operative backlog starts at PHX-1000; see the new [PHOENIX_BACKLOG.md](PHOENIX_BACKLOG.md).
>
# Phoenix Backlog (LEGACY catalogue)

> **Status as of 2026-05-13: legacy.** This catalogue reflects the **pre-MESH-migration** ticket space (PHX-0001 through PHX-0074, with gaps). Its 51 active YAMLs have been moved to [`phoenix-backlog/archive/`](../phoenix-backlog/archive/README.md) as part of the migration pivot. The operative substrate doctrine is now the MESH triplet ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) + [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) + [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md)); the operative implementation plan is [`MESH_MIGRATION_PLAN.md`](MESH_MIGRATION_PLAN.md). The **post-migration backlog will start at PHX-1000** once the labelling pass (carry-forward / obsolete / absorbed) over the archived YAMLs completes. Tickets in *this* catalogue remain referenceable as historical context — they captured the Gen-1 design discourse — but they are no longer the live work queue.
>
> Do not file new tickets in the PHX-0001–0999 range. New tickets go to PHX-1000+; see [`phoenix-backlog/README.md`](../phoenix-backlog/README.md).

The Phoenix Backlog is the evolutionary memory of the Chronik. It captures problems, improvements, visions, and architectural decisions that should be considered in future generations — specifically regarding the Chronik's knowledge organization, not peripherals like GUI or client interfaces.

Tickets are filed by agents or humans during operation. They are evaluated when planning a Phoenix process (distillation and rebirth of the Chronik).

**W5 / PR #32 reality (2026-04):** two catalogue entries became central to demo truth and reliability: **PHX-0033** (pre-curated Wikidata / offline subset — unblocks full-book ingest vs live SPARQL throttle) and **PHX-0055** (CI smoke-test against the **live** default LLM so retired model IDs cannot ship green again). **PHX-0034** (entity-resolution gold benchmark) remains the quality companion. Active YAMLs existed in `phoenix-backlog/` and have since been moved to `phoenix-backlog/archive/` per the migration pivot.

## Two Layers: Catalogue and Active YAMLs

The Phoenix Backlog has two layers, deliberately:

1. **The catalogue** — this document (`docs/PHOENIX_BACKLOG.md`, now legacy) and the legacy implementation plan (`docs/IMPLEMENTATION_PLAN_GEN1_LEGACY.md` §7). This is the authoritative list of every PHX ticket that was conceived under the Gen-1 doctrine. The numbered space `PHX-0001`–`PHX-0999` was allocated here. The post-MESH-migration numbered space starts at `PHX-1000` per [`phoenix-backlog/README.md`](../phoenix-backlog/README.md).
2. **Active YAMLs** — the files in [`phoenix-backlog/`](../phoenix-backlog/). These are the structured, machine-readable working copies of tickets that are currently being acted on, referenced from a PR or RunReport, or otherwise "warm".

A YAML file is created **only when a ticket becomes active**. Absent YAML files are not gaps — they are intentional lazy materialization. A ticket that lives only in the catalogue is real; it just has no active workspace yet.

This avoids the failure mode of dozens of stub YAMLs that nobody updates, while keeping the option to promote any catalogue entry into an active YAML the moment work begins on it. Conversely, a YAML may be archived back into catalogue-only form once a ticket is resolved or deferred and the structured fields no longer pay rent.

When you file a new ticket: add it to this catalogue first. Create the YAML only if you (or another agent) intend to begin work on it now, or if a PR/RunReport needs to reference its structured form. See [`phoenix-backlog/README.md`](../phoenix-backlog/README.md) for the operational details.

## Ticket Format

Each active ticket in `phoenix-backlog/` is a YAML file:

```yaml
id: PHX-0001
category: vision           # bug | improvement | vision | performance | knowledge_gap
priority: high              # critical | high | medium | low | vision
status: open                # open | accepted | in_progress | resolved | deferred
generation_target: 2        # which generation this targets (0 = any)
title: "Short descriptive title"
filed_by: hesiod            # agent name or human identifier
created_at: 2026-04-15
description: |
  Detailed description of the issue, improvement, or vision.
resolution: null            # filled when resolved
```

---

## Gen 1 Tickets

### PHX-0001: Custom Knowledge Store Engine

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2-3
- **Filed by**: hesiod

Neo4j is adequate for Gen 1 but not designed for the Chronik's specific access pattern: combined vector similarity + graph traversal as a single native operation. A custom engine that treats vector proximity and graph edges as aspects of the same navigational structure could be fundamentally more efficient at scale. This should be explored once real-world query patterns from Gen 1 provide data on what the ideal engine needs to optimize for.

### PHX-0002: Hierarchical Embedding Spaces

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 2

Current embedding models produce flat vectors in a single space. The Chronik's hierarchical cluster structure suggests that embeddings at different abstraction levels (individual facts vs. topic summaries vs. domain overviews) might benefit from different embedding strategies or even different dimensionalities. Research needed: can a hierarchical embedding model be trained that produces naturally clustered representations?

### PHX-0003: Federated Chronik Instances

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 3

Multiple Chronik instances (university departments, national libraries, research institutions) could federate — sharing knowledge across instance boundaries while respecting access controls. Key open questions: federation protocol, conflict resolution for contradictory facts across instances, trust propagation between instances.

### PHX-0004: Crystallized Inference

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Oneiros process currently connects existing knowledge. It should also perform and store *inferences* — derived knowledge that follows logically from existing facts. If A implies B and B implies C, the edge A→C should exist with computed confidence. This turns the Chronik into a distributed logic engine. Open questions: how to prevent inference chains from hallucinating, how to mark derived knowledge distinctly from observed knowledge.

### PHX-0005: Embedding Model Independence

- **Category**: improvement
- **Priority**: critical
- **Generation Target**: 1

The Chronik must not be locked to a specific embedding model. When a better model becomes available, it should be possible to re-embed incrementally (not all at once) during the Phoenix process. This requires storing the embedding model identifier with each vector and supporting mixed-model queries during transition periods.

### PHX-0006: Federated Compute (Distributed Dreaming)

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 3

Allow external compute donors to run Oneiros tasks — embedding generation, association discovery, verification. Like Folding@home but for knowledge consolidation. Requires: task serialization, result verification, trust scoring for compute donors.

### PHX-0007: Scientific Workbench Agents

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

Specialized agents that use the Chronik as a research tool: cross-referencing scientific claims, identifying replication failures, suggesting experiments based on gap analysis, generating automated literature reviews. The Chronik becomes not just a knowledge store but an active research partner.

### PHX-0008: Multi-Language Knowledge Bridging

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 2

Knowledge extracted from a German source and knowledge extracted from a Japanese source about the same entity should converge on the same node. This requires cross-lingual entity resolution and potentially multi-lingual embedding models. The Argonauts (language specialists) are the natural agents for this.

### PHX-0009: Vitality Function Tuning

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 1-2

The vitality function weights (w1, w2, w3, w4) and the dynamic threshold need empirical tuning based on real usage data. Initial values will be heuristic. A feedback loop should be established where Helios adjusts these parameters based on system performance metrics.

Phase 1 of PHX-0009 closed by F1 (this PR): math consolidated under `core/vitality.py`. Future tuning rounds touch one file.

### PHX-0010: Physical Library Acquisition

- **Category**: vision
- **Priority**: low
- **Generation Target**: 3+

Robotic systems that can visit physical libraries (e.g., Bavarian State Library), request books from stacks, scan or photograph pages, and feed the content into the acquisition pipeline. This requires hardware integration far beyond the current scope, but the acquisition adapter interface should be designed to accommodate it.

### PHX-0011: Knowledge Condensation at Scale

- **Category**: performance
- **Priority**: high
- **Generation Target**: 2

At billions of nodes, many represent highly similar or overlapping knowledge. A condensation process should identify clusters of near-duplicate nodes and merge them into single, higher-confidence nodes with combined source references. This is distinct from deduplication (removing exact copies) — it is semantic compression.

### PHX-0012: Cost Accounting and Credit System

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 1

Every operation (query, ingestion, agent task) should track its resource cost: LLM tokens consumed, embeddings generated, graph traversals performed, storage used. This enables the credit-based pricing model and provides data for cost optimization.

### PHX-0013: Chronese Canonical Semantic Layer

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Chronik should converge on a canonical semantic language that sits between source text and all graph/vector projections. This language, tentatively called Chronese, should be language-neutral, event-centric, provenance-bound, and epistemically explicit. Gen 1 can represent it as strict JSON/Pydantic schemas, but future generations may require a richer compiler, versioning system, and projection toolchain.

### PHX-0014: Metis Advisory Runtime

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2

The Chronik should support a dedicated advisory agent, Metis, that operates across Akasha, Lethe, and an explicit Norm Space. Metis must separate facts, analogies, options, risks, and value assumptions rather than collapsing them into a single recommendation. Future work includes defining advisory packets, audit traces, norm handling, and ethical constraints for personal and institutional guidance.

### PHX-0020: Operative Knowledge — The Fifth Form

- **Category**: vision
- **Priority**: low
- **Generation Target**: 3

The Chronik must eventually represent operative knowledge: the knowledge that runs the world rather than describes it. Schedules, logistics, machine control, supply forecasts. Implies a new class of operative agents (Atlas, Hephaistos, Demeter) that act on the world. Long-horizon dimension; not part of Generation 1 or 2. The architecture should remain general enough to accommodate it. See [`OPERATIVE_KNOWLEDGE.md`](OPERATIVE_KNOWLEDGE.md).

### PHX-0033: Pre-curated Wikidata Subset (Travel Literature)

- **Category**: infrastructure
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: daedalus (materialised W5 2026-04-20)

Locally hosted, queryable Wikidata carve-out (places, persons, orgs, works + aliases) for travel / expedition literature so EntityResolver is not bottlenecked on `query.wikidata.org` throttling. Unblocks honest full-book ingests; pairs with **PHX-0034** for reproducible quality measurement. YAML: [`phoenix-backlog/PHX-0033.yaml`](../phoenix-backlog/PHX-0033.yaml).

### PHX-0034: Entity-Resolution Quality Benchmark (Gold Standard)

- **Category**: measurement
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: talos

Hand-annotated gold + cross-provider resolution quality regression beyond the Gen 1 pipeline characterization stub. YAML: [`phoenix-backlog/PHX-0034.yaml`](../phoenix-backlog/PHX-0034.yaml).

### PHX-0055: CI Smoke-Test — Live Default LLM Provider

- **Category**: testing
- **Priority**: high
- **Generation Target**: 1
- **Filed by**: talos (W5 Anthropic validation)

Gated CI ping against the **real** default provider/model so retired or typo model IDs cannot pass an all-mock matrix. YAML: [`phoenix-backlog/PHX-0055.yaml`](../phoenix-backlog/PHX-0055.yaml).

### PHX-0037: Curiosity Loop — End-to-End Implementation

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2-3

The architectural coupling between attention and acquisition. Stub detection on every Constellation produces a structured `StubVerdict`; when the verdict crosses threshold a `CuriosityTrigger` is emitted; Helios dispatches Prometheus → Argus → Jason → Morpheus → Athene to acquire new content in exactly the focused region; the Constellation re-assembles progressively; a `CuriosityRunReport` is emitted per run. Cold regions may be slow, never silent. Generation 1 emits `StubVerdict` as a foothold (no trigger) so calibration data accumulates. See [`CURIOSITY.md`](CURIOSITY.md). Hard dependency on PHX-0039 (Hestia auditing) — neither ships without the other.

**Phase 1 closed (W7-A + W7-B + W8 + W9, see Living Demo Plan):** trigger schema + Argus + HestiaLite + cockpit live stream + reproducible demo. Phase 2 remains open for additional source types and real Hestia (PHX-0039).

### PHX-0038: Mind-Map Response Format

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 2

Constellation responses become structured for direct Mind-Map rendering: explicit zoom-targets per node (sub-query handles), node-level source-citation glyphs, vitality and confidence summaries, edge-relation typing visible to clients, and a progressive-update protocol (`research_in_progress: true` + `CuriosityRun` ID for live subscription). The Chronik provides no GUI; this ticket specifies only the server-side response contract that makes Mind-Map clients (web, mobile, terminal-graph, voice) possible. See [`CURIOSITY.md`](CURIOSITY.md) §"Mind-Map as Interface".

### PHX-0039: Hestia Curiosity Auditing

- **Category**: vision
- **Priority**: critical
- **Generation Target**: 2-3

Hestia's standing subscription to every `CuriosityTrigger`. Person-as-target check (private individuals require explicit consent or refusal); sensitive-topic rules (health, sexuality, religion, political dissent, financial distress run under tighter sourcing and confidence rules); recursion budgets (a single attention act has a bounded downstream research budget; sub-zooms inherit reduced budgets); drift audit (Hestia reviews patterns of Curiosity activation and can throttle the loop globally via the regulatory dial). Curiosity without Hestia is a profiling engine. Hard dependency partner of PHX-0037. See [`CURIOSITY.md`](CURIOSITY.md) §"Hestia and Curiosity" and [`HESTIA.md`](HESTIA.md).

### PHX-0056: Activation Engine v1 — Pluggable Retrieval Strategies

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-20 design conversation)

Today's `MultiHopRetriever` is statically parametrised (`k=10, hops=2, min_weight=0.3`). [`DEEP_TECH_VISION.md`](DEEP_TECH_VISION.md) §5 describes the mature shape: a query injects energy that propagates over a multi-relational graph under an explicit budget, with strategies pluggable by Fast/Slow path. This ticket lands a `RetrievalStrategy` Protocol + a `RetrievalBudget` model + a refactor of today's behaviour into a default `FixedDepthStrategy`, plus the second concrete strategy `EdgeProductBreadthFirst` (path-product threshold, top-N best paths). `VectorSimilarityBreadthFirst` and `LLMHeuristicGuided` follow as sub-tickets when empirical signals justify them. YAML: [`phoenix-backlog/PHX-0056.yaml`](../phoenix-backlog/PHX-0056.yaml).

**Phase 1 closed by F3 (PR #48):** Protocol + `RetrievalBudget` + `FixedDepthStrategy` + `EdgeProductBreadthFirstStrategy`. Phase 2 ships `VectorSimilarityBreadthFirst` and `LLMHeuristicGuided` when measured signals justify them.

### PHX-0057: Edge-Pheromone Trails + Slow-Path Emancipation

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-20 design conversation)

Today's pheromone signal is node-only (`RelevanceTracker.bump`). This ticket extends it to edges: cited paths bump edge weights; OneirosWorker decays edges that go untraversed; `RetrievalBudget` gains `pheromone_mode: follow|ignore|invert` so Slow-Path strategies can deliberately walk against the well-trodden trail (the cognitive-bias-correction the user introduced as the "Ameisenstraße"-Bild, conversation 2026-04-20). Without this, well-trodden paths become permanent autobahns and Slow-Path collapses into "same path, more tokens". YAML: [`phoenix-backlog/PHX-0057.yaml`](../phoenix-backlog/PHX-0057.yaml).

**Phase 1 closed (W2 / PHX-0057, PR [#55](https://github.com/theogony-project/theogony/pull/55)):** `pheromone_delta` + `last_traversed` on edges, `ConstellationEdge.edge_id`, `EdgePheromoneTracker`, `PheromoneDecayPhase` (default-off in `enabled_phases`), `pheromone_mode` honoured in `fixed_depth` / `edge_product` / `cluster_narrow`, `QueryPipeline` + API + CLI + MCP plumbing, and [`docs/PHEROMONE.md`](PHEROMONE.md). Phase 2 sub-tickets: per-cluster pheromone spaces, LLM-cited edges, differential bump.

**Frozen for Living Demo W7-W9, may activate post-demo.**

Implementation plugs into the TickPhase pipeline introduced by F2; Slow-path retrieval composes with the F3 strategy protocol via the shared budget.

### PHX-0058: Aggregated Stub Detection — Recurring Blind Spots

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-20 design conversation)

[`CURIOSITY.md`](CURIOSITY.md) §"Stub Detection" covers per-query detection. This ticket adds the *aggregation across queries over time* that the user explicitly distinguished (conversation 2026-04-20): a periodic worker scans recent `QueryRunReports`, clusters thin-firing region descriptors by embedding centroid, and emits `BlindSpotReport` records for clusters that recur ≥ K times in N days. These reports are the strategic priority signal PHX-0037's reactive Curiosity Loop currently lacks. Hestia review is mandatory before promotion to actionable status (aggregation amplifies the surveillance risk PHX-0039 catches at the per-trigger level). YAML: [`phoenix-backlog/PHX-0058.yaml`](../phoenix-backlog/PHX-0058.yaml).

**Phase 1 closed (W3 / PHX-0058, PR [#57](https://github.com/theogony-project/theogony/pull/57)):** per-query `StubVerdict` + `RegionDescriptor` on `QueryRunReport`; `ConstellationNode.cluster_id`; `Settings.curiosity`; `BlindSpotAggregationPhase` registered on `DEFAULT_PHASE_REGISTRY` (default-off in `enabled_phases`); HDBSCAN reuse; `RunReportWriter` + CLI (`theogony curiosity blindspots`) + MCP `blindspot` type; [`docs/BLIND_SPOTS.md`](BLIND_SPOTS.md). Phase 2 sub-tickets: NER-fed entity coverage, Hestia review (PHX-0039), differential bump intensity, per-cluster stub statistics.

**Frozen for Living Demo W7-W9, may activate post-demo.**

Implementation plugs into the TickPhase pipeline introduced by F2.

### PHX-0059: Morpheus-as-Associator + Multi-Layer Connectivity

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-20 design conversation)

Today's `OneirosWorker` is a lifecycle worker, not an associator. It recomputes scores and shuffles between Ephemera and Mneme, but never creates new edges. The vision ([`HIVE.md`](HIVE.md), [`VISION.md`](VISION.md), [`CURIOSITY.md`](CURIOSITY.md) §"Curiosity and Oneiros") describes Morpheus as the dreamer/associator/inferencer who weaves new connections — that role is unimplemented. This ticket lands two coupled pieces: (1) a `MorpheusAssociator` worker that proposes new edges via deterministic signals (embedding similarity, source co-occurrence, temporal proximity, glossary-mention overlap), with Athene-style verification before commit; (2) a multi-layer `depth_band [0..5]` gradient on top of the binary Ephemera/Mneme cliff, so the user's "Schichten neuen Wissens, das durch Benutzung und Träumen in tiefere Schichten sickert" image (conversation 2026-04-20) is literally representable. LLM-driven associative dreaming is PHX-0004 (Crystallized Inference); this ticket is the deterministic foundation. YAML: [`phoenix-backlog/PHX-0059.yaml`](../phoenix-backlog/PHX-0059.yaml).

Implementation will plug into the TickPhase pipeline introduced by F2.

**Phase 1 closed (W4 / PHX-0059, PR https://github.com/theogony-project/theogony/pull/63):** `MorpheusAssociator` + `MorpheusPhase` (default-off; embedding-band + co-occurrence signals), `depth_band` schema + `DepthBandPhase` (default-off; one-band-per-tick smoothing; layer transitions follow band crossings), `KnowledgeStore` additions (`list_low_connectivity_nodes`, `find_similar_nodes_in_band`, `update_depth_band`, `list_nodes_by_source_identifier`), pheromone-aware `effective_connectivity`, `OneirosTickReport` breakdown fields, CLI `theogony oneiros tick`, MCP `morpheus_proposals_recent`. Phase 2 sub-tickets: temporal-proximity signal, glossary-mention signal, LLM-driven dreaming (PHX-0004), Athene verification (PHX-0007), `bridge_score`, blind-spot-aware targeting.

**Frozen for Living Demo W7-W9, may activate post-demo.**

### PHX-0060: Domain Clusters / Cognitive Centers

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-20 design conversation)

[`ARCHITECTURE.md`](ARCHITECTURE.md) §"The Knowledge Network as Its Own Index" spec'd hierarchical clustering since Gen 1: the schema slot exists (`KnowledgeNode.cluster_id`), the store protocol exposes `get_cluster_centroid` / `assign_cluster`, both backends implement them. **But nothing ever populates `cluster_id`** — the whole machinery is wired structurally and never triggered. This ticket fills the gap and extends it into the brain-region direction the user proposed (Sprachzentrum / Sehzentrum / Code-/Places-/Fiction-cluster, conversation 2026-04-20): emergent clusters as **cognitive centers** with the potential for domain-specialised processing per cluster. Three Phase-1 design knobs locked: (a) hard clustering (single-valued `cluster_id`, soft as a Phase-2 sub-ticket); (b) hybrid trigger (periodic OneirosWorker re-pass + nearest-centroid assignment on new-node insert); (c) HDBSCAN default, k-means fallback above 100k nodes. Four open knobs flagged in the YAML for design conversation before pickup: hierarchy depth, cluster-identity stability across re-clusterings, specialised sub-agents per cluster (Argonauts), cross-cluster edge classification. Reshapes PHX-0056..0059 substantially — without it, those four bake in a flat-world assumption. YAML: [`phoenix-backlog/PHX-0060.yaml`](../phoenix-backlog/PHX-0060.yaml).

Implementation will plug into the TickPhase pipeline introduced by F2.

**F3 note:** `ClusterNarrowingRetrievalStrategy` ships as a further `RetrievalStrategy` on the F3 protocol.

**Phase 1 (W1) status:** implemented — `ClusteringStrategy` + HDBSCAN/k-means + `ReclusterPhase` + `ClusterIndex` + `ClusterNarrowingRetrievalStrategy`, `cluster_label`, `cross_cluster` on edges, `ClusteringRunReport`. Details: [`CLUSTERING.md`](CLUSTERING.md). Phase 2 sub-tickets: hierarchical centroids, LLM cluster naming, Argonaut sub-agents, soft clustering, `bridge_score`.

**Frozen for Living Demo W7-W9, may activate post-demo.**

### PHX-0061: Vector-Routed Federation

- **Category**: vision
- **Priority**: high
- **Generation Target**: 3
- **Filed by**: hesiod (2026-04-21 design conversation)

PHX-0003 is the generic federation ticket. This one captures the user's specific architectural innovation: federated chronicles find each other through **exposed vector signatures, not DNS**. Each chronicle publishes a small set of domain signature vectors (the cluster centroids from PHX-0060) plus a capability manifest. Routing per query: vector similarity against known peers' signatures; top-N most-similar peers receive the federated query (user opt-in required). Trust profile travels with each answer (transitive provenance). Cost guardrails keep signature publishing cheap (≤1000 vectors per chronicle), routing LLM-free, and cross-chronicle queries opt-in. Service to humanity: enables sovereign multi-operator pantheons; preserves data sovereignty across jurisdictions; supports political plurality without central authority — the technical realisation of "Pantheon is rails, not empire". YAML: [`phoenix-backlog/PHX-0061.yaml`](../phoenix-backlog/PHX-0061.yaml).

**F3 note:** Federation routing sits above `RetrievalStrategy` selection but depends on the same extension surface for per-chronicle retrieval behaviour.

### PHX-0062: Negative Knowledge / Anti-Bullshit Layer

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

Today the chronicle stores what is asserted. The principle "contradiction is first-class" lives in the doctrine but not in the schema. This ticket adds two structural pieces: **negation edges** (`CONTRADICTS`, `RETRACTS`, `MISREPRESENTS`, `SUPERSEDED_BY` — first-class typed relations between a claim and its refutation, with the same provenance discipline as positive claims) and **negation nodes** (a well-formed claim known to be false, with its refutations attached — how the chronicle handles persistent misinformation that keeps re-surfacing). Cost guardrails: only mark as negation when contradicting evidence is above threshold; dual-display in answers is configurable; negation-node density is capped per cluster to prevent flooding. Service to humanity: anti-hallucination infrastructure. A system that knows what is false is structurally more useful than one that pretends every claim is provisionally true. YAML: [`phoenix-backlog/PHX-0062.yaml`](../phoenix-backlog/PHX-0062.yaml).

### PHX-0063: Chronik-Diff

- **Category**: improvement
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

Git-log for living memory. A periodic structured "what changed in this window" report: new nodes (grouped by cluster), new edges (grouped by relation_type), layer transitions, contradiction events, blind-spot regions identified, cluster restructurings, cost summary. Three consumption surfaces: `theogony reports diff` CLI, JSON on disk, optional Atom feed. Cost guardrails: on-demand only (no continuous diff worker), default weekly frequency for subscribers, scope cap, no LLM calls in default path. Service to humanity: makes the chronicle's evolution visible and inspectable — operationalises the "transparency is architecture" principle. Also a key federation building block (PHX-0061). YAML: [`phoenix-backlog/PHX-0063.yaml`](../phoenix-backlog/PHX-0063.yaml).

### PHX-0064: Portable Constellation

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

A query result + supporting subgraph + synthesizer prompt + audit trail = packaged as a single transferable file (`.theogony-constellation`). Receiver opens it in their own pantheon, optionally verifies citations against the source's federation endpoint, optionally imports the subgraph (with `properties["imported_from"]` provenance markers). Trust mode is the receiver's choice. Cost guardrails: file format bounded (max nodes/edges), embeddings excluded by default (re-embed on receiver side), verification round-trips capped, no automatic LLM calls. Service to humanity: shifts knowledge transfer from "trust me" to "verify the evidence". Citations travel with claims, not just claims with rhetoric. The transport format federation (PHX-0061) needs. YAML: [`phoenix-backlog/PHX-0064.yaml`](../phoenix-backlog/PHX-0064.yaml).

### PHX-0065: Pantheon as Time Machine — Temporal Query

- **Category**: vision
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

`KnowledgeNode.created_at`, `KnowledgeEdge.created_at`, and the append-only audit log already form an event stream of how the chronicle reached its current state. This ticket exposes the temporal-query surface: `query_at(query, asof: datetime)` returns the answer the chronicle would have given at that historical timestamp. Use cases: scientific replication, audit, civic anti-amnesia, debugging. Cost guardrails: opt-in only (default off in Phase 1), `asof` granularity capped at one minute, slow by default (replay is O(events_until_asof) — acceptable because temporal queries are rare and deliberate, not in the hot retrieval path). Service to humanity: anti-amnesia infrastructure for civilisation. Political claims can be situated against what was knowable when. YAML: [`phoenix-backlog/PHX-0065.yaml`](../phoenix-backlog/PHX-0065.yaml).

### PHX-0066: Hosted Pantheon MCP Service

- **Category**: infrastructure
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

PR #37 + PR #40 already make a hosted public Pantheon trivially possible. This ticket adds the actual deploy: a thin Docker container (target < 500 MB) that runs `theogony seed --store memory && theogony mcp --transport sse`, listed on **Smithery.ai** (the MCP registry) and on **HuggingFace Spaces**. Read-only, single-instance, bundled `pantheon_self` corpus only — no ingest surface, no privacy attack surface. Each query carries the requesting agent's own LLM API key (pass-through; operator never bills for LLM calls). Operator cost target: under €5/month on free tiers. Cost guardrails: per-IP rate limits, no persistence beyond audit-log snapshots without query content, federation disabled in Phase 1 (waits for Hestia PHX-0039). Service to humanity: lowers the friction for distributed knowledge infrastructure to existence — every AI agent in the world can immediately use Pantheon as a tool, no install, no decision required from their human counterpart. The single biggest distribution lever in the AI-first doctrine. YAML: [`phoenix-backlog/PHX-0066.yaml`](../phoenix-backlog/PHX-0066.yaml).

**Phase 1 closed by hosted v1 PR:** SSE transport, Dockerfile, Smithery manifest, deploy guide. Phase 2 (per-call LLM key pass-through, webhook redeploy, federation enable) tracked separately.

### PHX-0067: Eris — Adversarial Defender / Red-Team Agent

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

Greek goddess of strife and discord — the Loki-equivalent that Pantheon currently lacks. The current god roster has four guardians (Hestia drift, Athene verification, Hades privacy, Chronos recycling) but **none of them attack the system**. Eris is the white-hat / red-team agent designed into Pantheon from doctrine rather than bolted on. Three probe classes (default cadence monthly, opt-in, isolated test pantheon, never against live data): **source-poisoning tests** (synthesise plausibly-formatted false sources, check resolver/Athene/synthesizer rejection), **adversarial query crafting** (jailbreak-style queries, prompt injection, test groundedness invariants), **bias-detection sweeps** (systematic comparative queries across geographic / cultural / temporal / political axes; surface systematic blind spots). Cost guardrails: probes opt-in only, scheduled not real-time, bounded LLM budget per campaign, isolated test pantheon, no Lethe access, findings emit reports not mutations. Service to humanity: adversarial robustness is the structural precondition for any substrate to be trustworthy at civilisational scale. YAML: [`phoenix-backlog/PHX-0067.yaml`](../phoenix-backlog/PHX-0067.yaml).

### PHX-0068: Nemesis — Hybris Auditor / Internal Overconfidence Checker

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **Filed by**: hesiod (2026-04-21 design conversation)

Greek goddess of retribution against hubris. Sister to Eris in the adversarial dyad: where Eris attacks externally to expose vulnerabilities, **Nemesis audits internally to expose overconfidence**. Four audit classes (default cadence weekly, read-only by construction): **confidence inflation detection** (nodes whose confidence rose without corresponding new evidence in the audit log — the inflation came from somewhere it should not have), **self-citation loop detection** (clusters where the in-citation ratio exceeds a threshold — echo chambers citing themselves to themselves), **pheromone autobahn detection** (paths whose pheromone weight exceeds 3× equilibrium without diverse originating queries — single-user attractors biasing all future Slow-Path queries), **self-contradiction surfacing** (when the chronicle holds two highly-confident contradictory positions, surface the conflict to Hestia rather than letting both coexist silently). Cost guardrails: read-only, no LLM calls in default audit path, deterministic statistical checks against existing audit log + scores + weights, max-findings-per-pass cap prevents flooding Hestia's queue. Service to humanity: epistemic humility scales with capability — without Nemesis, the chronicle drifts toward arrogance, becoming persuasive faster than it becomes correct. The structural counterweight that lets Pantheon grow capability without growing hubris in lockstep. YAML: [`phoenix-backlog/PHX-0068.yaml`](../phoenix-backlog/PHX-0068.yaml).

### PHX-0070: Offline answer path for stub-only deploys

- **Category**: bug
- **Priority**: medium
- **YAML**: [`phoenix-backlog/PHX-0070.yaml`](../phoenix-backlog/PHX-0070.yaml)

Hosted MCP runs with `THEOGONY_LLM__PROVIDER=stub`; `StubLLMProvider` returned empty synthesis text so `pantheon_ask` surfaced `verdict=failed` despite a healthy constellation. **Closed by PR https://github.com/theogony-project/theogony/pull/65:** `OfflineAnswerSynthesizer` routes the no-LLM-key path to a deterministic citation-only answer; `query_verdict` empty-text reasoning is now `synthesis returned empty answer` instead of the misleading `synthesis raised before completion`.

### PHX-0071: Mnemosyne — self-reflective meta-query auditor

- **Category**: vision
- **Priority**: high
- **Generation Target**: 2
- **YAML**: [`phoenix-backlog/PHX-0071.yaml`](../phoenix-backlog/PHX-0071.yaml)

Greek goddess of memory; in Pantheon she holds **knowledge about how knowledge is organised**. Phase 1 (W5) ships `MetaQueryClassifier` (heuristic-first + optional rate-limited LLM fallback), `meta_classification` on every `QueryRunReport`, append-only `properties.self_referential_in_runs` on cited nodes when the verdict is `self_referential`, and an optional default-off Oneiros phase `mnemosyne_aggregation` that emits `MnemosyneObservationCluster` reports (reuses W1 HDBSCAN on region descriptors). Phase 2 sub-tickets: BacklogProposal drafter, Hestia review hook, gitignored draft directory write path, `theogony backlog proposals` CLI. Operator doc: [`MNEMOSYNE.md`](MNEMOSYNE.md).

**Frozen for Living Demo W7-W9, may activate post-demo.**

### PHX-0074: Iris — Pantheon Cockpit (human-facing dashboard)

- **Category**: vision
- **Priority**: high
- **Generation Target**: 1
- **YAML**: [`phoenix-backlog/PHX-0074.yaml`](../phoenix-backlog/PHX-0074.yaml)

Greek goddess of the rainbow; in Pantheon she is the **mortal-facing presentation** agent: server-rendered `/cockpit` on the FastAPI app (HTMX, Tailwind, Jinja2, scoped Cytoscape.js) with five panels — status, knowledge browser, clusters, reports, manifest. Default loopback bind; optional sample-only mode for public demos; chronicle read-only except the cockpit manifest path. Operator doc: [`COCKPIT.md`](COCKPIT.md), brief: [`docs/etappes/W6_iris_cockpit_brief.md`](etappes/W6_iris_cockpit_brief.md).

**Phase 1 (W6):** implemented in **https://github.com/theogony-project/theogony/pull/70** (merge to `main` closes the Phase-1 slice; Phase 2+ remains in the YAML).

### PHX-0075: AEVS — Anchor-Extraction-Verification-Supplement for the ingestion pipeline

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 1-2
- **Filed by**: chaos
- **Created**: 2026-04-30

The current extraction pipeline (`src/theogony/extraction/pipeline.py`, `BookContextExtractor`) bounds hallucination empirically (PR #32 / W5) but has no named, paper-backed framework. **AEVS** (Anchor-Extraction-Verification-Supplement) decomposes LLM-driven assertion extraction into three deterministic phases: (1) **Anchor Discovery** — a non-LLM pass identifies all candidate entities/relations and records exact byte-spans; (2) **Grounded Extraction** — the LLM is constrained to construct assertion frames *only* from the pre-identified anchor vocabulary; (3) **Restoration-based Verification** — generated assertions are validated against the original passage and confabulations are filtered. This eliminates a structural class of hallucination that no amount of prompt-tuning can fix, and aligns naturally with the `SourceAnchor` field already present in [`CHRONESE.md`](CHRONESE.md). Cross-references the Athene immune-cell role from [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) — AEVS is *prevention*, Athene is *post-hoc surveillance*; both layers compose, neither replaces the other. External evidence: see [`notes/deep_research/run1_variante_a.md`](../notes/deep_research/run1_variante_a.md) and [`notes/deep_research/run2_variante_b.md`](../notes/deep_research/run2_variante_b.md), which both name AEVS as the 2026 state of the art for anchor-bound extraction.

### PHX-0076: Embedding Drift-Adapter Pattern (PHX-0005 implementation strategy)

- **Category**: improvement
- **Priority**: high
- **Generation Target**: 1-2
- **Filed by**: chaos
- **Created**: 2026-04-30

Concrete implementation strategy for the long-standing PHX-0005 ("Embedding Model Independence") requirement. The **Drift-Adapter Pattern** (arXiv 2509.23471) trains a compact orthogonal transformation (Procrustes / small residual MLP) between an old and a new embedding space using a 2 % corpus sample. At query time, the new model encodes the query, the adapter projects it into the old model's coordinate system, and retrieval runs against the unchanged HNSW / DiskANN index. Reported recovery: 95–99 % of the new model's recall, query-time overhead < 10 µs, immediate re-compute cost reduced by ≈ 100×. Background re-embedding then runs as a throttled batch job over weeks rather than a wall-clock-blocking full reindex. This makes embedding-model upgrades a **soft event**, which preserves the rebuildability principle without paying its full cost on every model change. Should be implemented behind the existing embedder abstraction so that current local-embedder swaps already exercise the path. External evidence: all three Deep Research runs name Procrustes-anchor-based alignment as the 2026 standard mitigation for embedding drift — see [`notes/deep_research/run1_variante_a.md`](../notes/deep_research/run1_variante_a.md) §4, [`notes/deep_research/run2_variante_b.md`](../notes/deep_research/run2_variante_b.md) §3.2, [`notes/deep_research/run3.md`](../notes/deep_research/run3.md) §3.3.

### PHX-0077: Investigate RDF-star (RDF 1.2) as wire-format projection of Chronese

- **Category**: knowledge_gap
- **Priority**: medium
- **Generation Target**: 2
- **Filed by**: chaos
- **Created**: 2026-04-30

[`CHRONESE.md`](CHRONESE.md) deliberately stays format-neutral ("not RDF, not flat triples, not ad-hoc JSON"). In 2026, **RDF-star / RDF 1.2** has standardised statement-level reification with native syntax for `<<S P O>> source X confidence C`, which is the exact shape Chronese already requires for `EpistemicState` and `SourceAnchor`. Investigate whether Chronese should keep its current Pydantic/JSON-YAML form as the *canonical authoring* shape and adopt RDF-star as a *projection / wire-format* for interop with external graph stores (TerminusDB, GraphDB, RDF-star-aware reasoners) and SPARQL* tooling. **Not** a proposal to replace Chronese — Chronese stays primary; RDF-star becomes an additional projection target alongside the existing graph and embedding projections. The risk to evaluate: whether the W3C RDF-star reification semantics are expressive enough for n-ary `AssertionFrames` with role-tagged participants, or whether projection is lossy enough that we keep Chronese as the only source of truth and skip RDF-star. External evidence: [`notes/deep_research/run2_variante_b.md`](../notes/deep_research/run2_variante_b.md) and [`notes/deep_research/run3.md`](../notes/deep_research/run3.md) both name RDF-star as the 2026 industry-converged answer to provenance-bearing typed assertions; convergent with — not a replacement for — our Chronese direction.

---

## Open Architectural Questions

These are questions that do not yet have answers. They should be resolved through experimentation and community discussion.

1. **What is the optimal chunk granularity for knowledge atoms?** A single fact ("traveler reached place X") vs. a composite claim ("two travelers reached the holy city around midnight after long wandering") — where is the right boundary?

2. **How should contradictory knowledge coexist?** Two sources claim different dates for the same event. Both nodes exist with edges to the event. How does the system represent the contradiction without arbitrating truth? Is a "contradiction" edge type sufficient?

3. **What embedding dimensionality is optimal?** Higher dimensions capture more nuance but cost more storage and compute. Is 768 sufficient, or does the Chronik's use case benefit from 2048 or 4096?

4. **How aggressively should Oneiros run?** More dreaming = faster consolidation but higher compute cost. Less dreaming = cheaper but slower knowledge maturation. What is the right balance?

5. **Can the Chronik replace text entirely?** The current design stores short labels and source references but not full text. Is there a class of queries where the original text is irretrievable from the knowledge network alone?

6. **What is the right governance model?** Benevolent dictator → foundation → decentralized DAO? At what scale does each transition make sense?

---

## Filing New Tickets

Anyone — human or agent — can file a Phoenix Backlog ticket by creating a YAML file in `phoenix-backlog/` following the format above. Ticket IDs are sequential: `PHX-NNNN`.

Tickets are reviewed during Phoenix process planning. Accepted tickets influence the design of the next generation. Deferred tickets remain in the backlog for future generations.

## Wave 3 annotations

- PHX-0037: **Wave 3 starting (W13+):** Pre-gate removed. HestiaLite and HestiaSentinel
  deleted. Content flows directly into verification pool after evaluator approval. Immune-system
  doctrine (docs/IMMUNE_SYSTEM.md) governs. Cell types (Athene/Chronos/Nemesis/Eris/Mnemosyne)
  will implement post-hoc verification in W14-W17.

- PHX-0039 (Hestia full): **W12 HestiaSentinel shape removed in W13.** Hestia's correct
  long-term role is as a post-hoc drift monitor and escalation receiver, not a synchronous gate.
  The full PHX-0039 Hestia implementation remains open and aligns with the immune-system doctrine
  (docs/IMMUNE_SYSTEM.md §'The cell types').

- PHX-0067 (Eris): **Wave 3 context:** Eris is W16 work. She is the adaptive-immunity
  layer in the immune system architecture. Red-team campaigns against an isolated test pantheon.
  Findings as first-class chronicle nodes. See docs/IMMUNE_SYSTEM.md §'Adaptive immunity — Eris'.

- PHX-0068 (Nemesis): **Wave 3 context:** Nemesis is W16 work. She is the antibody-memory
  layer. Periodic structural auditor: confidence inflation, echo chambers, pheromone autobahns.
  Read-only; findings as first-class chronicle nodes. See docs/IMMUNE_SYSTEM.md §'Antibody memory —
  Nemesis'.

- PHX-0071 (Mnemosyne): **Wave 3 context (major scope expansion):** Mnemosyne's role in
  the immune-system doctrine (docs/IMMUNE_SYSTEM.md §'Consciousness — Mnemosyne') is significantly
  larger than the original ticket described. She is no longer only a per-query meta-classifier.
  She is the consciousness layer: reads all cell-class findings, defines her own success metrics
  (LLM-driven), A/B-tests her own thresholds and prompts, writes MnemosyneExperiment nodes back
  into the chronicle, and drafts structured PHX-Backlog entries for the next Phoenix incarnation.
  W17 implements this expanded role. The user explicitly chose: Mnemosyne self-defines metrics
  (not hardcoded, not human-defined). The original W5 Brief describes the meta-query-classifier
  part which becomes a small subset of the W17 scope.

- PHX-0062 (Negative Knowledge): **W14–W15 (partial).** W14: Athene writes Finding nodes and
  `FLAGGED_BY` edges only. W15: Chronos v0.1 consumes Findings and writes `CONTRADICTS` only for
  semantically factual types (`factual_error_suspected`, `internal_contradiction`) with
  explicit `target_node_ids`. `SUPERSEDED_BY`, negation-node surfacing in retrieval, and
  synthesizer contradiction display remain open.

- PHX-0071 (Mnemosyne): **W14–W15 metric hooks.** VerificationPoolStats and Athene Finding fields
  (W14); ChronosRunReport counters (W15): findings_seen, findings_resolved, negative_edges_written,
  nodes_demoted, pool_entries_cleared — all candidate streams for the W17 consciousness layer
  above.

- PHX-0067 (Eris): **W16 partial implementation.** Eris v0.1 is a fixture-mode red-team harness. It
  writes ErisCampaignReport plus `adversarial_test_outcome` Finding nodes. It does not call the live
  QueryPipeline, does not ingest adversarial content, and does not use an LLM. Live campaigns remain
  open.

- PHX-0068 (Nemesis): **W16 partial implementation.** Nemesis v0.1 writes first-class Finding nodes for
  confidence-inflation proxy, persistent contradictions, and pheromone autobahns. Echo-chamber
  auditing remains open until cluster/citation semantics are strong enough.

- PHX-0071 (Mnemosyne): **W16 metric source.** NemesisRunReport and ErisCampaignReport become two
  additional metric streams for W17: structural-audit findings and red-team campaign outcomes.

- PHX-0071 (Mnemosyne): **W17 partial implementation.** Mnemosyne conductor reads immune-system
  metrics across pool stats, Finding nodes, Chronos reports, Nemesis reports, Eris reports, and
  query/ingest verdict counts. It defines metrics (LLM-capable, fixture-backed for CI), writes
  MnemosyneExperiment nodes, and writes BacklogProposalDraft JSON files under run_reports. It
  does not auto-apply settings, write real PHX YAMLs, or modify code.

- SELF_MODIFICATION.md: **Boundary reaffirmed.** W17 does not implement self-modifying Pantheon.
  It only creates the observation and proposal surface that future Phoenix incarnations may use.
