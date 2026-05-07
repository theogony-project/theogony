# Hesiod Brief — Nous: The Cognitive Synthesis Agent

**Filed by:** Chaos (vision role)  
**For:** Hesiod (architect), then Talos (implementer)  
**Date:** 2026-05-07  
**Status:** Ready for Hesiod planning

---

## 0. What you must read before this brief

This brief is self-contained but not self-sufficient. Before planning, read:

1. `notes/architecture/reading_agent_vision.md` — the user's cognitive model of reading, in detail
2. `notes/architecture/vector_native_spreading_activation.md` — the Tensor-Manifold target architecture
3. `docs/ARCHITECTURE.md` — system layers, KnowledgeStore interface, existing data model
4. `docs/BUILD_DOCTRINE.md` — Function-First Phase binding doctrine
5. `src/theogony/core/model.py` — the Pydantic models Talos must build against
6. `src/theogony/extraction/topology_parser.py` — what Nous supersedes

The current extraction pipeline (`topology_parser.py`) is what Nous replaces. Understanding it is the fastest way to understand the gap.

---

## 1. The Problem

The current pipeline treats text as a **spatial object** to be mined:

- One LLM call per chunk
- Stateless between calls — no memory of what was read before
- No Chronicle retrieval during processing
- Flat hierarchy — tree-shaped, not DAG
- No synthesis: concepts are extracted, not condensed
- No repair: contradictions are not detected mid-read
- No diagonal edges: a sentence concept cannot bind directly to a theme concept

The result is a Chronik with low edge density and weak cross-document connections. For Spreading Activation to work as the retrieval primitive, the Chronik needs 1000× more edges per node than a parser produces. Nous is how we get there.

---

## 2. The Vision (the user's own model)

Reading is not extraction. It is **synthesis across time**.

When a person reads the first sentence of a text, approximately 5–10 new concepts arrive from the words. Simultaneously — massively parallel, nearly free — roughly 50 prior-knowledge concepts activate in long-term memory. These range from tightly bound (Tibet → Sven Hedin) to loosely associated (Tibet → Buddhism → meditation → ...). From this activation storm ("ein großes Gewitter mit Potenzialgefälle") a synthesis condenses. This condensed synthesis is what primarily persists as the reader moves to the next sentence.

With each subsequent sentence, the previous synthesis is **pre-warmed** — those concepts fire faster and are preferentially integrated. A temporal hierarchy of meaning emerges: sentence syntheses condense into paragraph syntheses, paragraph syntheses into chapter syntheses.

As the text lengthens, once-stable meta-concepts no longer need the small-scale machinery. The basis layer is released — not deleted, but compressed — and processing resources are freed.

Contradictions and gaps trigger **repair**: the reader scans back through prior text, finds the spans in conflict, and revises the synthesis. Repair is not a mode switch. It is what the agent normally does, applied to a surfaced tension.

Two memory layers:
- **General knowledge** — fast, cheap, broad. In LLM terms: the model's parameters.
- **Specialised knowledge** — slower, more expensive, provenance-traceable. In our system: the Chronik.

The Chronik search runs **continuously in parallel** with the foreground reading, at roughly 20% of compute. It is driven by the active meta-concepts' embeddings. High-similarity hits flow into the synthesis with explicit provenance (`from_chronicle`). The agent may use or ignore them; ignored hits appear in the audit log.

The agent may decide an entire chapter needs only shallow processing if its core concept is already well-validated in the Chronik — **trust-and-skim**.

---

## 3. What Nous Is Not

To prevent backsliding into pipeline thinking:

- **Not** named-entity recognition + relation extraction
- **Not** one LLM call per chunk
- **Not** a fixed pipeline with a fixed sequence of stages
- **Not** a separate repair service with its own control flow
- **Not** a tree-shaped hierarchy
- **Not** a system that triggers synthesis on a hard rule
- **Not** a replacement for the Chronicle — Nous writes into the Chronicle, it does not replace it

---

## 4. Architectural Principles

### 4.1 Reading is temporal, not spatial

Nous processes text incrementally, unit by unit. It carries **state** forward across steps:

- A **working memory**: active concept set with weights and decay
- A **growing synthesis graph**: local to the current reading session, distinct from the Chronicle
- **Open tensions**: concepts or spans that are in conflict and need resolution

Each step:
1. Receives the next reading unit (sentence or paragraph)
2. Embeds it
3. Runs cheap vector math against working memory and Chronicle in parallel
4. Calls the LLM with: the unit text + working memory summary + Chronicle hints + open tensions
5. Receives structured output: new concepts, new edges, synthesis events, repair signals
6. Updates working memory and local synthesis graph
7. Writes to the Chronicle via the KnowledgeStore interface

### 4.2 Hierarchy is fixed at the level, fuzzy within

For v1, Nous operates over Wikipedia's natural structure. The levels are:

| Level     | Wikipedia equivalent | Example             |
|-----------|---------------------|---------------------|
| Domain    | Portal / WikiProject | "Geography"         |
| Theme     | Category             | "Exploration of Tibet" |
| Article   | Article              | "Trans-Himalaya"    |
| Chapter   | H2/H3 section        | "Geography and Climate" |
| Paragraph | Paragraph            | (the paragraph)     |
| Sentence  | Sentence             | (the sentence)      |

Levels are **anchors**, not containers. Within and across them:

- Multiple core concepts per level is the norm (a chapter may have 3–20)
- **Diagonal edges** are first-class: a sentence concept may bind directly to a theme concept
- **Multiple parents** per concept are allowed — DAG, not tree
- **Wiki-links** in the source text are pre-existing diagonal connections and candidate identity resolutions

### 4.3 Identity anchors — fuzzy is not rootless

Without stable identity, two readings of the same article produce unmergeable concept clouds. Nous must, where possible, resolve concepts to **Wikidata Q-IDs** for entity-like nodes and **P-IDs** (or the internal codebook) for relation types.

Resolution is **incremental and context-dependent**:
- First mention: emit a candidate Q-ID with low confidence
- After paragraph: confirm or revise
- After article: highest confidence, backfill earlier mentions

The existing `KnowledgeNode.external_ids` and `KnowledgeNode.resolution_tier` (0–4) fields are the canonical home. Nous builds incremental resolution into the reading loop, not as a post-hoc pass.

Confidence tiers:
- `resolution_tier=4`: alias-match across multiple languages, unique candidate
- `resolution_tier=3`: single-language alias match, one candidate
- `resolution_tier=2`: LLM guess with paragraph context
- `resolution_tier=1`: LLM guess from single sentence
- `resolution_tier=0`: unresolved, AKA-only, awaiting more context

### 4.4 Relation codebook

The existing codebook from the topology_parser:
`BINDS_TO, REINFORCES, CAUSED_BY, ABSTRACTION_OF, MODULATES, CONTRADICTS`

Where Wikidata P-IDs apply (`P31` instance_of, `P361` part_of, `P50` author, `P19` born_in, ...), use them as the relation type, or map the internal codebook entry to a P-ID set so the two systems stay reconcilable.

### 4.5 Synthesis events emerge; they are not triggered

No hard rule: "after paragraph X, synthesise." A synthesis happens when the agent decides something has condensed. For v1, paragraph boundaries and section endings are **default synthesis opportunities** — the agent may synthesise earlier, later, or skip.

Synthesis nodes are `KnowledgeNode` instances like any other, with `node_type=CONCEPT` and a `synthesised_from` relation (an edge type) pointing to the basis nodes. The synthesis relation is a **weighted edge with revision history**, not a tree pointer.

### 4.6 Repair is permanent, not modal

At every reading step, the agent compares the new unit against existing working memory. If tension is detected, the next action may be a **revision** of an earlier concept or synthesis — possibly several steps back. This is a normal mutation of the local synthesis graph. There is no separate repair mode.

Revision events should be recorded in the `AnnotatedReading` output (see §6) so the human can inspect when and why the agent reversed itself.

### 4.7 Parallel Chronicle activation

While the LLM foreground processes the reading unit, cheap vector math runs in parallel:
- kNN search in the Chronicle keyed off the current working memory's pooled embedding
- Budget: roughly 20% of wall-clock

Results returned to the LLM call as `chronicle_hints`: a list of `(node_id, label, similarity, provenance_anchor)` tuples. The LLM may use them (strengthening an existing concept, creating a new edge, triggering trust-and-skim) or ignore them. The decision is logged.

Provenance per concept is a gradient, not a binary enum:
- `support_text`: how strongly does the just-read text support this?
- `support_chronicle`: how strongly does a Chronicle hit support this?
- `support_inference`: how strongly does an implicit inference support this?

### 4.8 Provenance on all outputs

Every concept, every edge, every synthesis event carries:
- Source text anchor: article title + section + paragraph index + sentence index
- Extraction model: which LLM produced this
- Chronicle hits: which Chronicle nodes were offered and which were used
- Confidence: float 0.0–1.0
- Resolution tier: int 0–4

---

## 5. The Monkey

The two open empirical questions that Nous is built to answer:

**Monkey 1 (Nous):** Does cognitive synthesis produce a denser, better-connected Chronik than the current chunked parser? The hypothesis: yes, because synthesis weaves cross-sentence and cross-chapter connections that a parser cannot. Verification: run both pipelines on the same Wikipedia article; compare node count, edge count, edge type diversity, and cross-level diagonal edges.

**Monkey 2 (Spreading Activation):** Does Spreading Activation over a dense vector-graph retrieve better than ANN + graph traversal at high edge density? This cannot be tested until Monkey 1 is answered — we need Nous to produce the dense Chronik first.

Nous is Phase 1. It validates the ingest side. Spreading Activation is Phase 2. It validates the retrieval side. Monkey 2 requires Monkey 1.

---

## 6. Output Format: AnnotatedReading

Nous does not only write to the Chronicle. It produces an `AnnotatedReading` — a machine-readable, human-inspectable record of the reading process itself.

The `AnnotatedReading` is the unit of comparison between human and agent comprehension. It records:

- The text, segmented by reading unit
- At each step: working memory state (active concepts, weights), Chronicle hits (offered vs. used), synthesis decisions, repair events
- The resulting local synthesis graph (nodes + edges produced in this reading session)
- The Chronicle writes made (node IDs + edge IDs written)

For v1, the `AnnotatedReading` is a JSON file. No cockpit required. The human reads the JSON or evaluates it with simple statistics. Cockpit follows when the data model stabilises.

The `AnnotatedReading` schema is a **first-class Pydantic model** in `src/theogony/core/model.py` (or a dedicated `nous/model.py`). Schema-first, as always.

---

## 7. What Nous Does Not Build (v1 scope)

**Deferred to v2 or later:**

- Multi-resolution models (sentence=small, paragraph=medium, chapter=large). V1 uses one model on all levels. Multi-resolution added when it earns its complexity.
- Trust-and-skim mode. The mechanism is described; the implementation requires a working Chronicle with validated meta-concepts to skim against. Not available at the start.
- Full repair reach across sections. V1 repair is limited to within-section revision. Cross-section repair added when the local synthesis graph is large enough to make it useful.
- Cockpit visualisation. V1 output is JSON + RunReport.
- Streaming writes. V1 writes to Chronicle at paragraph-level synthesis events, not sentence-by-sentence.

---

## 8. Integration with the Existing System

### Chronicle interface

Nous writes through the existing `KnowledgeStore` protocol. No new store required. Node and edge shapes are unchanged (`KnowledgeNode`, `KnowledgeEdge` from `core/model.py`). New fields needed:

- `KnowledgeNode.nous_session_id: str | None` — which reading session produced this node
- `KnowledgeNode.synthesis_level: str | None` — "sentence" | "paragraph" | "chapter" | "article" | None
- `KnowledgeEdge.relation_codebook: str | None` — internal codebook entry when no P-ID applies

Hesiod decides whether these are new fields on the existing models or a Nous-specific extension model. YAGNI applies: only add what Nous actually needs to emit.

### RunReport

Every Nous reading session emits a `NousRunReport` (new schema, analogous to `IngestRunReport`). Minimum fields:

- `session_id: str`
- `source_url: str` (Wikipedia article URL or local file path)
- `reading_units_total: int` (sentences or paragraphs processed)
- `nodes_written: int`
- `edges_written: int`
- `synthesis_events: int`
- `repair_events: int`
- `chronicle_hits_offered: int`
- `chronicle_hits_used: int`
- `llm_calls: int`
- `llm_cost_eur: float`
- `wall_clock_s: float`
- `verdict: str` — "success" | "partial" | "failed"

### Build Doctrine

Function-First Phase applies unchanged. Nous must:
- Ingest fast, not perfectly
- Emit a `NousRunReport` with `verdict="failed"` on failure — no silent errors
- Never pre-validate content before writing to the Chronicle
- Write imperfect synthesis rather than no synthesis
- Be testable without a live Chronicle (InMemoryKnowledgeStore)

---

## 9. First Corpus

**Wikipedia article: Sven Hedin** (or the Trans-Himalaya article)

Rationale:
- The Chronik already contains Sven Hedin nodes from the Gutenberg ingest (Gutenberg #43497, 756 nodes, 139 edges). Diagonal connections to existing Chronicle nodes will be visible immediately.
- Wikipedia markup provides the six-level hierarchy for free.
- Wiki-links in the article are pre-existing candidate identity resolutions.
- The domain (Central Asian exploration, early 20th century) is rich in cross-concept connections that a parser would miss.

The first evaluation: run Nous on the Trans-Himalaya Wikipedia article, then compare:

| Metric | topology_parser (current) | Nous |
|---|---|---|
| Nodes produced | ? | ? |
| Edges produced | ? | ? |
| Edge-to-node ratio | ? | ? |
| Cross-level diagonal edges | 0 (tree) | ? |
| Chronicle hits used | 0 (no retrieval) | ? |
| New connections to existing Hedin nodes | 0 | ? |

If Nous produces a measurably denser, better-connected subgraph than the parser on the same article — Monkey 1 is answered.

---

## 10. Open Questions for Hesiod to Resolve

These are the architectural decision points. Hesiod picks one answer for each, with rationale, before Talos begins.

**Q1. Atomic reading unit.**  
Sentence or paragraph? Wikipedia gives paragraphs for free. Sentence-level gives more granular synthesis but more LLM calls and more state complexity. Hesiod's recommended starting point: **paragraph** for v1 (leverage Wikipedia's free structure, one LLM call per paragraph, manageable working memory size). Sentence-level can be added when paragraph-level results are understood.

**Q2. Working memory representation.**  
A bag of concept-IDs with float weights? A pooled embedding vector? Both? Decay function (exponential with τ in paragraphs, or use-count based)? Capacity ceiling (how many active concepts before compression)? Hesiod specifies the concrete data structure.

**Q3. Chronicle hit delivery to LLM.**  
How are Chronicle hits injected into the LLM call? Options: (a) text summary of top-N Chronicle nodes as additional prompt context, (b) list of `(node_id, label, similarity)` tuples that the LLM can reference, (c) structured JSON block. Hesiod picks the format that costs fewest tokens while preserving provenance traceability.

**Q4. Synthesis trigger.**  
Nous triggers a synthesis event when? Default: at every paragraph boundary. The agent may trigger earlier if working memory is dense and coherent. The agent may skip if the paragraph added nothing. Hesiod specifies the trigger condition and whether the LLM decides or a heuristic decides.

**Q5. Repair detection.**  
How does tension surface? Options: (a) the LLM is always asked "do you see any tension with the current synthesis?", (b) a cheap cosine-distance check between new embedding and existing synthesis embedding triggers a repair call, (c) explicit `CONTRADICTS` edges found in Chronicle hits trigger repair. Hesiod picks the cheapest reliable mechanism for v1.

**Q6. Identity resolution moment.**  
When does Nous commit a Q-ID? Options: (a) at first mention, low confidence, (b) at paragraph end if enough context, (c) at article end, backfill. Hesiod picks the strategy and specifies how backfilling earlier mentions works in the data model.

**Q7. `AnnotatedReading` schema location.**  
New file `src/theogony/nous/model.py`? Extension of `src/theogony/core/model.py`? Hesiod decides based on module boundary discipline.

**Q8. Parallelism implementation.**  
The Chronicle kNN search runs "in parallel" with the LLM call. In asyncio terms: `asyncio.gather` with the LLM call and the kNN search concurrently? Or sequential with the kNN search before the LLM call (simpler, more deterministic, slightly slower)? Hesiod picks.

---

## 11. What Hesiod Delivers

A plan document at `docs/etappes/nous_implementation_brief.md` containing:

1. **Answers to Q1–Q8** with rationale
2. **Module structure**: which new files/directories, what lives where
3. **Data model additions**: exact Pydantic field additions to existing models, or new models
4. **Etappe breakdown**: implementation sequence for Talos (S/M/L sizing, dependencies)
5. **Test strategy**: what the contract suite must cover before v1 is considered shippable
6. **Success metric**: the exact comparison protocol for Monkey 1 (what numbers, on what corpus, with what threshold)

Hesiod does **not** need to resolve the open empirical questions (when exactly does synthesis fire, what decay rate, etc.). Those are answered by running Talos's implementation on the first corpus and reading the JSON. The plan creates the conditions to run the experiment, not the experiment itself.

---

## 12. Talos constraints (pass-through from AGENTS.md and BUILD_DOCTRINE.md)

- Schema-first: Pydantic v2 with `extra="forbid"` on every new model
- No LLM calls in `__init__` methods
- Every new pipeline emits a `NousRunReport`
- Honest-failure: `verdict="failed"` with structured reason, not a silent exception
- YAGNI: only what this brief requires. No cockpit, no streaming, no multi-resolution models in v1.
- One PR per coherent change. Tests ship with the code they test.
- `pytest -q` must stay green. `ruff format` + `ruff check` must stay green.

---

*Chaos withdraws. The plan belongs to Hesiod.*
