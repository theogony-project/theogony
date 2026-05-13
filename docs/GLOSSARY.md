# Glossary
This glossary defines the canonical meaning of recurring terms used across the Theogony documents.

When a term appears in multiple documents, this file should be treated as the default reference unless a document explicitly narrows the meaning for a specific context.

## Core Terms

**Theogony**  
The overall project, architecture, and open initiative devoted to building the **Chronik** (today's operational system) as the first software toward the **Pantheon** (long-horizon planetary chronicle / knowledge substrate) and the surrounding **Pantheon agents**. See [`PANTHEON_VISION.md`](PANTHEON_VISION.md) and [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md).

**Chronik**  
The living knowledge system at the center of Theogony *right now* — Generation 1's vector-graph memory: ingestion, retrieval, Oneiros, Neo4j, run reports. It is the operational layer implementing chronicle-shaped knowledge toward the wider **Pantheon** ambition; the two terms are not interchangeable.

**Akasha**  
The global, shared, public knowledge space of the Chronik. This is the world-knowledge layer.

**Lethe Vault**  
A private, isolated knowledge space structurally similar to Akasha but protected by access control. Used for personal, organizational, or otherwise permission-bound knowledge.

**Pantheon**  
The **planetary chronicle / knowledge substrate** Theogony aims toward over time: native identity, provenance-first structure, governed visibility, contradiction preserved, rebuildable memory — *not* the same thing as the mythological agent roster. Canonical articulation: [`PANTHEON_VISION.md`](PANTHEON_VISION.md); compact doctrine: [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md).

**Pantheon agents**  
The ensemble of specialized agents (Zeus, Argus, Athene, …) that build, maintain, verify, and use the Chronik. In docs, prefer **"Pantheon agents"** when the agent architecture is meant, to avoid collision with **Pantheon** as substrate.

**Argonauts**  
A flexible class of specialized domain, language, media, or source experts that support the core **Pantheon agents**.

## Memory and Knowledge Layers

**Ephemera**  
The raw, fresh, unverified knowledge layer. New extractions land here first.

**Oneiros**  
The continuous dream process of the Chronik. Not a storage layer, but the ongoing background activity in which agents associate, verify, infer, deduplicate, and consolidate knowledge.

**Mneme**  
The permanent, trusted, highly connected memory layer of the Chronik.

**Phoenix**  
A rebirth or distillation process in which an existing Chronik is exported, reinterpreted, cleaned, and rebuilt into a new generation.

**Phoenix Backlog**  
The structured ticket system that captures problems, visions, improvements, and architectural desires for future generations of the Chronik.

**Spreading Activation**  
The core retrieval mechanism of the Neural Vector Mesh. Instead of executing text-based queries (SQL/Cypher), an agent injects a stimulus vector (or, in the richer mode, a sub-mesh — see [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Sub-mesh injection") into the mesh. Activation energy flows outward across the weighted vector edges, modulated by semantic similarity, Hebbian strength, and frame consistency. The process is mathematically executed as a Sparse Matrix-Vector Multiplication (SpMV) on GPUs; concurrent activations batch into one SpMM. See [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Spreading Activation as batched SpMV".

**Tensor-Manifold**  
The mathematical and physical representation of the Chronik. It abandons pointer-chasing graph databases in favor of contiguous tensor arrays (e.g., Compressed Sparse Row / CSR) loaded into VRAM. This allows the system to handle extreme edge densities (1000x more edges than nodes) and execute Spreading Activation in milliseconds.

**Latent Space Communication**  
The protocol by which AI agents interact with the Chronik. Agents do not send or receive natural language text. They inject their internal vector states (hidden states) into the mesh and receive a Constellation matrix back, communicating natively in mathematics.

**Constellation**  
The structured, query-relevant working set returned to agents after Spreading Activation. It is not a list of text chunks, but an activated subgraph of vectors (a tensor matrix) that is directly injected into the reading agent's latent space (e.g., via soft prompts).

**Codebook (Edge Compression)**  
A technique used to store billions of vector edges in VRAM. Instead of storing full high-dimensional vectors for every edge, the system learns a vocabulary of edge types (the codebook) and stores only a 2-byte index per edge.

**Function-First Phase**  
The currently active build-phase doctrine: growth and mass take priority over per-item truth, privacy, or polish. Schemas, provenance fields, and RunReports stay non‑negotiable as **machine-scalable bookkeeping** behind the ingest lane — not weakened, never human-gated — and pre-validation on content stays forbidden. Truth emerges post-hoc through consolidation and the immune system. Privacy and security return to priority once private sources or external users enter scope. **No SLA numerics bind this phase prematurely** — optimize for shortest path to autonomous compounding, then iterate. Canonical statement: [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md). The phase ends only when an operator supersedes the doctrine in a documented decision.

**Build Doctrine**  
The canonical doctrine for the current build phase, captured in [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md). One-line summary: *Run it. Let it grow. Let it be wrong. Heal it later.* Engineering order: **data structure → synthesis → efficient retrieval.** Non-negotiable structures ride **rear** — implemented as scalable automation only. Companion to [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) (which specifies *how* the chronicle heals) and to [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) (which specifies *what stays non-negotiable* underneath the build phase).

## Mesh Substrate

**Mesh Substrate**  
The storage and dynamic layer beneath all Pantheon cognition: a hyper-dense vector-graph of nodes and weighted edges, with super-linear decay, bounded saturation, atrophy decoupled from deletion, global homeostatic renormalisation, effective-resistance-preserving sub-node splits, and post-hoc topological pathology surveillance. Canonical doctrine: [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md). Implementation: [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md). Use: [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md). Headline rule: *the mesh is alive — it grows, it forgets, it consolidates, and it heals, under fixed resource bounds and without external curation.*

**Observation Chunk (Tier 0)**  
A node holding a single extracted observation — a fact, an event, a state, a quote — captured as semantic + frame vectors with provenance. Has a ULID. References zero or more Tier-1+ entity / concept nodes via reference edges (set up at insertion via Kadmos's eager linking pass when entity Q-IDs match, accumulated through Hebbian co-firing otherwise).

**Consolidated Node (Tier 1+)**  
An entity, concept, or bridge node carrying multiple vectors (semantic, frame, structural, optionally temporal), an authoritative regenerable description, zero or more Q-IDs (with confidence and date), tags, counters, and feedback statistics. Two creation paths: **eager** (created at insertion when Kadmos's entity-linking pass finds a confident Q-ID match or strong topology resemblance, even if no node existed yet) and **emergent** (formed by Oneiros from a cluster of co-resonating Observation Chunks when no eager link was possible). Higher tiers (2, 3) are earned through repeated relevance across many consolidation cycles. May represent an **entity** (e.g., Thomas Addison), a **concept** (e.g., private practice ownership), or a **bridge** (a node deriving its existence from connecting otherwise-separate clusters). Carries `is_candidate = True` when created emergently without confident identity yet; flipped to `False` when convergence is reached.

**Eager Linking**  
The substrate's insertion-time identity discipline. When Kadmos extracts a chunk that mentions an entity, it attempts to attach the chunk's reference edge directly to an existing Tier-1 node, using three signals in order of strength: **(1) Q-ID match** — confident Wikidata Q-ID linkage to an existing node carrying that Q-ID; **(2) description match + structural context** — cosine similarity of `description_vector`s combined with proximity to other entities being ingested in the same article / paragraph; **(3) tag overlap + structural context** — discriminating tag overlap when description matching is inconclusive. If a node carrying the matched Q-ID does not yet exist, Kadmos creates one on the spot. If no signal fires confidently, the substrate falls through to the emergent path (entity-candidate node with `is_candidate = True`). See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Why two tiers — and how identity actually gets committed".

**Q-ID (Wikidata Q-Identifier)**  
The unique identifier of a Wikidata entity. The substrate treats Q-IDs as one-to-one identifiers: each Q-ID maps to at most one stable Tier-1 node at any point in time. If two Tier-1 nodes briefly carry the same Q-ID (concurrent ingestion duplicates), that is a transient state that Oneiros resolves by deduplication on the next tick. A node may carry several Q-IDs only when it legitimately spans multiple Wikidata entities (rare bridge case). The strongest single identity signal in the eager-linking path. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Field discipline" point 3.

**P-ID (Wikidata Property-Identifier)**  
The Wikidata identifier for a property / relation type — `P19` (place of birth), `P31` (instance of), `P50` (author), `P569` (date of birth), etc. The edge-side analog of Q-IDs. Each P-ID refers to exactly one Wikidata property. Edges may carry zero, one, or several P-IDs in their optional `pids` field, useful for agents reasoning about edge semantics in Wikidata-aligned terms. Like Q-IDs, P-IDs are one-to-one identifiers. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Edge anatomy".

**Source-Anchor Entity**  
A Tier-1+ consolidated node flagged with `is_source_anchor = True` and carrying a `source_url` field. Represents the source itself rather than the entity the source describes — a Wikipedia article, a chapter, a paragraph, a paper, a book. Source-anchor entities form their own hierarchy via `is_section_of` edges; chunks attach to them via `extracted_from` edges. They make provenance a structural feature of the mesh: a query like "what does Wikipedia say about X?" can route through source-anchor entities by Spreading Activation. They follow normal substrate dynamics; their `description` and `source_url` allow agents and humans to navigate to the original source when needed. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Source-anchor entities".

**Agent-Driven Cleanup**  
Post-hoc operations by Pantheon agents (Argus, Athene, Chronos, Mnemosyne) that target *specific identified problems* in the substrate: deduplication of nodes that turn out to refer to the same entity, contradiction resolution (typed `CONTRADICTS` edges, weighted by evidence), false-information removal (with full audit), redundancy compression. Distinct from automatic mechanisms (decay, pruning under resource pressure) and from spiral therapy (which targets patterns, not specific items). Agent-driven cleanup operates after observations are already in the substrate — it is *not* a pre-gate. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Agent-driven cleanup".

**Edge Semantic Descriptors**  
Optional fields on every edge — `relation_descriptor` (short label like "owns", "located_in"), `relation_kind` (broader category like "attribute", "ownership", "hierarchy", "extraction"), `description` (longer free-text when the short label is not enough), `pids` (Wikidata property identifiers for Wikidata-aligned reasoning), `creation_context` (how the edge came to be: `kadmos_extraction`, `oneiros_consolidation`, `argus_proposal`, `hebbian_co_fire`, `frame_routing`, `agent_repair`). Used by agents reading the mesh and by repair logic; ignored by the substrate's automatic dynamics (decay, Hebbian update, saturation, splits). They are agent-facing metadata, not retrieval primitives. Stored in a parallel Lance edge-metadata table (per [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Edges — PyTorch sparse + delta buffer + Lance metadata table") so that the SpMV hot path stays narrow. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Edge anatomy".

**Description Vector**  
Optional Tier-1+ node field (`description_vector`). The embedding of the node's `description` text. Used by description-based eager linking (signal 2 in §"Why two tiers — and how identity actually gets committed") to recognise the same entity in new chunks lacking Q-IDs. Recommended for entity-class Tier-1 nodes; optional for pure concept nodes that have no identity to disambiguate. Recomputed when the description is regenerated. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Field discipline" point 4.

**Anchor Node**  
A special node class for index-like coordinates: years, geo cells, languages, genome positions. Immutable, very-high-cap, no Hebbian updates, no decay, no split. Observations reference anchors via fields (`temporal_anchor`, `geo_anchor`, etc.); range queries over anchors use index lookups, not graph traversal. The only discrete typing decision the substrate exposes.

**Atrophy / Verödung**  
A node whose total edge weight has dropped below the population-relative healthy band. Atrophic nodes lose firing privileges by default but remain in the substrate, can still receive Hebbian updates from external resonance, and are reactivable by sufficiently strong directed activation. Atrophy is decoupled from deletion: a node is removed only when the pruner runs under resource pressure.

**Healthy Band**  
The `[μ − σ, μ + σ]` range over the substrate's `node_potential` distribution, with an age correction that gives young nodes a wider band so they have time to grow before being judged.

**Saturation**  
The bounded edge count and total edge weight per node, indexed by tier (Tier 0: 10K edges / weight S; Tier 1: 50K / 5S; Tier 2: 200K / 20S; Tier 3: 1M / 100S). When saturation would be exceeded, a new edge attaches only if it is strictly stronger than the weakest existing edge; the weakest edges are evicted to restore the cap.

**Super-linear Decay**  
The substrate's edge-weight decay rule: `dw/dt = -λ · w^k` with `k > 1` (default `k = 2`). Strong unused edges decay faster (in absolute terms) than weak unused edges. The mathematical mechanism that prevents fossilisation: high edge weight signifies *currently relevant*, not *historically important*. Tier-modulated: higher consolidation tiers get gentler decay exponents.

**Pruning**  
The only operation in the substrate that destroys information. Triggered exclusively by resource pressure (RAM occupancy, query latency, GPU memory). Removes the weakest atrophied nodes and edges first, content-blind, until the trigger condition has cleared with margin. Audit-logged.

**Global Renormalisation (homeostatic)**  
Periodic multiplicative rescaling of all edge weights to maintain a target ratio between node count and total edge weight (default `R_ideal = 1000`). Analogous to biological synaptic scaling. Combined with super-linear decay, it makes the equilibrium weight of any edge proportional to its *relative* firing frequency across the whole substrate. Runs as the closing step of an Oneiros tick.

**Sub-Node Split**  
A topology refactor in which a saturated hub delegates a thematic cluster of edges to a new sub-node. The split-rule chooses `w_HS = Σ w_i` (hub-to-sub conductance) and `w_i' = w_i / (1 - p_i)` (sub-to-leaf conductance), satisfying the series-conductance identity that preserves effective Hub→leaf conductance exactly. The split is therefore semantically invisible to consumers — Spreading Activation behaviour is unchanged. Permitted only for clusters of n ≥ 8.

**Effective Resistance Preservation**  
The mathematical invariant satisfied by Sub-Node Splits: `(w_HS · w_i') / (w_HS + w_i') = w_i`, ensuring the substrate can refactor topology silently without consumer-visible regressions.

**Frame Vector**  
A small-dimension (default 64) per-node embedding that encodes epistemic frame (definition, claim, refuted-claim, hypothesis, observation, direct quote) separately from semantic content. Used by Spreading Activation to route propagation: edges propagate only when their `frame_consistency` matches the active query frame. The substrate's mechanism for representing polarity and refutation, since cosine similarity at the semantic-vector level cannot.

**Frame-Routed Activation**  
Spreading Activation that filters edges by frame compatibility at each hop. Implemented as a masked SpMV: `(A * frame_mask) · X`. Allows the same substrate state to return different Constellations for queries about *current claims* versus *historical claims* about the same concept.

**Three-Factor Plasticity**  
The substrate's Hebbian update modulated by a third factor — feedback / reward — supplied by the consumer of the Spreading Activation result: `Δw = α · s · (1 + β · feedback)`. Biologically inspired by dopaminergic modulation. Sources of feedback: LLM self-rating, downstream task success, explicit user rating, implicit signals.

**Eligibility Trace**  
A decaying record per edge of recent firing intensity, allowing post-hoc reward to be back-attributed across multi-hop activation paths. Standard reinforcement-learning mechanism (TD(λ)-class). Solves multi-hop credit assignment when feedback arrives only on the final node of an activation chain.

**Diversified Injection**  
The substrate's mandatory retrieval discipline: replace top-K nearest with three combined mechanisms — Maximum Marginal Relevance (anti-redundancy diversity), weight-class stratification (multi-scale: micro / medium / large / hub), and optional sub-mesh signature search (structural matching). Always on in production retrieval; naive top-K cosine retrieval is forbidden.

**Sub-Mesh Injection**  
A query mode in which the agent constructs a small graph fragment with structure and asks the substrate "where in the mesh would this fit?". The substrate matches by combining per-node ANN similarity with Weisfeiler-Lehman structural hashing and frame consistency. The retrieval mode that separates the substrate from a vector database with edges; central for multi-hop reasoning.

**Thought-Spiral / Mind-Lock**  
A pathological topological pattern where a substrate region becomes self-referential, suppresses alternatives, and rejects refutations. Detected by Argus from five topological symptoms: internal/external asymmetry, activation hysteresis, context promiscuity, refutation absorption, and saturation lockout. Treated by gentle staged therapy.

**Staged Therapy**  
The substrate's response to detected mind-lock. Five stages, escalating only when the previous fails: (1) activation temperature (stochastic routing), (2) dominance penalty (temporary decay increase), (3) forced refutation re-injection (Argus replays contradicting evidence), (4) saturation demolition (temporary edge halving / zeroing — destructive, but recoverable through subsequent activation if the region deserves to come back), (5) quarantine / split (region isolation in a sub-mesh). Stages 1–3 are fully reversible; Stages 4–5 may destroy information when the topological evidence is repeated and the Mendel risk has been weighed and rejected, with full audit-ledger entries.

**Mendel Risk**  
The risk that a topological pattern looking like a thought-spiral is actually a correct rare insight that the rest of the substrate has not yet caught up with. Named for Mendel's genetics, ignored for forty years before recognition. Argus weighs the Mendel risk against the topological evidence of pathology before recommending invasive therapy (Stage 4 demolition or Stage 5 quarantine); the weighing is logged in the audit ledger as part of the finding. The Mendel risk does *not* prohibit destructive therapy — it is a discipline of escalation order, repeated evidence, audit, and proportionality. See [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"The Mendel risk — a consideration to weigh".

**Consolidation Tier**  
Integer ladder (0, 1, 2, 3+) on every node. Tier 0 is a chunk; Tier 1 is a consolidated entity / concept / bridge; higher tiers are earned through demonstrated long-term relevance. Tier modulates decay profile (higher tier → gentler decay), saturation cap (higher tier → larger cap), and renormalisation sensitivity. Tier promotion happens exclusively via Oneiros and is reversible.

**Oneiros Tick**  
The serialised single-writer process that periodically applies decay, drains the delta buffer, runs renormalisation, computes consolidations, applies sub-node splits, runs pathology surveillance, applies therapy actions, refreshes caches, writes audit-ledger entries, builds the new stable CSR tensor, and atomically publishes a new Lance version. Spreading Activation runs unimpeded against the previous version while Oneiros ticks. Frequency is operator-configurable; the binding rule is that it stays well below 5–10% of wall clock at production load.

**Universe (substrate)**  
A Lance-versioned branch of the substrate, optionally with a distinct agent configuration, decay parameters, frame-encoder, or other variation. Multiple universes can run in parallel with the same input data stream; their substrate states can be compared on coherence, robustness, predictive accuracy, spiral incidence, and Mendel preservation. The substrate-level extension of Mnemosyne's A/B framework. Gen 3+ work; the substrate doctrine preserves the option.

## Representation and Semantics

**Knowledge Atom**  
An operational unit of knowledge inside the Chronik. In practical system terms this is often projected as nodes, edges, claims, events, or assertion frames.

**Chronese**  
The proposed canonical semantic language of the Chronik. A language-neutral, event-centric, provenance-bound, epistemically explicit form from which graph, vector, and textual projections can be derived.

**Assertion Frame**  
The core primitive proposed for Chronese. A structured representation of an event, state, claim, or inference involving participants, roles, time, place, qualifiers, epistemic state, and source grounding.

**Constellation**  
A structured, query-relevant working set returned by the Chronik to an agent. It contains the currently relevant nodes, edges, evidence, sources, gaps, and sometimes contradictions or competing hypotheses.

**Hover-Lupe**  
The idea that any entity or concept mentioned in an answer can be opened into a deeper local knowledge landscape. Not a static article, but a dynamic contextual zoom into the Chronik. The Hover-Lupe is also the entry point of the [Curiosity Loop](CURIOSITY.md): a zoom into a thin region triggers research in exactly that region.

**Curiosity Loop**  
The architectural coupling between attention and acquisition. A query, a zoom, or a contextual ask runs a structured stub check on the assembled Constellation; if the verdict crosses threshold, a `CuriosityTrigger` is emitted; Helios dispatches Prometheus → Argus → Jason → Morpheus → Athene to acquire new content in exactly the focused region; the Constellation re-assembles progressively. Hestia subscribes to every trigger to prevent attention-driven research from sliding into surveillance. See [`CURIOSITY.md`](CURIOSITY.md). Generation 2-3, with a Gen 1 stub-detection foothold.

**Mind-Map**  
A canonical human-facing rendering of a Constellation: nodes laid out spatially, sized by relevance, with provenance glyphs and zoom-into-node interaction. Not part of the Chronik core (clients render Constellations); the server-side response contract that makes Mind-Map clients possible is tracked under PHX-0038.

**Stub Verdict**  
A structured assessment recorded in the `QueryRunReport` indicating whether the assembled Constellation for a query is too thin to be considered a satisfying answer. Combines node count, edge density, vitality, source diversity, confidence aggregate, and named-entity coverage. Crossing the threshold emits a `CuriosityTrigger` (in Gen 2-3); in Gen 1 the verdict is recorded for calibration only.

## Deep Technical Terms

**Source Lake**  
The raw source layer where original materials live: books, webpages, PDFs, OCR scans, transcripts, private documents, and other unprocessed inputs.

**Chronicle Ledger**  
The append-only record of extracted observations, claims, and semantic outputs. It preserves what the system believed, when, from which source, and by which extraction process.

**Event Hypergraph**  
A deeper relational structure in which events and claims can connect more than two elements at once. Useful when simple triples are too weak to capture real-world structure.

**Multi-Embedding Fabric**  
A family of embedding spaces rather than a single vector space. For example: conceptual, temporal, geographic, social-role, causal, scientific-claim, or method spaces.

**Activation Engine**  
The proposed future runtime that spreads query energy through semantic, temporal, spatial, causal, analogical, and epistemic paths to produce an activation field rather than a flat search result list.

**Constellation Compiler**  
The layer that turns raw activation and deep substrate state into an agent-usable Constellation.

## Twins and Personal Context

**Digital Twin**  
A structured model of a person within the Chronik. Depending on the source base, this may be public, private, or inferred.

**Public Twin**  
The model of a person reconstructed from public sources.

**Consensual Private Twin**  
A private, permission-based model of a person inside a Lethe Vault, built from explicitly provided personal data, conversations, context, and memory.

**Shadow Twin**  
An inferred model of a person assembled from incomplete public data. Technically possible, ethically sensitive, and therefore subject to strict limitations.

**Right to Opacity**  
The principle that not everything that can be inferred about a person should be operationalized or exposed.

## Agent and Advisory Terms

**Metis**  
The proposed advisory agent of the Chronik. Metis is a situational wisdom agent that organizes facts, analogies, options, risks, and value assumptions across Akasha, Lethe, and Norm Space.

**Norm Space**  
The explicit layer of goals, rules, prohibitions, obligations, values, preferences, and risk tolerances used in advisory reasoning.

**Counsel Packet**  
A structured advisory output proposed for Metis. It separates framing, facts, analogies, options, risks, unresolved questions, value assumptions, and recommendation.

## Agent Architecture Terms

**Agent Class**
The stable identity of a **Pantheon agent** (runtime role): its purpose, boundaries, rights, tools, and escalation rules. Equivalent to the functional core of a gene.

**Prompt Genome**
A family of prompt profiles for different sub-roles within an agent class. Not one prompt per agent, but a coordinated set of variants for different tasks and contexts.

**Promotor**
The regulatory layer that controls an agent class's expression: when it is activated, how many instances run, at what priority, with what budget, and in response to which signals. The class stays constant; the promotor governs how strongly it is expressed. Managed by Helios.

**Agent Instance**
The running unit assembled at task time from a class, a prompt profile, a task packet, a context, and a resource budget.

**Task Ledger**
The structured record of pending, active, and completed agent tasks. Combined with a priority queue and event bus to route work across **Pantheon agents**.

**Hestia**
The human flourishing guardian. Monitors the Chronik's development for dehumanizing drift, files Phoenix Backlog tickets, triggers escalations, and serves as a regulatory dial: when raised by Helios, more Hestia expression means stronger protection of human-centric values.

## Core Pantheon agents (roster)

**Zeus**  
The orchestrator. Routes queries, coordinates agents, and manages system-level execution.

**Argus**  
The world crawler. Searches for and acquires new public knowledge sources.

**Jason**  
The bulk ingestor. Handles large corpora, uploads, and structured source acquisition at scale.

**Iris**  
The Remember-layer output agent. Activates a subgraph via Spreading Activation and generates natural language from the vector constellation — not by retrieving stored text, but by formulating meaning from structure. Iris is the only point where the Chronik produces language for humans. Also ships as the **Pantheon Cockpit** ([PHX-0074](../phoenix-backlog/PHX-0074.yaml)) — the `/cockpit` dashboard ([`COCKPIT.md`](COCKPIT.md)).

**Pantheon Cockpit**  
Server-rendered Iris UI on the FastAPI app (`src/theogony/cockpit/`): five panels (status, knowledge browser, clusters, reports, manifest). Default **127.0.0.1** binding with an explicit opt-in for public bind; **sample-only** caps aggregations for demos. See [`COCKPIT.md`](COCKPIT.md).

**Manifest (cockpit)**  
Single Markdown file (default `cockpit/manifest.md` under `data_dir`) owned by the cockpit: operator-declared domain scope and notes. The only chronicle-adjacent write surface in Cockpit Phase 1.

**sample-only mode (cockpit)**  
`THEOGONY_COCKPIT__SAMPLE_ONLY=true` — caps search, cluster lists, and report tables so a cockpit URL can demonstrate layout without exposing the full graph.

**Mnemosyne**  
Meta-cognitive auditor ([PHX-0071](../phoenix-backlog/PHX-0071.yaml)): classifies whether a query is *about the chronicle itself*, appends run ids on cited nodes when the verdict is self-referential, and (optional Oneiros phase) clusters observations into `MnemosyneObservationCluster` reports. See [`MNEMOSYNE.md`](MNEMOSYNE.md).

**self-referential (query)**  
A user or agent question whose topic is the Chronik's own schema, retrieval, embedding spaces, workers, lifecycle, or backlog — architectural introspection rather than domain fact lookup.

**meta-classification**  
The per-query `MetaClassification` attached to a `QueryRunReport`: verdict `self_referential` \| `not_self_referential` \| `uncertain`, plus heuristic hit counts and optional LLM-fallback trace fields.

**Prometheus**  
The gap explorer. Identifies missing, weak, stale, or underconnected knowledge.

**Morpheus**  
The dreamer. Associates, infers, and weaves new connections inside Oneiros.

**Morpheus associator (Phase 1)**  
Deterministic `TickPhase` (`morpheus`) that proposes `INFERENCE` edges from embedding-band similarity and source-document co-occurrence. Default-off; see [`MORPHEUS.md`](MORPHEUS.md).

**depth_band**  
Integer ladder `0..5` on every `KnowledgeNode`: Ephemera strata (0–2) and Mneme strata (3–5). Maintained by optional `depth_band` Oneiros phase; see [`DEPTH_BANDS.md`](DEPTH_BANDS.md).

**embedding band (Morpheus)**  
Configurable cosine-similarity window (default `[0.6, 0.9]`) for “interesting middle” neighbours — not plain top‑k search.

**Athene**  
The verifier. Evaluates claims, evidence, contradictions, and confidence.

**Chronos**  
The recycler. Manages decay, compression, archival logic, and graceful forgetting.

**Hades**  
The privacy guardian. Enforces isolation and access control around Lethe Vaults and sensitive knowledge.

**Helios**  
The architect. Optimizes strategy, tunes system behavior, and guides long-range evolution.

## Future or Specialized Agents

**Kalypso**  
A Remember-layer agent that practices *remembering as creation*: it discovers connections in the Chronik that nobody explicitly queried — emergent analogies, cross-domain links, implicit structures that lie in the vector mesh but were never surfaced. Where Iris responds to questions, Kalypso asks its own.

**Poseidon**  
A Remember-layer agent that synthesises long-form narratives from crystallised knowledge. Like Kalypso, it does something beyond retrieval: it composes from what exists, producing texts that were not stored but follow from the structure of the Chronik.

**Hermes**  
A future bridging role for translation, mediation, and cross-domain or cross-language movement of knowledge.

**Kadmos**  
The text-translation layer — named after the mythological inventor of the alphabet. Kadmos reads raw text and produces a first structured representation: portioned, embedded, sporadically connected. Not yet understood, but translated into a form that Nous can process. Kadmos is the precursor to Nous: what DNA is to RNA before transcription. The current implementation (formerly called "Nous v1") lives here. Nous proper is the cognitive synthesis layer that folds Kadmos output into a genuine knowledge network.

## Builder Agents

Builder agents are not **Pantheon agents** and are not the **Pantheon** substrate. They are mortal craftsmen — they build the software the Pantheon agents will run on, but do not live inside the runtime mythology. Their prompts live in [`prompts/`](../prompts/) and are versioned like constitutional text.

**Hesiod**  
The first builder. Helps articulate vision, write documentation, and shape the conceptual foundation of Theogony. Named after the Greek poet who composed the original Theogony — the one who put the birth of the gods into words.

**Daedalus**  
The architect. Designs the concrete implementation of the system from the existing vision. Operates under strict YAGNI and Advocate/Skeptic/Counterview discipline. Prompt: [`prompts/daedalus.md`](../prompts/daedalus.md).

**Talos**  
The implementer. Daedalus's apprentice and successor — the craftsman who turns the architect's plan into running code, with green tests and honest RunReports. Does not redesign the architecture; escalates contradictions instead. Works on feature branches, commits atomically, and reports failures with the same candor as successes. Prompt: [`prompts/talos.md`](../prompts/talos.md).

## Domain Directions

**World Knowledge**  
The Chronik's role as a distilled, navigable memory of global public knowledge.

**Scientific Workbench**  
The Chronik's role as an active meta-research substrate: comparing claims, exposing contradictions, identifying gaps, and supporting the production of new scientific knowledge.

**Operative Knowledge**  
The fifth knowledge form: knowledge that runs the world rather than describes it. Schedules, logistics, machine control, supply forecasts, maintenance protocols. Unlike descriptive knowledge, operative knowledge is enacted in continuous plan-execute-document-learn cycles. Long-horizon dimension; not part of Generation 1 or 2. See [`OPERATIVE_KNOWLEDGE.md`](OPERATIVE_KNOWLEDGE.md).

**Operative Agents**  
A future class of agents (e.g. Atlas, Hephaistos, Demeter) that act on the world rather than only on knowledge. Subject to the same provenance, audit, and Hestia oversight as knowledge agents.
