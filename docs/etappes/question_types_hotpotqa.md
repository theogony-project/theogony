# The by-type reading on a second corpus: HotpotQA (PHX-1128)

**Status:** 2026-11-11, draft written while the mesh is being built. No answer
from a mesh of this corpus exists yet; this page is committed before the
sitting so that how the five expectations are judged is on record ahead of the
figures. The abstract, the results and the decision follow.

## How the five expectations are judged

The expectations and their decision rules are
[`PHX-1128`](../../phoenix-backlog/PHX-1128.yaml)'s, written on 2026-11-11 with
[`question_types.md`](question_types.md) and unchanged since. What follows adds
nothing to them; it fixes, before any figure, the cell each is read from and
the points the ticket's wording leaves open.

One sitting: the sampled 1,000 questions of HippoRAG's HotpotQA release (seed
0, the set PHX-1089 used), the arms `closed_book`, `passages`, `vector_only`,
`constellation_typed` and `constellation_sources`, fifty entities grown from
one seed, five passages, deepseek-chat at temperature 0 with no fallback
provider — the settings of every 2Wiki sitting. "Holds" is `gold_in_context`:
the gold string stands in the material the arm showed. A test is the exact
two-sided paired sign test on exact match; an arm is *ahead* when it is better
on more questions than it is worse on and that test gives p < 0.05.
`answer_unnamed` is the 811 `bridge` questions, `answer_named` the 189
`comparison` questions (`qa_datasets.POOLED_TYPES`, PHX-1127).

| | read from | met | contradicted | undecided |
|---|---|---|---|---|
| (1) the edges find | `answer_unnamed`: `gold_in_context` of `constellation_typed` and of `vector_only`; the pair `constellation_typed` vs `vector_only` | the typed Constellation holds the gold on at least five points more of the 811 questions (41 questions or more) **and** is ahead | either fails | — |
| (2) no difference in reading | `answer_unnamed`, the questions whose gold both `constellation_typed` and `passages` hold; that pair | neither is ahead, on fifty discordant pairs or more | one is ahead | neither is ahead, on fewer than fifty |
| (3) the lead follows the finding | `answer_unnamed`: `gold_in_context` of `constellation_typed` and of `passages`; that pair on all 811 | the arm that holds the gold on five points more is not behind the other at p < 0.05; or, within five points, neither is ahead (fifty discordant pairs or more) | the arm that holds it more is behind at p < 0.05; or, within five points, one is ahead | within five points, neither ahead, fewer than fifty discordant pairs |
| (4) not finding costs the prior | `answer_unnamed`, the questions whose gold `constellation_typed` does not hold; the pair `constellation_typed` vs `closed_book` | worse on more questions than better | better on at least as many | — |
| (5) no lead on the named-answer questions | `answer_named`: the pair `constellation_typed` vs `passages` | the typed Constellation is not ahead, on fifty discordant pairs or more | it is ahead | it is not ahead, on fewer than fifty |

Four points the wording leaves open, settled here:

- **A significant difference contradicts whatever the count of discordant
  pairs.** The fifty-pair floor is the ticket's guard against granting "no
  difference" to a test with too few questions; it qualifies *met* only.
- **Five points are counted in questions**: a difference of 41 or more of the
  811.
- **(4) has no significance bar**, as written: more worse than better is met,
  anything else contradicted. Its p-value is reported beside it.
- **A failed call.** A call that fails three times is an empty answer and
  scores zero (the harness's rule since PHX-1123). If any of the 5,000 fails,
  the five verdicts are read a second time with the affected questions removed
  from every arm; if a verdict differs between the two readings the sitting is
  repeated, otherwise the first reading stands.

The first sitting in which the named model answers is the one that is read.
Everything else in the run — the Constellation with its sources, the answer
kinds, token F1, the other pairings — is read beside the five and is not part
of what was written down beforehand.

## The pools on this dataset

Read from the question file alone, before the sitting. The pooling of
PHX-1127 is named for whether a question names its answer, and on 2Wiki the
property is exact: none of the 521 golds of the first pool stands in its
question, and all 369 golds of the second that are not yes or no do. On
HotpotQA, whose questions and answers people wrote, it is close on one side and
loose on the other.

| | questions | entity / date / yes-no golds | gold stands in its question |
|---|---|---|---|
| `bridge` → `answer_unnamed` | 811 | 691 / 120 / 0 | 15 of 811 |
| `comparison` → `answer_named` | 189 | 121 / 5 / 63 | 79 of the 126 that are not yes or no |

Of the 47 comparison golds that do not stand in their question, some are a
longer form of a name the question carries (*Pavel Sergeyevich Alexandrov* for
*Pavel Alexandrov*) and some are a property two named entities share (*What
profession do Raj Kapoor and Mike Cahill share?* — *director*). So 142 of the
189 name their answer or are answered yes or no by the string match (case,
punctuation and articles aside), against 479 of 479 on 2Wiki. The mapping
stands as written on 2026-11-11; the looseness is a limit of expectation (5),
not a reason to redraw the pool.

Two more differences from 2Wiki that bear on what the figures can mean. Every
question here has exactly two supporting passages (on 2Wiki 765 have two and
235 four), and a passage is longer (median 83 words against 47). And the golds
are spans a person marked — *Finnmark county,*, *the Queen's gaoler* — so exact
match is harsher here and token F1 is given beside it.

Tickets: [`PHX-1128`](../../phoenix-backlog/PHX-1128.yaml); from
[`PHX-1127`](../../phoenix-backlog/PHX-1127.yaml).
