# What actually runs in the living substrate — an inventory

> **Abstract.** *Question.* Five times in a few weeks a doctrine
> mechanism turned up whose input nobody writes. A pattern, or five accidents?
> *Method.* For every mechanism the MESH doctrine prescribes, three separate
> questions: is it implemented, is it reached from a real path, are its inputs
> actually produced? Five readers took one doctrine area each; a second pass
> then tried to *refute* every "does not run" — of 110 attempts 105 confirmed,
> four corrected upward, one downward. *Result.* Of 119 mechanisms 9 run, 24
> partly, 34 are inert, 10 blocked, 42 absent; retrieval stands best, the
> dynamics that should make the substrate a living thing worst. Five patterns:
> (1) the substrate can only forget — fourteen ticks of decay, zero
> reinforcement ever drained, and the strongest credit a single query can write
> is 17 times smaller than one tick of decay, 254 times at the median; (2)
> seventeen fields hold exactly one value across all 5,002 nodes and 94,490
> edges — the substrate keeps no memory of its own activity, and everything that
> reads from that history reads nothing; (3) the tier ladder is inverted in the
> weight range the substrate inhabits; (4) five mechanisms are wired without
> discriminating power (frame routing on hashed frames with no caller, damping
> and hop limits the shipped operator never reads, a saturation cap of 10,000
> against a maximum out-degree of 1,093, no activation threshold); (5) two
> unguarded read-modify-write cycles, no lock, no snapshot. Side finding: all
> 1,206 `raw_text_ref` pointers led into a deleted scratch directory.
> *Consequence.* What is missing is sensors, not insight: activation memory
> first (built the same day, PHX-1101), then α against λ, then renormalisation
> before tier modulation. The full table of 119 is the appendix.

*2026-08-31. Against `data/mesh-founding` (5,002 consolidated nodes, 94,490
edges, 1,206 chunks, 14 ticks) and the state of `main` after PHX-1097.*

## Why this page exists

Five times in recent weeks, while working on something else, I stumbled onto
a doctrine mechanism whose **input nobody writes**: `decay_tier`,
the activation threshold, `frame_consistency`, the frame-routing caller,
`fired_total`. Each time the find was an accident, and each time it got noted
wherever it turned up — in a docstring, a comment, a ticket.

The suspicion was that this is a pattern, not five accidents. This page
checks that systematically: for every mechanism the MESH doctrine prescribes,
does it run?

**What "runs" means here.** Implemented *and* reached from a real path
(`retrieve` / `ingest` / `tick` / a CLI command) *and* its inputs are
actually produced. Three separate questions, and each one can be answered
no while the others are answered yes:

- implemented, but no caller → **inert**
- called, but the input is constant across the whole substrate → **also
  inert**, because a branch that reads a constant value cannot discriminate
  anything
- not implemented, and not implementable, because an input is missing →
  **blocked**

A test that calls something does not make it alive.

**Method and its limits.** Five readers each took one doctrine area;
afterward, for every area, a second pass tried to **refute** every "does not
run" — looking for writers, looking for callers, finding the path that does
make it work after all. A false "this is inert" is the expensive error here:
it sends the next piece of work at something that already runs. Of
110 refutation attempts: **105 confirmed, 4 corrected upward, 1 corrected
downward**. The four corrections are in the list below.

The number 119 is a decomposition decision, not a natural constant — a
17-step tick counts here as 17 lines, a field as one. The ratio 9/119 is
therefore less telling than the patterns beneath it. I re-measured the
*patterns* myself, rather than taking them over.

## The inventory

| | MESH_SUBSTRATE | MESH_RETRIEVAL | MESH_IMPLEMENTATION | total |
|---|---|---|---|---|
| **runs** | 4 | 3 | 2 | **9** |
| partial | 6 | 2 | 16 | 24 |
| **inert** | 26 | 4 | 4 | **34** |
| **blocked** | 8 | 1 | 1 | **10** |
| absent | 25 | 2 | 15 | 42 |
| | 69 | 12 | 38 | **119** |

Retrieval stands best — it is also the only one that has been worked on for
months. The substrate's *dynamics* — the thing meant to make it a living
thing — stands worst.

---

## Five patterns

### 1. The substrate can only forget

This is the most serious finding, and I re-measured it myself.

Decay runs: 14 ticks, λ=0.05, `Δw = -λ·dt·w²`, and the effect is visible in
the substrate (weights 0.2802–0.9049, the mode at 0.3112 reproduces a
forward simulation over 14 ticks). Hebbian reinforcement — the counterpart —
is wired, all the way through to the tick, and **has never fired on this
mesh**: all 14 tick records in the audit log carry `delta_drained: 0`, and
the sidecar file is empty. Every one of the 94,490 weights is pure ingestion
plus decay.

That alone would just be "nobody set the flag." The real finding is the
**calibration**. Eight real queries with `hebbian=True` against the live
substrate wrote 512 deltas:

    strongest delta from one query      2.9 · 10⁻⁴
    median delta                        1.9 · 10⁻⁵
    one tick of decay (median weight)   4.8 · 10⁻³

**The strongest reinforcement a single query can give an edge is 17 times
smaller than one tick of forgetting. At the median, 254 times.** And the
tick decays *every* edge, while a query only touches the few it activates.

"Fire together, wire together" is doctrine's first of the five primitives.
It is built, it is reachable, and at the shipped parameters it cannot hold
anything against the shipped decay. α and λ were never measured against
each other.

On top of that: decay is **unconditional**. Doctrine says "edges that do
*not* fire weaken themselves"; `decay_edges_inplace` decays all of them, and
the tick applies it *after* the merge — an edge just reinforced decays along
with the rest in the same pass. A firing signal to exempt from it does not
exist anyway (see pattern 2).

### 2. Seventeen fields hold exactly one value across the whole substrate

Measured across all 5,002 consolidated nodes and all 94,490 edges:

| Field | Value everywhere | what doctrine intends it for |
|---|---|---|
| `fired_total`, `fired_recent` | 0 | tier promotion, replay, decay gating |
| `positive_feedback_total`, `negative_feedback_total`, `feedback_recent` | 0 | three-factor RL |
| `eligibility`, `feedback_modulated_strength` | 0.0 | eligibility traces, modulated plasticity |
| `decay_tier` | 0 | tiered decay |
| `frame_consistency` | 1.0 | frame routing |
| `consolidation_tier` | 1 | tier promotion, saturation budgets |
| `consolidation_history` | empty | age correction in the atrophy band |
| `structural_vector`, `temporal_vector` | None | sub-mesh matching, temporal proximity |
| `activation_entropy`, `node_potential_cache` | None | pathology symptoms, pruning |
| `is_anchor` | False | a separate anchor class (an `anchor_nodes` table exists nowhere) |
| `qids` | empty | doctrine's strongest identity signal |

These are not seventeen bugs. This is **one** finding: doctrine describes a
substrate with a memory of its own activity, and **that memory is kept
nowhere**. Everything that reads from it — tier promotion, Oneiros' replay
to protect the rare-but-important, Argus' pathology monitoring, RL's
eligibility traces — reads a history that nobody writes down.

`qids` is on this list for a different reason: the 130 Q-IDs that once
existed were removed because 127 of them were confabulated. That was the
right call. The consequence is that the strongest of doctrine's three
identity signals does not exist on this mesh at all — and
`_ensure_consolidated_indexes` can therefore never pass its completeness
check, and scans the node table for 836 ms on **every** opening of the
workspace.

### 3. The tier ladder is inverted where the substrate actually lives

Doctrine says: higher consolidation tiers carry **gentler** decay
exponents — chunks k=2, entities k≈1.5, hubs k≈1.2 — so that working terms
evaporate and core structure stays.

`decay_tier` is 0 on every edge, so k=2 always runs, and the other branches
are unreachable. That was already known (PHX-1095). What's new is what
happens if the field were honestly written. For `0 < w < 1`, `w^1.2 > w^2` —
a *smaller* exponent removes *more* absolute weight. At this substrate's
actual median weight (0.3112) and λ=0.05:

    k = 2    (chunk)      loss per tick    0.00484
    k = 1.5  (entity)                      0.00863
    k = 1.2  (hub)                         0.01226   ← 2.5× as much

And every weight in the mesh sits below 1, because `w_max = 1.0` holds it
there. **The documented tier modulation would make consolidated structure
evaporate faster than chunks.** Filling in the field would not be a repair;
it would be the reversal of the intended effect. The mechanism only makes
sense once weights are allowed to live above 1 — which is what the global
renormalisation would provide, and it does not exist (see below).

### 4. Wired, but without discriminating power

Five mechanisms actually run and still cannot accomplish anything:

- **Frame routing** is called from `retrieve.py:423` — but only when a
  `query_frame` is passed, and **no caller in `src/` or `scripts/` does
  that**: not the CLI, not the cockpit, not the benchmark, not the demo GIF.
  There is no flag for it. Worse: the mesh's frame vectors are a salted
  SHA-256 projection of the label (`vectorizer.py:_hash_projection`), i.e.
  4,977 distinct hashes, no epistemic stance. Routing on that would mask
  edges by a hash.
- **The damping factor** (doctrine: ≈0.5 as the stop condition) is read only
  in the `raw` and `degnorm` branches. The shipped operator is `ppr`, which
  never reads it — and `mesh ask` has no `--damping` at all.
- **The maximum hop count** (doctrine: 3, never above 5) likewise applies
  only to `raw`/`degnorm`. `ppr` runs 12 iterations, and `mesh ask --hops`
  is passed through into a branch the default never enters.
- **Saturation** runs on every tick and has never yet cut anything off: cap
  10,000 against a measured maximum out-degree of 1,093. The accompanying
  `w_max` clamp is just as ineffective (largest weight 0.9049).
- **The activation threshold** (doctrine: ≈0.05 per node) does not exist in
  the code at all; Constellation membership is `v > 0.0` plus a budget.
  Building it in would not be a repair either — under PPR, a median of 9 of
  50 nodes reach that value (PHX-1095).

### 5. Two writers, no lock, no snapshot

Doctrine requires snapshot isolation for reads, buffered writes, and a
**serialised** Oneiros with exactly one writer per substrate.

None of it holds. `_READ_CONSISTENCY = timedelta(0)` means "re-check on
every operation" — the exact opposite of a pinned snapshot, and deliberately
so (PHX-1093). `checkout`, `restore` and `as_of` do not occur anywhere in the
repo, so a pass *could not* pin even if it wanted to. And there is no lock:
neither `filelock` nor `flock` nor a lockfile anywhere in `src/`.

By now there are **two** unprotected read-modify-write cycles across the
whole substrate — `run_minimal_tick` and, as of today, `run_consolidation`,
reachable simultaneously from different processes. Consolidation noted this
in its own docstring ("ordering is the only protection there is"), but
doctrine requires serialisation, and there is none.

---

## A side finding that deserves its own attention

**The substrate's only pointer back to its sources is dead.** All 1,206
chunk nodes carry a `raw_text_ref` of the form

    /private/tmp/claude-501/…/scratchpad/fullread/batch_00.txt#p1

— 13 different files in a session scratchpad, of which **not a single one
still exists**. `SourceProvenance.source_identifier` carries the same dead
path.

Doctrine names `raw_text_ref` explicitly as what lets the immune system or
an Oneiros tick re-derive a chunk off the hot path. On this mesh that is
impossible.

PHX-1084 fixed exactly this problem for the **source anchors** and corrected
ingestion going forward (`source_identifier` is now `gutenberg_{book_id}`).
The chunk layer of the existing mesh was never backfilled. So it is no
longer a code bug, but an uncleaned data artefact — on the mesh the demo
shows.

---

## What follows from this

Doctrine is not wrong. What's missing is not insight but **sensors**:
several of the described organs are connected to sensing elements that were
never built in. That is why the order of the next work is not arbitrary.

**Activation memory first.** Write `fired_total`, `fired_recent`,
`last_fired_at` back on the read path. That is little code and unlocks four
mechanisms at once: tier promotion, gating-capable decay, Oneiros' replay,
and the eligibility traces. Without it, pathology monitoring and therapy are
instruments meant to observe something that is never recorded.

**Then α against λ.** Leaving Hebbian reinforcement 17 to 254 times below
decay while claiming "the substrate learns from use" is the kind of gap this
repo would otherwise write up immediately. Either raise α, lower λ, or
restrict decay to unfired edges — but measured, not guessed.

**And renormalisation before tier modulation.** As long as every weight sits
below 1, the documented tier ladder reverses its own intent. Global
homeostatic renormalisation is the mechanism that lifts weights into a range
where the ladder does the right thing — so it comes first.

**Not next:** splits, pathology, therapy. All three read from the activation
history.

---

## Addendum, the same day

**PHX-1101 is built**, and with it the first entry from pattern 2 is
cleared: the read path now records which nodes made it into the working
set, ingestion records every reference to an already-existing node, and the
tick folds both in. `fired_total` went, on a copy of the founding mesh over
47 queries, **from one distinct value to 32** — Zeus 45, Theogony 43, the
source anchor 41, Phoebus Apollo 40.

The record above stands as it was measured. It is the state of August 31,
and an inventory that retroactively corrects itself is not one.

What that unlocks: tier promotion now has an input, decay could be
restricted to unfired edges (the doctrine-faithful answer to PHX-1102),
Oneiros' replay has a signal, and the eligibility traces have a basis. None
of that is thereby built — only no longer blocked.

**PHX-1102, the day after:** pattern 1 is half cleared. Decay now spares
what has fired — the rule from MESH_SUBSTRATE §2, measured as the one knob
of the three where used items hold (0.594 against 0.359 under the shipped
decay). The substrate can no longer *only* forget. Whether it *learns* is
not visible to retrieval on this mesh — ten rounds, no gold hit moved — and
why is in [`hebbian_calibration.md`](hebbian_calibration.md) and PHX-1104.

What this record means for the vision — which verbs of *"the mesh is
alive"* hold true today, which README sentences no longer do, and what
Gen 1 honestly promises — is in
[`what_gen1_promises.md`](what_gen1_promises.md).

## Appendix — the complete record

By doctrine document, and within that by status. Every line carries the
shortest true justification, mostly with `datei:zeile`. It is cut to 230
characters — the record should stay readable, and anyone who doubts a line
finds the evidence faster in the code than in a longer quote.

### MESH_SUBSTRATE.md — 69 mechanisms (4 runs · 6 partial · 26 inert · 8 blocked · 25 absent)


**runs**

- **description (ConsolidatedNode)** — Written at ingest for every node (kadmos_v2.py:385 via `_entity_description`, source_anchor.py:41-45) and read on real paths: it is the Constellation's display name (retrieval/constellation.py:64-71, 176) and it feeds the `consoli…
- **is_source_anchor (source-anchor entity class)** — Written by ingestion/source_anchor.py:36; live it partitions the mesh 1,219 anchors / 3,783 content nodes. Read on real paths and it changes behaviour: constellation.py:142 splits activated nodes into a separate anchor budget (`_P…
- **relation_descriptor (short relation label)** — Written on every edge; non-null on 94,490/94,490 live edges with 2,680 distinct values. Read on real paths: it is part of the edge identity used for dedup and delta merging (storage/edges.py:237, 490-498, 235-236 — keying by node …
- **tags (discriminating keyword cloud)** — Written at ingest (kadmos_v2.py:386 via `_concept_tags`, :523; source_anchor.py:46) and genuinely differentiating live: 1-7 tags per node, 7 distinct lengths across 5,002 nodes. Read on real paths — the tag-match linking signal (i…

**partial**

- **Agent-driven cleanup — Deduplication** — The *application* half exists and has run (consolidation.py:803-969; 48 clusters merged on data/mesh-s5-work, union of edges with weight-summing at :645-649, capped by `enforce_saturation` at :914, absorbed ids recorded at :933-93…
- **Hebbian update (w ← w + α·fire(i)·fire(j))** — Nothing structural — an opt-in flag nobody passes, plus an α/λ calibration that has never been measured against each other.
- **Oneiros operation B — Consolidation, Tier 0 → Tier 1** — Q-ID inheritance is blocked by there being no Q-IDs on the substrate at all.
- **Super-linear decay (dw/dt = -λ·w^k, k=2)** — Live and differentiating in its core: src/theogony/mesh/storage/edges.py:273-299 implements Δw = -λ·dt·w^k, called on every tick at src/theogony/mesh/runtime/oneiros_tick.py:413, driven by the real CLI `theogony mesh tick` (src/th…
- **Tick steps 8/9 — Compute and apply saturation evictions** — Called on every tick: oneiros_tick.py:414 → edges.py:310-334. Three documented parts are missing and the docstring says so (edges.py:315-319): no per-tier cap indexing, no companion weight-sum cap, no admission rule. Step 9's "app…
- **description_vector as a distinct identity-matching surface** — The linking signal itself IS live and load-bearing: src/theogony/mesh/ingestion/linker.py:114-127 scores it and the founding-mesh audit log records 7,281 `mesh_ingest_link_decision` rows with signals description=3,694, tag=633, em…

**inert**

- **ChunkNode.raw_text_ref (off-hot-path pointer for re-derivation)** — Written once, src/theogony/mesh/ingestion/kadmos_v2.py:322. `grep -rn raw_text_ref src/ scripts/ tests/` returns only schemas.py:56 and that line — no reader at all, including inside `run_consolidation`, which regenerates descript…
- **ChunkNode.source (SourceProvenance — immune-system anchor)** — Written at src/theogony/mesh/ingestion/kadmos_v2.py:317-321. No reader anywhere in src/, scripts/ or tests/ — nothing loads a ChunkNode and inspects `.source` (the store's only chunk reader is `get_chunk`, storage/nodes.py:237-242…
- **Edge.creation_context (asserted relation vs observed adjacency)** — Written on every edge at 11 sites in kadmos_v2.py (:335, :348, :427, :444, :480, :506, :546, :558, :578, :630, :658) and by the seed importer; live it is non-null on 94,490/94,490 edges with 8 distinct values (kadmos_paragraph_den…
- **Edge.decay_tier** — Independently confirmed live (already known): 0 on 94,490/94,490 edges, min = max = 0. Adding the upstream cause measured in my area: the derivation the code considers and rejects (storage/edges.py:284-293) is blocked because `Con…
- **Edge.description (free-text relation rationale)** — One writer, src/theogony/mesh/ingestion/kadmos_v2.py:470, which copies `relation.rationale`. That field defaults to "" (ingestion/reading_schemas.py:68) and the reading prompt never asks for it — the relations section of the syste…
- **Edge.eligibility (decaying recent-firing trace, credit assignment)** — The three-factor RL path as a whole — nothing propagates a firing trace or a reward.
- **Edge.feedback_modulated_strength (lifetime feedback audit)** — Same three hits and nothing more: schemas.py:113, storage/edges.py:50 (column), storage/edges.py:579 (serialisation). No writer, no reader, no test. Live: 0.0 on 94,490/94,490 edges.
- **Edge.frame_consistency** — The same missing frame encoder that leaves `frame_vector` a hash and `query_frame` unproduced.
- **Edge.last_fired_at (edge freshness / "edges that are not fired weaken")** — Set at creation and never advanced: `merge_edge_deltas` reinforces an existing edge with `cur.model_copy(update={"weight": nw})` only (storage/edges.py:254-259), leaving last_fired_at untouched, and `decay_edges_inplace` takes a u…
- **Edge.pids (Wikidata property identifiers)** — Genuinely written on two paths — kadmos_v2.py:476-480 at extraction and `_backfill_relation_pids` on every tick (oneiros_tick.py:86-91) — and 1,237 of 94,490 live edges carry one. But nothing reads the stored value. The one consum…
- **Edge.relation_kind (broader relation category)** — Written on every edge (kadmos_v2.py:333, 346, 425, 442, 468, 504, 544, 556, 576, 628, 656) and non-null on 94,490/94,490 live edges with 10 distinct values (co_occurrence 73,455; semantic 8,375; attribution 4,514; hierarchy 4,237;…
- **Hebbian edge creation between co-firing non-neighbours** — The create branch exists at src/theogony/mesh/storage/edges.py:260-269 (the `else` of the key lookup — a brand-new Edge with born_at/last_fired_at = now). It is unreachable from the production write path: the only producer of delt…
- **Node last_fired_at / node firing clock** — Set to creation time at every write site (kadmos_v2:314, linker.py:212, source_anchor.py:34, importer.py:180) and never advanced afterwards — no code path updates a node row on firing. The single non-write reference is `max(n.last…
- **Saturation — count cap per node** — Implemented and called: src/theogony/mesh/storage/edges.py:310-334, invoked every tick at src/theogony/mesh/runtime/oneiros_tick.py:414 with DEFAULT_MAX_OUT_DEGREE = 10,000 (edges.py:307), and again inside consolidation at src/the…
- **Three-factor reward modulation (1 + β · feedback)** — A consumer-supplied feedback value; MESH_RETRIEVAL's rater distinct from the consumer does not exist.
- **Tier-modulated decay (k=2 / 1.5 / 1.2 / 1 by tier)** — A writer for Edge.decay_tier (none in src/); node tiers are constant too (consolidation_tier == 1 on all 5,002 nodes), so a derivation would assign one constant; and correctness additionally requires §6 renormalisation to lift wei…
- **consolidation_history (when each tier promotion happened)** — Declared src/theogony/mesh/schemas.py:71. One writer, src/theogony/mesh/runtime/consolidation.py:591, and its own comment concedes the field's documented meaning is unavailable: "the substrate has no tier promotion to record (noth…
- **consolidation_tier ("1, 2, 3 — earned via Oneiros")** — Written as the literal `1` at all three creation sites (linker.py:213, source_anchor.py:35, seeds/wikidata5m/importer.py:181). Nothing ever increments it — no promotion code exists anywhere in src/. Live: 1 on 5,002/5,002 nodes. R…
- **description_generated_at / description_source_chunks (regeneration audit trail)** — Written at exactly one place, src/theogony/mesh/runtime/consolidation.py:893-899, inside the LLM-describer branch of `run_consolidation`. No reader anywhere in src/, scripts/ or tests/. Live: None and [] on 5,002/5,002 nodes — so …
- **frame_vector (both tiers) — epistemic-frame embedding** — No frame encoder exists. `query_frame` has no producer, and even with one the node side would be hashed label text.
- **is_candidate (entity-candidate flag; flips to False on convergence)** — Written True unconditionally for every node the linker creates (src/theogony/mesh/ingestion/linker.py:214) and left False on source anchors (source_anchor.py has no is_candidate) and on seeded nodes (seeds/wikidata5m/importer.py:1…
- **last_fired_at as an edge firing record** — `last_fired_at` is declared on Edge (src/theogony/mesh/schemas.py:107) and persisted (src/theogony/mesh/storage/edges.py:52, 581), but reinforcement never updates it: merge_edge_deltas strengthens an existing edge with `cur.model_…
- **node_potential_cache** — Declared src/theogony/mesh/schemas.py:92. Only occurrence outside the declaration is src/theogony/mesh/runtime/consolidation.py:593, setting it to `None`. Live: None on 5,002/5,002 nodes. The quantity is real and used, but compute…
- **positive_feedback_total / negative_feedback_total / feedback_recent** — Nothing supplies a feedback signal. `feedback` appears nowhere on the retrieval path; the CLI has no way to return a reward for a Constellation.
- **qids (Q-ID identity anchor, signal 1 of eager linking)** — A trustworthy entity linker. The lookup path (linker.py:311-333) is fully built and would work the moment a seeded or authoritative Q-ID existed; nothing on the reading path produces one.
- **source_url (machine-clean anchor on source-anchor entities)** — Written at src/theogony/mesh/ingestion/source_anchor.py:37. No reader: `grep -rn source_url src/theogony/mesh/` returns only the declaration (schemas.py:75) and that writer; the hits in cockpit/mesh_explorer.py:201 and reporting/m…

**blocked**

- **Oneiros operation — Tier promotion (Tier 1 → 2 → 3)** — `fired_total`/`fired_recent` have no writer, and Argus's pathology checks are unbuilt — three of the four promotion gates have no input.
- **Saturation — Σ weight cap per node (S, 5·S, 20·S, 100·S)** — S, the substrate-wide weight unit, which doctrine defines via the §6 renormalisation target — and no renormalisation exists to set it.
- **Symptom 2 — Activation hysteresis** — Per-node activation history: `fired_total`/`fired_recent` have no writer, and there is no activation log.
- **Symptom 3 — Context promiscuity** — `activation_entropy` has no producer, and the per-query context diversity it would be computed from is not recorded.
- **Symptom 4 — Refutation absorption** — No refutation/veridicality marker on chunks, and no per-insertion Hebbian record to compare a frame against.
- **Symptom 5 — Saturation lockout for legitimate new input** — There is no admission barrier, so no rejection events exist to sample.
- **structural_vector (ConsolidatedNode)** — Nothing in the repo computes a topology embedding — no Node2Vec/GraphSAGE anywhere in src/. The tick (src/theogony/mesh/runtime/oneiros_tick.py:398-415) has no phase that would produce one.
- **temporal_vector (ConsolidatedNode)** — No temporal-anchor extraction exists on the reading path; nothing produces a date/interval representation for a node.

**absent**

- **Agent-driven cleanup — Contradiction resolution** — `grep -rni "contradict" src/theogony/mesh/` returns nothing. No `ContradictionFinding` type, no `CONTRADICTS` edge kind, no writer. Measured on the live mesh: `relation_kind` takes 10 values across 94,490 edges — co_occurrence 73,…
- **Agent-driven cleanup — False-information removal** — No `RemovalProposal` type in src/ (grep). No removal path: MeshNodeStore exposes only `replace_all_consolidated` (nodes.py:336), no per-node removal with an evidence trail. No removal audit action exists — the founding mesh's audi…
- **Agent-driven cleanup — Redundancy compression** — No `RedundancyProposal` type in src/ (grep). The nearest built thing, consolidation.py, is a different operation: it merges Tier-1 entity candidates by shared capitalised name (consolidation.py:298-309), not "many chunks making es…
- **Anchor-node class (pure index nodes)** — `is_anchor` is declared on ConsolidatedNode (schemas.py:73) and is `False` on all 5,002 founding-mesh nodes (measured); `grep -rn "is_anchor" src/` finds only the declaration — no writer. The three per-observation fields doctrine …
- **Atrophied nodes lose firing privileges during Spreading Activation** — No propagation gate on node potential or atrophy exists. src/theogony/mesh/runtime/spreading.py (49 lines, single function `spreading_activation` at line 17) has no threshold or mask. src/theogony/mesh/retrieval/propagation.py has…
- **Atrophy (node marked atrophied, not removed)** — There is no atrophy anywhere in the repository: `grep -rn "atroph" --include="*.py" .` returns **zero matches** across src/, tests/ and scripts/. No `atrophied` field on ConsolidatedNode (src/theogony/mesh/schemas.py:57-95) or on …
- **Global homeostatic renormalisation** — Nothing external — but a correct implementation must be landed together with a rethink of w_max, or the first correction destroys every weight distinction in the substrate.
- **Healthy band [μ − σ, μ + σ] over node potential, with age correction** — A specification that survives a right-skewed potential distribution; plus consolidation cycles for the age correction, which never run.
- **Oneiros operation A — Replay (bridge-biased edge firing)** — No bridge metric exists in src/ — `grep -rni "bridge" src/theogony/mesh/` hits only eval/qa_retrieval.py, which uses "entity-bridge" to mean a co-occurrence edge in a benchmark ablation, not a topological bridge score. The one rep…
- **Pruning under resource pressure (the pruner)** — Two inputs: an operator resource-ceiling signal (nothing produces one), and the set of atrophied nodes the pruner sorts first (atrophy does not exist).
- **Saturation admission rule (new edge must beat the weakest incumbent)** — No rejection path exists. merge_edge_deltas creates or strengthens unconditionally (src/theogony/mesh/storage/edges.py:256-269) with no reference to the target node's incumbent edges, and enforce_saturation runs afterwards (oneiro…
- **Saturation caps indexed by tier** — Node tier promotion (Tier 0→1→2→3), which docs/MESH_MIGRATION_PLAN.md:315 records as not built and blocked on fired_total/fired_recent having no writer.
- **Symptom 1 — Internal/external edge asymmetry** — No implementation and no caller: nothing in src/ computes an intra-region vs. cross-region edge ratio, and there is no region abstraction to compute it over (grep for pathology/region sampling returns only oneiros_tick.py:61-62's …
- **Therapy Stage 1 — Activation temperature** — Spreading Activation is deterministic SpMV with no sampling: src/theogony/mesh/runtime/spreading.py:17-49 (`x ← damping · Aᵀ · x`) and src/theogony/mesh/retrieval/propagation.py:111 `propagate`. `grep -rniE "boltzmann|softmax|temp…
- **Therapy Stage 2 — Dominance penalty** — A region's share of total activation is not tracked; `fired_total`/`fired_recent` have no writer.
- **Therapy Stage 3 — Forced refutation re-injection** — No refutation framing, no signed Hebbian update, and no Argus-to-mesh channel.
- **Therapy Stage 4 — Saturation demolition** — No implementation: nothing in src/ halves or zeroes a region's strongest internal edges. There is also no place to record the audit doctrine makes binding — the audit log's six live actions are ingest and tick only, and there is n…
- **Therapy Stage 5 — Quarantine / split** — No split implementation, no region abstraction, and no cross-tick confirmation state.
- **Tick step 12 — Compute pathology samples** — oneiros_tick.py:61-62 `stub_pathology_phase` raises; no caller. `grep -rni "pathology|mind.lock|hysteresis|promiscuity" src/` returns only that stub and two docstring mentions (oneiros_tick.py:4, consolidation.py:29). No sampler, …
- **Tick step 13 — Apply therapy actions** — oneiros_tick.py:65-66 `stub_therapy_phase` raises; no caller. No escalation state, no stage thresholds, no Mendel-risk logging anywhere in src/.
- **Tick step 4 — Apply renormalisation (conditional on drift threshold)** — `grep -rn "renormal" src/ scripts/ tests/` returns exactly one hit — src/theogony/mesh/runtime/consolidation.py:29, a docstring listing renormalisation among the things S5 has *not* built. There is no implementation, no stub, and …
- **Tick step 5 — Apply pending agent-driven cleanup actions** — Both ends are missing: no agent emits a substrate finding, and no table stores one.
- **Tick steps 10/11 — Compute and apply sub-node splits** — oneiros_tick.py:57-58 `stub_split_phase` raises `NotImplementedError`; grep across the repo finds no caller. There is no split code at all: no cluster detection over a hub's outgoing edges, no `w_HS = Σ w_i`, no `w_i / (1 - p_i)`,…
- **activation_entropy (spiral / context-promiscuity signal)** — Declared src/theogony/mesh/schemas.py:91. The only occurrence outside the declaration in all of src/ and scripts/ is src/theogony/mesh/runtime/consolidation.py:594, which sets it to `None` (a cache invalidation of a value never co…
- **is_anchor (anchor-node class: no Hebbian update, no decay, no split)** — `grep -rnw is_anchor src/ scripts/ tests/` returns exactly one hit in the whole repository: the declaration at src/theogony/mesh/schemas.py:73. (The tests/mesh/test_constellation_anchor_budget.py hits are a local variable of that …

### MESH_RETRIEVAL.md — 12 mechanisms (3 runs · 2 partial · 4 inert · 1 blocked · 2 absent)


**runs**

- **Diversified injection A — Maximum Marginal Relevance** — `mmr_order` (src/theogony/mesh/retrieval/diversified.py:49-82) is called by `select_seeds` (diversified.py:132), which is called by `retrieve` (retrieve.py:404-412) on all four real paths above. λ = 0.6 exactly as doctrine specifi…
- **Diversified injection B — weight-class stratification** — `class_seats` and `WeightClasses` (src/theogony/mesh/stratification.py:98-183 and :65-95) are called from diversified.py:143, reached from retrieve.py:404-412, with global class boundaries supplied by `MeshRuntime.weight_classes()…
- **Spreading Activation as the universal retrieval primitive** — `Propagator.propagate` (src/theogony/mesh/retrieval/propagation.py:111-163) is called at src/theogony/mesh/retrieval/retrieve.py:433, and `retrieve()` is reached from four real paths: `theogony mesh ask` (src/theogony/mesh/cli.py:…

**partial**

- **"Diversified injection (A + B) is *always* on" / nearest-neighbour seeding forbidden** — MMR and stratification are live (above), but they do not cover the seed set. `_name_anchor_seeds` (retrieve.py:211-293) looks up capitalised spans by label and injects up to 8 nodes at a flat weight of **1.0** (retrieve.py:289); t…
- **The modulated Hebbian rule (three-factor plasticity)** — a feedback signal `f_target` (no channel exists — see "Sources of feedback") and a per-edge propagation trace `s_ij` that `propagate` does not produce.

**inert**

- **Feedback storage — per-edge `feedback_modulated_strength`** — Declared on `Edge` at src/theogony/mesh/schemas.py:113, given an Arrow column at src/theogony/mesh/storage/edges.py:50, and persisted from the model default at edges.py:579. `grep -rn feedback_modulated_strength` over src/ returns…
- **Feedback storage — per-node `positive_feedback_total` / `negative_feedback_total` / `feedback_recent`** — All three are declared on `ConsolidatedNode` (src/theogony/mesh/schemas.py:93-95). There is no writer anywhere in src/. The single reader is the consolidation merge, which sums them into the merged node (src/theogony/mesh/runtime/…
- **Frame routing during Spreading Activation (frame-routed activation / masked SpMV)** — a frame encoder producing epistemic frames rather than a hash projection, plus a `query_frame` on some real caller (there is no flag, API parameter, or config to set one).
- **Relation-conditioned masked hop (`Propagator.relation_masked_hop`)** — a query-relation input on the retrieval API and a relation-restricted adjacency builder — neither exists anywhere in src/.

**blocked**

- **Eligibility traces (multi-hop credit assignment)** — the per-edge propagation strength `s_ij(t)` — `Propagator.propagate` returns node activations only, so there is nothing to accumulate a trace from.

**absent**

- **Diversified injection C — sub-mesh injection (structural matching)** — Nothing exists. `grep -rni 'weisfeiler|wl_hash|submesh|sub_mesh|region_scor'` over src/ and scripts/ returns zero implementation hits — the only match in the repo is a disclaimer at scripts/mesh_relation_retrieval.py:11 ("This is …
- **Sources of feedback (LLM self-rating, downstream task success, explicit user rating, implicit signals)** — None of the four channels exists. **LLM self-rating** (doctrine's default, "every activation"): `grep -rni 'self_rating|self-rating|rater|f_target|reward'` over src/theogony/mesh/ returns one hit — the honesty note at retrieve.py:…

### MESH_IMPLEMENTATION.md — 38 mechanisms (2 runs · 16 partial · 4 inert · 1 blocked · 15 absent)


**runs**

- **Diversified seeding — MMR over per-vector ANN results plus weight-class stratification** — select_seeds runs on every retrieval (src/theogony/mesh/retrieval/retrieve.py:404-412), consuming real ANN hits from search_consolidated_by_vector (:361). MMR is genuinely implemented (diversified.py:49-82) and class seats are all…
- **Warm tier — LanceDB tables as source of truth** — MeshNodeStore creates/opens chunk_nodes and consolidated_nodes (src/theogony/mesh/storage/nodes.py:173-200); EdgeStore opens mesh_edges / edge_metadata / edge_dedup_index (src/theogony/mesh/storage/edges.py:466-479). Live on data/…

**partial**

- **Audit ledger — a record for every non-trivial Oneiros operation** — The ledger is real, append-only and reached from ingest and tick (src/theogony/mesh/storage/audit.py; oneiros_tick.py:454). But the actions it actually holds on data/mesh-founding are only mesh_ingest_link_decision (7,281), mesh_i…
- **CSR holds (source, target, weight, decay_tier, frame_consistency)** — build_csr_from_columns (src/theogony/mesh/storage/edges.py:337-417) takes weight and frame_consistency and computes weight * frame (:408); decay_tier is not passed at all. Measured across all 94,490 edges of data/mesh-founding: fr…
- **Cold tier — historical Lance versions, queryable on demand** — The audit-trail half is live (mesh_audit, 13,883 rows). The versioned-snapshot half is deliberately destroyed: _DEFAULT_VERSION_RETENTION = timedelta(0) (src/theogony/mesh/storage/nodes.py:95) and every tick calls prune_history on…
- **Damping factor (default ≈ 0.5) as the propagation stop condition** — DEFAULT_DAMPING = 0.5 (src/theogony/mesh/retrieval/defaults.py:66) and it is applied in the raw and degnorm branches (propagation.py:143, :152). But the shipped default operator is ppr (defaults.py:61-62, retrieve.py:305), whose b…
- **Delta buffer: lock-free append, single batched flush, bounded size** — None of the three properties holds. append_hebbian_delta takes a global threading.Lock and opens the sidecar file once per delta inside it (src/theogony/mesh/storage/edges.py:139-145) — 64 opens per query at the default hebbian_ma…
- **Forbidden: reads that mutate the version they read from** — Opening the substrate for reading performs writes and full scans. MeshNodeStore.__init__ calls _ensure_consolidated_indexes() (src/theogony/mesh/storage/nodes.py:216, body :297-320), which adds rows; EdgeStore.__init__ calls _ensu…
- **Lance edge-metadata table kept off the SpMV hot path** — The table exists and is live (94,490 rows). Both of its doctrinal properties fail. (a) 'Edges that are pure Hebbian co-firings with no descriptor are not in this table ... typically 10-30% of edges' — on data/mesh-founding the met…
- **Maximum hop count (default 3, never above 5 for production queries)** — hops=3 is honoured for raw/degnorm (defaults.py:65, propagation.py:139, :148). The shipped default operator is ppr with DEFAULT_PPR_ITERS = 12 (defaults.py:62), executed as 12 propagation iterations (propagation.py:157-162) — abov…
- **Nodes — two Lance tables with per-vector HNSW indices** — Two tables exist and are live. The indices are not HNSW: ensure_indices builds IVF_PQ (src/theogony/mesh/storage/nodes.py:449-456) plus a BTree on id (:436). Coverage is one table only — ensure_indices touches consolidated_nodes a…
- **Tick step 15 — Write the new audit-ledger entries** — One audit row per tick is written and it is real (oneiros_tick.py:454-467; 14 rows in data/mesh-founding). But it is flat: edges_before/after, delta_drained, lambda, dt, max_out_degree, index status, versions_pruned, pids_backfill…
- **Tick step 16 — Build the new stable CSR tensor** — The tick does the opposite: it *invalidates* the CSR cache twice (oneiros_tick.py:431 and :449) and never calls `rebuild_csr`. The CSR is rebuilt lazily by the next reader (oneiros_tick.py:303-318), so the first query after a tick…
- **Tick step 17 — Publish the new Lance version atomically** — `replace_all_edges` (edges.py:754-784) is atomic per table only, and its own docstring says so: "this is atomic *per table*, not across the three. Lance gives no cross-table transaction" (edges.py:769-773). `current_lance_version(…
- **Tick step 3 — Apply decay (super-linear, tier-modulated)** — Called on every tick: oneiros_tick.py:413 → src/theogony/mesh/storage/edges.py:273-298. The super-linear part runs and is the only thing measurably changing edges (audit rows show weight loss across all 14 ticks). The tier-modulat…
- **Tick step 6 — Compute consolidation candidates** — The co-firing history the doctrinal candidate rule keys on: `fired_total`/`fired_recent` have no writer.
- **Tick step 7 — Apply consolidations** — Implemented (consolidation.py:803-969), reached from a real path (scripts/mesh_consolidate.py:83), and it has actually run: data/mesh-s5-work's audit log carries 1 `mesh_oneiros_consolidation` row, and 48 of its 4,934 consolidated…
- **Write the new Lance version atomically; publish the pointer for subsequent readers** — replace_all_edges is atomic per table via mode='overwrite' (src/theogony/mesh/storage/edges.py:782-790), and its own docstring says plainly that it is not atomic across the three: 'a failure between the first and second overwrite …

**inert**

- **Append-only COO delta buffer — the Hebbian write path** — Implemented (src/theogony/mesh/storage/edges.py:88-158) and drained by the tick (oneiros_tick.py:409). Its only producer is append_hebbian_deltas (retrieve.py:98-103), reachable only behind the opt-in --hebbian flag (cli.py:518-52…
- **Frame routing — per-frame mask on the active edges, (A * mask) · X** — build_frame_routed_csr is implemented (src/theogony/mesh/retrieval/frame_routing.py:70-101) and has exactly one caller, retrieve() (retrieve.py:423), gated on a non-zero query_frame (retrieve.py:421). Nothing passes one: `mesh ask…
- **Saturation eviction (Oneiros step 8-9)** — enforce_saturation is called on every tick (src/theogony/mesh/runtime/oneiros_tick.py:414) and is implemented (edges.py:310-334). But DEFAULT_MAX_OUT_DEGREE = 10_000 (edges.py:307) and the largest out-degree on data/mesh-founding …
- **Tick step 2 — Drain the delta buffer** — Implemented and called: oneiros_tick.py:409 `drained = self.edges.delta.drain()`, merged at :412. A producer exists behind an opt-in flag — src/theogony/mesh/cli.py:518-526 `mesh ask --hebbian`, default `False` — reaching src/theo…

**blocked**

- **Automatic, statistical Hot↔Warm tier movement** — fired_recent / fired_total — declared on both node schemas, never written by any path

**absent**

- **Agent-driven cleanup queue drained by the tick (step 5)** — Of the four record types doctrine names, only MergeProposal exists (src/theogony/mesh/runtime/consolidation.py:140); RemovalProposal, ContradictionFinding and RedundancyProposal have zero definitions in src/. MergeProposal is prod…
- **Anchor nodes — separate anchor_nodes Lance table plus inverted anchor index** — Grep over src/, scripts/, tests/ for anchor_nodes and anchor_index returns exactly one hit — the doctrine line itself. No temporal_anchor or geo_anchor field exists anywhere in src/. The live workspace data/mesh-founding/lance con…
- **Global renormalisation (step 4, and the per-tick operations table)** — No implementation anywhere in src/. Grep for renormalis / renormaliz / drift_threshold / global_renorm returns one hit, a docstring in src/theogony/mesh/runtime/consolidation.py:29 listing it among the things not built. run_minima…
- **Hot tier — working-set nodes as dense PyTorch tensors in RAM/VRAM** — No working-set structure exists. The only resident tensor is a whole-graph CSR cache on the runtime (src/theogony/mesh/runtime/oneiros_tick.py:162, built at :303-318 from the full Lance edge table) — not a subset, not per-node, ne…
- **K concurrent Spreading Activation queries fold into one batched SpMM** — Every propagation multiplies a single column. _spmv does x.unsqueeze(1) (src/theogony/mesh/retrieval/propagation.py:41); same shape in runtime/spreading.py:47, eval/link_prediction.py:188, eval/qa_retrieval.py:527. No (N, K) activ…
- **Minimum-activation threshold (default ≈ 0.05) per node** — No threshold exists on any propagation or assembly path. Constellation membership is `v > 0.0` cut by top_k (src/theogony/mesh/retrieval/constellation.py:128-134), and the module states it outright at :116-127, with the measuremen…
- **Oneiros — serialised, single-writer per substrate instance** — No lock, lease or lockfile exists: grep over src/ for filelock, FileLock, flock, lockfile, O_EXCL returns nothing. The only locks in the mesh package are EdgeDeltaBuffer._lock (edges.py:103) and an embedder load lock. run_minimal_…
- **Pruning trigger — RAM / p95-latency / GPU thresholds firing an immediate pruner** — Grep across the repo for prune_ram_threshold, prune_latency_threshold and prune_gpu_threshold returns hits only in the doctrine file. No resource-pressure pruner exists. The similarly-named prune_history (nodes.py:484, edges.py:63…
- **Reads — snapshot isolation, a Lance version pinned per Spreading Activation pass** — _READ_CONSISTENCY = timedelta(0) (src/theogony/mesh/runtime/oneiros_tick.py:127) is passed to both lancedb.connect calls (:149, :192). Zero means 're-check the latest version on every operation' — the opposite of pinning. The comm…
- **Refresh node_potential_cache and activation_entropy for all touched nodes (step 14)** — No writer exists. Measured on data/mesh-founding: node_potential_cache is None on all 5,002 consolidated nodes and activation_entropy is None on all 5,002. run_minimal_tick has no such phase (oneiros_tick.py:398-484). One half has…
- **Stable CSR sparse tensor built by Oneiros at the end of each tick** — run_minimal_tick (src/theogony/mesh/runtime/oneiros_tick.py:398-484) never builds a CSR. It calls invalidate_csr_cache() (:431, :449) and stops. Every reader rebuilds it from the row-per-edge Lance table instead (EdgeStore.csr_fro…
- **Tick frequency — operator-configurable schedule** — There is no scheduler, daemon, interval setting or cron entry anywhere. run_minimal_tick has exactly one non-test caller: the `theogony mesh tick` CLI command (src/theogony/mesh/cli.py:232). Grep for schedule/cron/interval/daemon …
- **Tick step 1 — Pin the input snapshot** — src/theogony/mesh/runtime/oneiros_tick.py:408-414 — the tick reads live tables (`count_rows`, `delta.drain`, `load_all_edges`) with no version pin. src/theogony/mesh/storage/nodes.py:87-88 states outright that "nothing in this cod…
- **Tick step 14 — Refresh node_potential_cache and activation_entropy** — Both fields exist on the schema (src/theogony/mesh/schemas.py:91-92) and are `None` on all 5,002 consolidated nodes in data/mesh-founding (measured). run_minimal_tick has no refresh phase. The only writes in src/ set them to `None…
- **consolidation_tier column partitioning consolidated_nodes; counters/timestamps/qids/description as typed columns** — The Lance schema is id, payload_json, semantic_vector, frame_vector, description_vector (src/theogony/mesh/storage/nodes.py:186-193) — verified against the live table. consolidation_tier, fired_total, born_at, qids, description, i…
