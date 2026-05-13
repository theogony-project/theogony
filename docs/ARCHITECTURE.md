# Architecture

> **Precedence.** This document describes the **Generation-1 architecture as currently implemented** (four-layer pipeline, in-memory / Neo4j store, KnowledgeNode / KnowledgeEdge schema with single embedding and string relation types). For **substrate behaviour, runtime, and use**, the operative doctrine is the MESH triplet:
>
> - [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) — two-tier nodes (Observation Chunks Tier 0 + Consolidated Nodes Tier 1+), edge anatomy (quantitative core + optional semantic descriptors), super-linear decay, saturation, atrophy ≠ death, agent-driven cleanup, staged therapy
> - [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) — LanceDB nodes + PyTorch sparse CSR edges + delta buffer, MVCC concurrency, batched-SpMV runtime, Hot / Warm / Cold tiering
> - [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) — diversified injection (MMR + weight-class stratification + sub-mesh signature), three-factor reinforcement learning, frame-sensitive resonance, multi-modal extension
>
> Where this document's schema, store interface, or memory model conflict with the MESH triplet at the substrate level, the triplet is operative. The four-layer architecture and the agent-roster sections below remain useful as a description of the Gen-1 system as it ships today.

## Overview

Theogony is a four-layer system with a cross-cutting **Pantheon agents** framework (Zeus, Argus, Athene, … — see [`GLOSSARY.md`](GLOSSARY.md)). The central component is **the Chronik** — Generation 1's living vector-graph knowledge network that stores knowledge as interconnected embeddings, relations, and provenance rather than as static text. Long-horizon direction for the *substrate* itself is the **Pantheon** (planetary chronicle); the Chronik is the first operational instantiation. At maturity, the graph and vector layers are operational projections of a deeper canonical semantic layer: **Chronese**.

### The Three Cognitive Layers

The Chronik's agent ecosystem maps onto three cognitive functions. Language enters and exits at the edges — everything in between operates in vector space. See [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) for the binding doctrine.

| Layer | Function | Agents | Medium |
|---|---|---|---|
| **Observe** | Read the world into vectors | Argus, Kadmos, Nous | Text in → vectors out |
| **Learn** | Consolidate, connect, dream | Chronik, Oneiros | Vectors + edges only |
| **Remember** | Retrieve and express | Iris, Kalypso, Poseidon | Vectors in → text out |

**Observe** brings knowledge into the system. Argus finds sources. Kadmos translates raw text into a primitive vector mesh — nodes with embeddings, local typed edges, no text stored. Nous weaves the primitive mesh into a denser synthesis graph: diagonal edges, cross-paragraph connections, synthesis nodes at higher abstraction levels. After Kadmos, no source text remains in the system.

**Learn** is the internal life of the Chronik. Oneiros is not a batch job — it is a continuous thinker that simulates both Observe and Remember internally: it runs activation patterns across existing knowledge, treats the results as new observations, and writes back denser connections. This is how the Chronik grows wiser without reading new texts.

**Remember** translates vector constellations back into meaning for humans and agents. Iris activates a subgraph via Spreading Activation and generates language from the vector structure — not by retrieving stored text, but by formulating from structure. Kalypso discovers connections nobody queried. Poseidon synthesises long-form narratives. Both do something beyond retrieval: *remembering as creation* — producing from the existing structure something that was not yet explicitly there.

## Terminology Alignment

Canonical terminology for this document is defined in [`GLOSSARY.md`](GLOSSARY.md).

For consistency across the project, this architecture document uses the following meanings:

- **Theogony** = the overall project, architecture, and open initiative
- **Pantheon** = long-horizon planetary chronicle / knowledge substrate (not the agent roster)
- **Pantheon agents** = mythological-role agent architecture (Zeus, Argus, …)
- **Chronik** = the living knowledge system at the center of Theogony (Gen 1 operational layer)
- **Akasha** = the global public knowledge space
- **Lethe Vaults** = private, permission-bound knowledge spaces
- **Ephemera** = the fresh, unverified memory layer
- **Oneiros** = the continuous dream process of consolidation and association
- **Mneme** = the trusted, permanent memory layer
- **Chronese** = the proposed canonical semantic language beneath graph and vector projections
- **Constellation** = the structured, query-relevant working set returned to agents
- **Metis** = the future advisory agent working across Akasha, Lethe, and Norm Space

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Retrieval API                                     │
│  Agent-facing service for knowledge access                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: The Chronik                                       │
│  Vector-graph knowledge network                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Ephemera │→ │ Oneiros  │→ │  Mneme   │                  │
│  │ (raw)    │  │ (dream)  │  │ (known)  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Extraction                                        │
│  Raw content → knowledge atoms                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Acquisition                                       │
│  Adapters for content sources                               │
└─────────────────────────────────────────────────────────────┘

Cross-cutting: Pantheon agents (agent system)
```

## Mortal-facing surfaces

Three surfaces let people interact with Theogony without writing agent code:

- **Pantheon Cockpit (Iris, [PHX-0074](../phoenix-backlog/PHX-0074.yaml))** — server-rendered HTML dashboard at `/cockpit` on the FastAPI app: status, knowledge browser, cluster drill-down, run reports, and a single editable manifest file under `data_dir`. Defaults to loopback binding; optional **sample-only** mode caps what a public URL may show. Operator documentation: [`COCKPIT.md`](COCKPIT.md). Phase 1 is chronicle-read-only except that manifest path.
- **Operator CLI** — `theogony …` for ingest, reports, workers, and diagnostics.
- **MCP over HTTP/SSE** — agent-facing `pantheon_*` tools on hosted and local deploys ([`PHX-0066`](PHOENIX_BACKLOG.md#phx-0066-hosted-pantheon-mcp-service) / [`hosted/README.md`](../hosted/README.md)).

## Layer 0: Acquisition

Acquisition adapters bring raw content into the system. Each adapter implements a common protocol:

```python
class AcquisitionAdapter(Protocol):
    async def search(self, query: str) -> list[SourceCandidate]: ...
    async def acquire(self, candidate: SourceCandidate) -> RawContent: ...
    def supports(self, source_type: str) -> bool: ...
```

The adapter interface is radically open by design. Today's adapters fetch text from APIs. Future adapters could control a robot reading physical books in a library, process satellite imagery, or ingest sensor data. The extraction pipeline downstream does not care where the content came from.

### Gen 1 Adapters

- **GutenbergAdapter** — downloads books from Project Gutenberg via the Gutendex API
- **WebSearchAdapter** — searches the web and retrieves page content
- **WikidataAdapter** — queries Wikidata SPARQL for entity information

### Future Adapters

- ArXiv, PubMed, Europeana, Internet Archive
- Library automation (physical book retrieval and scanning)
- User upload / organizational data import (via Jason)
- Real-time feeds (news, social media, sensor data)

## Layer 1: Extraction

The extraction pipeline transforms raw content into knowledge atoms — the nodes and edges that populate the Chronik.

```
RawContent
  │
  ├─ Text Cleaning ─── normalize, remove boilerplate
  │
  ├─ Named Entity Recognition ─── identify entities (persons, places, concepts, events, ...)
  │
  ├─ Relation Extraction ─── identify typed relations between entities
  │
  ├─ Entity Resolution ─── align entities with Wikidata (Q-IDs) and/or assign native Chronik ids (`AKA-…`); see *Identity: bootstrap vs maturity* under KnowledgeNode
  │
  ├─ Embedding Generation ─── compute semantic vectors for each knowledge atom
  │
  ├─ Label Generation ─── create short human-readable labels
  │
  ├─ Source Reference Creation ─── anchor each atom to its origin (URL, page, snippet)
  │
  └─ Output: list[KnowledgeNode] + list[KnowledgeEdge] → Ephemera
```

### Canonical Semantic Layer (Chronese)

The extraction pipeline should eventually emit a richer canonical semantic form before graph and vector projection. We call this form **Chronese**.

Chronese is:

- language-neutral
- event-centric
- provenance-bound
- epistemically explicit
- projection-friendly

In Generation 1, Chronese can exist as strict JSON/Pydantic structures rather than a separate runtime language. The critical architectural point is that graph nodes, edges, and embeddings should be understood as *projections* from richer semantic assertion frames, not as the deepest truth of the system.

### Tiered Processing for Cost Efficiency

Not all extraction steps require expensive models:

| Step | Cheap (default) | Expensive (escalation) |
|------|-----------------|----------------------|
| NER | spaCy, GLiNER | LLM-based extraction |
| Relations | Pattern matching, lightweight models | LLM-based relation extraction |
| Entity Resolution | Wikidata SPARQL exact match | LLM disambiguation |
| Embeddings | Local sentence-transformers | OpenAI / Cohere embeddings |
| Labels | Template-based | LLM-generated |

Escalation happens when the cheap method produces low-confidence results. This keeps costs minimal for routine extraction while preserving quality for difficult cases.

## Layer 2: The Chronik

The core of the system. A navigable vector-graph knowledge network.

### Data Model

#### KnowledgeNode — A Knowledge Atom

In the long view, nodes and edges are operational projections from richer Chronese assertion frames. They remain the practical unit for retrieval, indexing, and agent access, while the deeper semantic form preserves event structure and epistemic detail.

#### Identity: bootstrap vs maturity

**Bootstrap (Gen 1):** Entities are minted with **native `AKA-…` ids** in the store. **Wikidata Q-ids** (and other catalog ids) live in `external_ids` when resolution succeeds. That gives deduplication, linking, and migration safety without pretending Wikidata is the philosophical center of the system.

**Maturity (Pantheon direction):** The north-star model is **Pantheon-native identity first**, external registries second — including entities public systems will never enumerate. The Chronik's current shape is a deliberate down-payment on that story, not its final form. See [`PANTHEON_VISION.md`](PANTHEON_VISION.md) § "From Imported IDs to Native Identity".

The scope of a knowledge node is unbounded. It represents everything from a macro-concept (Quantum Mechanics) to the minute details of a specific individual (a "digital twin"). Every person, place, thing, event, and timestamp that exists in the source material becomes a node.

```python
class KnowledgeNode:
    id: str                       # Gen 1: AKA-{…} native Chronik id (primary key in store)
    embedding: list[float]        # semantic vector (768-4096 dimensions)
    node_type: NodeType           # person | place | concept | event | claim | ...
    label: str                    # short human-readable label
    layer: Layer                  # ephemera | mneme
    cluster_id: str | None        # knowledge region membership
    external_ids: dict[str, str]  # {"wikidata": "Q2444884", "gutenberg": "43497", ...}
    source_ref: SourceRef         # provenance anchor for citation
    scores: NodeScores            # confidence, relevance, connectivity, freshness
    vitality: float               # computed lifecycle score
    created_at: datetime
    last_accessed: datetime
    last_verified: datetime | None
```

#### KnowledgeEdge — A Typed, Weighted Relation

```python
class KnowledgeEdge:
    source_id: str
    target_id: str
    relation_type: str            # P-ID style (like Wikidata properties) or custom
    weight: float                 # 0.0-1.0, strengthened/weakened over time
    confidence: float             # how certain is this relation
    bidirectional: bool
    provenance: Provenance        # extraction | inference | wikidata | query_cooccurrence | agent
    created_at: datetime
```

#### SourceRef — Provenance Anchor

Every knowledge atom retains a traceable link to its origin:

```python
class SourceRef:
    source_type: str              # gutenberg | web | wikidata | arxiv | library | user | ...
    url: str | None               # link to original
    identifier: str | None        # book ID, DOI, ISBN, library call number
    location: str | None          # page, chapter, paragraph, character offset
    snippet: str | None           # short verbatim quote (1-3 sentences) for citation
    accessed_at: datetime
```

#### NodeScores and Vitality

```python
class NodeScores:
    confidence: float     # how well-verified (sources, corroboration, Athene checks)
    relevance: float      # how often accessed or linked (query hits, edge references)
    connectivity: float   # how well-connected in the graph (degree, centrality)
    freshness: float      # time-decayed recency

vitality = w1*confidence + w2*relevance + w3*connectivity + w4*freshness
```

Vitality determines the lifecycle of a node. The threshold for action (compress, archive, delete) is **dynamic** — adjusted by storage pressure, query latency, and knowledge density in the node's region.

### Memory Architecture

Knowledge flows through three phases:

**Ephemera** — Raw, unverified, freshly extracted. High detail, low confidence. Every new knowledge atom starts here.

**Depth bands (PHX-0059 Phase 1)** — Beyond the binary Ephemera/Mneme `layer`, every node carries `depth_band ∈ [0..5]` (see [`DEPTH_BANDS.md`](DEPTH_BANDS.md)). An optional Oneiros phase (`depth_band`, default **off**) steps the ladder at most one band per tick and performs `promote` / `degrade` exactly at the 2↔3 boundary crossings.

**Oneiros** — Not a storage layer, but the continuous dream process. Background agents work on Ephemera nodes:
- Morpheus: finds associations, creates edges, infers new knowledge. Phase 1 ships as an opt-in tick phase (`morpheus`, default **off**) with deterministic **embedding-band** and **source co-occurrence** signals; proposals are `INFERENCE` edges at low confidence until Athene exists. See [`MORPHEUS.md`](MORPHEUS.md).
- Athene: verifies facts, cross-checks sources, adjusts confidence
- Chronos: identifies redundancy, staleness, decay candidates

This mirrors hippocampal replay in the human brain — the process by which daily experiences are consolidated into long-term memory during sleep. Except the Chronik never sleeps. Oneiros runs continuously, constantly firing connections into existing areas of knowledge.

The Gen-1 **OneirosWorker** tick is implemented as an ordered **TickPhase** pipeline (`src/theogony/memory/tick_phase.py`, `tick_phases.py`): each lifecycle step (snapshot, neighbour counts, score recompute, bulk write, promote, degrade, optional **depth_band**, **morpheus**, optional **recluster**, …) is a small async phase sharing a mutable `TickContext`. Operators can disable or reorder phases via `Settings.oneiros.enabled_phases`; future tickets add phases instead of extending a single god-method.

**Edge pheromones (PHX-0057 Phase 1)** — After each query in the default `follow` mode, cited graph edges receive a small `pheromone_delta` bump and `last_traversed` stamp (`EdgePheromoneTracker`). An optional Oneiros phase (`pheromone_decay`, default **off**) decays overlays on edges that have been idle past `Settings.oneiros.edge_pheromone.decay_horizon_days`. Retrieval can set `pheromone_mode` to `ignore` or `invert` for Slow-Path reads that skip write-back. See [`PHEROMONE.md`](PHEROMONE.md).

**Mneme** — Promoted knowledge. High confidence, well-connected, verified. This is "known" knowledge. Promotion requires crossing a confidence threshold AND a minimum connectivity threshold — an isolated high-confidence fact is still suspect.

**Degradation** flows the other way: Mneme nodes whose vitality drops below the dynamic threshold are demoted back toward Ephemera, compressed, archived, or deleted.

### The Knowledge Network as Its Own Index

At exabyte scale, flat vector search is impossible. The Chronik solves this by making the graph structure itself the navigational index:

1. **Clustering (PHX-0060 Phase 1, implemented)**: Nodes carry a single-valued `cluster_id` (technical handle, re-minted when cluster membership shifts beyond a Jaccard threshold) and an optional `cluster_label` (stable semantic name when inherited across passes). Each cluster has a centroid vector. **Phase 1 is flat** (one level of clusters); centroids-of-centroids and deeper hierarchy are explicitly deferred to Phase 2. Periodic **recluster** runs inside `OneirosWorker` (opt-in via `enabled_phases`); **insert-time** assignment uses an in-memory `ClusterIndex` (nearest centroid) so new nodes land in roughly the right region before the next full pass.

2. **Entry via vector similarity**: A query embedding can be compared against cluster centroids (fast, approximate), narrowing to the top-N regions — this is the optional `cluster_narrow` retrieval strategy, which composes with the default `fixed_depth` graph walk (see [`RETRIEVAL_STRATEGIES.md`](RETRIEVAL_STRATEGIES.md) and [`CLUSTERING.md`](CLUSTERING.md)).

3. **Navigation via graph traversal**: Within the region, the query follows weighted edges. Traversal cost is O(depth × branching factor), not O(n).

4. **Weight thresholds prune the search space**: Only edges above a dynamic weight threshold are followed. The product of weights along a path must exceed a minimum — weak paths are abandoned.

5. **Multi-hop recursive search**: From each discovered node, another similarity search can be initiated, finding related knowledge that the initial entry point might have missed. Deduplication prevents combinatorial explosion.

**Cross-cluster edges:** every `KnowledgeEdge` may carry `properties["cross_cluster"]: bool`, set at insert time from endpoint `cluster_id`s and recomputed after each recluster sweep.

This makes the Chronik queryable in milliseconds, regardless of total size. The complexity of a query depends on the *depth* of the question, not the *size* of the knowledge base.

### Sharding for Scale

The hierarchical cluster structure maps naturally to distributed deployment:

- Each major knowledge region can live on a separate shard (server/cluster)
- Cross-shard edges connect regions (e.g., an explorer biography in Literature connects to "Tibet" in Geography)
- A routing layer directs queries to the right shard based on cluster centroids
- The Phoenix process can reorganize shards as the knowledge landscape evolves

Gen 1 runs on a single instance. The architecture supports sharding from day one through the cluster abstraction, even if it is not yet distributed.

### KnowledgeStore Interface

All access to the Chronik goes through an abstract interface. This allows backend replacement (Neo4j today, custom engine tomorrow) without changing any other layer.

```python
class KnowledgeStore(Protocol):
    # Vector search
    async def vector_search(self, embedding, k, layer, filters) -> list[ScoredNode]

    # Graph traversal
    async def traverse(self, start_id, max_depth, min_weight, relation_types) -> list[Path]

    # The core operation: multi-hop vector + graph search
    async def multi_hop_search(self, embedding, k, hops, min_weight) -> list[ScoredNode]

    # Node/edge CRUD
    async def upsert_node(self, node: KnowledgeNode) -> str
    async def upsert_edge(self, edge: KnowledgeEdge) -> None
    async def get_node(self, node_id: str) -> KnowledgeNode | None
    async def get_neighborhood(self, node_id, depth, min_weight) -> Constellation

    # Lifecycle
    async def promote(self, node_id: str) -> None
    async def degrade(self, node_id: str) -> None
    async def delete(self, node_id: str) -> None

    # Cluster management
    async def get_cluster_centroid(self, cluster_id: str) -> list[float]
    async def assign_cluster(self, node_id, cluster_id) -> None

    # Bulk operations (Phoenix process)
    async def export_layer(self, layer: Layer) -> AsyncIterator[KnowledgeNode]
    async def import_nodes(self, nodes: AsyncIterator[KnowledgeNode]) -> None
```

Gen 1 implementation: `Neo4jKnowledgeStore` — leverages Neo4j's native vector indexes and Cypher for combined graph+vector queries.

**Retrieval strategies (PHX-0056 Phase 1 + PHX-0060 Phase 1).** Graph+vector navigation is not
hard-wired to a single algorithm: a `RetrievalStrategy` protocol turns a query
embedding plus a `RetrievalBudget` into a `MultiHopResult`. The default
`FixedDepthStrategy` preserves the original `multi_hop_search` behaviour; optional
strategies (`EdgeProductBreadthFirstStrategy`, `ClusterNarrowingRetrievalStrategy`) plug in via settings, HTTP,
or pipeline construction. See [`RETRIEVAL_STRATEGIES.md`](RETRIEVAL_STRATEGIES.md).

## Layer 3: Retrieval API

The agent-facing service. This is how LLMs and agents access the Chronik.

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Natural language query → multi-hop search → constellation |
| `/search` | POST | Direct vector similarity search |
| `/advise` | POST | Structured advisory workflow for Metis: constellation + constraints + norms → counsel |
| `/node/{id}` | GET | Get a node with its neighborhood (the "hover lens") |
| `/node/{id}/neighborhood` | GET | Get graph neighborhood to depth N |
| `/ingest` | POST | Submit content for extraction and ingestion |
| `/gaps` | GET | What does the Chronik not know well? (Prometheus output) |
| `/health` | GET | System status, metrics, layer sizes |

### The Constellation Response

When an agent queries the Chronik, it does not receive text chunks. It receives a **Constellation** — a structured subgraph of relevant knowledge:

```python
class Constellation:
    nodes: list[ConstellationNode]     # relevant nodes with labels, types, scores
    edges: list[ConstellationEdge]     # relevant edges with types, weights
    suggested_sources: list[SourceRef] # citations the agent can use
    gaps: list[str]                    # identified knowledge gaps
```

The agent (LLM) interprets this constellation and synthesizes a human-readable answer. Every entity in the answer can be linked back to a node in the Chronik, enabling deep exploration (the "hover lens" effect).

### Intuition-Guided Retrieval

The expected query flow for an LLM using the Chronik:

1. **Receive question** from user
2. **Use trained intuition** to understand the domain and formulate a search plan
3. **Call `/query`** with the natural language question
4. **Receive constellation** — nodes, edges, sources, gaps. This constellation acts as an instant, massive context engine. For example, in political fact-checking (where human amnesia is a vulnerability), the constellation immediately surfaces historical contradictions, parallel events, and underlying networks behind claims about US/EU/China policy.
5. **Synthesize answer** from the constellation, citing sources.
6. **Link entities** — each mentioned entity references its Chronik node.
7. If gaps are significant, **trigger acquisition** via `/ingest`

The LLM does not need to know facts. It needs to know how to navigate the Chronik and interpret constellations. This is a fundamentally different skill from memorization.

### Curiosity Loop

Retrieval and acquisition are not separate phases in maturity. They are coupled by attention.

Every query, every zoom into a Constellation node, and every contextual ask runs a structured **stub check** on the assembled Constellation: node count, edge density, vitality scores, source diversity, confidence aggregate, and named-entity coverage of the question. The check produces a structured `StubVerdict` recorded in the `QueryRunReport`, together with a compact `RegionDescriptor` (query embedding plus dominant cluster / type) for later clustering.

An optional Oneiros tick phase (`blind_spot_aggregation`, **off** by default) scans recent stub-firing query reports and emits `BlindSpotReport` candidates using the same HDBSCAN path as periodic re-clustering — see [`BLIND_SPOTS.md`](BLIND_SPOTS.md).

When the verdict crosses the stub threshold, a **Curiosity Trigger** is emitted. The trigger is a typed event consumed by Helios (orchestrator), which dispatches a directional research run:

1. **Prometheus** formalises the gap — what is missing, what would close it, what is the acceptable source-diversity floor.
2. **Argus** searches the open web for candidate sources.
3. **Jason** acquires bytes from the most promising candidates via the same `AcquisitionAdapter` protocol used for direct ingest.
4. **Morpheus** extracts entities and relations from the new content.
5. **Athene** verifies, scores confidence, and resolves contradictions against existing nodes.

The Constellation re-assembles progressively as new nodes and edges land in the focused region. The querying agent (or human client) receives an immediate response with whatever Constellation is currently available, plus a `research_in_progress: true` flag and a `CuriosityRun` ID to subscribe to. Honest progress updates flow on that subscription. Cold regions may be slow; they may not be silent.

A `CuriosityRunReport` is emitted for every run, alongside the existing `IngestRunReport`, `QueryRunReport`, and `OneirosTickReport`.

**Hestia subscribes to every Curiosity Trigger.** Person-as-target checks, sensitive-topic rules, recursion budgets, and drift audit are part of the loop, not optional add-ons. Curiosity without Hestia is a profiling engine. See [`HESTIA.md`](HESTIA.md) and the full mechanism in [`CURIOSITY.md`](CURIOSITY.md).

This is a Generation 2-3 capability for the outward loop. Generation 1 emits `StubVerdict` + `RegionDescriptor` on every query and can persist aggregated blind-spot candidates when operators enable the phase — it still does **not** dispatch the Curiosity trigger automatically. See PHX-0037, PHX-0038, PHX-0039, and [`BLIND_SPOTS.md`](BLIND_SPOTS.md).

### Advisory Layer (Metis)

On top of retrieval sits a dedicated advisory role: **Metis**.

Metis is not primarily a retrieval agent. It is a situational wisdom agent that works across:

- **Akasha** — world knowledge
- **Lethe** — private or institutional context
- **Norm Space** — goals, constraints, laws, values, and prohibitions

Its function is to transform constellations into structured counsel. A serious Metis response should separate:

1. relevant facts
2. relevant analogies
3. plausible options
4. risks and uncertainties
5. value assumptions

This keeps advisory output inspectable and prevents guidance from collapsing into hidden ideology.

## Pantheon agents: agent system

Agents are async workers that operate across all layers. Each implements a common protocol:

```python
class Agent(Protocol):
    name: str
    async def run(self, task: Task) -> TaskResult: ...
```

### Agent Model: Class, Genome, Promotor, Instance

An agent in the **Pantheon agent** roster is not simply a prompt. It is a four-part structure modelled on metagenetics:

**Agent Class** — the stable identity: purpose, boundaries, rights, tools, escalation rules. The equivalent of a gene's functional core. Example: `HestiaClass`, `ChronosClass`.

**Prompt Genome** — a family of prompt profiles for different sub-roles within the class. Not one prompt per god, but a set of coordinated variants. Example: `hestia_sentinel`, `hestia_auditor`, `hestia_gap_finder`. Each profile defines tone, depth, check mode, and escalation style.

**Promotor** — the regulatory layer that controls *expression*: when an agent class is activated, how many instances run, at what priority, with what budget, in response to which signals. The class stays constant; the promotor governs how strongly it is expressed. Example: when drift risk is detected, Helios raises Hestia's promotor — more instances, lower escalation threshold, higher priority.

**Agent Instance** — the running unit, assembled at task time:

```text
Instance = AgentClass + PromptProfile + TaskPacket + Context + Budget
```

Example:
```text
HestiaInstance =
  HestiaClass
  + hestia_auditor
  + task: review_new_sensorium_proposal
  + context: surveillance_risk, human_flourishing_constraint
  + budget: medium
```

Prompts must be treated like code: versioned, testable, comparable, and rollback-capable. A prompt is not decoration. It is the constitutional text of an agent.

### Task Sources

Agents receive tasks from three sources:

1. **External** — user queries, API events, uploads, new sources
2. **Internal** — Prometheus discovers gaps, Athene discovers conflicts, Hestia detects drift, Phoenix Backlog generates review tasks
3. **Regulatory** — Helios or Zeus trigger rebalancing, audits, intensification of specific agent classes, or throttling under resource pressure

Practically: a **Task Ledger + Priority Queue + Event Bus**. Simple in Generation 1, extensible later.

### Orchestration: Zeus and Helios

Two distinct orchestration roles:

**Zeus (operative orchestration)** — handles running traffic: receives tasks, assigns agent instances, distributes budgets, tracks dependencies, manages Fast/Slow path routing, monitors latency and cost.

**Helios (regulatory orchestration)** — changes the expression state of the **Pantheon agents**: which agent classes run more or less, which prompt profiles are preferred, which thresholds apply, when Hestia gets more resources, when Phoenix should be prepared. If Zeus is the conductor, Helios is the endocrine regulator.

### Agent Roster

| Agent | Role | Layer |
|-------|------|-------|
| **Zeus** | Orchestrator — routes queries, coordinates agents, manages resources | 3 → all |
| **Argus** | WorldCrawler — autonomous web exploration and content acquisition | 0 |
| **Jason** | BulkIngestor — large corpus ingestion from organizations or data repositories | 0 → 1 |
| **Iris** | Pantheon Cockpit (human dashboard at `/cockpit`, PHX-0074) plus contact-style intake where applicable — see [`COCKPIT.md`](COCKPIT.md) | 0 |
| **Prometheus** | GapExplorer — identifies knowledge gaps, creates acquisition tasks; primary trigger-handler for the [Curiosity Loop](CURIOSITY.md) | 2 |
| **Morpheus** | Dreamer — association, inference, edge creation (Oneiros worker) | 2 |
| **Athene** | Verifier — fact-checking, confidence scoring, bias detection | 2 |
| **Chronos** | Recycler — lifecycle management, vitality decay, cleanup | 2 |
| **Hades** | PrivacyGuard — tenant isolation, PII detection, access control for Lethe Vaults | 2 |
| **Metis** | Advisory agent — structured counsel across Akasha, Lethe, and Norm Space | 3 → 2 |
| **Hestia** | Human Flourishing Guardian — audits drift, files backlog tickets, escalates dehumanization risk, regulatory dial for human-centredness | all |
| **Helios** | Architect — meta-optimization, regulatory orchestration, promotor management, system evolution | all |

### Argonauts (Domain Experts)

The Argonauts are a dynamic, extensible team of specialized agents — domain experts, media specialists, language specialists, source specialists. They support the core agents with deep knowledge of specific fields. New Argonauts emerge as the Chronik grows into new domains.

### Future Agents (not in Gen 1)

- **Kalypso** — captures interesting discoveries from novel connections
- **Poseidon** — synthesizes long-form articles from crystallized knowledge
- **Hermes** — translates and bridges knowledge across languages and domains
- **Kadmos** — text-translation layer: reads raw text, produces first structured vector representation (portioned, embedded, sporadically connected); precursor to Nous. The current "Nous v1" implementation is Kadmos.
- **Nous** — cognitive synthesis layer: receives Kadmos output, folds it into a genuine knowledge network through LLM-driven understanding, revision, and emergent hierarchy

## Multi-Tenancy: Lethe Vaults and Personal Twins

The Chronik has two primary knowledge spaces:

- **Akasha** (global) — public world knowledge, shared by all users.
- **Lethe Vaults** (private) — isolated tenant-specific knowledge.

A Lethe Vault is structurally identical to the Akasha space (same node/edge model, same indexes) but logically and physically isolated. Hades enforces access control.

This enables the creation of **private digital twins**. A user can store their personal data, private conversations, and localized context in a Lethe Vault. This knowledge remains invisible to the outside world, acting as a highly personal context layer for the user's agents. Only with explicit, granular consent can specific nodes from a Lethe Vault be merged into the central Akasha Chronik.

A query from an authorized agent can search **both** Akasha and the user's Lethe Vault simultaneously. The retrieval merges results transparently, but private knowledge never leaks.

Use cases: personal digital twins, secure corporate knowledge bases, classified intelligence. The user pays for the marginal storage and compute cost of their vault.

## The Phoenix Process

Over time, the Chronik accumulates structural debt: orphaned nodes, redundant paths, outdated embeddings, fragmented clusters. The Phoenix process distills the existing Chronik into a cleaner version:

1. **Export** — traverse the Mneme layer, extract all nodes with metadata, edges, source refs
2. **Distill** — re-embed with the current best embedding model, re-evaluate vitality, drop nodes below threshold, merge near-duplicates
3. **Rebuild** — import into a new KnowledgeStore backend (potentially a different technology)
4. **Verify** — run Athene over the new network to confirm consistency
5. **Switch** — the new Chronik replaces the old; the old is archived

The Phoenix process enables:
- Embedding model upgrades (re-embed everything with a better model)
- Technology migration (e.g., Neo4j → custom engine)
- Structural cleanup (noise, orphans, fragmentation)
- Knowledge compression (merge redundant paths, raise abstraction level)

It is not scheduled. It is triggered when system metrics indicate that a rebirth would be beneficial.

## The Phoenix Backlog

A structured system for tracking improvements, bugs, visions, and feature requests for future generations of the Chronik. Agents and humans can file tickets. Tickets are evaluated during Phoenix process planning.

This is specifically about the **Chronik's knowledge organization** — not about GUI, API design, or peripherals. It is the evolutionary memory of the system itself.

## Technology Stack

| Component | Today (Gen 1 bridge) | Target architecture | Rationale |
|-----------|----------------------|---------------------|-----------|
| Language | Python 3.12+ | Python 3.12+ | Ecosystem, ML libraries, community |
| Knowledge Store | Neo4j 5.x (graph + vector indexes) | LanceDB / Parquet | Neo4j runs today; LanceDB is the append-only columnar vector target |
| Tensor Engine | — | PyTorch CSR tensors | SpMV for GPU-resident Spreading Activation |
| API | FastAPI | FastAPI | Async, fast, OpenAPI docs |
| Embeddings | sentence-transformers (local) | Nomic Embed v2 or similar | Fast, local, high-dimensional vector generation |
| NER / Pre-processing | spaCy + GLiNER | spaCy + GLiNER | Fast, local, deterministic Text-to-Topology Blueprinting |
| Relation Extraction | LLM-based (configurable) | LLM-based (configurable) | Translates blueprint into typed edges |
| Synthesis Agent | Chunked LLM pipeline | **Nous** (cognitive reading agent) | Temporal synthesis replaces stateless chunk parsing |
| Entity Resolution | Post-Hoc Agents (Athene) | Post-Hoc Agents (Athene) | Asynchronous, never blocks ingestion |
| Data Models | Pydantic v2 | Pydantic v2 | Validation, serialization, documentation |
| Agent Orchestration | asyncio + taskgroups | asyncio + taskgroups | Lightweight, no heavy framework |

**On Neo4j:** it is the working store for Generation 1 and is fully supported. It is explicitly a bridge — the target retrieval primitive is Spreading Activation over PyTorch CSR tensors, which Neo4j's pointer-chasing architecture cannot support at the required edge density (1000× edges per node). The `KnowledgeStore` interface exists so the transition does not require rewriting anything above the store layer.

All other technology choices are behind abstract interfaces. Every component can be replaced without affecting the rest of the system.

## Scaling Path

| Scale | Nodes | Storage | Deployment |
|-------|-------|---------|------------|
| Gen 1 (single book) | thousands | megabytes | single machine |
| Gen 1 (hundreds of books) | millions | gigabytes | single machine |
| Gen 2 (large corpus) | billions | terabytes | clustered |
| Gen 3 (distilled internet) | trillions | petabytes | globally distributed |

The architecture supports this progression without fundamental redesign. The KnowledgeStore interface, the cluster hierarchy, and the agent protocols remain the same. What changes is the backing infrastructure and the sophistication of the agents.

## Defense and Self-Improvement (Immune-System Pattern)

The Chronik's defense, repair, and self-improvement layers do not sit in front of the ingest pipeline. They sit beside it, as asynchronous parallel cell types that sample, observe, and act on already-ingested content. This is a deliberate architectural choice; the reasoning is in [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md).

The five cell classes:

| Cell type | Pantheon agent | What it does |
|---|---|---|
| T-helper (surveillance) | Athene | Samples ~2% of new chronicle content, runs verification checks, writes Findings as first-class nodes |
| T-killer (clearance) | Chronos | Acts on Athene findings + aging signals, writes `CONTRADICTS` / `SUPERSEDED_BY` edges, demotes vitality, in extreme cases logs deletions |
| Antibody memory (structural audit) | Nemesis | Detects recurring pathologies (confidence inflation, echo chambers, pheromone autobahns); structurally read-only |
| Adaptive immunity (red-team) | Eris | Synthesizes adversarial probes against an isolated test pantheon; finds blind spots before live data does |
| Consciousness (self-improvement) | Mnemosyne | Observes all cells, defines her own success metrics, A/B-tests thresholds and prompts, writes drafts into the Phoenix Backlog for the next incarnation |

All cells consume from a structured **verification pool**: a sampling reservoir (not a queue) of recently produced or modified content. Each cell has its own sampling strategy. Findings are written back as typed nodes/edges; the chronicle thus contains its own self-observation.

What does **not** live in this architecture: a pre-gate that filters content based on judgement of truth, sensitivity, or appropriateness. Pre-validation gates are forbidden by doctrine — see [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) and [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md).

What does live at the gate: only operative self-defense — HTTPS-only enforcement on web fetch, robots.txt compliance, rate limits per host, response size cap, redirect-chain cap, content-type validation, IP-literal-host rejection, request timeouts. These are physical-barrier reflexes (skin, mucous membranes), not epistemic judgement.

### Long-horizon: self-modification

The self-improvement loop closes when the Pantheon writes its own next version. This is documented as a long-horizon principle in [`SELF_MODIFICATION.md`](SELF_MODIFICATION.md). It is not implemented in any current generation. The architecture must, however, be built today in a way that does not foreclose it: deterministic deploys, tests as canonical specification, agent-readable documentation (AGENTS.md), no folk-knowledge deploy steps.

## Project Structure

```
theogony/
  src/theogony/
    core/                      # data model, store interface, vitality
    stores/                    # KnowledgeStore implementations (Neo4j, ...)
    memory/                    # Ephemera, Mneme, Oneiros process
    agents/                    # Pantheon agents (runtime roles) — not "the Pantheon substrate"
    extraction/                # text → knowledge atoms pipeline
    acquisition/               # source adapters (Gutenberg, web, ...)
    retrieval/                 # multi-hop search, constellation assembly
    api/                       # FastAPI agent-facing service
    phoenix/                   # distillation process, backlog management
    config/                    # settings, defaults
  tests/
  docs/
  phoenix-backlog/             # structured ticket files
  pyproject.toml
  README.md
  PHILOSOPHY.md
  LICENSE
```
