# The Memory of Contradiction (PHX-1107)

> **Abstract.** *Finding.* The mesh could not represent a contradiction:
> ten relation kinds, none of them a disagreement, and frame vectors that were a
> salted hash of the label. Everything that heals would have to read from that.
> *Built.* Epistemic frames as seven weighted axes instead of seven labels (nine
> stances as points: refuted against current cosine −0.50, definition against
> current +0.98); `contradicts` and `supersedes` as relation kinds with
> `valid_from` / `valid_to` on the edge; the founding corpus read again with
> stances (eight stance values in use, 39 paragraphs `disputed`, 30
> `contradicts` relations written by the reader itself); and a contradiction
> pass — 690 structural candidates, 74 confirmed (11%), 334 edges, 141
> paragraphs marked disputed, eleven minutes. Two things made the pass find
> anything: descriptor normalisation (parenthood arrives under more than thirty
> spellings, half of them reversed: 0 → 202 candidates) and a two-step
> adjudicator that first asks whether the relation is single-valued (36 of 100
> confirmed → 3 of 60). *Measured* on seven verified contradictions of the
> corpus: both sides in the Constellation for 6 of 7 on the re-read mesh, 5 of 7
> on the old one. The strongest finding is the control: frame routing on the old
> hashed frames costs 42 points (5/7 → 2/7); on real frames it costs nothing.
> Routing did nothing at all until entities inherited the centroid of their
> paragraphs' frames — 82% of them held no stance — and after that it trades one
> question for another rather than gaining. *Limits.* 86% against 71% confounds
> re-reading with framing; extraction noise sits among the confirmed
> contradictions; frame promotion is not part of the tick.

**Status:** 2026-09-12, measured. Branch `feat/phx-1107-contradiction`.
**Prompted by:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §B — the one finding of the vision ledger that fixes the order.
**Tools:** `src/theogony/mesh/frames.py`, `src/theogony/mesh/runtime/contradiction.py`, `scripts/mesh_contradictions.py`, `scripts/mesh_contradiction_eval.py`, gold set `eval/gold/founding_contradictions.json`.

## The Finding

Five non-negotiables from PANTHEON_VISION fail not for lack of code but for
lack of a data model. The substrate could not say that it doubted something:
`relation_kind` had ten values and none of them was a disagreement,
`temporal_vector` was `None` on every node, and `frame_vector` — the field
into which the doctrine relocated epistemic stance — carried a salted
SHA-256 projection of the label (PHX-1095). 5,002 nodes, 4,977 distinct
vectors, no stance in them.

That meant frame routing could only mask by a hash, and everything that
would need to read from the frame — Athene, Chronos, the immune system, the
Chronik, the second pillar, the "scientific workbench" — had nothing to
read. The verb *heals* was not unbuilt. It was unbuildable.

## What Was Built

### 1. The Frame as a Factorised Basis, Not a Label

The doctrine names seven frames (definition, current claim, historical
claim, refuted claim, hypothesis, observation, direct quote) and says they
are "learned embedding regions", with a rule-based bootstrap as an explicit
intermediate step. This is that bootstrap, and it is **factorised rather
than enumerated**: seven axes span the space, and the frames are points
within it.

| Axis | Poles | Weight |
|---|---|---|
| veridicality | asserted ↔ denied | 2.0 |
| modality | factual ↔ hypothetical | 1.0 |
| time | current ↔ historical | 1.0 |
| standing | uncontested ↔ contested | 1.0 |
| force | in force ↔ superseded | 1.0 |
| attribution | direct ↔ attributed | 0.5 |
| register | general ↔ specific | 0.5 |

The factorisation is the point: a historical claim that has *also* been
refuted is both — `time = −1` and `veridicality = −1` — and no enumeration
of seven labels can express that. Kadmos still outputs a label, because a
label is what a language model reliably produces; the label names a point,
and points can be mixed.

Veridicality carries double weight, because denial is the very reason the
doctrine introduces the field at all: "Thyroxine is an oxindole derivative"
and its negation land at the same semantic point.

**What the cosine then does** — this is the doctrine's arithmetic, not a
claim about it:

| | against *current claim* |
|---|---|
| Definition | +0.98 |
| Observation | +0.77 |
| Direct quote | +0.77 |
| Historical claim | +0.65 |
| Superseded | +0.50 |
| Refuted | **−0.50 → 0.0** |

Exactly the Kendall behaviour from MESH_RETRIEVAL: "What is thyroxine?" does
not retrieve the refuted structure from 1915. What it retrieves is not the
historical stance alone — which *affirms* what the refutation denies, so
the two oppose each other — but the profile that mixes both.

**Two design flaws were measured and fixed while building this.** A direct
quote, without positive veridicality, was exactly orthogonal to every claim
and got damped to zero by every factual question — on a corpus that is half
direct speech, that would have erased half the substrate from retrieval.
And the contradiction profile, built from stances, inherited their positive
veridicality, which overrode everything else: it let every plain claim
through and damped the refuted one to zero — the opposite of what it is
there for. It is now written in axes — "contested or superseded, and silent
on whether it is true" — and damps every uncontested claim to exactly zero.

### 2. Who Carries Which Stance

- **Chunks** (the observation) carry the paragraph's stance.
- **Entities and source anchors** are neutral. "Zeus" is neither asserted
  nor denied; the claims about him sit on the chunks. The zero vector is
  neutral by construction and is never damped.
- **Edges** get `frame_consistency` from their endpoints — the missing pass
  that PHX-1095 named ("a missing pass, not missing data"). Where one
  endpoint is an entity, the value is 1.0; where both are paragraphs, it
  carries information.
- **`valid_from` / `valid_to`** on every edge, the smallest representation
  of time that non-negotiable 3 requires. Both ride in `payload_json`, so no
  existing mesh needs a migration.

### 3. The Pass That Finds Contradictions

A stance says how *one* paragraph speaks. A contradiction is a relation
*between* two, and a reader who reads paragraph by paragraph never sees it
— it never sees the other paragraph. So it takes a pass over the finished
mesh; the doctrine describes it in the voice of an agent that does not
exist (Argus, MESH_SUBSTRATE §"Contradiction resolution").

Candidates structurally, then adjudicated — the same division of labour as
Oneiros consolidation. A candidate is two relations that share one endpoint
and a descriptor and disagree about the other:

    Night  --bore-->  the Fates        (Theogony 211-225)
    Themis --bore-->  the Fates        (Theogony 901-906)

**The filter that makes this precise is provenance, not semantics.** Two
relations from the same paragraph are an enumeration — "Rhea bore Hestia,
Demeter, Hera" are three edges and not a disagreement — so a candidate
requires that the two sides be attested by *different* paragraphs. Without
this filter, every genealogy in the corpus is a contradiction.

What remains is usually still compatible: Zeus fathers many children, and
`father_of` is not functional. That is what the adjudicator is for — the
question is whether both can be true at once, not whether they look alike.

Confirmed contradictions get `contradicts` edges between the attesting
paragraphs, and those paragraphs are set to the `disputed` stance. The
second part is the one that carries the finding into retrieval. Nothing is
deleted and no side is declared false.

## The Gold Set

Seven contradictions, each with both attesting passages verified in the
corpus (line number and verbatim quote):

| Question | Side A | Side B | Scope |
|---|---|---|---|
| Who bore the Fates? | Night, without a father | Themis, by Zeus | within the Theogony |
| Who was Asklepios's mother? | Arsinoe | Koronis | across works |
| Who was Helen's mother? | a daughter of Okeanos | Nemesis | across works |
| Who bore Typhoeus? | Earth, by Tartaros | Hera, alone and in anger | across works |
| Whose daughter is Nemesis? | Night's | Zeus's | across works |
| How was Aphrodite born? | from the foam | daughter of Zeus | across works |
| Did Hephaistos have a father? | Hera alone | Zeus his father | within the Theogony |

Two of them the corpus itself flags as contested ("Some say (Asclepius) was
the son of Arsinoe, others of Coronis", line 1433; "Hesiod, however, makes
Helen the child neither of Leda nor Nemesis", line 1455) — those, Kadmos can
recognise while reading. The other five can only be found by comparing
across paragraphs.

**Works and Days is not included in this edition.** The ticket had
suspected the Pandora narrative and the ages of man as contradictions;
neither exists here. The Muses, the ticket's other example, are unanimously
daughters of Zeus and Mnemosyne throughout the corpus.

The measurement is one that no existing harness can express: **both-sides
recall**. A question counts only if the Constellation carries an entity
from each side. Four entities from one side and none from the other count
zero — that is exactly the encyclopedia behaviour the Chronik is meant to
refuse.

## The Re-read Corpus

1,206 paragraphs, 2 h 27 min, €0.39 (`deepseek-chat`). For the first time,
the substrate carries epistemic stances:

| Stance | Paragraphs |
|---|---|
| `current_claim` | 380 |
| `direct_quote` | 298 |
| `historical_claim` | 290 |
| `observation` | 111 |
| `definition` | 66 |
| `disputed` | **39** |
| `hypothesis` | 20 |
| `refuted_claim` | 2 |

On top of that, **30 `contradicts` relations that the model wrote by itself
while reading** — places where the text names the dispute. And
`frame_consistency` now carries something for the first time: of 127,402
edges, 5,590 sit below 1.0, and of those **185 sit at exactly 0** — edges
between paragraphs holding opposing stances. PHX-1095 had measured the
field at exactly 1.0 on all 94,490 edges of the old mesh.

Before the full run, five paragraphs were checked individually to see
whether the model uses the vocabulary at all: five of five correct, and on
the Helen fragment it wrote `relation_kind: contradicts` on its own. The
*first* attempt had set twelve of twelve paragraphs to `current_claim` —
the prompt named the stance but did not show that it is a top-level field,
and the model wrote it onto the relations instead.

## The Contradiction Pass

690 candidates, 74 confirmed (11%), 334 `contradicts` edges, 141 paragraphs
set to `disputed`. 11 minutes, fractions of a cent.

Among them, genuine mythological contradictions: Laomedon versus Tros as
the father of Ganymedes, Theia versus Euryphaessa as the mother of Eos and
Selene, Klymene versus Alkmene as the mother of Iphiklos, Tyro versus
Althaia as the mother of Pheres. And noise from extraction: fragment
numbers that "sit" in two places, and a pair "February part_of 1321 /
1325".

**Two things were needed for the pass to find anything at all.**

*Descriptor normalisation.* The structural filter compares (endpoint,
descriptor), so it sees a disagreement only if both sides spell the
relation the same way. Kadmos does not: parenthood arrives under more than
thirty spellings — `bore` 145, `son_of` 120, `fathered` 80, `daughter_of`
79, `father_of` 45, `mother_of` 45, `parent_of` 43, `child_of` 26 — and half
of them point in the other direction. With a curated kinship class and
canonical direction: **202 parenthood candidates instead of zero.** The
direction is not cosmetic here; it is what makes the grouping functional: a
child has one father and one mother, a mother has many children, so the
question worth asking is always "how many parents does this child have".

*A two-step adjudicator.* The first prompt confirmed 36 of 100 candidates —
"Apollo went to A / went to B" as a contradiction. The second first asks
whether the relation admits only one value at all, and only then whether
the values differ: 3 of 60. It also recognises aliases ("Earth parent_of
Cyclopes / Gaia bore Cyclopes" → compatible).

## The Measurement: Does a Contested Question Return Both Sides?

Seven questions, `k_seeds=1`, `top_k=50`. A question counts only if the
Constellation carries an entity from *each* side.

| Mesh | Profile | both sides | sides avg |
|---|---|---|---|
| old (hash frames, consolidated) | `any` | 71% (5/7) | 1.71 |
| old (hash frames) | `contradiction` | **29% (2/7)** | 1.00 |
| new, framed | `any` | **86% (6/7)** | 1.86 |
| new, framed | `contradiction` | 86% (6/7) | 1.86 |

**The strongest finding sits in the second row.** On the old mesh, the same
frame routing costs 42 points — it masks by a salted hash and destroys the
Constellation. On the new one, it costs nothing. PHX-1095 had suspected
that "routing on them today would mask edges by a hash"; this is the number
for that.

The comparison of 86% against 71% conflates two changes — the new mesh was
also re-read and is unconsolidated (5,688 nodes against 4,934) — and so it
carries less far than the row above it.

### The Routing Only Works Once Entities Carry a Stance

The first measurement after the re-read gave **identical** numbers for
`any`, `contradiction`, and `what_is`, question by question. The reason: a
Constellation is made of entities, and 82% of entities held no stance — the
stance sat on the chunks. `frame_consistency` is 1.0 by construction for a
neutral node, so every profile scaled every edge by 1.0. The same shape as
PHX-1104: the substrate held something the operator could not read.

MESH_RETRIEVAL names the missing step in a subordinate clause — the frame
is said to be "mutable by Oneiros during consolidation (when many chunks
with consistent frames consolidate, the consolidated node inherits the
dominant frame)". Built as `run_frame_promotion`: every node takes the
centroid of the frames of the paragraphs that mention it. Centroid rather
than mode, because the mixture is the signal — a figure who appears in
forty calm paragraphs and two contested ones should read as mostly calm and
a little contested. 3,590 of 5,688 nodes inherited one, 1,207 source
anchors remained neutral.

After that, question by question:

| Question | `any` before | `contradiction` before | `any` after | `contradiction` after |
|---|---|---|---|---|
| fates-parentage | both | both | both | **one** |
| helen-parentage | one | one | one | **both** |
| the remaining five | both | both | both | both |

**The routing now does something, and it is the expected thing.** It
retrieves the Helen question, which no other profile retrieves — the one
where the corpus names the dispute itself ("Hesiod, however, makes Helen
the child neither of Leda nor Nemesis"), so its paragraphs were read as
`disputed`. And it loses the Fates, two plain genealogy paragraphs with no
dispute marker, which are only structurally at odds.

In the aggregate, that is a trade, not a gain. As a mechanism, it is the
difference between provably ineffective and demonstrably effective.
