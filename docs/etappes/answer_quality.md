# Does a Constellation help a model answer? — first measurement

*2026-08-26, `data/mesh-founding` at 14 ticks, deepseek-chat, temperature 0,
top_k 50, the 47-question founding gold set.*

Every retrieval number this repo has published answers "did the expected entity
reach the working set". None of them answers the question the working set exists
for. `mesh ask` returns a Constellation and synthesises nothing, and the question
was explicitly deferred when the answer budget moved to 50 (PHX-1069).

Three arms, same model, same questions, same wording apart from where the
material comes from:

| arm | material |
|---|---|
| `closed_book` | none — what the model already knows |
| `vector_only` | top-50 nodes by cosine, as plain text |
| `constellation` | the same nodes, plus the edges among them and what they assert |

## The result

| arm | answer recall | complete answers |
|---|---|---|
| closed_book | **50%** | 13/47 |
| vector_only | 47% | 12/47 |
| constellation | 46% | 13/47 |

All three within four points. **The corpus is Hesiod and the model has read
Hesiod**, so the aggregate cannot discriminate — which is why the closed-book arm
is not a formality but the control that makes the others readable.

On the slice where it can discriminate — the 34 questions the model does *not*
answer fully from memory:

| arm | recall on that slice |
|---|---|
| closed_book | 29% |
| vector_only | **45%** |
| constellation | 42% |

**Retrieval earns its place: +16 points over pretraining.** The substrate's
content is doing real work.

**The graph does not, on this corpus.** Constellation against plain vector search
at equal budget: 7 questions better, 7 worse, 33 unchanged. That is the arm
designed to falsify the project, and on this evidence it does not separate.

## The finding that matters more than either

Cross-referencing what retrieval delivered against what the answer named:

```
111 expected entities, constellation arm
                      named   not named
in the context           32          53
not in the context        0          26
```

**Retrieval delivers 85 of 111 (77%). The answer names 32.** Sixty-two per cent
of what retrieval works so hard to find is lost in the step after it — and no
instrument was looking there. Note also the zero: in the context arms the model
names nothing it was not given.

## What this measurement cannot do, measured

The prompt was nearly the whole result. The first version offered an escape —
"if the material does not contain the answer, reply UNKNOWN" — and the model took
it 20 times on questions whose answers were in front of it:

| prompt | recall | complete | declined |
|---|---|---|---|
| with the UNKNOWN escape | 31% | 10/47 | 20 |
| exhaustive, no escape | 47% | 17/47 | 0 |
| exhaustive + explicit scan step | 52% | 18/47 | 0 |

Twenty-one points from how the question is asked. The first draft of this
experiment would have reported *"the substrate performs worse than the model's
own knowledge"*.

And the noise floor, measured rather than assumed — same constellations, same
model, temperature 0:

| | run 1 | run 2 |
|---|---|---|
| "Answer using ONLY the material given…" | 50% | 52% |
| "Answer **the question** using ONLY the material given…" | 48% | 49% |

**Two points of run-to-run variance at temperature 0, and two to three points
from three words of prompt.** The difference between the arms is one to four
points. *The signal is the size of the noise.*

## Second round: is the loss in how the Constellation is rendered?

The first round left an obvious hypothesis: 50 entity descriptions and 120
relation lines is a poor way to hand a graph to a model. Chasing it produced a
concrete defect and a negative result.

### What the model was actually reading

For *"What children did Theia bear to Hyperion?"* — expected Helius, Selene, Eos
— the relation section opened with:

```
- Theogony authored Aphrodite
- Phrixus sacrificed_to Zeus
- Theogony was jealous of Homer
- Theogony was jealous of Homer
- Theogony was jealous of Homer
- Theogony was jealous of Homer
```

**The substrate holds the answer literally**: `Theia --bare--> Helius`,
`--bare--> Selene`, `--bare--> Eos`, plus `Hyperion --father of-->` each of them.
None of it was shown.

Two causes, both measured:

- `Theogony -> Homer` carries **nine distinct relations**; the CSR holds a
  position for each and sums their weights to **6.382**, against **0.859** for
  `Theia -> Helius`. Edges were ordered by that sum, so pairs ranked by *how many
  ways* they were connected rather than by their bearing on the question.
- The descriptor index is keyed by pair, so one row per CSR position printed the
  pair's single winning descriptor nine times. Over the 47 questions at a
  200-edge budget, **4,105 of 9,400 slots (44%) went to repetitions of the same
  pair**; 59% on the worst question.

Fixed (PHX-1088): one row per unordered pair, keeping the direction that claims
more, ordered by the activation of the endpoints. Repetition 44% → **0%**.
Retrieval unchanged at 77% / 36 of 47, as it must be — this is display.

### And it did not move the answer

| | answer recall |
|---|---|
| before the fix | 46% |
| after the fix | 46% |

Within the noise floor. **The 62% loss is not a rendering problem.**

### Does the relation section help at all?

Same constellations, three renderings:

| rendering | recall | complete |
|---|---|---|
| nodes + relations (shipped) | 42% | 11/47 |
| **nodes only** | **45%** | **14/47** |
| relations only | 41% | 11/47 |

**Dropping the relations improves the answer**, by three points — inside the
noise, so the honest statement is that the graph's relations contribute nothing
measurable here, not that they harm.

### Does more context dilute?

The question deferred in PHX-1069, now measured on answers rather than recall:

| top_k | constellation | vector_only |
|---|---|---|
| 10 | 28% | 39% |
| 20 | 36% | 45% |
| 50 | 46% | 47% |
| 100 | **49%** | **51%** |

**More context helps, monotonically, to 100.** No dilution. And plain cosine beats
the Constellation at every budget, most widely at the tightest — eleven points at
ten nodes. Spreading Activation fills the top of a small budget with nodes that
are *related* where the question wanted nodes that are *similar*.

## What follows

1. **The answer step is the bottleneck, not retrieval.** 77% reaches the working
   set and 46% reaches the answer. Every point of retrieval work since PHX-1068
   has been spent upstream of the larger loss — and the loss is not rendering.
2. **The graph's contribution to the answer is not measurable on this corpus.**
   Relations neutral to slightly negative; plain cosine ahead at every budget.
   That is the arm built to falsify the project, and this round did not clear it.
3. **This corpus cannot settle it either way.** Canonical Greek mythology, 47
   questions, and a noise floor as large as the effect. The HippoRAG trio
   (3 × 1000 questions with gold answers, already on disk) can.
4. **No claim here rests on one arm's number.** They rest on differences, and the
   differences under five points are not claims.

---

# Third round: the seeding ceiling, on this corpus

*2026-08-26, after PHX-1089.*

The HippoRAG run produced a testable prediction for the founding substrate:
Spreading Activation's advantage lives at **narrow** seeding — +5.0 exact match
at hybrid/S=2 on 2WikiMultihopQA and nothing at S=10. The founding measurements
were all taken at the shipped default of `k_seeds=8`, which is the wide end.

## Retrieval says the prediction holds, and sharply

`scripts/mesh_corpus_qa.py --seed-sweep`, 47 questions, 14 ticks, top_k=50:

| k_seeds | recall | fully answered |
|---|---|---|
| 1 | **84%** | 36/47 |
| 2 | 81% | 36/47 |
| 3 | 81% | 37/47 |
| 5 | 80% | **38/47** |
| **8 (shipped default)** | 77% | 36/47 |
| 16 | 71% | 33/47 |
| 32 | 64% | 27/47 |

Monotone. **The shipped default costs seven points of recall against `k_seeds=1`**
— and this is the mechanism the seeding-ceiling result predicted, reproduced on a
different corpus and a different pipeline.

Tuned honestly rather than read off the aggregate — alternating halves, ties
broken toward the narrower setting:

| tuned on | chose | held-out | today (k=8) | at the chosen value |
|---|---|---|---|---|
| A | k=1 | B | 82% | 82% (+0) |
| B | k=3 | A | 73% | **79% (+6)** |

Never negative; +6 in one direction and flat in the other. Same shape as the
answer-budget split: one half has headroom, the other is saturated.

## The answer does not move

| k_seeds | answer recall |
|---|---|
| 1 | 46% |
| 2 | 45% |
| 3 | 47% |
| 8 | 44% |
| *vector_only (no seeding)* | *46%* |
| *closed_book* | *49%* |

Flat, inside the two-to-three point noise floor. **Seven points of retrieval
recall reach the working set and none of them reach the answer** — the same 62%
gap PHX-1087 measured, swallowing the improvement whole.

## What this leaves open, and for whom

The retrieval finding is unambiguous and it is about a **shipped production
default**. It is also a doctrine question rather than a tuning one, which is why
it is written down here rather than changed:

`MESH_RETRIEVAL` §"Diversified injection" specifies "K seeds from each class …
typically 5–25 per class, total 20–100". The implementation uses **8 total**,
because weight-class stratification is a hub-cap over 64 ANN hits with no class
seats (audit finding, still open). So the shipped 8 already does not honour the
doctrine's number, and narrowing to 3 moves further from a figure that assumes a
mechanism which does not exist.

Two honest readings, and the evidence does not choose between them:

- **Narrow it.** Seven points of recall, +5.0 end-to-end exact match on the
  external benchmark where the answer step is not the bottleneck, and the
  forbidden pattern in the doctrine is *top-K by cosine* — which narrowing MMR
  while keeping name anchors moves away from, not toward. At `k_seeds=1` the
  actual seed count is still a median of 3, because name anchors contribute two.
- **Build stratification first.** The doctrine's 20–100 assumes four weight
  classes with their own seats. Tuning a number whose mechanism is missing tunes
  the symptom.

PHX-1056 proposes the change and has been open since before either measurement.
It now has fresh evidence — its earlier founding-mesh evidence was withdrawn as
non-reproducing (PHX-1083).

---

# Fourth round: what the 62% gap is made of

*2026-08-26, after the stratification work. Recall 80%, 38 of 47 fully answered.*

The gap between what retrieval delivers and what the answer names was the largest
single number in this project. Three hypotheses tested, two refuted, one shipped.

## The substrate knows the name and shows an epithet

Reading what the model actually gets for the questions it fails:

```
### cronus-children: Who are the children of Cronus and Rhea?
  OK Hestia    Vesta — Roman goddess of the hearth, equivalent to the Greek Hestia.
  OK Demeter   dear mother — The mother of the goddess, whom she hopes to see again.
  OK Hades     Host of Many — Epithet of Hades, god of the underworld.
  OK Zeus      her father — Zeus, the father of Persephone.
```

Every one scores as retrieved. The model reads *Vesta*, *dear mother*, *Host of
Many*, *her father* — and is asked who the children of Cronus are.

`_name_index` resolves a gold name through **tags**; the Constellation displays
the **description head**, which is whatever the mention was called. Measured:
**29% of gold entities (32 of 111) are displayed under a name other than the one
they answer to**, and the canonical name is sitting in the tags:

| looked for | displayed | tags |
|---|---|---|
| Hestia | Daughter of Cronos — … | `['Daughter of Cronos', 'Athena', 'Hestia', …]` |
| Zeus | son of Cronos — … | `['son of Cronos', 'Zeus', 'Jupiter', …]` |
| Eos | dawn — Personified as … | `['dawn', 'Eos', …]` |

**The obvious fix makes it worse.** Rendering the other names alongside —
`Hestia [also called: Daughter of Cronos, Athena]` — scored **50% against 60%**
on the same run. The tags carry wrong aliases: Hestia's include *Athena*, Death's
include *entrance*. Surfacing them injects errors faster than it resolves names.
Refuted and left alone; the tag-quality problem is upstream of the renderer.

## Passages are not available, by doctrine

HippoRAG converts 70–75% of what it retrieves into answers; this converts 38%.
The most visible difference is that HippoRAG hands over **passages** and this
hands over **names**.

That route is closed on purpose. `MESH_SUBSTRATE` §"What the substrate does not
do" forbids raw text beyond an opaque `raw_text_ref` pointer, naming "extracted
paragraph bodies" and "multi-sentence source passages" specifically. The
substrate is vector-native and the doctrine's read surface is the `description` —
bounded at 200–500 characters, regenerated by Oneiros from the resonant chunks.

Which is S5 work. The descriptions in the mesh today are whatever Kadmos wrote
per mention, never consolidated — and that is exactly the epithet problem above.

## What did work: stop showing the whole graph

Answer recall through the model, three runs per arm:

| relations shown | runs | |
|---|---|---|
| none at all | 57 / 52 / 52 | |
| **every edge among the kept nodes** | **50 / 50 / 51** | ← the old default |
| ranked seed-first, not cut | 52 / 52 / 53 | |
| cut to the edges touching a seed | 50 / 53 / 53 | ← shipped |

**The unscoped relation list was the worst arm in six runs of six — worse than
showing no relations at all.** 200 lines of everything-connected-to-everything,
of which a median of 63 touch a seed.

Shipped as two changes with different owners: the Constellation now *ranks*
seed-touching edges first, and the answer renderer *cuts* at them. Ranking alone
does not recover the loss; the non-seed tail still occupies the prompt.

Honest about the size: roughly three points, and the spread is nearly the size of
the effect. The same arm through an ad-hoc renderer scored 56/53/56 — the only
difference was the header wording, and three words are worth two to three points
on this instrument. The figures above are the shipped path's.

## Where the gap actually stands

Retrieval 80%, answer ~53%. The conversion is 66%, from 38% when this round
started — but most of that came from the retrieval work (stratification, seed
count), not from closing the gap itself.

What remains is not a rendering problem. It is that the substrate's read surface
is a per-mention description written by an extractor, where the doctrine
specifies a consolidated one regenerated by Oneiros. **That is S5**, and it is the
same answer PHX-1064 reached from the retrieval side a month ago.
