# The Plan from the Vision — September 2026

> **Abstract.** The original vision, sentence by sentence, held against
> what this repository has measured: a ledger of 620 claims
> (`vision_claims_ledger.json`), 258 of them load-bearing — 171 confirmed, 170
> partly, 61 refuted. *Seven verbs.* The substrate reads (statelessly, per
> paragraph — not yet "like a mind"), activates (confirmed: +0.102 recall@5 over
> kNN on held-out 2WikiMultihopQA), learns from use (holds what it uses; on
> 2Wiki +1.3 on used and −1.5 on held-out questions), dreams (refuted as a
> process: no scheduler, and the +34.8% figure is an in-memory simulation),
> heals (no), grows where it is looked at (Gen-1 skeleton only), thinks inside
> (blocked on GPU, not one measurement). *The finding that sets the order.* Five
> of the vision's non-negotiables fail at the data model, not for lack of code:
> nowhere in the mesh can a contradiction be represented, and the frame vector
> that was meant to carry epistemic stance is a salted hash of the label. *Four
> tracks, with results.* A, renormalisation (PHX-1106): displacement removed, a
> robust gain from use not shown. B, the memory of contradiction (PHX-1107):
> both sides of a known contradiction retrieved in 6 of 7 cases. C, the
> instrument: gold set repaired (PHX-1098), contradiction gold set, the answer
> arm on an unknown corpus (PHX-1110: +3.6 EM from the edges). D, Nous — reading
> with working memory — is next. *Deliberately not next:* the MNLM (H100-class
> compute), the curiosity loop, federation, porting the agent roster, S4/S6,
> scale. An appendix lists the load-bearing claims that can no longer stand as
> written, each with its source line and its evidence.

*2026-09-03. Basis: the original, comprehensive vision — `PHILOSOPHY.md`,
`docs/VISION.md`, `PANTHEON_VISION.md`, `DEEP_TECH_VISION.md`,
`TARGET_ARCHITECTURE.md`, `CHRONICLE_PRINCIPLES.md`, `CURIOSITY.md`, `HIVE.md`,
`ROADMAP.md`, `BUILD_DOCTRINE.md`, the migration plans — held sentence by
sentence against what this repository has measured since August. The ledger
with all 620 claims, each with source, evidence, and status, sits alongside
it: [`vision_claims_ledger.json`](vision_claims_ledger.json). 258 of them are
load-bearing; 61 are refuted, 170 partly confirmed, 171 confirmed, the rest
open, unverifiable, or value.*

## How this plan came about

The doctrine inventory (PHX-1100) measured which *mechanisms* run. It says
nothing about which *promises* the vision thereby keeps or breaks — and the
vision is the reason everything is built. This page takes the reverse path:
from the vision to the measurement, and from that to the order.

Four decisions that stood open have been made and implemented along the
way, each with its number:

- **Consolidation has been applied to `data/mesh-founding`.** Retrieval
  84 → 87%, 36 → 39 full questions; the identity of 68 candidates has been
  resolved; of the two answer losses, two were scorer artefacts. The old mesh
  sits at `data/mesh-founding.pre-consolidation-2026-09-02`.
- **`DEFAULT_K_SEEDS` is 1** — but only because the mesh is a different one.
  Under PHX-1091's own tune/test protocol (three mixes, both directions): on
  the *old* mesh, `k=1` loses held-out in 3 of 6 splits; on the *consolidated*
  one it is chosen in 6 of 6 and wins in 5 of 6 (+0.092 · +0.087 · +0.071 ·
  +0.109 · 0.000 · +0.159). The decisions are linked; alone, the second would
  have been wrong.
- **All 1,206 `raw_text_ref` values point to a source again** —
  `gutenberg_348#p1..1210` instead of a deleted session directory (PHX-1103).
  For the first time since the full run, the substrate can trace a chunk back
  again.
- **`constraints.txt` pins the packages that have broken the repo four
  times**, and is installed in CI and the install line with `-c` (PHX-1076).
  pyproject stays loose.

Alongside that, the five wrong sentences of the README status section have
been corrected, and `llms.txt` with them.

## The vision in seven verbs

What the vision attributes to the substrate can be brought down to seven
verbs. Each held against the ledger:

| Verb | Vision | Status | Evidence |
|---|---|---|---|
| **reads** | Nous reads like a human — sentence by sentence, with working memory, revising | Kadmos v2 reads statelessly per paragraph; there are two Kadmos v2; Monkey 1 never run | TARGET_ARCHITECTURE:158, ROADMAP:32 |
| **activates** | no lookup, activation; constellation instead of document | **confirmed** — the primitive on every real path; +0.102 recall@5 over kNN on held-out 2Wiki | TARGET:102, qa_benchmark |
| **remembers / learns from use** | every interaction strengthens or weakens; the system gets better through use | since PHX-1101/1102: holds what it uses; on 2Wiki +1.3 on used, **−1.5 on held-out** | PHILOSOPHY:108, heartbeat_2wiki |
| **dreams** | Oneiros runs continuously, writes denser connections back | **refuted as a process**: no scheduler, the generation branch unreachable; the +34.8% figure is an in-memory simulation | PHILOSOPHY:100-102, VISION:84 |
| **heals** | immune system, contradiction resolution, promotion to Mneme | **no** — no symptom, no therapy, no promotion, and *no contradiction representable* | VISION:34, PANTHEON:244 |
| **grows where it is looked at** | the curiosity loop: attention becomes acquisition | Gen-1 skeleton; nothing on the mesh | CURIOSITY:5-17 |
| **thinks inside** | the MNLM thinks *inside* the mesh, vectors in, vectors out | blocked on GPU; not a single measurement | ROADMAP:212, PHX-1035 |

Two verbs carry, three have only just been connected, two exist only as
document. That is more honest than *"the mesh is alive"* — and it is more
than was true four weeks ago.

## The one finding that sets the order

The ledger contains 61 refuted claims. Most are mechanisms that are not
built — the inventory already knew that. Five of them are something else:
they are **non-negotiables** from `PANTHEON_VISION` §"Non-Negotiable
Principles", and they fail not for lack of code, but at the **data model**:

| Non-negotiable | Status in the mesh |
|---|---|
| 2 — contradiction, uncertainty, competing interpretations are preserved | no representation of a contradiction, anywhere; `relation_kind` has 10 values, none is *contradicts* |
| 3 — time is intrinsic: change, supersession, expectation, decay | only decay; `temporal_vector` is `None` on every node; no validity, no supersession |
| 1 — every claim carries origin, basis, revision path | provenance yes (alive again since today), revision no: edges have neither trust, nor author, nor history |
| 5 — authority, access, responsibility machine-readable | no field for it, in no schema |
| "Chronicle instead of encyclopedia" — the new, the disputed, the superseded representable | Gen 1 had `DISPUTED` as a status; the mesh no longer has it |

The MESH doctrine moved all of that into one field: `frame_vector`, the
epistemic stance of a node — assertion, denial, hypothesis, contradiction.
And `frame_vector` is today a salted SHA-256 projection of the label
(PHX-1095). The frame carries a hash, not a stance.

**This is the same finding as PHX-1101, one level up.** There, the
substrate kept no memory of its own *activity*, and everything that read
from it — promotion, replay, decay gating, RL — could not run. Here it
keeps no memory of *contradiction*, and everything that would need to read
from it — Athene, Chronos, the immune system, the chronicle, Metis's
prerequisites, the second pillar "scientific workbench" — cannot run. The
verb *heals* is not unbuilt. It is unbuildable, until the substrate knows
what a contradiction is.

## The plan — four tracks, in this order

### A. Learning safely — the renormalisation (PHX-1106)

The verb *learns* is connected and displaces. MESH_SUBSTRATE §6 provides
for the counterforce; the ledger says it is not built; the 2Wiki heartbeat
says it is needed (−1.5 on held-out over 50 rounds). A tick step after decay
that holds the weight per node to a target sum. Fixes the inverted tier
ladder along the way.

*Done when:* on 2Wiki over 50 rounds, used ≥ +1 and held-out ≥ 0 — and the
same on HotpotQA and with a second seed, so that two questions' worth of
effect does not carry the whole load. One to two sessions.

**Result (2026-09-12, [`renormalisation.md`](renormalisation.md)):** built
and measured, the condition not met as stated — and not by the baseline:
the +1.3 gain from PHX-1104 was a seed (+0.3 on HotpotQA, −0.7 with seed 1).
What holds across both datasets and both seeds is the displacement
(−1.5 / −2.3 / −2.3), and global renormalisation *with a cap* cancels it
out every time (+1.5 / −0.7 / +0.7) for half a point on the used. Without a
cap, §6 is invisible and then a reinforcer (−3.8). `mesh tick` now runs
with this by default, set point 0.9 of the entry mass. The verb *learns*
stays at *holds, without displacing*; whether it ever *wins* is decided not
by the dynamics but by the generation branch (PHX-1100), which is
unreachable.

### B. The memory of contradiction (PHX-1107)

The finding above, as a blueprint. Not the whole immune system — the
prerequisite for it that all the healing verbs share:

1. **Real frames.** Kadmos outputs an epistemic stance per chunk and per
   relation — asserted, denied, hypothetical, disputed, superseded — and
   the vectorizer projects it into the 64-d frame space over a fixed basis
   instead of a hash. That turns frame routing from inert to effective,
   without changing a single line in retrieval: the mechanism has been
   waiting for its signal since S3.
2. **`contradicts` and `supersedes` as `relation_kind`**, with `valid_from`
   / `valid_to` on the edge — the smallest representation of time that
   satisfies non-negotiable 3. No new schema; the fields are free.
3. **A contradiction gold set** on the founding corpus. Hesiod contradicts
   himself (the birth of Aphrodite, the parents of the Muses); demo beat 2
   has hinged on exactly such a question since PHX-1045.
4. **Re-reading the founding corpus**, with frames. 1 h 41 min, €0.26 — the
   cheapest way to get a substrate that knows what it doubts.

*Done when:* a contradiction question from the gold set returns both sides
in the constellation, frame routing on the newly read mesh has a
measurable effect (recall on the contradiction set, with versus without),
and the verb *heals* has, for the first time, an entry point on which
Athene could find something. Three to five sessions.

**Result (2026-09-12, [`contradiction.md`](contradiction.md)):** built and
measured. The corpus has been re-read with frames (stances over eight
values, 39 paragraphs `disputed`), the contradiction pass confirmed 74
contradictions and wrote 334 edges, and a disputed question returns both
sides in 6 of 7 cases. Frame routing has an effect — but only after
entities inherit the stance of their paragraphs, and as a trade rather than
a gain. The strongest finding is the control: on the old mesh with hash
frames, the same routing costs 42 points. The verb *heals* thereby has, for
the first time, an entry point.

### C. The instrument — ongoing, small

Everything above becomes visible only if the instrument can see it. Three
things, each half a session: the gold aliases (PHX-1098, so that "Helios"
does not miss "Helius"); the answer arm on a corpus the model cannot
recite from memory (HippoRAG, where the control group does not sit at
50%); and the contradiction gold set from B as a third instrument
alongside retrieval and answer.

**Result, first and third piece (2026-09-16,
[`gold_aliases.md`](gold_aliases.md), [`contradiction.md`](contradiction.md)):**
the contradiction gold set came into being with B (seven cases, both-sides
recall). The aliases are built, and building them turned up the file's
second bug: 30 names stood in their own question, three expectations were
wrong. Re-scoring the same answers overturns one claim: deepseek's prior
knowledge stands under the corrected gold at **86%**, not 50, and the graph
sits below it at 75% — the old scorer had systematically undervalued the
control group. Graph over vector search holds at +11. **This makes the
second piece — the answer arm on a corpus the model does not know — no
longer a supplement, but the only way to ask the question "does the graph
help with answering."**

**Result, second piece (2026-09-16,
[`qa_constellation.md`](qa_constellation.md), PHX-1110):** the question has
been asked and answered. On 2WikiMultihopQA, 1,000 questions, prior
knowledge 33.8% EM, a mesh of all 6,119 passages: the constellation answers
**+3.6 EM over the same fifty entities without edges** (p = 0.03) and ties
with five passages — but only without the structural edges, which made up
60% of the shipped rendering; with them, +0.7 remains. The harness's
rendering form has left them out since this measurement. Where the graph
wins are the comparison questions (+5.6 over passages on 836 questions);
where it loses, yes/no and dates, which an entity description does not
carry. Along the way, a second quadratic term in reading turned up (one
Lance fragment per node), fixed by compaction every 200 paragraphs. Track C
is thereby complete; next, track D.

### D. Nous — reading with working memory (Monkey 1)

The vision's first verb, and its phase 1. It stands here at the back, not
because it matters less, but because the measurement says where it pays
off: under passage seeding the construction is almost invisible (±0.01),
under entity seeding it is decisive (+0.18). The better reader pays off
where the answer is an entity or a path — and the instrument for that
comes out of B and C. Building Nous earlier would mean being unable to
measure it.

## What deliberately does not come next

- **The MNLM** (phase 4, Monkey 3): blocked on H100 compute time. The
  falsifier now has the ablation controls the deep audit demanded. As soon
  as compute time is available, the brief is ready; until then, every
  sentence about it is a promise.
- **The curiosity loop on the mesh**: needs stub detection, triggers, a
  dispatcher — and above all something that writes the acquisition back
  into the substrate. After B, because new knowledge must first be able to
  arrive as *disputed*.
- **Federation, visibility, tiers**: non-negotiable 5. The vision itself
  says, not in Gen 1.
- **The agent roster on the mesh** (Argus, Athene, Chronos, Nemesis, Eris,
  Mnemosyne): the Gen-1 code runs on the store that is being superseded.
  Porting it to the mesh means giving them something to find — B.
- **S4 and S6** (backend abstraction, removal of the legacy path): 105
  files reference the old schema. Pure engineering work, without which no
  undertaking of the vision fails. After A and B, once the mesh is the
  better substrate on every surface.
- **Scaling to 4.81 M** (S2.5): the RAM bug in the resolver is real and
  small; it is not what is blocking the vision today.
- **Chronese**: refuted by `TARGET_ARCHITECTURE` itself — vectors are the
  medium, not a canonical language. Stays a document.

## Corrections to doctrine and vision (PHX-1108)

The ledger names sentences that are phrased as status and are no longer
true, or assumptions that stand as facts and are refuted by measurement.
Three are corrected today, because they are pure status lines; the rest
sit in the ticket, so the documents keep their voice and still don't lie:

- `TARGET_ARCHITECTURE` §Monkey 2 — *"Not yet run"* → measured, +0.102.
- `TARGET_ARCHITECTURE` §Density — *"Minimum viable density 20:1"* →
  refuted in both directions: the advantage shows up at 7:1, and denser
  bridges move nothing.
- `CHRONICLE_PRINCIPLES` 12 — *"consolidation + immune system — live
  today"* → consolidation as a pass since 2026-08-31, immune system no.
- In the ticket: the tier ladder (§2), the threshold 0.05, "10–30% of
  edges with a descriptor", HNSW (it's IVF-PQ), "append-only ledger"
  versus overwrite-and-prune per tick, "Oneiros runs continuously" (VISION,
  PHILOSOPHY, CHRONIK_SCALE), the window of `fired_recent`.

## Appendix — the load-bearing claims that can no longer stand as written

From the ledger's 258 load-bearing claims, the refuted ones, with source
and the evidence in one sentence. The full text is in
[`vision_claims_ledger.json`](vision_claims_ledger.json).

| Claim | Source | Evidence |
|---|---|---|
| There is no nightly batch; Oneiros runs continuously | PHILOSOPHY:100, VISION:84 | `run_minimal_tick` has one caller outside the tests, the CLI; the interval worker drives the Gen-1 store |
| Oneiros writes denser connections back | PHILOSOPHY:102 | the generation branch is unreachable from the query path; every one of the 94,490 edges comes from ingestion |
| Good knowledge is promoted to Mneme | VISION:34 | `consolidation_tier` = 1 on every node; no promotion in the code |
| Q-IDs are the strongest identity signal | CHRONICLE_PRINCIPLES:36, ROADMAP:67 | 127 of 130 were confabulated; the mesh no longer has any; the strongest corruption vector, not the strongest signal |
| Contradiction and uncertainty are preserved | PANTHEON:244 | no representation of a contradiction in the mesh |
| Time is intrinsic | PANTHEON:248 | only decay; `temporal_vector` is `None` everywhere |
| Authority, access, responsibility machine-readable | PANTHEON:256 | no field, in no schema |
| Redundancy collapse: a second reading adds edges, not a node | PANTHEON:194 | six Zeus nodes, until PHX-1097; `MergeNodes` is an MNLM DTO, not a substrate primitive |
| A chronicle does not get harder to run the wiser it gets | PANTHEON:228 | consolidation a handrail; MNLM blocked; no working set, the whole CSR in memory |
| Kadmos v2 reads with working memory and revises | TARGET:158 | the production reader has no state across paragraphs |
| Nous condenses via a GNN encoder, text never as an intermediate medium | TARGET:39 | no GNN in the repo; the Nous brief "ready for implementation" since May |
| Minimum density 20:1, below which SA does not beat kNN | TARGET:113 | +0.102 held-out at ≈ 7:1; density sweeps flat |
| A verbatim layer preserves source text for forensics and citation | DEEP_TECH:45 | forbidden by TARGET; only a pointer, which was dead until today |
| Chronese is the native language; graph, vector, text are projections | CHRONESE:3 | TARGET says the opposite, and TARGET is binding |
| Self-improvement stage 1 (consolidation + immune system) is live today | CHRONICLE_PRINCIPLES:54, ROADMAP:274 | consolidation as a pass since 2026-08-31; immune system no; corrected today |
| The ledger is append-only; errors are superseded, not overwritten | BUILD_DOCTRINE:65 | node and edge tables are written with `overwrite` every tick and pruned to retention 0 |
| These structural properties cost nothing and make growth-with-errors repairable | BUILD_DOCTRINE:67 | a full run had to be repeated because the name was discarded on write; chunks were untraceable until today |
| Gen 1 does not implement the curiosity loop, but in a way that lets it be retrofitted without a re-founding | CURIOSITY:11 | the re-founding happened: the MESH pivot of 2026-05-13 |
| Hestia has a standing subscription to every curiosity trigger | CURIOSITY:143 | HestiaLite was deleted in W13; `hestia.py` is a schema without a runtime |
| The Oneiros tick runs every few minutes, with renormalisation and tiered decay | CHRONIK_SCALE:146 | no scheduler; only k=2; no renormalisation |
| Neo4j is fully reversible behind the store protocol | GEN1_LEGACY:588 | the migration plan called the discrepancy structural and wrote six steps |

---

## Addendum 2026-09-11 — Track E: the latent last mile (PHX-1109)

The prompt was Jakob's question about the reports that language models are
increasingly doing their thinking in internal layers and no longer need
readable intermediate steps. The research turned up two findings that must
be kept apart:

- **Today's frontier models already compute essential parts without a
  trace in the text.** Baherwani, Goldstein, and Panda (July 2026) raise
  the accuracy of 13 frontier models by up to 13 points using
  content-free filler tokens; Wang (April 2026) calls the latent
  trajectory the field's working hypothesis and the text its projection;
  since May, Anthropic has been translating activations into language via
  an autoencoder and finding there what the chain withholds.
- **Architectures without text intermediate steps work, but small.**
  Coconut (Meta) feeds the hidden state back in, a continuous thought
  encodes several next steps at once. Recurrent depth (Huginn, 3.5B)
  reaches the reasoning performance of considerably larger models. LOTUS
  (June 2026) closes the gap to explicit chain-of-thought at 3B, at 2.5-
  to 6.9-fold lower latency — and at the same time says earlier latent
  methods fell behind above 1B. Kohli et al. (COLM 2026): recurrent
  transformers combine, in a single forward pass, facts that never
  occurred together in training. No frontier lab has shipped a latent
  reasoner (Turing Post, July 2026).

**What this means for Theogony, in four sentences.** The direction of the
core thesis becomes respectable, for a different claim than ours: text is
not the medium *inside* the model either. For us, everything still runs
through text, which is why VISION:44 ("the agent does not read context, it
receives structure") is unmeasured for us. What latent thinking takes
away — the readable trace — is exactly what a substrate with origin,
revision path, and readable contradiction offers — **the substrate is the
audit trail that latent models no longer produce**, and that only holds if
PHX-1107 exists. And the competition sharpens: if models compose facts in
their weights, the mesh must show that it composes what was read
*yesterday*, with provenance (Monkey 3).

**Track E, placed after B, begun today because it uses the instrument
that is already there.** xRAG (2024) shows: a frozen retriever, a frozen
model, a small trained projector, one document as one token. Carried over
to us: node vectors from bge-small-en, a projector into the embedding
space of an open small reader; the constellation becomes soft tokens plus
edge structure instead of a block of text. Three arms with the same local
reader, the same scoring as the answer instrument, an untrained projector
as control. The MNLM brief rejected this path as diluted; the brief is
right about the horizon and wrong about the order.

*Done when:* the soft constellation is measured against the text
constellation on the gold set, with spread. A null result is a result.
Nothing changes about the order A → B: both are prerequisites for any
reader, whether text or latent.

**Result (2026-09-12, [`latent_mile.md`](latent_mile.md)):** the vector
arrives, the answer does not. A frozen 3B reader reads the node's
identity from the projected node vector (2.4 against 6.8 nats per name
token with the correct versus a foreign vector, on unseen nodes), but
forms no answer from fifty such tokens: strictly scored, text 49%, prior
knowledge 14%, vectors 9–11%, better than the text on no question. What
is built is xRAG stage 1; the lever is stage 2, instruction tuning with
self-distillation, and that needs question-answer data beyond the gold
set. VISION:44 splits into "receives structure" (yes) and "no text
translation required" (no, at this scale). Track E stays after B; the
order does not change. A side finding for the instrument: 30 of the 111
gold names appear in their own question (PHX-1098).
