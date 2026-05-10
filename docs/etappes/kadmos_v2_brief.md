# Kadmos v2 — architecture: cognitive reading as a translation layer

**Filed by:** Hesiod (architect)  
**Date:** 2026-05-08 (renamed 2026-05-09)  
**Status:** Architecture decision — ready for implementation planning  
**Supersedes:** `docs/etappes/nous_hesiod_brief.md` (Kadmos v1 — stateless JSON extractor)  
**Previous filename:** This document was originally `nous_v2_brief.md`. It was renamed because the described agent belongs to the **Kadmos layer**, not Nous.

**Place in the pipeline:**

```
Text (Wikipedia)
    ↓
Kadmos v2  ←── this document
    Input:  raw text
    Output: semantically rich intermediate with working memory,
            syntheses, revisions — still text-oriented, with labels
    ↓
Embedding pass (internal to Kadmos)
    Labels → vectors. Edges → vectors. Text discarded. Provenance id retained.
    ↓
Nous (GNN encoder + synthesis layer)
    Input:  vector mesh (no text)
    Output: denser vector mesh (diagonal, cross-level, emergent)
```

Kadmos v2 yields a much richer intermediate than v1 — but it remains the **translation layer**. The LLM reads with working memory and performs revision, yet it produces semantically labeled concepts and edges that are then translated into vectors. Text is Kadmos v2’s input and leaves the system completely after the embedding pass.

**Boundary with Nous:** Nous never receives text. Nous receives the finished vector mesh from Kadmos and folds it through GNN encoders and spreading activation. If text is passed to “Nous” in an implementation step, that step is Kadmos, not Nous.

---

## 0. Guiding image

When a human reads text, there is no batch processing. Something continuous happens: concepts arise, activate prior knowledge, condense into syntheses, and are revised when later text changes the context. The result is not an extract — it is **understanding** that builds and rebuilds while reading.

Kadmos v2 models that. The LLM is not an extractor but an **interpreter with working memory**. The network that emerges is not a by-product — it **is** reading, materialized.

---

## 1. What Kadmos v1 got wrong by calling itself Nous

Three structural failures that explain why the earlier implementation failed as a *cognitive synthesis layer* — and why Kadmos as a *translation layer* still has a place:

**Failure 1 — LLM as extractor.** v1 asked the LLM: “Extract entities and relations from this paragraph.” That is NLP-pipeline thinking. The model does not “understand” text when treated as a data source — it understands when it *reads*, in the context of what came before.

**Failure 2 — No active working memory.** v1 did not give each LLM call the prior understanding. Every paragraph was processed in isolation. That is the equivalent of reading each sentence alone and closing the book after each one.

**Failure 3 — Wrong substrate.** A pointer-chasing graph database cannot run tensor operations, spreading activation, or mass implicit wiring. The target architecture is LanceDB + PyTorch.

---

## 2. Cognitive model (foundation)

Source: `notes/architecture/reading_agent_vision.md` — described directly by the product owner.

**Sentence level:** A sentence introduces ~5–10 new concepts. In parallel it massively activates ~50 prior-knowledge concepts in long-term memory — not sequentially, but like a storm with a potential gradient. From that activation storm **a synthesis condenses**. That synthesis is what primarily carries into the next sentence.

**Paragraph level:** Sentence syntheses condense into paragraph syntheses. The paragraph synthesis is not the sum of sentences — it is the distillate when the reader compresses what was read into a coherent intermediate understanding.

**Chapter and article level:** Paragraph syntheses condense further. The hierarchy is **emergent, not prescribed**: it arises from reading itself, not from a fixed structural template.

**Revision:** When a later passage casts an earlier concept in a new light, the reader goes back — not in the text, but in understanding. They revise the synthesis that contained the earlier concept. That is not a bug; it is the normal case.

**Parallel search:** While reading, two cheap background searches run in parallel:
- Similarity: which concepts in long-term memory lie close to what is being read?
- Edge traversal: from active concepts, move vertically to syntheses, then diagonally or horizontally into other branches — what is there?

These searches yield **candidates**. The LLM judges whether suspected proximity is a real connection.

---

## 3. The three components of Kadmos v2

### 3.1 Working memory (ReadingState)

Working memory is the core. It is neither a log nor a rigid database schema — it is the live state of the reader during the passage.

It contains:

**Active concepts** — a set of concepts that are currently “warm.” Each concept has:
- A **label** (human-readable, LLM-assigned)
- An **embedding** (384-dim, computed locally)
- An **activation weight** (float 0–1, decays over time/steps)
- A **revision history** (list of changes with step references)
- A **source anchor reference** (which passage first introduced the concept)

**Active connections** — edges between active concepts. Each connection has:
- Source and target concept ids
- A **connection type** (LLM-assigned, free-form — not from a codebook)
- An **understanding weight** (how strongly the LLM sees the link)
- A **rationale** (one LLM sentence on why the link holds)
- A revision history

**Syntheses** — condensed understanding nodes at a higher abstraction. A synthesis bundles several concepts. It has an embedding implied by the LLM’s description and then computed locally.

**Open questions / tensions** — concepts or links where the LLM signaled uncertainty. These are passed explicitly into the next step.

Working memory has a **capacity limit** (~30–50 active concepts). When full, the weakest activated concepts are **compressed** — folded into a synthesis and removed from the active set. That matches human “forgetting” detail while retaining understanding.

### 3.2 The reading act (ReadingStep)

Each step — a sentence, a paragraph, a chapter end; granularity is chosen dynamically — does the following:

**Step A: hypothesis generation (parallel, cheap, no LLM)**

Two processes run together:

1. **Similarity search** over the existing local mesh (and later over the Chronicle): embeddings of currently active concepts serve as query vectors; kNN returns candidate concepts that lie close semantically. These are presented to the LLM as “suspected proximity.”

2. **Edge traversal** in the local mesh: from active concepts, traverse the mesh — vertically to higher syntheses, then diagonally or horizontally into other branches. Because hierarchy is fuzzy, there are no sharp levels: a concept may link directly to an article-level synthesis without going through paragraph- and chapter-level syntheses. Traversal results are also given to the LLM as candidates.

Both deliver **not facts** but **hypotheses**: “Maybe these belong together.” The LLM decides.

**Step B: LLM reading step (the actual read)**

The LLM receives:

```
SYSTEM: You are a reader with working memory. You read a text
section by section. At each step you say how your understanding changes.

USER: {
  "current_reading": "<section text>",
  "current_understanding": {
    "active_concepts": [...],   // compact view of warm concepts
    "active_connections": [...], // most important active links
    "open_tensions": [...],      // what remains unclear
    "recent_syntheses": [...]    // latest condensations
  },
  "hypotheses": {
    "similarity_candidates": [...], // from step A
    "traversal_candidates": [...]   // from step A
  }
}
```

The LLM does not answer with “extracted entities.” It answers with an **understanding update**:

```json
{
  "new_concepts": [...],
  "new_connections": [...],
  "confirmed_hypotheses": [...],
  "rejected_hypotheses": [...],
  "revisions": [...],
  "synthesis": null | {...},
  "open_tensions": [...]
}
```

**Key:** `revisions`. When the LLM sees that an earlier concept or link must be reinterpreted, it emits a revision with rationale and a reference to the step where the revised concept originated. The concept in working memory is updated — with revision provenance.

**Step C: update working memory**

The LLM response is written into ReadingState:
- Add new concepts
- Add new connections
- Apply revisions (with provenance)
- Update activation weights (new concepts at 1.0, referenced ones slightly boosted, others slightly decayed)
- If capacity exceeded: compression

**Step D: write local mesh**

Concepts and links from ReadingState are written to the local reading-session mesh (LanceDB). Not yet into the global Chronicle — that is a separate step after reading.

### 3.3 Granularity choice

v1 used one LLM call per paragraph. That is rigid. In v2 the system chooses dynamically:

**Sentence granularity:** When a section introduces many new concepts or triggers revision, read at sentence level. More calls, finer understanding.

**Paragraph granularity:** The default for information-dense paragraphs.

**Chapter granularity (skim):** When active working-memory concepts already cover the chapter title well — when the prior step signaled familiar terrain — a chapter can be read with a single “skim” call. That matches human “trust and skim.”

Granularity choice is part of the LLM output: `"next_granularity": "sentence" | "paragraph" | "section" | "skim"`.

---

## 4. The local reading mesh

During reading a **local mesh** forms — not the global Chronicle, but a session-specific mesh materializing understanding of the current article.

This mesh lives in LanceDB (in-process, not persisted across sessions). It contains:

- **Concept nodes:** embedding vector + label + activation weight + revision history
- **Understanding edges:** no codebook, no fixed schema. The LLM describes the link in one sentence. The embedding of that description *is* the edge embedding.
- **Synthesis nodes:** abstractions over several concept nodes. Their position in vector space is computed (weighted average of base nodes plus the embedding of the LLM-generated synthesis label).

Edges arise from **understanding** (LLM judgment), not raw similarity. But similarity among edge embeddings is what later enables spreading activation through the mesh.

After a full read, the local mesh is the **understanding of the article** — not an extract, but a knowledge structure showing how concepts connect, at which levels, with which strength, with which revision history.

### 4.1 Mesh density

Where does the 1000:1 ratio come from?

Primarily **implicit edges:** after reading, when all concept embeddings sit in the local mesh, a post-pass runs: each node receives kNN edges to nearest neighbors in embedding space. These edges carry no LLM label — they are pure vector proximity, weighted by cosine similarity. They materialize associative links a reader has without being able to state them explicitly.

Explicit edges (LLM-assigned): ~800 nodes × ~10 links ≈ ~8,000  
Implicit edges (vector proximity, k=200): ~800 × ~200 ≈ ~160,000  

Ratio ~200:1. With Chronicle embedding (existing nodes add more edges): significantly higher.

Difference from v1: implicit edges come **after** LLM-driven understanding — they are condensation, not replacement.

---

## 5. Revision — the centerpiece

Revision is what fundamentally distinguishes Kadmos v2 from v1.

### 5.1 How revision is triggered

In every LLM call the model checks current understanding against the new passage. It may trigger revision when:

- An earlier concept is wrong or incomplete given new context
- An earlier link turns out mistaken or reversed
- An earlier synthesis was too coarse and must be split

The LLM signals this via the `revisions` field in its response.

### 5.2 What a revision contains

```json
{
  "target_concept_id": "...",
  "revision_type": "update" | "split" | "merge" | "invalidate",
  "reason": "...",
  "triggering_passage": "...",
  "old_understanding": "...",
  "new_understanding": "..."
}
```

`split`: one concept becomes two. `merge`: two become one. `invalidate`: a concept was wrong — it is not deleted (provenance preserved) but marked invalid.

### 5.3 How far revisions reach

In v1: only within the current section. In v2: across the whole reading session. Working memory holds all concepts with birth-step references. A revision may point to step 3 while we are at step 47.

Constraint: the LLM only sees the **compact rendering** of working memory, not the raw text of all prior steps. It can only revise what is visible in current working memory. What was already compressed into a synthesis remains addressable at the synthesis level — revision then targets the synthesis, not each base concept individually.

---

## 6. Technical substrate

### 6.1 LanceDB as primary store

The local reading mesh lives in an in-process LanceDB instance. Append-only, no locking, no transactions. Corrections are written as new rows with `supersedes` references, never as in-place updates.

After reading: the local LanceDB can be exported into the global Chronicle (separate step, not part of reading itself).

### 6.2 Embeddings

Every concept gets an embedding immediately — local, no LLM, using the configured embedding model (BAAI/bge-small-en-v1.5 or better). The embedding of the concept label is the primary vector.

Edge embeddings are computed from the embedding of the connection description (the sentence the LLM gave as rationale).

### 6.3 PyTorch for spreading activation (post-read)

After reading, when the local mesh is complete, a spreading-activation pass may run over the graph — as a CSR tensor in PyTorch, not as graph-database traversal. That is the step that **materializes** implicit kNN edges and brings the mesh toward the desired density.

### 6.4 KnowledgeStore protocol

Kadmos v2 does **not** write the session-local mesh through the legacy `KnowledgeStore` API shape that was tuned for the old graph-backed path; it writes directly to LanceDB for the local reading mesh.

The global Chronicle is filled after reading via a separate export step into whatever global store the deployment uses, decoupling the read path from persistence infrastructure.

---

## 7. What v2 explicitly does not build (scope)

- **No global Chronicle integration during reading.** Step A similarity search runs only over the local reading-session mesh initially. Chronicle-wide search is a v3 topic.
- **No multi-article sessions.** v2 reads one article per session.
- **No cockpit.** Output is JSON + AnnotatedReading + RunReport.
- **No streaming.** Reading is synchronous, one step after another.
- **No multi-resolution model stack.** One LLM for all granularities.

---

## 8. What Monkey 1 means in v2

The comparison metric from the v1 brief still applies, with shifted expectations:

| Metric | v1 result | v2 target |
|--------|-----------|-----------|
| Edge/node ratio (explicit) | 1.10 | 5–15 (LLM links + syntheses) |
| Edge/node ratio (total with kNN) | 1.10 | 100–500 |
| Revision events | 0 | measurable > 0 |
| Synthesis hierarchy levels | 1 (all paragraph) | 3–4 (paragraph, section, article) |
| Cross-source connections (on Chronicle export) | 636 | higher, through understanding |

The 1000:1 ratio remains a long-range goal for Chronicle export with a kNN pass. Within one reading session (explicit + implicit edges): 100–500:1 is the realistic v2 target.

---

## 9. Open decisions for the implementation plan

Hesiod answers these in the implementation brief built on this architecture decision:

**Q1 — Granularity bootstrap.** Does the first step start at sentence, paragraph, or dynamically by article length?

**Q2 — Working-memory compression.** When exactly do we compress? On capacity overflow, or proactively at section boundaries?

**Q3 — Hypothesis budget.** How many candidates from similarity and traversal per step? More candidates → better judgments, higher token cost.

**Q4 — Revision reach.** How far back can the LLM revise? Only active concepts, or compressed syntheses too?

**Q5 — LanceDB schema.** How are concepts, edges, and revisions modeled? Separate tables vs one unified assertions table?

**Q6 — AnnotatedReading format.** What exactly is in the output JSON? Full revision graph vs final reading state only?

**Q7 — Edge embedding.** Embed the connection-description sentence (richer, costlier) vs mean of source and target embeddings (cheap, loses link type nuance)?

---

## 10. Why this is hard — and why it is right

The hard part of v2: the LLM must “remember” earlier steps without receiving raw text from all prior steps (too long, too expensive). The solution — a compact rendering of working memory — is itself a design problem. Too compact: the model loses context and cannot revise well. Too verbose: prompts become expensive and slow.

That is the core problem Kadmos v2 must solve. There is no canned answer; it is empirical: build, measure, calibrate. That is the value of the first corpus run.

Why it matters: it is the problem you **must** solve to build a system that truly reads instead of only extracting. v1 avoided it by isolating every paragraph. v2 confronts it.

---

*Hesiod withdraws. The architecture belongs to the implementer.*
