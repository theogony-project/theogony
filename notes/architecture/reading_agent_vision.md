# Reading Agent — Vision

**Author:** Chaos (vision/reflection role) — handed off to Hesiod and Talos.
**Status:** Orientation note — captures the vision, not the plan.
**Date:** 2026-05-03.
**Conversation:** Long reflection session with the user. The user explicitly asked
that this vision be persisted before implementation begins.

---

## Why this document exists

The Run-9 pipeline (`src/theogony/extraction/topology_parser.py`, single-pass and
hierarchical Macro→Subdivide) **parses text**. The user wants a system that
**reads text** — that synthesises knowledge the way a human does when reading,
not the way an NLP parser extracts named entities.

Run 10 (`notes/deep_research/run10_brief.md` and the three responses) gathered
external research on a "cognitively-plausible reading agent". This document is
**not** a digest of those reports. It is the **user's own vision**, with my
reflection, captured so Hesiod can plan and Talos can build without me having
to be in the loop.

Cross-references:
- `notes/deep_research/run10_brief.md` — research brief.
- `notes/deep_research/run10_gemini.md`, `run10_deepseek.md`, `run10_manus.md` — responses.
- `src/theogony/extraction/topology_parser.py` — what is being superseded.
- [`oss_adjacent_landscape.md`](oss_adjacent_landscape.md) — adjacent OSS/research; includes the same web articles in a mesh-market context.

### External articles (web)

Short pointers only; not part of the vision transcript above.

- **[The Math You Need To Start Understanding LLMs](https://hackaday.com/2026/05/04/the-math-you-need-to-start-understanding-llms/)** (Hackaday, 2026-05-04) — Points to Giles Thomas on logits, embeddings/matrix operations, and transformers/attention. Useful didactic background for “vectors as internal state” and why attention is more than glorified autocomplete.

- **[The RAG era is ending for agentic AI — a new compilation-stage knowledge layer is what comes next](https://venturebeat.com/data/the-rag-era-is-ending-for-agentic-ai-a-new-compilation-stage-knowledge-layer-is-what-comes-next)** (VentureBeat, 2026-05-04) — Vendor/analyst narrative: shift **reasoning upstream** into a **compilation** phase (task-specific artifacts, governed retrieval) instead of rediscovering structure every cold RAG session. **Resonance:** “grow or ingest messy, then consolidate for reuse” aligns with our function-first + post-hoc immune posture. **Contrast:** enterprise product framing (e.g. Pinecone Nexus / KnowQL); Pantheon targets a **vector-native mesh** and **Spreading Activation**, not SQL-shaped agent queries over compiled documents.

---

## The diagnosis

The current pipeline hands an LLM one chunk of text, receives one JSON, writes
it to the Chronicle. It is **stateless across calls**, **monolithic**, has
**no reflection**, performs **no Chronicle retrieval during processing**, has
**no temporal hierarchy**. It treats text as a spatial object that gets mined.
The user wants a system that treats text as a **temporal experience** that gets
synthesised.

A measurement against the user's mental model of reading:

| Mechanism (user's words)                              | Run-9 pipeline | Should be |
|-------------------------------------------------------|----------------|-----------|
| Concepts emerging sentence by sentence                | absent         | central   |
| Pre-warmed prior concepts firing faster               | absent         | central   |
| Parallel similarity search in long-term memory        | absent         | central   |
| Synthesis of synthesis (sentence → paragraph → ...)   | spatial only   | temporal  |
| Repair through reflection on contradictions/gaps     | absent         | emergent  |
| Trust-and-skim when meta-concept is well-validated   | absent         | optional  |
| Fuzzy hierarchies, multi-parent membership            | tree-shaped    | DAG       |

---

## The vision in the user's own words

The user described reading as a continuous, multi-level synthesis process. The
following points are reproduced or paraphrased closely; quotations are theirs.

**The first sentence.** About 5–10 new concepts arrive directly from the text.
Simultaneously, a "massively parallel, energy-cheap" search runs through prior
knowledge — the user estimates this activates roughly 50 already-learned
concepts, ranging from tightly bound to loosely associated. From this storm
("ein großes Gewitter mit Potenzialgefälle") a synthesis condenses. This
synthesis is what primarily remains as the next sentence is read.

**Subsequent sentences.** The same storm happens, but the previous sentence's
concepts are already pre-warmed and fire faster. They are preferentially
integrated into the new synthesis. A synthesis hierarchy emerges over time.

**Simplification with length.** As a longer text proceeds, some core concepts
become stable — either because they were already known or because the
synthesis has become certain. At that point, much of the small-scale concept
machinery (the 5–10 per sentence and their 50 prior-knowledge activations) can
be released. The user calls this freeing of memory and processing resources
during reading.

**Gaps and contradictions.** They trigger repair. The user describes repair as
the result of reflection: comparing new information to existing synthesis,
noticing a conflict, possibly skimming back through the prior text to find the
spans involved, and reworking the synthesis. **Repair is not a separate
subsystem.** It is what the agent normally does, applied to a surfaced
conflict.

**Two memory layers.**
- **General knowledge** — fast, cheap, broad. In the LLM analogy: the language
  model's parameters themselves.
- **Specialised knowledge** — slower, more expensive to access, but with
  traceable provenance. In our system: the Chronicle.

The user proposes that the Chronicle search should run **continuously in
parallel** with the foreground reading, at roughly **20% of compute**, driven
by the active meta-concepts. High-similarity hits should flow into the
synthesis with explicit provenance, so the agent can later request more from
that source. The agent might even decide a chapter only needs shallow
processing if its core concept is already strongly represented and validated
in the Chronicle.

---

## What this vision is **not**

To prevent backsliding into pipeline thinking:

- It is **not** named-entity recognition + relation extraction.
- It is **not** one LLM call per chunk.
- It is **not** a fixed pipeline with a fixed sequence of stages.
- It is **not** a separate "repair service" with its own control flow.
- It is **not** a tree-shaped hierarchy.
- It is **not** a system that decides synthesis on a hard trigger.

---

## Architectural principles that follow

These are the principles. They are **not** a plan. Hesiod will translate them.

### 1. Reading is temporal, not spatial

The agent processes the text incrementally, unit by unit. It carries **state**
forward across steps: a working memory of active concepts with weights, a
growing synthesis graph, open questions or tensions. Each step reads the next
unit, compares it to state, updates state.

### 2. Hierarchy is fuzzy, not hard

Concepts belong to syntheses with **weights**, often to **multiple** syntheses
at once. Synthesis nodes are concepts like any other — same node type in the
Chronicle, just at higher granularity. The "synthesised_from" relation is a
**weighted edge with revision history**, not a tree pointer.

### 3. Fixed levels as anchors, fuzzy content within

For v1, the user has accepted **fixed hierarchy levels**, modelled on
Wikipedia, because Wikipedia gives them to us for free as markup:

| Level     | Wikipedia equivalent          | Example                   |
|-----------|-------------------------------|---------------------------|
| Domain    | Portal / WikiProject          | "Geography"               |
| Theme     | Category                      | "Exploration of Tibet"    |
| Article   | Article                       | "Trans-Himalaya"          |
| Chapter   | H2/H3 section                 | "Geography and Climate"   |
| Paragraph | Paragraph                     | (the paragraph itself)    |
| Sentence  | Sentence                      | (the sentence itself)     |

Levels are fixed. **Within and across them**, everything stays fuzzy:

- **Multiple core concepts per level** is the norm, not the exception. A
  chapter may carry 3 to 20 core concepts, strongly interconnected.
- **Diagonal edges** between any two levels are first-class. A sentence
  concept may bind directly to a theme concept without going through paragraph
  and chapter.
- **Multiple parents** per concept are allowed.

Wikipedia gifts us:

- Structural hierarchy as markup — no EDU detection needed for v1.
- **Wiki-links** are pre-existing diagonal connections between articles **and**
  pre-existing candidate identity resolutions (a `[[Sven Hedin]]` link points
  at a specific entity, not just a string).
- **Multiple categories per article** demonstrate fuzzy theme membership in
  the source format.
- **Wikidata IDs** carry provenance and identity (see principle 4 below).

### 4. Stable identity anchors — fuzzy is not rootless

Fuzzy graphs without anchors drift. Two readings of the same article would
spawn two unmergeable concept clouds; cross-document linking would collapse;
the Chronicle would become an opaque pile. To stay on the ground, the agent
must, where possible, **resolve concepts to stable entity identities** —
**Wikidata Q-IDs** for entity-like nodes, **P-IDs** (or an analogous compact
codebook) for relation types.

- **Some concepts are entities.** Persons, places, organisations, specific
  events, named works — these have stable referents in the world. They should
  carry a Q-ID when one exists.
- **Some concepts are abstract.** A synthesis, a theme, a sentence-level
  idea — these float in the fuzzy graph and may not have Q-IDs. That is fine;
  they stay tethered by **connecting to** grounded entities.
- **Resolution is incremental and context-dependent.** The agent may emit a
  candidate Q-ID after the first sentence ("Hedin") and confirm or revise it
  after more context ("Sven Hedin = Q60005"). Larger context — paragraph,
  chapter, article, even cross-article — earns stronger resolution. The Q-ID
  assignment is itself a revisable property with a confidence weight, fitting
  the revision-history model.
- **Relations have a codebook.** Run-9 introduced BINDS_TO, REINFORCES,
  CAUSED_BY, ABSTRACTION_OF, MODULATES, CONTRADICTS as a compact internal
  codebook. Where Wikidata **P-IDs** apply (`P31` instance_of, `P361` part_of,
  `P50` author, `P19` born_in, …) they should be used as the relation type, or
  the internal codebook entry must map to a P-ID set so the two systems stay
  reconcilable.
- **Confidence tiers, not boolean.** Resolution is not "matched / unmatched".
  It is a tier (the existing `resolution_tier` 0–4 in the Pydantic models is
  the right shape): alias-match across multiple languages with a unique
  candidate ranks higher than an LLM guess from a single sentence. Below a
  threshold, a node stays unresolved (`AKA-` only) and waits for more context.

The existing `KnowledgeNode.external_ids` and `KnowledgeNode.resolution_tier`
fields are already the canonical home for this. Talos should keep them and
build incremental resolution into the reading loop, not as a separate
post-hoc pass.

### 5. Syntheses emerge; they are not triggered

There is **no hard rule** "after paragraph X, synthesise". A synthesis happens
when the agent decides something has condensed. For v1, the structural levels
(end of paragraph, end of section) may serve as **default opportunities**, but
the agent must remain free to synthesise earlier or later, or to revise an
existing synthesis when new information arrives.

### 6. Reflection and repair are permanent, not modal

In every reading step, the agent compares the new unit against the existing
state. If it finds tension, its next action may be a **revision** of an
earlier concept or synthesis — possibly several steps back in the trail. The
revision is a normal mutation of the graph. **There is no separate repair
mode.**

A larger-scale synthesis (paragraph, chapter) may revise a smaller-scale one
(sentence, paragraph). That is reflection over what the fine-grained step
produced — exactly the user's "repair through reflection".

### 7. Parallel activation as a background process

While the foreground (LLM calls) processes the text, **cheap vector math**
runs in parallel:

- Spreading activation in the **local** synthesis graph of the current reading
  session.
- kNN search in the **Chronicle** keyed off the active concepts' embeddings.

Both produce "pre-warmed" candidates that are passed to the next LLM call as
hints, with **explicit provenance** (`from_chronicle` vs.
`from_local_session`). The agent may use them or ignore them; what was
ignored remains visible in the audit log so the human can see whether the
agent missed something obvious.

This is the user's "20% parallel compute" idea, rendered concretely.

### 8. Multi-resolution with differently strong models (optional)

The user proposed — and this should be treated as **option, not requirement**
— that different scales might call different models:

- **Sentence** with a small, cheap model.
- **Paragraph** with a mid-size model.
- **Chapter** (and above) with a large, capable model.

A larger model may correct a smaller one's output when it sees the broader
context. This is an elegant way to apply reflection at the appropriate
resolution while keeping cost down. A v1 with **one model on all levels** is a
valid starting point; multi-resolution should be added when there is evidence
it earns its complexity.

### 9. Provenance is mandatory, but as a gradient

Every concept and every edge carries provenance. The user's framing implies
this should not be a hard enum (`from_text` xor `from_chronicle`) but a set
of **partial supports**:

- `support_text` — how strongly does the just-read text support this?
- `support_chronicle` — how strongly does a Chronicle activation?
- `support_inference` — how strongly an implicit inference?

This makes provenance fuzzy in the same way the rest of the model is. The
exact representation is for Hesiod and Talos to decide; the requirement is
that the audit can trace **why** a concept exists.

---

## Visualisation

The user has explicitly relaxed the cockpit-first requirement:

> Es ist auch in Ordnung, wenn wir mit Stufe C beginnen und dann vorerst
> statistische Auswertungen machen. Oder ich lese das JSON einfach selbst.

So the implementation can begin **without** a cockpit. The first version of
the agent should produce a JSON output in a format the user can read directly
or evaluate with simple statistics. A cockpit follows once the data model has
stabilised.

When the cockpit eventually arrives, the user has named what it must show:

- The text, with the current reading focus highlighted.
- The growing concept graph, with edges thickening or thinning, concepts
  glowing with current "warmth", multiple concepts per level visible.
- The Chronicle queries — when, what was asked, what was returned, what was
  taken up, what was ignored.
- The trajectory: scrubbing back to see the state at any earlier step.

Reading vs. parsing should be **visible**: concepts arriving with the text
rather than all at the end, edges changing weight retroactively, syntheses
absorbing their basis concepts, diagonals appearing organically, repair waves
propagating backwards when new information arrives.

---

## Open questions (for empirical iteration with a human in the loop)

These cannot be solved by another research brief. Only by running the agent
on a real Wikipedia article and seeing what happens.

1. **Atomic reading unit.** Sentence, clause, EDU? Wikipedia gives us
   paragraph segmentation for free — is that enough for v1?
2. **Number of models.** One model on all levels, or multi-resolution with
   small/mid/large? When does the added complexity earn its keep?
3. **Action budget per step.** How many actions may the agent emit per
   reading step before we should worry about loops?
4. **Consolidation moment.** When exactly does the basis layer "release"?
   Strictly at section boundaries, or dynamically when synthesis strength
   crosses a value?
5. **Skim trust threshold.** When is the Chronicle "strong enough" on a
   concept that skim mode is allowed?
6. **Repair reach.** May a section-level synthesis revise a sentence-level
   synthesis from section 1?
7. **Identity resolution moment.** When does the agent commit a Q-ID — at
   first mention with a confidence guess, only after enough context, or at
   article end? And how is the resolution backfilled into earlier mentions?
8. **Relation codebook vs. P-IDs.** Where does the internal Run-9 codebook
   (BINDS_TO, REINFORCES, …) end and the Wikidata P-ID space begin? Are some
   internal types phased out in favour of P-IDs once the system matures?

These will be answered by reading the JSON the agent produces. Not before.

---

## Hand-off

**Hesiod** plans the architecture from these principles. The open questions
above are iteration points in that plan, not items to resolve up front.

**Talos** implements according to Hesiod's plan. The Builder doctrine
(`prompts/talos.md`, `AGENTS.md`, `docs/BUILD_DOCTRINE.md`) applies
unchanged. In particular: schema-first with Pydantic; RunReports for any
non-trivial pipeline; honest-failure; YAGNI.

Chaos withdraws.
