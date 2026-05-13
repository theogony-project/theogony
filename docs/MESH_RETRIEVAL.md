# Mesh Retrieval

**Status:** canonical doctrine for retrieval, learning, and cross-modal extension on the mesh substrate. Specifies how agents inject queries, how Spreading Activation diversifies, how the substrate learns from agent feedback, how the multi-agent ecology stays honest, and how non-textual modalities attach.
**Companion docs:** [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) (the substrate this document operates on), [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) (the runtime that executes it), [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) (the post-hoc verification framework that contains the multi-agent ecology), [`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md) (the operator-facing framing of the multi-agent dynamic), [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) §"Vector-Vector-Mesh" and §"Language is the Edge, Not the Substrate" (related general principles this document extends), [`etappes/mesh_native_lm_brief.md`](etappes/mesh_native_lm_brief.md) (the MNLM that uses the substrate as its native medium).
**Audience:** every Pantheon agent that issues a query, every builder agent that implements one, the MNLM, and any future agent that consumes a Constellation.

**Precedence.** Together with [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) and [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md), this document is the **operative substrate doctrine**. Where the substrate triplet conflicts with older doctrine documents on substrate-layer behaviour, runtime, or use, the substrate triplet is operative.

---

## Why this doc exists

The substrate doctrine in [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) defines the mesh's mechanical and dynamic behaviour. The implementation guidance in [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) defines how that behaviour is realised in storage and runtime. Neither, by itself, says anything about what a *good query* looks like, how the substrate **learns** from queries, how to keep the substrate from becoming an echo chamber under that learning, or how to extend the substrate beyond text.

This document closes those four gaps:

1. **How queries enter the substrate** without collapsing into a self-confirming central tendency.
2. **How the substrate learns** from the agents that consume its activations — and how it avoids the failure modes that come with self-reinforcing systems.
3. **How the multi-agent ecology** keeps the substrate from drifting into one perspective's blind spots, framed as a deliberate strategy-game dynamic among agents with distinct epistemic stances.
4. **How modalities beyond text** attach to the substrate without requiring a structural rewrite — and what to defer.

The headline rule is one sentence:

> **Retrieval is conversation between the agent and the substrate; both speak in vectors and structure; both must keep their conversation honest.**

The rest of this document specifies what *honest* means in operational terms.

---

## Spreading Activation as the universal retrieval primitive

Every retrieval against the mesh uses Spreading Activation. Per [`TARGET_ARCHITECTURE.md`](TARGET_ARCHITECTURE.md) §"Three Non-Negotiable Technical Decisions" §3 and the [`GLOSSARY.md`](GLOSSARY.md) entry, this is binding: there is no SQL, there is no Cypher, there is no "fast path" for simple lookups that bypasses Spreading Activation. The primitive is universal because the substrate's value comes from multi-hop, structural, frame-aware retrieval that flat similarity cannot produce.

A query has the following lifecycle:

1. **Construction.** The querying agent assembles a query — minimally a single vector, ideally a small sub-mesh with structure (see §"Sub-mesh injection" below).
2. **Diversified seeding.** The substrate selects a diverse set of seed nodes from which propagation will start (see §"Diversified injection").
3. **Propagation.** Spreading Activation runs as batched SpMV across the mesh. Frame routing filters which edges propagate at each hop (see §"Frame-sensitive resonance"). Damping and threshold determine convergence.
4. **Constellation extraction.** The activated subgraph above the threshold is the Constellation — a structured working set, not a list of text chunks ([`GLOSSARY.md`](GLOSSARY.md)).
5. **Consumption.** The Constellation is injected into the consuming agent's reasoning context. For the MNLM this is Latent Space Injection per [`etappes/mesh_native_lm_brief.md`](etappes/mesh_native_lm_brief.md). For text-output agents (Iris) this becomes the basis for natural-language synthesis.
6. **Feedback.** The consuming agent rates the Constellation; the rating modulates Hebbian updates along the activation trace (see §"Three-factor reinforcement learning").

Every step except the last is read-only against the substrate; only the last writes back. This is the basis of the substrate's read-heavy MVCC concurrency model in [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Concurrency model".

---

## Diversified injection

A naive retrieval-by-cosine-similarity collapses against the substrate's own pathologies: it always finds the most popular nodes, always lands in the densest regions, and silently amplifies whichever bias dominates the embedding distribution. The substrate's retrieval discipline rejects this in three ways, each addressing a distinct failure mode.

### A. Maximum Marginal Relevance (anti-redundancy diversity)

Instead of top-K most similar to the query, the substrate selects K seeds that are simultaneously near the query *and* far from each other. The standard Maximum Marginal Relevance criterion:

```
seed_i = argmax_n  [ λ · sim(n, query) − (1−λ) · max_{m ∈ already_selected} sim(n, m) ]
```

Default `λ ≈ 0.6`. The result is K seeds covering different sides of the query's semantic neighbourhood, not K versions of the same answer.

This is well-known in IR; the substrate makes it the *default*, not an option. Standard nearest-neighbour seeding is forbidden in production retrieval — it would always land in the substrate's central tendency and starve the periphery.

### B. Weight-class stratification (multi-scale retrieval)

Nodes are categorised by their accumulated edge weight (`node_potential` from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Node anatomy"). The substrate maintains roughly four weight classes:

- *micro* — `node_potential` below the 25th percentile of all nodes
- *medium* — 25th to 75th percentile
- *large* — 75th to 95th percentile
- *hub* — above the 95th percentile

For every query, the seeding pass selects K seeds from each class independently. Total seeds: `4·K_per_class` (typically 5–25 per class, total 20–100).

**What this gives the substrate.** Hubs deliver the gestalt context of the query's region. Medium nodes deliver the thematic frame. Micro nodes deliver the specific facts that are usually the actual answer. Without stratification, hub nodes win every retrieval (they are central to every cluster), and the long tail of specifics is starved. Stratification gives the substrate's depth a chance.

This is also the substrate's structural Mendel-risk mitigation at retrieval time. Per [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"The Mendel risk — a consideration to weigh", rare-but-correct knowledge must have a route to the answer. Weight-class stratification guarantees that route exists by construction — independently of whatever therapy or cleanup actions Argus is performing elsewhere.

### C. Sub-mesh injection (structural matching, not point matching)

The most powerful retrieval mode is **sub-mesh injection**: the agent constructs a small graph fragment — several nodes with relationships among them — and asks the substrate "where in the mesh would this fragment fit?".

**Why this is different.** A point query asks "find me things that are near this single concept." A sub-mesh query asks "find me a region of structure that resembles *this entire shape*." For multi-hop reasoning, for analogy retrieval, for cross-domain pattern matching, the structural question is the right one. Point queries cannot see structure.

**The matching algorithm (combined per-node and structural).** Let the agent's sub-mesh be `Q` with `q` nodes and some edges, and the big mesh be `M`.

1. **Per-node ANN.** For each node `q_i ∈ Q`, find the top-K nearest in `M` by semantic vector. Call these the *candidate matches* for `q_i`.
2. **Region detection.** Identify *candidate regions* in `M` where many candidate matches lie within a small graph distance of each other (a Spreading Activation of moderate intensity from each candidate-match set finds the regions where the activations overlap).
3. **Region scoring.** Each candidate region receives three scores:
   - **Per-node similarity:** mean cosine similarity between the query nodes and their matches in the region.
   - **Structural similarity:** Weisfeiler-Lehman hashing on both `Q` and the region produces structural fingerprints; their overlap is the structure score. WL hashing is cheap (O(edges) per pass, two or three passes give a good fingerprint) and requires no training.
   - **Frame consistency:** mean `frame_consistency` of edges in the matched region (from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Edge anatomy").
4. **Region ranking.** Combine the three scores by a weighted sum (defaults: 0.5 per-node, 0.3 structural, 0.2 frame). Top-N regions become activation seeds for the actual Spreading Activation pass.

The metaphor is: the agent says "here is a small piece of mesh I'm thinking with — where in the substrate would it feel at home?". The substrate replies with the regions whose shape, content, and frame resonate with the query's shape, content, and frame.

For multi-hop reasoning (`A` related to `B`, which is related to `C`, which is related to `D` — what does the substrate know about this kind of pattern?), sub-mesh injection is the operation that separates the substrate from a vector database with edges. It is the central retrieval discipline once the substrate matures past the prototype.

### When to use which

| Query intent | Mode |
|---|---|
| Retrieve facts about a single concept | MMR + weight-class on the single query vector |
| Answer a direct factual question | MMR + weight-class + frame routing |
| Reason multi-hop / analogy / cross-domain | Sub-mesh injection |
| Detect novelty / find regions never seen before | Sub-mesh injection with low region-score threshold |
| Verify a hypothesis | Sub-mesh injection of the hypothesis as a structured assertion |

Diversified injection (A + B) is *always* on. Sub-mesh injection (C) is on when the agent provides structure; otherwise it falls back to A + B over a single query vector.

---

## Three-factor reinforcement learning

Pure Hebbian learning ("co-firing strengthens edges") is unsupervised — it amplifies whatever patterns emerge from query frequency, not whatever patterns are actually useful. The substrate adopts the biological **three-factor plasticity** model, where Hebb is modulated by a third factor: a reward / feedback signal from the consumer of the activation.

This is biologically standard (dopaminergic modulation of synaptic plasticity, e.g. Frémaux & Gerstner, 2016) and operationally well-understood as a form of policy gradient learning over the mesh's edge weights.

### The modulated Hebbian rule

For each edge `(i, j)` traversed during a Spreading Activation pass, with propagation strength `s_ij`, given a feedback signal `f_target ∈ [-1, +1]` for the target node `j`:

```
Δw_ij  =  α · s_ij · (1 + β · f_target)
```

- `α` — base Hebbian rate (e.g. 1e-2 per firing)
- `β` — feedback modulation strength (typical 1.0; range 0.5 – 2.0)
- `f_target = 0` → degenerates to plain Hebb
- `f_target = +1` → 2× strengthening (with β = 1)
- `f_target = -1` → no update (with β = 1)
- `f_target = -1` and `β > 1` → active weakening

The substrate writes the modulated Δw into the delta buffer per [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Edges — PyTorch sparse + delta buffer". No structural change; the modulation is just a scalar in the update.

### Eligibility traces (multi-hop credit assignment)

A multi-hop activation `a → b → c → d` may produce feedback only on the final node `d`. The eligibility trace (TD(λ)-class, classical reinforcement learning) lets the feedback distribute backward through the path.

Each edge maintains a fast-decaying `eligibility` that increments with recent firing:

```
eligibility_ij(t+1)  =  γ · eligibility_ij(t)  +  s_ij(t)            with γ ≈ 0.7
```

When feedback `f` arrives for some target node `d`, every edge whose eligibility trace is non-zero receives an update proportional to its eligibility:

```
Δw_ij  =  α · f · eligibility_ij
```

Closer-to-target edges have higher eligibility (less decay) and receive more credit; distant ancestor edges receive less. This is the substrate's mechanism for crediting upstream paths that contributed to a useful answer, even when the answer node is several hops away.

### Sources of feedback

The substrate accepts feedback from four channels with different signal qualities and frequencies:

| Channel | Signal quality | Frequency | Cost |
|---|---|---|---|
| **LLM self-rating** — the consuming LLM, after generating its response, rates which Constellation nodes were essential | Medium — biased but consistent | Every activation | Cheap (one extra structured-output call) |
| **Downstream task success** — was the answer accepted? Did the user follow up with confusion? Did the agent's plan succeed? | High — closer to ground truth | Sparse | Low (passive observation) |
| **Explicit user rating** — thumbs up/down or structured rating | Highest | Very sparse | High (intrusive) |
| **Implicit signals** — time-on-result, reformulations, abandonment | Low — noisy | Continuous | Very low |

The default production pipeline combines (1) LLM self-rating on every activation with (2) downstream task success when available. The other channels are optional bonuses.

**LLM self-rating discipline.** The rating LLM should not be the same model (or even necessarily the same vendor) as the consuming LLM, to avoid confirmation bias. A small dedicated rater model with a structured-output schema is cheap and scales linearly with query volume. Random sampling of ~5% of activations should use a *different* rater (or no rater at all, defaulting to plain Hebb) as an exploration measure to prevent the substrate from over-optimising for one rater's biases.

### Risks — and how the substrate already mitigates them

Three-factor learning makes substrates more useful and substantially more dangerous. The substrate's existing mechanisms address each risk:

**Risk 1: Confirmation feedback loops.** If the rater's "useful" judgement is biased toward what it expects to see, the substrate learns to confirm its own expectations.
- *Mitigation:* Different rater than consumer (above); periodic random no-rating runs; Argus's spiral detection (the **refutation absorption** symptom from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"The five topological symptoms") catches the worst form of this.

**Risk 2: Reward hacking.** Edges that consistently receive positive feedback grow so dominant they fire even in inappropriate contexts.
- *Mitigation:* Frame routing at hubs (below) prevents universally-positive edges from firing in incompatible frames; the **dominance penalty** therapy from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Five staged therapies" downweights regions that exceed an activation share threshold.

**Risk 3: Sparse rewards.** Most activations produce no explicit feedback signal.
- *Mitigation:* LLM self-rating provides a rating on every activation, so β · feedback is rarely 0; eligibility traces back-propagate sparse rewards across multi-hop paths.

**Risk 4: Mendel suppression.** Rare-but-correct activations get penalised because the rater finds them unfamiliar.
- *Mitigation:* The Mendel risk from [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"The Mendel risk — a consideration to weigh" — Argus weighs the probability of pathology against the Mendel risk before recommending invasive therapy; weight-class stratification guarantees rare nodes have routes to the answer. Three-factor learning operates on top of these safeguards, not in their absence.

The substrate is designed so that turning on three-factor learning does not silently degrade the substrate's openness. The mitigations are part of the substrate's structure.

### Storage

Per-node lifetime counters `positive_feedback_total`, `negative_feedback_total`, `feedback_recent` (rolling window) — already in the `ConsolidatedNode` schema in [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Tier-1+ — Consolidated Node". Per-edge `feedback_modulated_strength` (lifetime audit) and `eligibility` (current trace) — already in the `Edge` schema in [`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Edge anatomy". No new schema is needed; the substrate doctrine anticipated three-factor learning when it specified those fields.

---

## Frame-sensitive resonance

The substrate's frame vector ([`MESH_SUBSTRATE.md`](MESH_SUBSTRATE.md) §"Node anatomy") encodes *epistemic frame* separately from *semantic content*. This document specifies how it is used in retrieval.

### Why polarity cannot live in vectors

A naive embedding of "Thyroxine is an oxindole derivative" and "Thyroxine is *not* an oxindole derivative" produces nearly identical vectors. The negation is lexical detail; the embedding model represents the semantic centroid. Cosine similarity between the two is ~0.95+.

This means: if the substrate stored only semantic vectors and ran cosine retrieval, a refuted historical claim about Thyroxine would be retrieved with the same priority as the correct current understanding. The substrate's "knowledge" of the refutation is invisible to retrieval.

This is an unsolvable problem at the vector level. No realistic semantic encoder distinguishes negation reliably enough for production retrieval. The substrate's response is to **lift polarity out of the vector and into the frame.**

### Frame as a separate vector

Each node carries a `frame_vector` of small dimension (default 64-d). The frame vector is produced by an encoder trained (or rule-bootstrapped, see [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Open implementation questions") to distinguish epistemic frames:

- **Definition** — "Thyroxine is iodothyronine."
- **Current claim** — "Treatment X is effective for condition Y."
- **Historical claim** — "In 1915, Kendall held thyroxine to be an oxindole derivative."
- **Refuted claim** — explicit refutation framing: "Thyroxine is *not* an oxindole derivative."
- **Hypothesis** — "It is hypothesised that X."
- **Observation** — "The patient reported X."
- **Direct quote** — "X said: 'Y'."

These are not stored as discrete labels; they are *learned* embedding regions. A small contrastively-trained frame encoder collapses semantically-similar but frame-distinct sentences to neighbouring points only when the frames agree. The frame_vector for the Kendall historical claim is far from the frame_vector for the current Thyroxine ontological claim, even though their semantic_vectors are close.

### Frame routing during Spreading Activation

A query carries a frame context (or, more often, *seeks* certain frames). Each query has an active frame profile — a small vector representing what kinds of claims the query wants.

| Query type | Active frame profile |
|---|---|
| "What is Thyroxine?" | Definition + Current claim |
| "What did Kendall originally think Thyroxine was?" | Historical claim + Refuted claim |
| "What evidence is there for hypothesis X?" | Observation + Direct quote |

Spreading Activation propagates an edge only when the edge's `frame_consistency` exceeds the dot product (or similar comparison) of the active frame profile with the edge's endpoint frame vectors. This is the **frame-routed activation** mechanism.

**Practical effect.** A query "What is Thyroxine?" propagates strongly through edges whose endpoints are framed as definitions or current claims. It propagates weakly through edges whose endpoints are framed as historical or refuted claims. The Kendall oxindole-derivative chunk is in the Constellation only if a low-threshold parameter explicitly admits historical context; in default operation it is not retrieved for the "what is" query.

A query "What did Kendall think Thyroxine was?" inverts the frame profile. The same Kendall chunk is now retrieved with high priority. The same substrate state, queried in two different frames, returns two different Constellations — this is the substrate's representation of the truth-being-held-at-different-times structure that flat encyclopaedias lose.

### Implementation notes

The frame_vector is computed by Kadmos at insertion (using the heuristic encoder described in [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Open implementation questions" until a trained one exists) and is mutable by Oneiros during consolidation (when many chunks with consistent frames consolidate, the consolidated node inherits the dominant frame).

The `frame_consistency` on each edge is a precomputed cosine of the endpoint frame vectors. It is updated by Oneiros at the same time as decay; for stable mesh regions it stabilises and then stops changing. SpMV with frame routing is the masked SpMV described in [`MESH_IMPLEMENTATION.md`](MESH_IMPLEMENTATION.md) §"Frame routing" — element-wise mask before matrix multiplication, fused into the GPU kernel.

---

## The multi-agent strategy game

Theogony's design intent ([`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md)) frames the Pantheon as a society of specialised agents with distinct roles and incentives, interacting on the Chronik as a shared map. This document specifies the *retrieval-side* consequences of that framing: how agent diversity prevents single-perspective drift, how parallel "universes" enable empirical comparison of substrate-formation strategies, and how the substrate can be used as the substrate for its own meta-evaluation.

### Distinct epistemic stances per agent

The Pantheon's agent roster ([`GLOSSARY.md`](GLOSSARY.md) §"Core Pantheon agents") was not designed for ensemble diversity, but it produces it. Each agent has a structural bias, captured in its prompt and its activation patterns:

| Agent | Structural bias | Frame profile preference |
|---|---|---|
| **Argus** | Looks for contradictions, novelty, gaps | Refuted claim + Observation + Hypothesis (high priority on the unsettled) |
| **Athene** | Verifies, checks consistency | Definition + Current claim (high priority on the established) |
| **Morpheus** | Associates, finds patterns across distant regions | Cross-domain bridges, structural similarity (frame-agnostic) |
| **Mnemosyne** | Watches the substrate's own behaviour | Meta-frames; cares about activation patterns more than content |
| **Iris** | Synthesises for human consumption | Definition + Current claim + Direct quote |
| **Kalypso** | Discovers what was never queried | Low-traffic regions, periphery (frame-agnostic; structural) |

A query that passes through multiple agents — say, the same factual question routed independently to Athene (verifier) and Argus (sceptic) — produces two different Constellations from the same substrate state, because the agents inject differently-framed sub-meshes and consume them differently. **A claim that survives both Constellations has a different epistemic status than a claim that appears in only one.**

This is not an additional verification layer on top of the substrate. It is the substrate already running multi-perspective queries by virtue of having a multi-perspective agent population. The infrastructure cost is essentially zero — the substrate is already performing batched activations; routing K activations through K agents is what it does anyway.

### Parallel universes — empirical comparison of strategies

Lance's versioning gives the substrate **branching for free**. A "universe" is a Lance branch of the substrate, plus an agent configuration applied to it. Different universes can:

- run with different decay exponents (k = 1.5 in one, k = 2 in another, k = 2.5 in a third)
- run with different agent populations (heavy on Argus in one, heavy on Athene in another)
- run with different frame-encoder models (production encoder vs. an experimental contrastive variant)
- run with different Mendel-safeguard thresholds
- run on the same input data stream

This is not a thought experiment. Lance branches are operationally cheap to create and maintain; the substrate's MVCC layer makes the branches mutually isolated. The infrastructure cost is roughly proportional to the number of unique edges across branches (shared edges share storage).

**Comparison metrics.** What makes one universe's substrate "healthier" than another's? The substrate doctrine and the immune-system doctrine together suggest several:

| Metric | Definition | Direction |
|---|---|---|
| **Coherence quotient** | Fraction of active high-confidence claims that *do not* contradict other active high-confidence claims (per `CONTRADICTS` edges, [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md)) | Higher is better |
| **Robustness** | Variance of the substrate's answers to a fixed test question set over time | Lower is better |
| **Predictive accuracy** | Substrate's answers to held-out test questions vs. ground truth | Higher is better |
| **Spiral incidence** | Count of pathology findings per thousand Spreading Activation passes | Lower is better |
| **Mendel preservation** | Fraction of rare-but-correct test answers that survive across N consolidation cycles | Higher is better |
| **Update efficiency** | Bits of information delta per ingest event (compare consolidated vs. raw entropy) | Higher is better |
| **Activation cost** | Mean SpMV runtime per query at fixed mesh size | Lower is better |

These are well-defined statistics on a Lance-versioned substrate. Mnemosyne's A/B framework from [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md) §"Self-improvement loop" extends naturally to N-way universe comparison.

**Cross-universe migration.** A claim that consolidates as true in one universe may be tested as a hypothesis in another. The successful claim becomes a candidate insertion in the other universe (with reduced confidence reflecting that it came from a different substrate). Truth in this framing emerges across universes, not within any single one. This is Phoenix-incarnation-class work and explicitly Gen 3+, but the substrate's design must not foreclose it.

### Why this matters for retrieval

The strategy-game frame is not gamification — see [`STRATEGY_GAME_ANALOGY.md`](STRATEGY_GAME_ANALOGY.md) §"Non-Goals". It matters at the retrieval layer for one practical reason: **the substrate's defence against confirmation bias is structural diversity at the agent level, not algorithmic policing inside the substrate.** The substrate cannot defend itself against its own consumer's biases by being more careful. It can only do so by being consumed in parallel by multiple agents with structurally different incentives.

This is the substrate-side instantiation of [`IMMUNE_SYSTEM.md`](IMMUNE_SYSTEM.md): the immune system is sample-based and asynchronous *because* the substrate is multi-consumer and the consumers' diversity is the verification mechanism. Pre-validation gates fail because they pretend a single judge can replace the diversity of consumers.

---

## Multi-modal extension

The substrate's mechanics — Hebbian update, super-linear decay, saturation caps, splits, frame routing, pathology surveillance — operate on abstract nodes and edges. Nothing in any of them references textual content specifically. **The substrate is therefore modality-agnostic by construction.** Adding image, molecular, genetic, or geographic content does not require restructuring; it requires adding modality-specific embedding pipelines and (optionally) modality-specific frame encoders.

This affordance is a property of the substrate doctrine, not a feature to be designed in later. The doctrine was already this way.

### What kinds of modalities can attach

Any data type with a robust vector embedding can attach:

| Modality | Embedding model class | Vector dim | Notes |
|---|---|---|---|
| **Images** | CLIP, DINOv2, SigLIP | 512–1024 | Cross-modal text-image alignment is mature |
| **Audio** | Wav2Vec2, AudioMAE | 768–1024 | Music vs. speech vs. environmental — separate sub-encoders may help |
| **Proteins** | ESM-2, AlphaFold-derived | 1280 | Structure embeddings; aligned to function via downstream models |
| **Small molecules** | ChemBERTa, MolFormer, Uni-Mol | 768 | SMILES strings or 3D structures |
| **DNA / RNA sequences** | Nucleotide Transformer, DNA-BERT | 768–1024 | Genomic position is a separate temporal-anchor-class concern |
| **Source code** | StarCoder embeddings, CodeBERT | 768–4096 | AST-aware encoders give better structure |
| **Geographic** | H3 cells + lat/lng + learned spatial embeddings | small | Almost always a temporal/spatial anchor, not a fan-out concept |
| **Time series** | Chronos, TimesNet | 384–512 | Dense temporal embedding alongside the temporal-anchor field |

The list is open. Whatever has an embedding model can have a vector; whatever has a vector can be a node.

### Two architecture options — single mesh vs. parallel meshes

When the second modality enters the substrate, an architectural question opens. Both choices are doctrine-conformant; the choice between them is engineering, not philosophical.

**Option A — Single mesh, multiple modal vectors per node.**

A node carries every modal vector that applies to it: a node about adrenaline carries `semantic_vector` (text), `molecule_vector` (chemical structure), `pathway_vector` (metabolic context), and so on. Modalities that don't apply to a node leave the corresponding vector null. Spreading Activation operates on the substrate normally; per-modality retrieval uses the relevant vector for similarity.

*Pros:* Single substrate, single set of dynamics, single Oneiros. Cross-modal connections are ordinary edges. Bridge nodes (an image of a goitre connected to the textual description and to the molecule) are just nodes that participate in multiple modalities.

*Cons:* Sparse vector columns waste storage. Modalities with very different decay characteristics (images perhaps decay differently than text claims) cannot have separate dynamics.

**Option B — Parallel meshes per modality, with bridge nodes.**

Each modality has its own substrate (its own Lance tables, its own edge tensor, its own Oneiros). Bridge nodes exist in two or more modality-substrates simultaneously, with cross-substrate edges connecting them. A Spreading Activation that crosses a bridge propagates into the foreign substrate and back.

*Pros:* Each substrate uses its modality's optimal storage and dynamics. Modality-specific consolidation strategies. Storage-efficient (no sparse modal vectors).

*Cons:* Cross-modal queries involve multiple substrates — the runtime complexity increases. Bridge maintenance is its own concern.

**Recommendation.** Start with Option A. It is structurally simpler and the storage cost of sparse modal vectors is not painful at Tier 0 / Tier 1 scales. Only migrate to Option B if and when a single modality grows large enough that its own scaling concerns dominate (e.g., if the substrate ingests millions of medical images and the image-mesh becomes a Tier-2-class workload by itself). The migration from A to B is a clean refactor: extract all nodes with non-null `image_vector` into a separate substrate, keep a bridge node in the original substrate that carries the cross-substrate edges. Nothing in the substrate's logic changes.

### Concrete value

The point of multi-modal extension is that retrieval becomes inherently cross-modal. A query about thyroid disorders activates simultaneously:

- the textual description of goitre formation and Coindet's iodine treatment
- a histological image of thyroid tissue
- the chemical structure of iodine
- the SMILES string of thyroxine
- the metabolic pathway diagram showing thyroid hormone synthesis
- a temporal anchor at 1820 (Coindet's first iodine therapy)

The MNLM consuming this Constellation reasons across all of them in vector space, without anyone having converted images to text descriptions or chemicals to natural language. This is the fully-realised form of the [`CHRONICLE_PRINCIPLES.md`](CHRONICLE_PRINCIPLES.md) §10 *"Vector-Vector-Mesh"* principle: the substrate accepts whichever representation a domain naturally produces and reasons across them in their native form.

This is not Gen 1 work. It is the affordance the substrate's design preserves so that Gen 2+ can build it.

---

## What retrieval does not do

A small set of forbidden patterns. Everything not on this list is an affordance.

1. **No top-K-by-cosine retrieval as the *default* production path.** Diversified injection (MMR + weight-class stratification, optionally sub-mesh signature) is the production default for the reasons in §"Diversified injection". A pure top-K-by-cosine retrieval starves the long tail and amplifies whatever bias dominates the embedding distribution. (Specialised tools — e.g., an anchor-node range query for "what happened in 1819?" — may use index lookups and are not subject to this rule. The rule is about the default conceptual-query path.)

2. **No "rate this Constellation" feedback path that makes the consuming agent the substrate's only feedback channel.** Three-factor reinforcement learning needs at least two independent feedback sources (per §"Sources of feedback" — typically LLM self-rating *plus* downstream task success, with the LLM rater being a different model from the consumer). A single-channel feedback loop is a self-confirming loop and amplifies the consumer's biases into substrate weights.

3. **No three-factor learning without the supporting mechanisms from `MESH_SUBSTRATE.md`.** Frame routing, weight-class stratification, and Argus's pathology surveillance (with Mendel-weighed therapy) are the substrate's defences against reward hacking. Turning on RL without them turns the substrate into a confirmation-bias amplifier. The mechanisms are not optional dependencies; they are structural prerequisites.

That's the entire forbidden list for retrieval. Three points.

Everything else is an affordance: special-purpose query paths (anchor-range queries, structural-similarity queries, frame-targeted queries), agent-specific feedback channels, multi-modal queries that span vector kinds, parallel-universe substrate experiments (per §"Parallel universes — empirical comparison of strategies"), modality-specific tunings for parallel meshes (per §"Multi-modal extension"). All are permitted and useful when applied with care.

The mental model: retrieval is a conversation between the agent and the substrate; both must keep the conversation honest. The three points above are what *honest* means at the structural level. The rest is taste, judgement, and engineering.

---

## Open questions

- **Frame-encoder training data.** A from-scratch contrastive frame encoder requires labelled frame examples. Bootstrap path: rule-based frame extraction during Kadmos extraction (looking for cue words: "claimed", "wrongly believed", "demonstrated", "hypothesised", direct quotes), generates pseudo-labels at scale; then a small contrastive trainer over the corpus. The right size for this encoder is probably 64–128 dimensions and a few million parameters — a project-scale model, not a foundation model.

- **MMR `λ` and weight-class boundaries.** Both are tuning parameters; both should be A/B-tested via Mnemosyne once the substrate has enough query volume.

- **Sub-mesh injection cost at scale.** WL-hashing is O(edges) per pass; per-node ANN is fast on Lance HNSW; combined region scoring is a small extra pass. The combination should hit single-digit-millisecond latency per sub-mesh query at Tier 1 substrate sizes. Empirical confirmation is open.

- **Three-factor learning convergence.** With many concurrent queries and noisy feedback, edge weights should converge to a stable equilibrium representing relative usefulness. The convergence rate, the equilibrium variance, and the right `α / λ` ratio are empirical questions for early Tier-1 deployment.

- **Multi-agent A/B at the universe level.** Mnemosyne's A/B framework was designed for parameter tuning; running it at the universe level (whole agent populations against each other) is a research direction, not a production capability today. The substrate doctrine preserves the option.

- **Multi-modal frame consistency.** Does an image have an "epistemic frame"? A photograph and a diagram of the same anatomical structure carry different epistemic implications. The frame encoder should extend to non-textual modalities; what the right embedding looks like is open research.

---

## One-line summary

> **Diverse seeding, frame-aware propagation, three-factor learning with Mendel-weighed safeguards, and multi-agent perspectives — all converging into a single Constellation per query that the consumer reasons over in vector space.**
