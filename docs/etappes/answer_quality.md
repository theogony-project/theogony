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
