# The Mesh Substrate

**Status:** canonical doctrine for the storage layer beneath all Pantheon cognition. Binds every agent that reads or writes the Chronik mesh.
**Companion docs:** [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) (storage, concurrency, hardware), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) (injection, spreading activation, learning, modality), [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) (the architectural commitments this substrate realises and, in places, refines), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) (the ten general principles this doctrine extends), [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) (sample-based post-hoc verification, which the substrate's pathology layer makes structural), [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) (function-first phase rules — the substrate is built under those rules).
**Audience:** every Pantheon agent, every builder agent, every external contributor whose code touches a node, an edge, a vector, or a tick.

**Precedence.** This document and its companions ([`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md)) are the **operative substrate doctrine**. Where they conflict with older doctrine documents — including `TARGET_ARCHITECTURE.md`, `CHRONICLE_PRINCIPLES.md`, or `IMMUNE_SYSTEM.md` — these documents are operative for substrate-layer behaviour. The older documents remain authoritative for everything they cover that is *not* about substrate mechanics, dynamics, or use; but where the substrate triplet says something different about how nodes behave, how edges form, how identity is committed, how cleanup happens, or how retrieval works, these documents win. This is not a small claim, and it is deliberate: the substrate triplet records design conclusions reached after the older documents were written, and the project's design has moved.

---

## Why this doc exists

The architecture so far has been correct about *what* the substrate must be — a hyper-dense vector-graph, LanceDB + PyTorch, Spreading Activation as the retrieval primitive ([`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md)). It has been comparatively silent about *how the substrate must behave over time* — how nodes are born, how identity is committed, how edges strengthen and decay, how saturation is bounded, how forgetting works without becoming catastrophic, how agents can intentionally clean up the substrate, and how the substrate defends itself against its own pathologies.

This document closes that gap. Its purpose is to make the substrate's behaviour fully specified, so that no agent can credibly claim it was undefined and so that the design's affordances are visible at the same level of detail as its disciplines.

The headline rule is one sentence:

> **The mesh is alive: it grows, it links, it forgets, it consolidates, and it heals — under fixed resource bounds, with active agent participation in cleanup and repair, and without external pre-validation curation.**

The rest of this document specifies how that one sentence is realised.

---

## The two-tier node model

The substrate has exactly **two classes of nodes**. There is no third class, no special-purpose taxonomy, no schema typing beyond these two.

### Tier 0 — Observation Chunks

A Tier-0 node is a single extracted observation — a fact, an event, a state, a quote — captured in vector form together with its frame and provenance.

Examples (extracted by Kadmos from the same Wikipedia paragraph about the discovery of adrenaline):

- *"T. B. Aldrich and Takamine Jōkichi extracted a substance from animal kidneys in 1901 and named it adrenaline."*
- *"Aldrich determined the molecular formula of adrenaline."*
- *"Friedrich Stolz achieved the chemical synthesis of adrenaline in 1904."*
- *"Adrenaline (1904) was the first artificial production of a hormone in biochemistry."*

Each of these is one Tier-0 chunk. None of them is "the Adrenaline node" or "the Aldrich node". Each is a captured observation with its own embedding, its own frame, and its own provenance. The chunk's identity is its `ULID` and nothing else.

Tier-0 chunks are short-lived in the sense that most of them never become long-term substrate features. They contribute their evidence into the mesh dynamics and either accumulate enough resonance to be promoted into Tier-1 structure or fade under decay.

### Tier 1+ — Consolidated Nodes (Concepts, Entities, Bridges)

A Tier-1 node is what emerges when many Tier-0 chunks consistently co-resonate around the same conceptual content. The Tier-1 node is *not* extracted from text — it is constructed by Oneiros from the residue of co-firing chunks. It carries the richer metadata an emergent concept deserves: multiple vectors, an optional human-readable description (regenerable, not authoritative), zero or more `Q-IDs` as bootstrap anchors to external systems, and the counters Argus uses to monitor health.

Higher tiers (Tier 2, Tier 3) exist for nodes that have demonstrated repeated relevance over many Oneiros consolidation cycles. Tier promotion is earned, never declared. Higher-tier nodes get larger saturation budgets and slower decay profiles — they are the substrate's long-term memory.

A consolidated node may represent:

- An **entity** — `Thomas Addison`, `Hatton Garden`, `the year 1819`, `adrenaline (the molecule)`
- A **concept** — `private practice ownership`, `house-buying as a life-event type`, `endocrine disease`, `synthetic chemistry`
- A **bridge** — a node that derives its existence from connecting otherwise-separate clusters; `London_real_estate` between `London` and `real estate`

All three sub-kinds use the same data structure. There is no `node_type` enum that distinguishes them. The kind is observable from the topology — a bridge has high cross-cluster connectivity, an entity has external Q-IDs, a concept lacks Q-IDs but has dense structural neighbourhood — but it is never a stored category.

### Why two tiers — and how identity actually gets committed

Identity in the substrate has **two paths**, with the eager path itself supported by **three signals** ranked by strength.

**Path 1 — Eager linking when the evidence is clear.** When Kadmos extracts a chunk that references an entity, the insertion path attempts to link the chunk's reference edge directly to an existing Tier-1 node. The decision uses three signals, in order of strength:

1. **Q-ID match (strongest).** A confident Q-ID linkage at insertion is the substrate's clearest identity signal. If Kadmos's linker says this chunk mentions `Q336997` with high confidence, and a Tier-1 node already exists carrying that Q-ID, the chunk's reference edge attaches directly. If no such node exists, Kadmos creates one on the spot, populated with the Q-ID, an initial description, an initial semantic_vector, and an initial description_vector (see §"Field discipline" point 4 below).

2. **Description match + structural context (nearly as strong when the description is discriminating).** Many entity references arrive without a confident Q-ID, especially when the source is not pre-linked to Wikidata. But a description like "T. B. Aldrich, American chemist (1861–1938) who isolated adrenaline" carries enough discriminating features (name + profession + birth/death years + what they're known for) to identify a person uniquely in most cases. The substrate uses **description-based eager linking**: it computes the description embedding (`description_vector`) of the candidate reference, runs cosine similarity against existing Tier-1 nodes' `description_vector`s, and combines the result with **structural context** — proximity to other entities already identified in the same article, paragraph, or chunk-cluster being ingested. If a single candidate node clearly wins (high description similarity + strong shared structural neighbourhood), the chunk's reference edge attaches to that node. The combined score must exceed a tunable confidence threshold; below the threshold, fall through to signal 3.

3. **Tag overlap + structural context (weaker, fast disambiguation).** Even without Q-ID and without a fully discriminating description, a candidate reference may share enough discriminating tags (profession, birth-year decade, geographic origin) with exactly one existing Tier-1 node to make linkage safe. This signal is used when description-based matching is ambiguous; it is the fastest of the three but the most error-prone, so the confidence threshold is the highest.

If none of the three signals fires confidently, the substrate falls through to Path 2.

**Path 2 — Emergent identity when no signal is decisive.** The chunk's reference attaches to a fresh **entity-candidate node** (Tier-1 with `is_candidate = True`). Subsequent chunks that resonate with this candidate accumulate evidence. Oneiros, on its next tick, either:

- consolidates several candidates into a confirmed Tier-1 entity once convergence is reached (`is_candidate` flips to `False`),
- merges a candidate into an existing entity if a later chunk supplies the missing identity link (Q-ID, description, or structural),
- or lets the candidate atrophy if it never accumulates support.

This is **eager-when-clear, emergent-when-not.** The substrate uses the strongest available identity signal at every insertion. Pure emergence-only would be wasteful (re-discovering what is already known); pure eager-only would be brittle (committing identity decisions on weak evidence and producing wrong fusions that are expensive to undo). The three-signal eager path lets the substrate take Path 1 in *most* real cases — Q-IDs are present in well-curated sources, descriptions are present in any source detailed enough to support a Tier-1 node — and falls through to Path 2 only when the evidence genuinely cannot decide.

The two-tier structure (Chunks vs. Consolidated) remains the same. What's hybrid is how Tier-1 nodes get *populated*: some are created eagerly through Q-ID linking, some through description+structural matching, some through tag+structural matching, some are formed by Oneiros through co-firing convergence on candidates. Many are some combination — a Q-ID-anchored node grows through consolidation as more references arrive and more candidates merge in.

This refines [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) §3 *"Native identity over time"* by specifying both halves of the temporal trajectory: the early eager half (when Q-ID, description, or tag evidence is decisive) and the later emergent half (when only accumulated topology can decide). Both halves are doctrine.

---

## Node anatomy

Both tiers share a common spine of fields. Tier-1+ nodes extend it. Both shapes are Pydantic v2 with `ConfigDict(extra="forbid")`, per [`AGENTS.md`](../AGENTS.md) §1.

### Tier-0 — Observation Chunk

```python
class ChunkNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ULID                            # zeitsortable, lock-free generation
    born_at: datetime
    last_fired_at: datetime
    fired_total: int = 0
    fired_recent: int = 0               # rolling window counter

    semantic_vector: list[float]        # dense embedding; default 1024-d (BGE-M3 class)
    frame_vector: list[float]           # epistemic-frame embedding; default 64-d

    source: SourceProvenance            # who / where / when extracted (immune-system anchor)
    raw_text_ref: str                   # opaque pointer; raw text is NOT stored in the mesh
```

`raw_text_ref` exists because the immune system may sometimes need to re-derive the chunk from its source — and because human debugging occasionally wants to look at the literal source string behind a vector. It is **not** retrieval payload. No agent ever consumes `raw_text_ref` during Spreading Activation; the retrieval primitives operate on vectors, not strings, and reading the raw text on the hot path would defeat the substrate's entire reason for being vector-native.

### Tier-1+ — Consolidated Node

```python
class ConsolidatedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ULID
    born_at: datetime
    last_fired_at: datetime
    fired_total: int = 0
    fired_recent: int = 0

    consolidation_tier: int = 1         # 1, 2, 3 — earned via Oneiros
    consolidation_history: list[datetime] = []  # when each tier promotion happened
    is_candidate: bool = False          # True for entity candidates created on first encounter
                                        # without confident identity link; flipped to False
                                        # when Oneiros confirms or merges into a stable identity
    is_anchor: bool = False             # True for the special anchor-node class
                                        # (year, geo cell, language, genome position) per
                                        # §"Splits in the wild — also: temporal nodes are special"
    is_source_anchor: bool = False      # True for source-anchor entities — see §"Source-anchor entities"
    source_url: str | None = None       # populated when is_source_anchor; URL or anchor-style reference
                                        # to the source document / chapter / paragraph

    semantic_vector: list[float]                    # aggregate semantic representation across all evidence
    frame_vector: list[float]                       # epistemic-frame embedding
    structural_vector: list[float] | None = None    # learned from local topology (Node2Vec/GraphSAGE)
    temporal_vector: list[float] | None = None      # for nodes with strong temporal anchor
    description_vector: list[float] | None = None   # embedding of the description text — used for
                                                    # description-based eager linking; recommended for
                                                    # entity-class Tier-1 nodes, optional otherwise

    description: str | None = None      # short discriminating text — ~200–500 chars typical;
                                        # for entities: name + key discriminators (profession,
                                        # birth/death year, what they're known for); for source-anchors:
                                        # source title + URL; regenerable from chunks, authoritative
                                        # for repair / disambiguation / LLM injection
    description_generated_at: datetime | None = None
    description_source_chunks: list[ULID] = []      # provenance of the description; auditable

    tags: list[str] = []                # structured keyword cloud — discriminating features
                                        # (profession, geographic origin, year decade, etc.);
                                        # used as a fast disambiguating bag during eager linking

    qids: list[QIDTag] = []             # Wikidata Q-IDs as identity anchors; per §"Field discipline"
                                        # point 3, normally exactly one; multiple only when the node
                                        # legitimately spans multiple Wikidata entities (rare); never
                                        # the same Q-ID on two stable Tier-1 nodes

    activation_entropy: float | None = None   # diversity of activating contexts (spiral signal)
    node_potential_cache: float | None = None # cached Σ edge weights, Oneiros-refreshed
    positive_feedback_total: int = 0    # lifetime three-factor reward
    negative_feedback_total: int = 0    # lifetime three-factor penalty
    feedback_recent: int = 0            # rolling-window net feedback
```

### Field discipline

These rules govern every field in either tier. They name what is binding, and what is open.

1. **Multiple vectors per node are first-class.** Each vector serves a distinct purpose. The substrate does *not* attempt a single fused vector that "represents the node". Different retrieval modes (semantic, structural, frame-routed, temporal) read different vectors. See [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Frame-sensitive resonance".

2. **`ULID`, never sequential integers, never UUID4.** ULIDs give time-ordering for free, are lock-free to generate, and are already in use in `docs/research/mnlm/poc/mesh_inputs/`. A second numeric primary key is forbidden — it invites the temptation to leak it to consumers and harden it into identity.

3. **`Q-IDs` are unique identifiers and the strongest identity signal the substrate accepts.** Wikidata Q-IDs are one-to-one: `Q336997` refers to exactly one person, Thomas Addison; there cannot validly be two distinct entities both bearing that Q-ID. The substrate honours this:
   - **Each Q-ID maps to at most one stable Tier-1 node.** If at any moment two Tier-1 nodes carry the same Q-ID, that is a *transient duplicate state* triggered by concurrent ingestion — it must be resolved by Oneiros (or Argus) on the next tick via §"Agent-driven cleanup" deduplication. The duplicate is a signal, not a feature.
   - **Eager linking respects this.** Before creating a new entity node for a Q-ID-linked chunk, Kadmos checks whether a Tier-1 node carrying that Q-ID already exists. If yes: link to it. If no: create one. The substrate's invariant is that the Q-ID → Tier-1-node mapping is a function, not a relation.
   - **A single node may carry several Q-IDs only when it legitimately spans multiple Wikidata entities** — for example, a bridge concept that aggregates two Wikidata items the substrate has decided to merge, or a node still carrying multiple candidate Q-IDs because the linker has not yet converged on one. The latter is also a transient state: Oneiros either picks one (when evidence accumulates) or splits the node (when the candidates turn out to refer to distinct entities).
   - `QIDTag` carries `(qid, confidence, attached_at)` so Argus can reason about Q-ID assignment as a first-class claim that may itself be revised — the *attachment* of a Q-ID to a node is auditable, even though the Q-ID's reference (the Wikidata entity) is fixed.

4. **`description` is regeneratable and authoritative for its purposes; `description_vector` is the identity-matching surface.** Tier-1 descriptions exist for several consumers: the human debugger reading the mesh, the LLM that needs a short anchor when the activated subgraph is injected, agents performing repairs or disambiguation, the consolidation logic that needs to compare prospective merges, and — crucially — the eager-linking pass that uses `description_vector` for description-based identity matching (per §"Why two tiers — and how identity actually gets committed", signal 2). Descriptions are regenerated by Oneiros from the strongest currently-resonant chunks; `description_generated_at` and `description_source_chunks` make every regeneration auditable. **Substrate logic and consuming agents may read descriptions as authoritative information**, with the understanding that they are summary projections of the underlying chunk evidence — not the chunks themselves. When the description changes (regeneration), `description_vector` is recomputed from it.
   
   For entity-class Tier-1 nodes, populating `description_vector` is recommended — it is the primary mechanism by which the substrate can recognise the same entity in new chunks that lack Q-IDs. For pure concept nodes that have no identity to disambiguate, `description_vector` may be left null. Cost: one extra ~1024-d vector per node where it applies; benefit: identity matching works without Wikidata.

5. **No hierarchical pointer field exists.** No `parent_node_id`, no `belongs_to_category`, no `is_part_of`. Hierarchies that matter to a query are computed from the topology at retrieval time, or expressed via *edges with semantic descriptors* (an edge with `relation_kind = "hierarchy"` and `relation_descriptor = "is_section_of"` is a hierarchy edge, not a hierarchy field). Adding a hierarchy field breaks the universal-node-class promise and ossifies the very classifications that the mesh is designed to refactor as evidence shifts. (The source-anchor pattern in §"Source-anchor entities" is exactly this — a hierarchy of articles → chapters → paragraphs, expressed as edges, not as parent pointers.)

6. **No general `node_type` enum** — but the substrate does carry a few discrete classifications by structural necessity:
   - The tier integer (`consolidation_tier`) — Tier 0 chunks vs. Tier 1+ consolidated nodes vs. higher tiers.
   - The `is_candidate` flag — entity candidates created on first encounter without confident identity.
   - The `is_anchor` flag — anchor nodes (year, geo cell, language, genome position) which obey different mechanics per §"Splits in the wild — also: temporal nodes are special".
   - The `is_source_anchor` flag — source-anchor entities (Wikipedia articles, chapters, paragraphs, URLs) per §"Source-anchor entities" below. These follow normal substrate dynamics but carry an additional `source_url` field and frequently sit at the top of source hierarchies.
   
   Beyond these four flags, "Concept", "Entity", "Bridge", "Hub" are descriptions of *behaviour* rather than stored types. An entity is whatever currently has Q-IDs and external resemblance; a hub is whatever currently has high fan-out. These properties shift over time, and the substrate must let them shift without rewriting types.

7. **Edge weights are not stored on the node.** They are stored on edges (see below) and only cached as `node_potential_cache` on the node for the local saturation check. Putting per-edge weights on the node explodes the row size and makes every edge update a node update.

---

## Source-anchor entities

A class of Tier-1+ consolidated nodes flagged with `is_source_anchor = True`. These represent **the source itself**, not the entity the source describes:

- *Person Thomas Addison* is one entity (`Q336997`, biographical description, etc.).
- *Wikipedia article "Thomas Addison"* is a separate source-anchor entity (`source_url = "https://en.wikipedia.org/wiki/Thomas_Addison"`, description `"Wikipedia article on Thomas Addison"`).
- *Chapter "Discovery of Addison's disease" within that article* is yet another source-anchor entity, linked to the parent article via an edge with `relation_kind = "hierarchy"`, `relation_descriptor = "is_section_of"`.
- *Wikipedia article "Biochemistry"* is another source-anchor entity, linked to chapters and to the entities those chapters discuss.

Source-anchor entities turn provenance into a structural feature of the mesh rather than only a metadata field on chunks. Benefits:

- The substrate can answer "what does Wikipedia say about Thomas Addison?" by following edges to the relevant source-anchor entity and from there to the chunks that were extracted from it.
- Multiple chunks extracted from the same source share the same source-anchor entity — saving storage and giving Argus a single point at which to assess source reliability.
- Source hierarchies (article → chapter → paragraph) are expressed as ordinary edges with `relation_kind = "hierarchy"`, not as a parallel hierarchy schema.
- A source-anchor entity that has accumulated many flagged chunks (false-information findings, contradictions) is a structural signal about source quality — Argus can reason about reliability per-source without a separate source-quality table.

**Description convention.** Source-anchor descriptions follow a stable, machine-parseable format. The description combines a *source-type tag*, the source's *human-readable title*, and a *structured anchor* (URL, DOI, ISBN, or similar) in parentheses. The format is:

```
{type}: {title} ({anchor})
```

Examples covering the common cases:

- `'Wikipedia article: Thomas Addison (https://en.wikipedia.org/wiki/Thomas_Addison)'`
- `'Wikipedia section: Discovery of Addison's disease — Thomas Addison § Career (https://en.wikipedia.org/wiki/Thomas_Addison#Career)'`
- `'Wikipedia paragraph: ¶3 of Thomas Addison § Early life (https://en.wikipedia.org/wiki/Thomas_Addison#Early_life:p3)'`
- `'Wikipedia article: Biochemistry (https://en.wikipedia.org/wiki/Biochemistry)'`
- `'Book: The History of Endocrinology, by John Smith (ISBN:978-0-12-345678-9)'`
- `'Book chapter: "Thyroid hormones" — The History of Endocrinology, chapter 4 (ISBN:978-0-12-345678-9#ch4)'`
- `'Paper: "On the Constitutional and Local Effects of Disease of the Suprarenal Capsules" by Thomas Addison, 1855 (doi:10.1000/example)'`
- `'Web page: Pantheon Project — About (https://example.org/about)'`
- `'Dataset: Human Protein Atlas v22 (https://www.proteinatlas.org/about)'`

The format mirrors the natural-language way agents and humans refer to sources, while leaving a structured anchor embedded for direct provenance retrieval. The `source_url` field on the node carries the same anchor separately in a machine-clean form (no surrounding title text), so a consumer that needs the URL specifically does not have to parse it back out of the description. The `description_vector` (when populated on a source-anchor) embeds this whole description string, so source-anchor entities can be matched against each other and against incoming source citations via the same description-based eager-linking signal that named entities use — see §"Why two tiers — and how identity actually gets committed" signal 2.

For sources without a globally-resolvable anchor (private corpora, internal documents), use a stable internal identifier in the same parenthetical position — e.g., `'Internal report: Q3 2024 ingestion review (internal://reports/2024-q3-ingest)'`. The convention is about *uniqueness and re-derivability*, not about web-public reachability.

**Mechanics.** Source-anchor entities follow normal substrate dynamics: they have semantic_vector and frame_vector and (often) description_vector, they participate in Hebbian update and decay, they can be consolidated (a once-stable Wikipedia article URL is itself a stable thing), and they can be sub-node-split when one source-anchor accumulates too many references (rare but possible — a heavily-cited textbook with many chapters might split into per-chapter sub-nodes). They never carry Q-IDs unless the source itself has one (some sources do — books with ISBNs, papers with DOIs; these can be treated as identity anchors analogous to Q-IDs).

**Relationship to chunk provenance.** A Tier-0 chunk's `source: SourceProvenance` field still carries the immune-system-required source identity. The new pattern is additive: when Kadmos extracts a chunk, it both populates the chunk's `source` field *and* creates (or links to existing) a source-anchor entity, then attaches an edge from chunk to source-anchor with `relation_kind = "extraction"`, `relation_descriptor = "extracted_from"`, `creation_context = "kadmos_extraction"`. The chunk now has both an inline provenance record (cheap to read for the immune system) and a structural connection to the source-anchor (queryable via Spreading Activation).

This is optional infrastructure — substrates that don't need source-as-entity reasoning can leave `is_source_anchor` false on every node. But for substrates that ingest from cited sources (Wikipedia, scientific literature, web crawls), creating source-anchor entities is the cleanest way to make source-as-entity queries possible.

---

## Edge anatomy

Edges are the substrate's truth. Everything the mesh "knows" is encoded in which nodes are connected, with what strength, with what frame consistency, and — optionally — with what semantic descriptor and Wikidata property identifier. Nodes hold material; edges hold meaning.

```python
class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: ULID
    target_id: ULID
    weight: float                       # current conductance; in [0, w_max], not normalised
    born_at: datetime
    last_fired_at: datetime

    decay_tier: int = 0                 # decay-profile index; higher tier → gentler decay
    frame_consistency: float = 1.0      # how well the edge's endpoints share a frame

    eligibility: float = 0.0            # decaying recent-firing trace, for credit assignment
    feedback_modulated_strength: float = 0.0  # lifetime sum of feedback-modulated updates (audit)

    # Optional semantic descriptors — useful for agents reading the mesh,
    # for repair operations, and for human inspection. None of these are
    # required; substrate dynamics (decay, Hebbian update, saturation,
    # splits) ignore them. They are agent-facing metadata, not retrieval
    # primitives.
    relation_descriptor: str | None = None    # short label, e.g. "owns", "located_in", "happened_in_year"
    relation_kind: str | None = None          # broader category, e.g. "attribute", "ownership",
                                              #   "hierarchy", "movement", "attribution",
                                              #   "temporal", "causal", "co-occurrence",
                                              #   "extraction" (chunk → source-anchor)
    description: str | None = None            # longer free-text description of the relation;
                                              #   max ~512 chars; useful when relation_descriptor
                                              #   is too short to capture nuance
    pids: list[PIDTag] = []                   # Wikidata property identifiers for this relation:
                                              #   P19 (place of birth), P31 (instance of),
                                              #   P50 (author), etc. Like Q-IDs on nodes, P-IDs
                                              #   are unique identifiers — each P-ID refers to
                                              #   exactly one Wikidata property
    creation_context: str | None = None       # how this edge came to be:
                                              #   "kadmos_extraction", "oneiros_consolidation",
                                              #   "argus_proposal", "hebbian_co_fire",
                                              #   "frame_routing", "agent_repair"
```

Edges carry both *quantitative* fields (weight, freshness, decay tier, frame consistency, eligibility) and *optional semantic descriptors* (`relation_descriptor`, `relation_kind`, `description`, `pids`, `creation_context`). The descriptors are not the substrate's primary truth — that lives in the vectors and the topology — but they are valuable information for agents reading the mesh, performing repairs, or reasoning about the structure of the relations.

`relation_descriptor` is a short string label intended for human and agent comprehension (e.g., "owns", "located_in", "happened_in_year", "contradicts"). `relation_kind` is a broader category. `description` is a free-text longer form when the short label is not enough. `pids` lists Wikidata property identifiers — P19 (place of birth), P31 (instance of), P50 (author) — analogous to Q-IDs on nodes. P-IDs are one-to-one identifiers (each P-ID refers to exactly one Wikidata property); the substrate honours this just as it honours Q-ID uniqueness on nodes. `creation_context` records how the edge came to be (`kadmos_extraction`, `oneiros_consolidation`, `argus_proposal`, `hebbian_co_fire`, `frame_routing`, `agent_repair`).

These fields are *optional* and *not enums* (with the exception of P-IDs being constrained to the Wikidata namespace when present). An edge created by pure Hebbian co-firing may have everything set to `None` — the topology has no semantic story to tell about why this co-firing happened. An edge that Kadmos extracts as "Thomas Addison was born in 1793 in Long Benton" may carry `relation_descriptor = "born_in"`, `relation_kind = "attribute"`, `pids = [(P19, 0.95, ...)]`. An edge proposed by Argus during contradiction resolution may carry `relation_descriptor = "contradicts"`, `relation_kind = "attribution"`. Agents that need this information read it; agents that don't need it ignore it.

The substrate's automatic dynamics (decay, Hebbian update, saturation enforcement, splits, renormalisation) read only the quantitative fields — they propagate via SpMV against (source, target, weight) tuples in the edge tensor. The semantic descriptors travel with the edge for the benefit of consumers and repair logic. See [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Storage choices" for how this dual nature is realised in storage: a fast PyTorch sparse CSR tensor for the runtime SpMV, a parallel Lance edge-metadata table for the rich descriptors.

This is a deliberate departure from the older "no string labels on edges" guidance in `TARGET_ARCHITECTURE.md`. That guidance was correct about its concern — string labels must not be the *retrieval primitive*, and the substrate must reason in vector space — but extending that into "no string information at all on edges" was overreach. The substrate dynamics ignore the descriptors; agents can use them. Both are doctrine.

---

## The dynamics

The substrate is governed by five primitive operations and one homeostatic correction. Together, they produce all the emergent behaviour the substrate needs: growth, forgetting, consolidation, hub formation, refactoring, and pathology resistance.

### 1. Hebbian update

When two nodes co-fire during a Spreading Activation pass, the edge between them strengthens.

```
w_ij ← w_ij + α · fire(i) · fire(j) · (1 + β · feedback)
```

`α` is the Hebbian rate, default small (≈ 1e-2 per firing). `β` controls the strength of three-factor reward modulation; `feedback ∈ [-1, +1]` is supplied by the consumer of the activation result. Feedback details are in [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Three-factor reinforcement learning". When no feedback is provided, the rule degenerates to plain Hebb (β · feedback = 0). Negative feedback can drive the update to zero or, with `β > 1`, actively weaken.

If an edge does not exist between two co-firing nodes, the Hebbian update creates one — subject to the saturation check below.

### 2. Super-linear decay

Edges that are not fired weaken — and stronger unused edges weaken faster than weaker unused edges.

```
dw/dt = -λ · w^k          with k > 1   (default k = 2)
```

Quadratic decay (k = 2) means a 0.8-weight edge loses absolute weight 16× faster than a 0.2-weight edge. The asymmetry is the point.

**Why super-linear, not multiplicative.** Multiplicative decay (`w *= 1 − λ`) preserves the relative ordering of edge weights but makes strong edges hard to lose. That is exactly the failure mode the substrate must avoid: strong edges that no longer reflect reality but persist because they were once strong. Under super-linear decay, the *only* way an edge stays at high weight is to be actively maintained by ongoing co-firing. The high-weight region of the mesh therefore always reflects *currently relevant* structure, not historically important structure.

**Half-life intuition.** Solving the ODE for k = 2: the time for an edge to drop from `w_0` to `w_1` is `(1/w_1 − 1/w_0) / λ`. So 0.8 → 0.7 takes ~0.18/λ time units; 0.2 → 0.1 takes 5/λ — about 28× slower. Strong edges have a long descent through the middle range and a long tail at the bottom, but their initial drop from saturation is steep.

**Tier-modulated decay.** Higher consolidation tiers carry gentler decay exponents. Tier 0 chunks: k = 2 (aggressive). Tier 1 entities: k ≈ 1.5. Tier 2 hubs: k ≈ 1.2. Tier 3 long-term substrate: k = 1 (linear) or even sub-linear in extreme cases. This creates a layered memory: working concepts evaporate fast unless reinforced; foundational structure persists. The tier itself is earned through Oneiros, never assigned. See §"Consolidation, splits, and tier promotion".

### 3. Saturation — both count and weight

Each node has two saturation caps, indexed by tier:

| Tier | Max edges (count) | Max Σ weight |
|---|---|---|
| 0 — Chunk | 10 000 | S |
| 1 — Concept / Entity | 50 000 | 5·S |
| 2 — Established | 200 000 | 20·S |
| 3 — Hub | 1 000 000 | 100·S |

`S` is the substrate-wide weight unit, set by the global renormalisation target (see §6 below). Concrete numbers are tuning parameters; the binding rule is the *shape* — **both** axes are bounded, **both** caps grow with tier, and the count cap rises faster than the weight cap so that hubs hold many lighter connections rather than few very heavy ones.

When a new edge would cause either cap to be exceeded, the mesh enforces:

1. **The new edge must be strictly stronger than the weakest existing edge at the saturated node.** Otherwise it is rejected.
2. **The weakest existing edge(s) are removed until the cap is restored** (after accepting the new edge).

This is not a queue, not a heuristic, not subject to override. It is the only way the substrate stays bounded without arbitrary cleanup. It also produces, as a side effect, a precious property: every existing edge at a saturated node is, in some sense, *defended*. New evidence can join the conversation only if it brings enough strength to displace incumbent evidence. This makes the substrate resistant to noise — and, as discussed in §"Pathology and therapy" below, sometimes too resistant.

### 4. Atrophy ≠ death (decoupled)

A node whose `node_potential` (sum of edge weights) drops below the population-relative *healthy band* is **atrophied**, not removed. The healthy band is currently defined as the `[μ − σ, μ + σ]` range over the substrate's node-potential distribution, with an age correction: nodes younger than ~3 consolidation cycles get a wider band so they have time to grow before being judged.

Atrophied nodes:

- **stay in the substrate**
- **lose firing privileges** (they do not propagate during Spreading Activation by default, though they can be reactivated by sufficiently strong directed activation — the "suddenly remembered" mechanism)
- **continue to receive Hebbian updates** if external evidence resonates with them (atrophy is reversible)
- **are candidates for pruning** when, and only when, the system is under resource pressure

This decoupling is non-negotiable. It produces a beautiful invariant:

> **The mesh loses memory only under genuine resource pressure. In a system with unbounded RAM and unbounded compute, nothing is ever forgotten.**

A second, equally important invariant: forgetting is *scalable*. The same mesh code running on a 32 GB laptop forgets more than the same mesh on a 1 TB workstation, because the laptop hits resource pressure sooner. There is no fixed `forgetting_rate` parameter. Forgetting is a function of how much room the mesh has to think.

### 5. Pruning (only under resource pressure)

When the operator-defined resource ceiling is breached — RAM occupancy above threshold, query latency above target, edge tensor exceeding GPU memory — the **pruner** runs. The pruner has the simplest possible logic in the entire substrate:

1. Sort all atrophied nodes by `node_potential` ascending. Sort all edges by `weight` ascending.
2. Drop from the bottom until the resource pressure is below the recovery threshold.

There is no policy beyond ordering. Atrophied nodes and weakest edges go first. The pruner does not look at content, does not consult Q-IDs, does not consider provenance. Those are not its concerns. Its concern is that the mesh fits in the box.

Pruning is the *only* operation in the substrate that destroys information. Every other operation either creates or transforms or moves; pruning alone deletes. The doctrine that pruning happens only under pressure is therefore the substrate's most important data-preservation guarantee.

### 6. Global homeostatic renormalisation

The substrate maintains a target ratio between node count and total edge weight. The target is a tuning parameter; a reasonable default is `R_ideal = 1000` (i.e., one node carries on average 1000 weight units across all its edges).

Once per Oneiros tick (or on a configurable schedule):

```
ratio_actual = Σ(all edge weights) / count(all nodes)
if |ratio_actual / R_ideal − 1| > ε:
    correction_factor = R_ideal / ratio_actual
    for every edge: w ← w · correction_factor
```

`ε` (default ≈ 0.01) avoids unnecessary work on tiny drifts. The correction is multiplicative across **all** edges — uniform across tiers, weights, ages — so relative ordering is preserved. The mesh's energy budget stays bounded.

**Tier-aware variant (optional refinement).** Higher-tier edges may receive a softer correction (e.g., 50% of the renormalisation factor) so that consolidated long-term knowledge erodes more slowly under global pressure. This is a free parameter, not a binding rule.

**What this gives the substrate.** Combined with super-linear decay, renormalisation is the synaptic-scaling analogue of biological cortex (Turrigiano & Nelson, 2004): individual synapses adjust quickly through Hebbian dynamics, while a slower homeostatic loop keeps the total post-synaptic input in a stable range so the system as a whole neither saturates nor goes silent. In the substrate, this means an edge's stable weight is proportional to its **relative** firing frequency across the whole mesh. A perfectly-average-firing edge holds its weight; an edge that fires more often than average grows; one that fires less shrinks. There is no absolute "important" threshold — relevance is always defined relative to current substrate activity.

---

## Consolidation, splits, and tier promotion

The substrate does not consolidate continuously. Consolidation is the work of **Oneiros**, which runs on its own schedule (originally as a periodic batch; in production possibly continuously with backpressure). When Oneiros runs, it performs four kinds of operation, in order:

### A. Replay — protecting the rare-but-important

Oneiros samples the substrate's edges with a bias toward *bridges* — edges that connect otherwise-separate dense regions, or that are the only path between two clusters. These "structurally important" edges fire even when no external query touches them, protecting them from super-linear decay. Without this protection, the mesh would lose the rare-but-important class of knowledge (the telephone-number / Mendel-class facts) within a few decay cycles. The bridge metric is a topological computation — no human has to mark anything "important."

### B. Consolidation — promoting Tier 0 → Tier 1 (and onward)

When a cluster of Tier-0 chunks reliably co-fires across many distinct activation contexts, Oneiros proposes a Tier-1 consolidated node. The consolidated node:

- carries a description regenerated by a small LLM call from the strongest member chunks
- inherits Q-IDs that appear with high consistency across the member chunks (with reduced confidence if disagreement existed)
- builds initial edges to other consolidated nodes by aggregating the chunk-level edges
- receives a `consolidation_tier = 1` and an updated decay profile

The Tier-0 chunks remain in the substrate. They are not deleted by promotion. The Tier-1 node sits *above* them, aggregating their evidence; if the consolidation later turns out to be wrong (say, two distinct people were merged into one Tier-1 node), Argus can mark the consolidated node as suspect and Oneiros can split it back into separate Tier-1 nodes that re-attach to the appropriate chunks. Promotion is reversible.

Tier 1 → Tier 2 → Tier 3 promotions follow the same pattern, gated on different thresholds: number of distinct activation contexts, age, breadth of incoming references, and survival across Argus's pathology checks.

### C. Sub-node splits — managing hubs

When a Tier-2 or Tier-3 hub approaches saturation **and** its connections cluster into recognisable sub-themes, Oneiros may split it.

Example: the `London` hub holds millions of associations. When Oneiros's clustering pass detects that many of those associations group naturally into themes (`real_estate`, `restaurants`, `history`, `government`, `music`), it proposes sub-nodes — `London_real_estate`, `London_history`, etc. — and moves the relevant edges from `London` to each new sub-node. `London` retains only edges to the new sub-nodes and to other genuinely top-level peers.

The mathematics of the split is non-trivial because the split must **not change the effective resistance** between the hub and any of the former leaves. (Otherwise, every consumer of the substrate would notice that a quiet maintenance operation changed the mesh's apparent structure, which is unacceptable.)

**The split rule.** Let the hub be `H` and let `n` edges with weights `w_1, …, w_n` be moved into a new sub-node `Sub`. Treat each weight as conductance (`R = 1/w`). The substrate sets:

```
w_HS  =  Σ w_i                              (hub-to-sub conductance)
w_i'  =  w_i · w_HS / (w_HS − w_i)          (sub-to-leaf conductance, per former edge)
       =  w_i / (1 − p_i)     where  p_i = w_i / Σ w_i
```

This satisfies the series-conductance identity `(w_HS · w_i') / (w_HS + w_i') = w_i`, which means the effective conductance from `H` to each former leaf is **exactly preserved**.

**Properties.**

1. The hub's edge count drops from `n` to `1` (one edge to `Sub`); this is the saturation relief.
2. Sub-leaf weights are slightly larger than the original direct weights. The scaling factor is `1/(1 − p_i)`. For balanced large clusters (n ≥ 10), the inflation is negligible (~10% or less). For small clusters (n = 2 or 3), it is significant. Practical rule: **splits require n ≥ 8** to avoid wasting saturation budget on minor reorganisations.
3. The total weight on `Sub` is `Σ w_i' + w_HS ≥ 2 · Σ w_i`. The split therefore costs additional saturation budget — `Sub` carries about double the weight that the moved edges carried at the hub. This is the unavoidable price of the relay; it must be checked against `Sub`'s tier saturation cap.
4. **Spreading Activation behaviour is structurally invariant under the split.** Any propagation that previously reached a former leaf via the hub now reaches it via the same effective conductance, just through one extra hop. Consumers do not observe the split.

This invariance is what allows Oneiros to split aggressively when needed — the substrate refactors itself silently without consumer-visible regressions.

### D. Splits in the wild — also: temporal nodes are special

The `London` example above generalises to most concept hubs. But two kinds of node should *not* be sub-node-split:

- **Pure index nodes** — `the year 2021`, `the year 1819`, `H3 cell 88234fa3...`, `the German language`, `the genome of Homo sapiens`. These are anchors on a continuous axis. Their meaning is "this is a coordinate", not "this is a concept." They should not own their associations as fan-out edges; instead, every observation node carries an optional `temporal_anchor`, `geo_anchor`, or `language_anchor` field, and queries over these axes use index lookups, not graph traversal.

This is a separate **anchor-node class** that obeys different rules: very high cap (effectively unbounded), no Hebbian updates, no decay, no split. They are immutable infrastructure. The decision to make a node an anchor is made at creation time by the extractor — and once made, is not revisited. It is the only discrete typing decision the substrate exposes, and it is made for a clear engineering reason: temporal and spatial axes have different topology than conceptual neighbourhoods, and pretending otherwise leaks performance and correctness.

---

## Agent-driven cleanup

The substrate's automatic mechanisms — decay, Hebbian reinforcement, saturation enforcement, atrophy, pruning under resource pressure — handle the substrate's bulk maintenance without intervention. Pantheon agents may also act on the substrate intentionally, performing cleanup that the automatic mechanisms cannot: identifying *specific* problems and resolving them.

Agent-driven cleanup operates on existing substrate state, post-hoc, in the same discipline as the immune system. It is **not** a pre-gate. It does **not** block insertion. It happens after observation chunks are in the substrate and after Oneiros has had a chance to consolidate them. The agents that do this work are reading the substrate as it currently exists, finding specific identified problems, and acting on what they find.

The four canonical operations:

### Deduplication

Argus or Athene detects that two Tier-1 nodes refer to the same underlying entity — same Q-ID, near-identical descriptions, dense overlap of referencing chunks, or strong topology resemblance. The agent emits a `MergeProposal` finding (a typed record per [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Findings as first-class chronicle data"). Oneiros applies the merge on its next tick, preserving the union of edges (with weight-summing on duplicate target edges, capped by the recipient node's saturation), updating the audit ledger, and tagging the resulting node with the union of provenance. The pre-merge Tier-1 IDs are recorded so that historical references (audit trails, federation peers) can still resolve.

### Contradiction resolution

Argus identifies two claims with directly contradicting frame-content combinations — for example, one chunk asserts "Drug X causes effect Y" with frame *current claim*, another asserts "Drug X does not cause effect Y" with the same frame. Argus emits a `ContradictionFinding` linking the two and writes `CONTRADICTS` edges between them with appropriate `relation_descriptor` and `relation_kind` fields. The substrate's effective answer to a query about Drug X then naturally surfaces the contradiction, and downstream activations carry the unresolved tension. Oneiros may, when evidence accumulates strongly enough on one side, weaken the edges to the contradicted node — but the resolution is evidence-driven, not adjudicated. Argus makes contradiction *legible*; the substrate's dynamics decide which side the topology eventually favours.

### False information removal

When an agent has high confidence — beyond "this might be wrong" into "this is demonstrably wrong, and I have the evidence" — that a chunk or consolidated node carries factually incorrect information, the agent emits a `RemovalProposal` finding with the supporting evidence trail. Oneiros applies removal on its next tick, logging the removal in the audit ledger together with the evidence. The removed node is **not silently forgotten**: the audit record persists, so the substrate retains the memory that this claim was once present and was later refuted. This matters for federation, for Mnemosyne's self-improvement loop ([`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Self-improvement loop"), and for keeping the substrate honest about what it once believed.

Removal is permitted but reversible only by re-acquisition from sources. Agents should weigh the evidence carefully before proposing removal — the bar is "demonstrably wrong with traceable evidence," not "I disagree" or "this seems unlikely". Disagreement and likelihood are handled by frame-tagging and contradiction modelling, not by removal.

### Redundancy compression

When many chunks make essentially the same observation in slightly different words, an agent (typically Athene during a verification pass) can propose consolidation. Oneiros consolidates them with appropriate strength preservation: the resulting Tier-1 node carries the aggregate evidence of all merged chunks. The chunks themselves either fold into the consolidated node (when the redundancy is total) or remain as Tier-0 historical record (when the chunks have distinct provenance worth preserving). Argus or Oneiros chooses on a per-cluster basis.

### Why these are not pre-gates

Each of these operations targets *specific identified problems* in the substrate as it exists, after evidence has accumulated. They are the opposite of pre-validation:

- A pre-gate decides "does this content deserve to enter?" before the content is in the substrate. Forbidden by [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) and [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) and by this document.
- Agent-driven cleanup decides "how should the substrate be repaired given what is already there?" after the content is in. Permitted, encouraged, and structurally necessary for substrate hygiene at scale.

The distinction is in *when* the operation happens and *what evidence* is available. Pre-gates have only the new chunk to judge; agent cleanup has the whole substrate plus the new chunk plus the history of what other chunks said about the same topic. Agent cleanup, automatic decay, pruning under resource pressure, and pathology therapy are four separate mechanisms with four different triggers — they do not interfere with each other, and together they make the substrate self-maintaining.

---

## Pathology and therapy

The substrate's dynamics are powerful because they are self-reinforcing. They are also dangerous for the same reason: a region that fires often enough may become so dominant that it suppresses alternatives, absorbs corrections instead of being weakened by them, and locks new evidence out by saturation. This pattern has biological analogues — rumination, obsession, monomania — and it must be detectable and treatable in the substrate.

This is distinct from agent-driven cleanup (above): cleanup targets *specific identified problems*; therapy targets *patterns of pathology* that emerge from the substrate's own dynamics. Both are post-hoc, both are agent-driven, both are auditable. They differ in what they look for and what they do.

This section specifies how the pathology / therapy loop works. The discipline is post-hoc, sample-based, asynchronous — Argus inspects topology on her own schedule and emits findings; Oneiros applies therapy at tick boundaries; no real-time gate inspects every Hebbian update. The substrate-level surveillance described here and the claim-level immune-system work share this temporal logic; both reject pre-gating by design, because pre-gating would force diagnostic decisions on insufficient evidence and would lock the substrate into whoever last validated it.

### The five topological symptoms of a thought-spiral

A region of the substrate exhibits **mind-lock pathology** when it shows one or more of:

1. **Internal/external asymmetry.** The ratio of edges that stay inside the region to edges that cross out grows pathologically. A healthy concept connects outward; a spiral closes in on itself.

2. **Activation hysteresis.** After being activated, the region's energy decays slower than comparable regions of similar size. The region "hangs" — biological rumination.

3. **Context promiscuity.** The region is activated by too many semantically diverse contexts. It pulls activation away from contextually-more-appropriate alternatives. (`activation_entropy` per node is the per-node counterpart.)

4. **Refutation absorption.** Refutation-framed chunks that *should* weaken edges in the region instead get incorporated as positive reinforcement. This is the killer diagnostic and the hardest to detect — it requires the frame-sensitive encoder to be working correctly *and* a meta-observation that compares "this chunk's frame was refutative; why did its insertion strengthen the very edges it should have weakened?".

5. **Saturation lockout for legitimate new input.** Chunks that *should* attach to the region are rejected at the saturation barrier because every existing edge in the region is too strong. The region cannot self-correct because it has no room left to update.

All five are expressible as graph-statistical computations over a sample of the substrate. They are Argus's substrate-level surveillance work. Argus does **not** read content to detect them; she reads topology.

### Five staged therapies

Therapy escalates only when the previous stage fails to bring the diagnostic metric back into the healthy band. The discipline is biological-medical: the gentlest effective intervention, then up.

**Stage 1 — Activation temperature.** During selected Oneiros cycles, Spreading Activation routing is made stochastic instead of deterministic-strongest. A Boltzmann sampling over the top-K outgoing edges (with a configurable temperature) means the substrate occasionally tries weaker paths. Over time this gives suppressed alternatives a chance to fire and accumulate Hebbian strength. Nobody is harmed; it is the substrate's equivalent of cognitive defocusing.

**Stage 2 — Dominance penalty.** When a region's share of total activation exceeds a rolling-window threshold, the region's decay rate is temporarily increased. The substrate's equivalent of synaptic fatigue: what fires too often, tires. This is reversible the moment the activation share normalises.

**Stage 3 — Forced refutation re-injection.** Argus searches the historical corpus for chunks that contradict the dominant region's claims and re-injects them with *amplified* refutation framing and explicit absorption protection (the chunk is tagged so that the Hebbian update from its insertion is forced to weaken, not strengthen, the contradicted edges). This is targeted therapeutic confrontation.

**Stage 4 — Saturation demolition.** In severe cases, the strongest internal edges of the region are temporarily halved or zeroed. This opens saturation budget for alternatives. It is high-risk — the substrate has lost information that may have been correct — but the lost information is recoverable through subsequent re-activation if it deserves to come back. This is the substrate's equivalent of cognitive disruption.

**Stage 5 — Quarantine / split.** The region is moved into an isolated sub-mesh that continues to exist but no longer interacts with the main substrate. The main substrate regrows the relevant area without the region's interference. This is mesh dissociation: nothing is destroyed; the region is contained. If new evidence in the main substrate later re-converges on the quarantined pattern, the bridge can be re-established. This is the most invasive and the slowest to commit to; Argus requires multiple confirmations across multiple Oneiros cycles before recommending it.

### The Mendel risk — a consideration to weigh

A topological pattern that *looks* like a thought-spiral may be a correct rare insight the rest of the substrate has not yet caught up with. Mendel's genetics was rejected for four decades because the rest of biology was not ready; an over-aggressive anti-spiral mechanism in 1865 would have suppressed it.

This is a real risk and Argus must weigh it before recommending invasive therapy. The discipline is escalation order, audit trail, and proportionality:

- **Stages 1–3 (temperature, dominance penalty, refutation re-injection)** are reversible and information-preserving. Apply freely when topological symptoms are clear; the cost of a false positive is small.
- **Stage 4 (saturation demolition)** halves or zeroes specific edge weights but keeps endpoints. Edge state is partially recoverable through subsequent activation if the region deserves to come back. Apply when symptoms are persistent across multiple Oneiros cycles and Stages 1–3 have not normalised the region.
- **Stage 5 (quarantine / split)** isolates without destroying. Apply when symptoms are severe and persistent and Stage 4 has not normalised the region.

**Therapy *may* destroy information** — Argus may zero individual edges, may mark specific chunks for removal, and may even propose removal of consolidated nodes when the topological evidence of pathology is strong and the Mendel risk has been weighed and rejected. Every destruction is logged in the audit ledger with the topological evidence that justified it; recovery requires re-acquisition from sources but is not architecturally precluded.

The substrate does *not* enforce a categorical "no destruction" rule. It enforces:

- **Escalation order** — Stages 1–3 before 4 before 5.
- **Repeated evidence** — destructive therapy requires symptoms persisting across multiple Oneiros ticks, not single-tick samples.
- **Audit trail** — every destruction is logged with the topological evidence that justified it.
- **Proportionality** — Argus weighs probability of pathology against Mendel risk *before* recommending Stage 4 or Stage 5; the weighing is itself logged as part of the finding.

The judgement is Argus's, made for each specific region. Mnemosyne tracks Argus's destruction recommendations over time and tunes Argus's thresholds via the standard A/B framework when calibration data accumulates.

The substrate's stance: contestation and weak evidence stay legible — the substrate does not flatten itself into settled summaries, and a region holding a minority position keeps the right to grow back if subsequent evidence supports it. But this epistemic openness is not a categorical prohibition on destruction. Refusing to ever remove anything would prevent the substrate from cleaning up information that has been demonstrated wrong — and an everything-we-ever-thought, never-reconsidered substrate is itself a flattening, just one biased toward the past rather than toward the present. The binding constraint is *audit*, not *preservation-at-all-costs*: information may go, but the substrate does not silently forget that it once held the claim.

### Argus's substrate role

Argus's role expands here from claim-level contradiction detection to **structural pathology surveillance**. The work is sample-based and post-hoc — Argus does not run on every Hebbian update, she samples regions on her own clock. When she finds pathology, she emits a `Finding` (per the schema in [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Findings as first-class chronicle data") with the topological evidence and a proposed therapy stage. Oneiros consumes the finding and applies the therapy on its next tick. The cycle closes.

---

## Worked example: Thomas Addison and Thyroxine

To make the doctrine concrete, trace what happens when Kadmos extracts the following two paragraphs from Wikipedia (originally given in German; for the doctrine they are sketched abstractly):

> *"Thomas Addison discovered in 1849 a disease originating in the adrenal glands. T. B. Aldrich and Takamine Jōkichi extracted in 1901 a substance from animal kidneys, which they called adrenaline. Aldrich determined the molecular formula and Friedrich Stolz achieved the chemical synthesis in 1904. With this, biochemistry achieved in 1904 the first artificial production of a hormone."*
>
> *"Goitre formation is another hormonal disease of the thyroid gland, which since 1820 (after Jean-François Coindet) could be relieved by iodine administration. Only in 1915 did Edward Calvin Kendall succeed in isolating a crystalline substance of the thyroid gland. He erroneously held it to be an oxindole derivative and therefore named it thyroxine. Synthetically, thyroxine was made producible from 1926 by Charles Robert Harington."*

What happens in the substrate, step by step:

**Insertion (Kadmos / Tier 0 chunks + eager Tier-1 entity creation).**

Kadmos extracts ~10 observation chunks per paragraph, each carrying its own semantic vector and its own frame vector. The frame vector for Kendall's claim about the oxindole derivative is *historical-attributional with negative-veridicality marker*, distinct from the frame vector of "thyroxine is iodothyronine" (which would be *current-ontological*).

Kadmos also runs an entity-linking pass. For named entities it can confidently identify — Thomas Addison (Q336997), Edward Calvin Kendall (Q1289672), Thyroxine (Q186437), the Adrenal Gland (Q190454), the Year 1849, the Year 1820, etc. — the insertion path **eagerly attaches each chunk's reference edges to the corresponding Tier-1 entity nodes**. If those Tier-1 entity nodes do not yet exist in the substrate, Kadmos creates them on the spot, populated with: the Q-ID, an initial semantic vector (from the entity's name + immediate context), an initial frame vector, and an initial description (a one-line LLM-generated summary).

For named entities Kadmos cannot link to a Q-ID confidently — say, a "Friedrich Stolz" mentioned with limited disambiguating context — Kadmos still attempts **description-based eager linking** (per signal 2 in §"Why two tiers — and how identity actually gets committed"): it builds a description from the available context ("Friedrich Stolz, German chemist, achieved chemical synthesis of adrenaline in 1904") and runs cosine similarity against existing Tier-1 nodes' `description_vector`s, weighted by structural proximity to the other entities being ingested in the same paragraph (Aldrich, Adrenaline, Year 1904). If a single existing node clearly wins, link to it. If not, create an entity-candidate with `is_candidate = True` and a description_vector populated from the candidate's own description; later evidence may confirm or merge it.

For non-entity concepts the chunk involves — `private practice ownership`, `house-buying as a life-event`, `chemical synthesis as a method`, `endocrine disease` — Kadmos creates Tier-1 concept candidates as it encounters them. These have no Q-IDs (none exist in Wikidata for some of these), but they have descriptions and accumulate references over time. Oneiros consolidates them when the same concept gets referenced from multiple chunks.

Kadmos also creates **source-anchor entities** for the source itself. The two paragraphs come from a Wikipedia article (say, "History of biochemistry" or "Hormone"). Kadmos creates (or links to existing) source-anchor entities for the article and for the relevant section / chapter. Each chunk attaches an edge to its source-anchor entity (`relation_kind = "extraction"`, `relation_descriptor = "extracted_from"`). The source-anchor entities themselves connect via `is_section_of` edges into the broader source hierarchy. Once these exist, queries like "what does Wikipedia say about the discovery of adrenaline?" can route through the source-anchor side of the substrate.

So after ingesting these two paragraphs, the substrate has:
- ~20 Tier-0 chunk nodes (the observations themselves)
- A handful of Tier-1 entity nodes for the named individuals, places, and dates (`Thomas Addison`, `Kendall`, `Thyroxine`, `Adrenal Gland`, `Year 1849`, etc.) — created eagerly because Q-ID linking was confident; each carries a `description_vector` to support later description-based identity matching
- A handful of Tier-1 concept nodes for the abstract concepts mentioned (`hormone discovery`, `chemical synthesis`, `endocrine disease`)
- Source-anchor entities for the article and its relevant section, with `is_source_anchor = True` and `source_url` populated
- Reference edges from every chunk to every entity / concept it mentions, plus `extracted_from` edges from chunks to source-anchors, plus `is_section_of` edges between source-anchors — all carrying `relation_descriptor`, `relation_kind`, and (where applicable) `pids` such as `P19` for "born in" or `P31` for "instance of"

**Spreading activation (immediate).**

The next user query "Tell me about the discovery of thyroxine" injects through the diversified-injection path (per [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Diversified injection"). Spreading Activation finds the `Thyroxine` Tier-1 entity node directly via its Q-ID-anchored vector, and propagates outward through the chunks that reference it and the related entities (`Adrenal Gland`, `Kendall`, `Year 1915`, etc.).

The Kendall-error chunk is included in the activation with its frame-tag intact. Because the query is *current-ontological* in frame, the Kendall chunk's *historical-attributional* frame produces low `frame_consistency` against the active query frame; the chunk's contribution is therefore weighted-down at the propagation step. The user's answer correctly says "Thyroxine is iodothyronine — Kendall originally thought it was an oxindole derivative, but that turned out to be wrong; the name stuck."

If instead the query had been "What did Kendall originally think the structure of thyroxine was?", the active query frame would be *historical-attributional*, and the Kendall chunk would propagate with full strength.

**Consolidation refinement (Oneiros, ongoing).**

As more chunks arrive that reference `Thomas Addison`, Oneiros enriches the existing entity node: the description is regenerated from the strongest current chunks, the structural vector is updated from the local topology, the `consolidation_tier` may rise to 2 if the entity proves to be widely-referenced. The eager Tier-1 entity created at first insertion grows in evidential richness over time.

If two entity nodes turn out to refer to the same person (e.g., a `Friedrich Stolz (chemist)` candidate and a separately-created `F. Stolz` candidate accumulate enough overlapping evidence), Argus or Athene proposes a `MergeProposal` and Oneiros applies the merge per §"Agent-driven cleanup".

**Hub formation and split (much later).**

After many years of operation (hypothetically), the `London` Tier-1 entity node has reached Tier 3 and is approaching its million-edge cap. Oneiros detects sub-clusters in its connections — `real_estate`, `restaurants`, `history`, `government` — and proposes sub-node splits. The splits run; effective resistance is preserved per §C above; consumers notice nothing.

**Pathology and therapy (hypothetical).**

If, over time, a sub-cluster in the substrate started absorbing refutations of itself instead of being weakened (Symptom 4 from §"The five topological symptoms"), Argus would detect it from the topology and emit a `Finding`. Oneiros would apply Stage 1 (activation temperature) on the next tick. If that does not normalise the metric, Stage 2, then Stage 3. If the pathology is severe and persistent, Stage 4 destruction may be applied — with the Mendel risk weighed first.

**Agent-driven cleanup (whenever).**

If a researcher discovers that a chunk in the substrate carries factually wrong information (perhaps a Wikipedia article changed and the chunk reflects the obsolete version), an agent (Argus or a domain expert) emits a `RemovalProposal` finding with the supporting evidence. Oneiros removes the chunk on its next tick; the removal is logged in the audit ledger. The substrate continues to "remember" that this claim was once present, by virtue of the audit record.

**Resource pressure (hypothetical).**

If the operator's hardware tier changes (e.g., move from a 256 GB workstation to a 32 GB laptop), the pruner activates and removes the weakest atrophied nodes and edges first. The high-tier consolidated nodes (`Thomas Addison`, `Thyroxine`) and their strongest edges survive. The fine-grained Tier-0 chunks of the original Wikipedia article are first to go; the consolidated entities and concepts persist. This is the substrate's graceful degradation under reduced resources.

---

## Second worked example: one sentence, several chunks, concepts without Q-IDs

The first worked example shows what happens when richly-named, Wikidata-anchored content arrives. A second example shows the more common case in real biographical or narrative text: a single sentence produces *several* chunks, most reference targets are *abstract concepts without Q-IDs*, and the same entity gets piled with new evidence rather than re-created.

Source sentence (continuing the Wikipedia article about Thomas Addison):

> *"He bought a house in Hatton Garden in 1819, and from that time had a private practice."*

This sentence describes two distinct happenings (the purchase event and the resulting state of practising medicine privately from then on). Kadmos extracts **two or three chunks**, each capturing a different angle of the underlying material:

- **Chunk A** — *"Thomas Addison bought a house in Hatton Garden in 1819."* (frame: *event / transaction*)
- **Chunk B** — *"Thomas Addison owned a house in Hatton Garden from 1819 onwards."* (frame: *state / ownership*)
- **Chunk C** — *"Thomas Addison ran a private practice from 1819 onwards."* (frame: *activity / profession*)

Each chunk is a Tier-0 node with its own `semantic_vector`, its own `frame_vector`, and its own reference edges. They share most of their targets but are *not* duplicates: A's frame is the moment of transaction, B's frame is the resulting ownership state, C's frame is the consequent professional activity. They will be retrieved differently by frame-routed queries (see below).

**Entity-targets these chunks reference.** The chunks attach reference edges to a mix of Q-ID-anchored entities and concept nodes that have no Q-ID:

| Target node | Tier | Q-ID? | Description (excerpt) |
|---|---|---|---|
| `Thomas Addison` | 1 | `Q336997` (yes) | *"Thomas Addison (1793–1860), English physician, described Addison's disease and the suprarenal capsules."* |
| `Hatton Garden` | 1 | `Q6597321` (yes) | *"Hatton Garden, district of central London known historically for jewellery trade and medical practices."* |
| `Year 1819` | anchor | n/a (anchor node) | the temporal anchor for 1819 on the substrate's time axis |
| `Private practice` | 1 | none | *"the practice of running an independent medical service, paid by patients directly rather than through a hospital or institution"* |
| `House ownership` | 1 | none | *"the legal and practical state of owning a residential property"* |
| `Buying property` | 1 | none | *"the transaction of acquiring a real-estate property in exchange for payment"* |

Three of these are Q-ID-anchored entities; three are pure concepts the substrate forms on its own (no Wikidata item exists for "the abstract practice of running a private medical practice in a way you can refer back to"). Both kinds use the same Tier-1 `ConsolidatedNode` schema; only `qids` differs (`[Q336997, …]` vs. `[]`).

**Edges produced by the three chunks.** Each chunk attaches reference edges to its targets with `relation_descriptor`, `relation_kind`, and (where applicable) Wikidata P-IDs:

| Edge | `relation_descriptor` | `relation_kind` | `pids` |
|---|---|---|---|
| Chunk A → Thomas Addison | `"subject"` | `"attribution"` | — |
| Chunk A → Hatton Garden | `"location_of_event"` | `"attribute"` | `[P276]` *(location)* |
| Chunk A → Year 1819 | `"happened_in_year"` | `"temporal"` | `[P585]` *(point in time)* |
| Chunk A → Buying property | `"event_kind"` | `"attribute"` | `[P31]` *(instance of)* |
| Chunk B → Thomas Addison | `"subject"` | `"attribution"` | — |
| Chunk B → Hatton Garden | `"located_at"` | `"attribute"` | `[P276]` |
| Chunk B → House ownership | `"state_kind"` | `"attribute"` | `[P31]` |
| Chunk B → Year 1819 | `"began_in_year"` | `"temporal"` | `[P580]` *(start time)* |
| Chunk C → Thomas Addison | `"subject"` | `"attribution"` | — |
| Chunk C → Private practice | `"activity_kind"` | `"attribute"` | `[P31]` |
| Chunk C → Year 1819 | `"began_in_year"` | `"temporal"` | `[P580]` |

The frame difference between Chunk A's `"location_of_event"` edge and Chunk B's `"located_at"` edge is exactly the point: same target (Hatton Garden), different relation type, because the underlying frame differs (transaction at a place vs. residence at a place). The mesh distinguishes them, both via the chunks' `frame_vector`s and via the explicit edge metadata.

**What about identity for the named entities?** Thomas Addison already exists in the substrate from earlier paragraphs (the prior worked example created the `Q336997` node when his name was first encountered). Each new chunk attaches a *new* reference edge to the *existing* Thomas Addison node — `fired_total` and `fired_recent` increment, the node accumulates evidence, and Oneiros will regenerate the description on its next consolidation tick if the new chunks bring discriminating content. **No second Thomas Addison node is created.** The Q-ID uniqueness invariant (§"Field discipline" point 3) guarantees this even if the new chunks reach the substrate via concurrent ingestion: at most a transient duplicate, resolved by Oneiros immediately.

Hatton Garden, on the other hand, may not yet exist when these chunks arrive. If it does not, Kadmos creates the Tier-1 entity node on the spot from the Wikidata link plus the local extraction context, with an initial description and an initial `description_vector`. Subsequent mentions in other paragraphs link to this same node.

The three concept nodes (`Private practice`, `House ownership`, `Buying property`) almost certainly do not exist yet, and they have no Q-IDs to anchor against. They are created as entity-candidates (`is_candidate = True`) with a description derived from the local context. Many subsequent biographies will reference the *same* concept of "private medical practice"; over time Oneiros consolidates the candidate nodes into a single stable concept, `is_candidate` flips to `False`, and a richer description accumulates. The substrate's concept formation is exactly this — a Q-ID-less Tier-1 node that earns its existence by being referenced from many directions.

**What this example shows that the thyroxine example does not.**

1. **One sentence produces multiple chunks.** Each chunk is a distinct frame of the same underlying happening. The chunks are not redundant; they are different angles, retrievable independently.
2. **Most reference-targets in real text have no Q-ID.** Abstract activity categories, life-event types, professional roles, ownership states — none of these have Wikidata items. The substrate forms them as concept nodes through eager-candidate-creation followed by emergent consolidation. Wikidata anchors named entities; the substrate forms its own concept layer for everything else.
3. **An existing entity accumulates evidence rather than spawning duplicates.** Each new chunk adds a reference edge to the existing `Thomas Addison` node; nothing about Addison's identity is *re-decided* at insertion. The Q-ID uniqueness invariant makes this safe even under concurrent ingestion.
4. **Edge metadata carries the relational structure that the chunk's frame alone cannot.** `"location_of_event"` vs. `"located_at"` distinguishes Chunk A's transactional frame from Chunk B's ownership-state frame, even though both edges target Hatton Garden. The P-IDs make the relations machine-interpretable when the substrate needs to align with external Wikidata-shaped knowledge.

**Retrieval downstream.** With these chunks in place, the substrate serves frame-distinct queries from the same underlying state:

- *"When did Addison move his practice to Hatton Garden?"* — frame: *event/transaction* + temporal. Activates Chunk A strongly, Chunk B and C weakly. Constellation: Addison, Hatton Garden, Year 1819, Buying property.
- *"What property did Addison own?"* — frame: *state/ownership*. Activates Chunk B strongly, A and C weakly. Constellation: Addison, Hatton Garden, House ownership, Year 1819.
- *"Where did Addison practice medicine privately?"* — frame: *activity/profession*. Activates Chunk C strongly, A and B weakly. Constellation: Addison, Private practice, Hatton Garden (via the shared location), Year 1819.

**Three queries, three different Constellations, one underlying mesh state.** The chunks' apparent redundancy is structurally useful: each chunk carries the right frame for one class of query, and frame routing during Spreading Activation makes sure each query lands on its own subset of evidence. This is what the two-tier model and the frame_vector buy together — the substrate represents the same underlying material as different views, and surfaces the right view at the right time.

---

## What the substrate does not do

A small set of forbidden patterns — the discipline lines the substrate's correctness depends on. Everything not on this list is an affordance. The substrate is designed for intelligent agents working in a richly-equipped space; it constrains the few things that, if violated, make the substrate structurally incoherent.

1. **No insertion-time content validation gates.** The substrate accepts every chunk that arrives. Identity linking (eager when Q-ID / description / structural signals are clear, emergent when not), deduplication, contradiction resolution, false-information removal, and consolidation all happen *post-hoc* — see §"Agent-driven cleanup" and §"Pathology and therapy". A function that returns `False` for "do we want this chunk?" before insertion is forbidden because pre-gates force identity and quality decisions on the weakest possible evidence (a single chunk in isolation), and they create a bottleneck in which the system's actual epistemic state becomes invisible. The substrate's strength is *post-hoc* evidence accumulation across many chunks; pre-gates throw that strength away. ([`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) and [`BUILD_DOCTRINE.md`](BUILD_DOCTRINE.md) reach the same conclusion from different angles; the substrate doctrine arrives at it from the dynamics themselves.)

2. **No raw text storage in the substrate beyond the `raw_text_ref` pointer.** The substrate's primitives — Hebbian update, super-linear decay, Spreading Activation, frame routing, sub-mesh signature matching — operate on vectors and structure. They do not read strings. Storing the full source text inside a mesh node would be dead weight on every read, every SpMV, every consolidation pass: it has no place in the substrate's hot path. `raw_text_ref` exists as an opaque pointer back to the source so the immune system can re-derive a chunk when needed; no agent treats it as retrieval payload. (This prohibition applies to *raw source text*. Short text fields — `description`, `relation_descriptor`, `description` on edges, `tags`, `source_url` — are summary metadata, regenerable, and explicitly permitted; they are how agents and humans read the mesh. See §"Field discipline" point 4, §"Source-anchor entities", and §"Edge anatomy".)

3. **No hard hierarchical pointer field on nodes.** No `parent_node_id`, no `belongs_to_category`, no `is_part_of`. Hierarchical structure that matters at retrieval is computed from topology, or materialised as separate views. The reason is in §"Field discipline" point 5: hierarchies ossify and constrain refactoring of the very classifications the mesh is designed to evolve.

4. **No fixed decay rate.** Decay is super-linear and tier-modulated. Code that assumes uniform `λ` across all edges, or constant `λ` over time, is wrong about the substrate.

5. **No silent destruction.** Information *may* be destroyed — by pruning under resource pressure, by agent-driven cleanup of demonstrable false information, by therapy at Stages 4 and 5 when the Mendel risk has been weighed and rejected. But every destruction is logged in the audit ledger with the trigger and (for agent-driven destruction) the supporting evidence. The substrate never quietly forgets that it once held a claim. This is the only restriction on destruction.

That's the entire list. Five disciplines.

Everything else is an affordance: eager Q-ID linking when identity is clear, agent-driven cleanup of contradictions and redundancies, descriptions as authoritative information, edges with semantic relation descriptors, therapy that destroys information when the evidence supports it. All are permitted and useful when applied with care.

The mental model: the substrate is a living workspace, not a sterile database. It has discipline (the five points above) and it has freedom (everything else). Agents that understand the five disciplines and use the freedom intelligently are the substrate's productive citizens.

---

## Open questions and known limits

These are the points where the doctrine deliberately stops short of prescription, because the right answer requires running the substrate at scale to find out.

- **Exact tuning of `α`, `λ`, `β`, `R_ideal`, tier thresholds, and saturation caps.** The shape is fixed; the numbers are empirical. Mnemosyne's A/B framework (per [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Self-improvement loop") is the right place to tune them once the substrate has enough activity to produce statistically meaningful comparisons.

- **The frame-vector embedding model.** The substrate's frame-sensitive routing requires an encoder that produces embeddings reflecting epistemic frame (definition, claim, refuted-claim, hypothesis, observation), distinct from semantic content. Off-the-shelf sentence encoders are only partly suitable. A small contrastively-trained frame encoder is the likely path; details belong in [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Frame-sensitive resonance".

- **Cold-start dynamics.** When the substrate is small (< 10 000 nodes), the population statistics that define the healthy band are noisy. The substrate needs a bootstrap regime in which decay is gentler and pruning is suppressed, until enough mass exists for statistics to mean something. The exact cross-over is a tuning problem.

- **Multi-modal extension.** The substrate dynamics are modality-agnostic — Hebb, decay, saturation, splits, frame routing, pathology all operate on abstract nodes and edges. Adding image, molecular, genetic, or geographic vectors does not require structural change. The choice between *one mesh with multiple modal vectors per node* and *parallel meshes with bridge nodes* is an engineering judgement that is made when the second modality enters production. See [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Multi-modal extension" for the affordance discussion.

- **Federation-aware dynamics.** When the substrate federates across multiple instances, the global renormalisation and the population-relative healthy band become harder to define. Local-substrate and global-federation versions of the same metric will need to coexist. This is Gen 3+ work.

- **Hardware backpressure on Oneiros.** Oneiros's tick frequency, Argus's sampling rate, and the pruner's pressure threshold form a control loop. Tuning that loop so the substrate stays responsive under varying load is operations work, not doctrine.

---

## Why the substrate's mechanism is a system

The components of the substrate's dynamics interact. They were not designed independently and they do not produce the same behaviour independently:

- **Super-linear decay** keeps individual edges from fossilising; without it, the high-weight region of the mesh becomes a record of historical importance rather than current relevance.
- **Saturation caps** prevent hubs from growing unboundedly; without them, Spreading Activation's per-step cost grows with the maximum node degree.
- **Atrophy ≠ death decoupling** allows scalable forgetting that adapts to varying hardware tiers; without it, the substrate either forgets too aggressively (always at full speed) or too conservatively (never under pressure).
- **Frame vectors** carry polarity that semantic vectors cannot; without them, refutations get confused with endorsements at the cosine-similarity level.
- **Staged therapy with Mendel-weighted destruction** allows targeted intervention without arbitrary suppression; without it, the substrate either ossifies into echo chambers or destroys minority insight without weighing.
- **Agent-driven cleanup** allows the substrate to repair specific identified problems; without it, the substrate accumulates contradictions and redundancies that the automatic mechanisms cannot resolve.

A subset of these mechanisms — for example, super-linear decay without renormalisation, or saturation without splits — produces a substrate that fails differently than the full design. That is not necessarily wrong, but it is a different system. Implementations should be honest about which subset they realise and which failure modes are open as a result.

This document commits to the full mechanism as the *target*. Early implementations will not realise everything at once, and that is acceptable — the substrate's behavioural target is something the codebase walks toward, not a precondition for shipping any individual layer. The Phoenix Backlog tracks what is missing; honest run reports surface failure modes; the substrate's own A/B mechanism (Lance-branched parallel universes per [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md) §"Parallel universes — empirical comparison of strategies") tunes the parameters as evidence accumulates.

---

## Implementation pointer

Concrete storage layout, concurrency model, batched-SpMV runtime, hardware tier targets, and version control strategy live in [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md). The retrieval-side disciplines — diversified injection, sub-mesh signature search, three-factor reinforcement learning, multi-agent strategy-game framing, and multi-modal extension — live in [`MESH_RETRIEVAL.md`](MESH_RETRIEVAL.md). The MNLM that consumes the substrate is specified in [`etappes/mesh_native_lm_brief.md`](etappes/mesh_native_lm_brief.md).

This document binds the substrate's *behaviour*. Those documents bind its *implementation* and its *use*. Together they are the full specification.

---

## One-line summary

> **The mesh holds material; the edges hold meaning; the dynamics hold both alive and bounded.**
