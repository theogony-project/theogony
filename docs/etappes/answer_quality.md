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

## What follows

1. **The answer step is the bottleneck, not retrieval.** 77% reaches the working
   set and 46% reaches the answer. Every point of retrieval work since PHX-1068
   has been spent upstream of the larger loss.
2. **This corpus cannot settle whether the graph helps.** Canonical Greek
   mythology, 47 questions, and a noise floor as large as the effect. The
   HippoRAG trio (3 × 1000 questions with gold answers, already on disk) can.
3. **No claim here rests on one arm's number.** They rest on differences, and the
   differences under five points are not claims.
