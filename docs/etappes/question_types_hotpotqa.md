# The lead follows the finding, and on HotpotQA the passages find (PHX-1128)

> **Abstract.** *Question.* PHX-1127 read the answer runs on 2WikiMultihopQA
> by question type and gave an account of what it saw: on the questions that
> do not name their answer the mesh leads five retrieved passages because its
> edges find an answer the passages do not hold, and where both materials hold
> it the two are read alike. That was one dataset, with the pools drawn after
> the figures were in view. Does the account hold on a corpus built another
> way, when what it implies is written down first? *Method.* Five
> expectations, each with the figure that contradicts it, written into the
> ticket on 2026-11-11; the cells they are read from and the points their
> wording left open, committed in this page the same day, before a mesh of
> this corpus was complete. A mesh replayed from the readings of HotpotQA's
> 9,811 passages, cached in August, with no model call. One sitting: 1,000
> questions and five
> arms — no material, five passages by cosine, fifty entities without edges,
> the typed Constellation, the Constellation with its source paragraphs —
> answered by deepseek-chat at temperature 0, named and with no fallback:
> 5,000 answers, no failed call, 0.79 USD under a limit of 5. HotpotQA's 811
> `bridge` questions are the pool `answer_unnamed`, its 189 `comparison`
> questions `answer_named`. *Result.* One expectation is contradicted, two are
> met, two are undecided. **(1) The edges find: contradicted.** On the 811
> questions the typed Constellation holds the gold on 48.8% and the entities
> without edges on 52.9%, four points fewer where five more were expected,
> and it is not ahead on exact match (85 better, 75 worse, p = 0.48). **(3)
> The lead follows the finding: met, with the arms' places exchanged.** The
> passages hold the gold on 77.1% of those questions and lead the typed
> Constellation by 10.7 points, 49.7% against 39.0% (155 / 68, p = 5 × 10⁻⁹).
> **(4) Not finding costs the prior: met.** On the 415 questions whose gold
> the typed Constellation does not hold it is 18 better and 42 worse than the
> model with no material (p = 0.003). **(2) No difference in reading:
> undecided.** Where both hold the gold the arms are 21 / 26 on 338
> questions, 47 discordant pairs against a floor of fifty. **(5) No lead on
> the named-answer questions: undecided.** The typed Constellation is behind
> there, 10 / 23 (p = 0.035), on 33 discordant pairs. Over all 1,000
> questions the passages score 53.9%, as they did in August, the
> Constellation with its sources 47.5%, the typed Constellation 43.9%, the
> entities without edges 42.7%, the prior 34.3%. *Limits.* One sitting, one
> model name, one mesh; (2) and (5) did not reach the count that decides
> them; the pools' names fit this dataset loosely; the passages arm is top-5
> by cosine and no multi-hop retriever; a gold here is often a span, on which
> exact match is harsh, though token F1 pairs the same way on the whole
> pools; the split by whether the gold names a node was made after the
> figures. *Decision.* PHX-1128 is closed. That the mesh's edges find what
> passages do not is a property of 2Wiki's construction; the etappe of
> PHX-1127 carries a dated note and the README, `llms.txt` and `AGENTS.md`
> say so where they quote it. What carried over is the other half of the
> account: the lead goes to the arm whose material holds the answer, and a
> Constellation that does not hold it costs the model what it knew.

**Status:** 2026-11-12, one sitting (18:16 to 18:50 UTC). The two sections
that follow stand as committed on 2026-11-11 (`137d10c`), while the first
replay was running, and the section on the mesh as committed on 2026-11-12
before the sitting (`5cf74df`). How often each arm's material holds the gold needs no
model; over all questions it was counted just before the sitting began, and
by pool it was first seen in the run file.
**Instrument:** `scripts/mesh_qa_mesh_ingest.py --dataset hotpotqa` (replay,
no model call; `IngestRunReport` `01M78DZ3R0NNFNF0F9Q85F2HZF`),
`scripts/mesh_identity_controls.py`, `scripts/mesh_qa_constellation.py` (the
sitting, behind the spend limit of PHX-1124 at its default) and
`scripts/mesh_qa_by_type.py`, all from commit `c190137`. Run file
`data/run_reports/qa_constellation/hotpotqa_1000.json`; everything else under
`data/run_reports/phx1128/`. Fifty entities grown from one seed, five
passages, SQuAD exact match and token F1, `gold_in_context` as each arm's
ceiling, the exact paired sign test: the settings of every 2Wiki sitting.
**Checked:** every figure below that is read from the run file was computed
a second time by a script that imports nothing from this repository and
scores the answers itself (`data/run_reports/phx1128/recompute/`). It
disagrees with the harness on none of the 5,000 rows' exact match or F1 and
with none of the figures. The controls and the split by node name need the
mesh and were computed once.

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

## The mesh and its controls

The mesh is the replay of the readings cached on 2026-08-15, through the
shipped reader and with no model call (`scripts/mesh_qa_mesh_ingest.py`):
9,811 paragraphs, 53,080 entity nodes, 87,431 mentions, 81,029 typed
relations, 1,262,612 edges, one connected component. Three things about the
build belong to the record.

**The first replay failed.** It read every paragraph and then filled the disk
in the pass that links paragraphs sharing entities: one audit transaction per
pair, 152 GB of manifests for 61,306 of 71,009 pairs
([`PHX-1129`](../../phoenix-backlog/PHX-1129.yaml), fixed on this branch). The
incomplete mesh was removed. The mesh read here is the rebuild from the fixed
code, in which the same pass took 18 seconds and the workspace stayed under
1.15 GB. Both builds count 72,703 nodes; the first stopped 9,702 pairs short
of its links.

**Its run report says `partial`.** Seven of the cached readings are empty
(passages 238, 634, 2469, 5139, 6821, 7375 and 9530, counted from zero: *Ken
Riley*, *Queenie Ashton*, *ISS year long mission*, *Hands on in Between*, *Pan
Wenshi*, *Trik Turner*, *Black Nativity*). The replay hands the reader an
empty completion for each, the reader counts a failed reading, and the
`IngestRunReport` carries status `partial` and verdict `failed`. The seven are
in the mesh as paragraphs without entities. None of them is one of the 1,988
supporting passages of the sampled questions. They were not read again, which
would have been a paid extraction; 2Wiki's cache has no empty reading.

**The linker's known defect is in this mesh as it is in 2Wiki's.**
[`PHX-1122`](../../phoenix-backlog/PHX-1122.yaml) estimates that 15% of the
2Wiki mesh's mentions sit on a node that does not bear their name. Counted
here by string — does the paragraph that mentions a node carry the node's
label — 14.9% of this mesh's 81,853 paragraph-and-node pairs do not, against
13.7% of the 2Wiki mesh's by the same count. The count is not the audit: an
alias fails it and is right. But among the twenty-five most-mentioned nodes
are *University of British Columbia* (106 paragraphs, 4 of which carry the
name), *Walt Disney Productions* (92, 17), *Aberdeenshire* (57, 8), *Times
Square* (57, 1) and *Northern Iowa* (55, 1).

The identity controls of PHX-1118 (`scripts/mesh_identity_controls.py`),
beside the 2Wiki mesh built by the same reader (`data/mesh-2wiki-off`):

| | 2Wiki | HotpotQA |
|---|---|---|
| paragraphs | 6,119 | 9,811 |
| entity nodes | 29,786 | 53,080 |
| mentions | 43,118 | 87,431 |
| entity nodes mentioned from two paragraphs or more | 5,725 | 10,535 |
| description, median characters | 79 | 85 |
| entity golds that are the name of a node | 715 of 836 | 448 of 812 |
| — of which the name of two nodes or more | 10 | 15 |

The last two rows are the ones that bear on the answers. On 2Wiki six entity
golds in seven are the name of a node; here 364 of 812 are the name of none.
A gold on this dataset is often a span and not an entity's name — *guitarist*,
*US$13 billion*, *the State House in Augusta*, a full name such as *Vincent
Anthony Guaraldi* — and a Constellation holds such a gold only where some
node's description carries the words.

## What was read

All 5,000 calls were answered by the model the run names (`answered_by`:
deepseek-chat 5,000; served by deepseek-flash), none failed, so the second
reading the rules provide for a failed call was not needed. The sitting spent
0.79 USD of its limit of 5.

Exact match, in percent:

| | questions | prior | passages | entities, no edges | typed Constellation | with sources |
|---|---|---|---|---|---|---|
| **answer_unnamed** (`bridge`) | 811 | 28.0 | 49.7 | 37.7 | 39.0 | 42.9 |
| — its entity golds | 691 | 29.4 | 49.3 | 39.4 | 40.7 | 43.7 |
| — its dates | 120 | 20.0 | 51.7 | 28.3 | 29.2 | 38.3 |
| **answer_named** (`comparison`) | 189 | 61.4 | 72.0 | 64.0 | 65.1 | 67.2 |
| all | 1,000 | 34.3 | 53.9 | 42.7 | 43.9 | 47.5 |
| all, token F1 | 1,000 | 44.2 | 65.7 | 54.1 | 55.3 | 58.9 |

How often the material holds the gold, in percent, with 2Wiki's
unnamed-answer questions beneath for comparison:

| | passages | entities, no edges | typed Constellation | with sources |
|---|---|---|---|---|
| answer_unnamed | 77.1 | 52.9 | 48.8 | 60.4 |
| answer_named | 68.8 | 55.6 | 55.0 | 61.9 |
| 2Wiki, answer_unnamed ([`question_types.md`](question_types.md)) | 35.1 | 33.8 | 56.8 | 69.7 |

The passages arm is PHX-1089's kNN arm on this dataset, which scored 53.9% and
54.1% exact match and 65.6% F1 in August
([`hipporag_answers.md`](hipporag_answers.md)); it scores 53.9% and 65.7%
here. The prior was 30.6% then and is 34.3% now: the model served under the
name has changed since ([`PHX-1125`](../../phoenix-backlog/PHX-1125.yaml)).
The passages arm also shows the least text, 2,900 characters to a prompt on
average against 5,000 for the entities, 5,600 for the typed Constellation and
9,000 with the sources.

## The five expectations

**(1) The edges find — contradicted.** Both of its conditions fail. The typed
Constellation holds the gold on 396 of the 811 unnamed-answer questions and
the entities without edges on 429: 33 questions fewer, where the expectation
was 41 more. On exact match the typed Constellation is 85 better and 75 worse
(39.0% against 37.7%, p = 0.48; token F1 135 / 119), so it is not ahead. On
2Wiki the same pair read 93 / 36 and the ceilings 56.8% against 33.8%. The
edges here change which questions hold their answer, not how many: they bring
the gold into the material on 60 questions where the entities by cosine lack
it, and lose it on 93 where those have it.

**(2) No difference in reading — undecided.** Both the typed Constellation and
the passages hold the gold on 338 of the 811 questions. There the
Constellation is 21 better and 26 worse (p = 0.56): 47 discordant pairs, three
short of the fifty the rule asks before "no difference" may count as met.
Nothing in the cell speaks against the expectation; the rule does not let it
pass. 2Wiki's cell was 17 / 19 on 118 questions.

**(3) The lead follows the finding — met.** The passages hold the gold on 625
of the 811 questions and the typed Constellation on 396, a difference of 28.2
points, so the arm the expectation speaks of is the passages; it is not
behind, it leads, 155 better and 68 worse (49.7% against 39.0%, p = 5 × 10⁻⁹;
the interval the discordant pairs give is 7 to 14 points; token F1 221 /
107). The expectation was written for whichever arm found more. On 2Wiki that
was the Constellation, by 21.7 points of ceiling, and it led.

**(4) Not finding costs the prior — met.** On the 415 unnamed-answer questions
whose gold the typed Constellation does not hold, it is 18 better and 42 worse
than the same model with no material. The rule has no significance bar; the
sign test gives p = 0.003. On 2Wiki the cell read 4 / 18. Beside it, on the
questions each does not hold the gold for, the passages are 7 / 15 on 186
(p = 0.13) and the entities without edges 21 / 32 on 382 (p = 0.17): the same
direction in all three, clear of chance in the Constellation alone, as on
2Wiki. Where the typed Constellation does hold the gold it is 141 better and
28 worse than the prior.

**(5) No lead on the named-answer questions — undecided.** On the 189
`comparison` questions the typed Constellation is 10 better and 23 worse than
the passages (65.1% against 72.0%, p = 0.035). It is not ahead; it is behind.
But the two arms differ on 33 questions, and the rule counts the expectation
as met only from fifty, so it is recorded as undecided, as written. On 2Wiki
the pool read 73 / 93.

Each pairing once more by which of its two arms held the gold, on the
unnamed-answer questions, better / worse with the questions of the cell in
brackets:

| answer_unnamed | both hold it | only the first | only the second | neither |
|---|---|---|---|---|
| typed vs passages | 21 / 26 (338) | 35 / 0 (58) | 4 / 128 (287) | 8 / 1 (128) |
| typed vs entities without edges | 39 / 22 (336) | 33 / 0 (60) | 4 / 46 (93) | 9 / 7 (322) |
| sources vs passages | 33 / 31 (420) | 39 / 0 (70) | 1 / 99 (205) | 5 / 3 (116) |
| 2Wiki, typed vs passages, September | 17 / 19 (118) | 81 / 6 (178) | 2 / 33 (65) | 0 / 8 (160) |

The table is 2Wiki's with the two outer columns exchanged. There the
Constellation held the answer on 178 questions where the passages did not,
against 65 the other way; here it is 58 against 287.

## Beside the five

None of this was written down beforehand.

- **The Constellation with its sources** (PHX-1114) is 3.9 points above the
  typed Constellation on the unnamed-answer questions (53 / 21, p = 0.0003;
  14 / 3 on the dates, 39 / 18 on the entity golds) and holds the gold on
  60.4% of them. It is still behind the passages: 78 / 133 there (p = 0.0002)
  and 6.4 points over all questions (90 / 154, p = 5 × 10⁻⁵). On 2Wiki it was
  the strongest arm, 6.8 points ahead of the passages.
- **Dates.** On the pool's 120 dates the typed Constellation scores 29.2% and
  the passages 51.7% (9 / 36, p = 7 × 10⁻⁵); it holds a date on 24.2% of the
  questions, the passages on 73.3%. This is the reversal PHX-1127 found on
  2Wiki's 52 dates.
- **Against the prior** the typed Constellation gains 9.6 points over all
  questions (185 / 89) and the passages 19.6 (250 / 54).
- **Yes or no.** All 63 yes/no questions are in the named-answer pool, and no
  arm moves them: 87.3% with no material, 85.7% with passages, 82.5% with the
  typed Constellation (3 / 5 against the passages). The collapse PHX-1110 saw
  on 2Wiki's yes/no questions in September is not here.
- **Where the Constellation and its own entities without edges both hold the
  gold, the Constellation is ahead**, 39 / 22 on 336 questions (p = 0.04; on
  2Wiki 15 / 10 on 137). One split among many, uncorrected.
- **The edges over all questions** are worth 1.2 points of exact match
  (102 / 90, p = 0.43), against 3.6 on 2Wiki.

**By whether the gold is the name of a node.** The identity controls say that
364 of the 812 entity golds name no node, so the unnamed-answer questions were
split three ways after the figures were in: the entity golds that are the name
of a node, those that are not, and the dates. The split is post hoc and is
given for what it suggests.

| answer_unnamed | questions | passages hold | typed holds | passages | typed | typed vs passages |
|---|---|---|---|---|---|---|
| entity gold, the name of a node | 373 | 80.4% | 73.5% | 63.3 | 61.4 | 43 / 50, p = 0.53 |
| entity gold, the name of no node | 318 | 74.5% | 29.2% | 33.0 | 16.4 | 16 / 69, p = 5 × 10⁻⁹ |
| date | 120 | 73.3% | 24.2% | 51.7 | 29.2 | 9 / 36, p = 7 × 10⁻⁵ |
| 2Wiki: entity gold, the name of a node | 350 | 36.6% | 67.1% | 25.4 | 40.6 | 92 / 39 |
| 2Wiki: entity gold, the name of no node | 119 | 26.9% | 46.2% | 11.8 | 6.7 | 5 / 11 |
| 2Wiki: date | 52 | 44.2% | 11.5% | 32.7 | 7.7 | 3 / 16 |

Where the gold is the name of a node the two arms are level on HotpotQA, and
nearly all of the passages' lead is on the spans and the dates: 53 and 27 of
the 87 questions it is ahead by. And where the gold is the name of a node,
the typed Constellation holds it about as often on the two corpora, 67% and
74% of the time. What differs is the other arm: five
passages by cosine hold such an answer on 37% of 2Wiki's questions and on 80%
of HotpotQA's.

## What it means

**The account of PHX-1127 had two halves, and one of them carried.** That the
lead goes to the arm whose material holds the answer was met, with the arm
changed; that the two are read alike where both hold it was not contradicted
and not decided; that a Constellation which does not hold the answer costs the
model what it knew was met a second time. That the mesh is the arm that finds,
and that its edges are what finds, was contradicted on both of its conditions.
By the ticket's own words the reading of PHX-1127 is then a property of
2Wiki's construction.

**What 2Wiki's lead was made of.** On 2Wiki's unnamed-answer questions five
passages by cosine hold the answer 35% of the time; on HotpotQA's, 77%. A
2Wiki question is generated from two Wikidata relations and names the first
entity only, so the paragraph that carries the answer shares little with the
question. A HotpotQA question was written by a person with both paragraphs in
view. That is a reading of the two constructions and was not measured here.
What was measured agrees with it at two levels: PHX-1089 found graph-ranked
passages worth 5.0 points over kNN on 2Wiki and 0.9, not significant, on
HotpotQA, and on the questions that do not name their answer the edges are
worth 11 points of exact match on one corpus and one on the other. Where
plain retrieval already finds the paragraph, the edges have nothing left to
find.

**A Constellation carries names.** Its material is fifty entities, each with a
description of some 85 characters, and the relations among them. An answer
that is an entity's name is in it three times in four; a span or a date is in
it little more than one time in four, and in a passage three times in four.
The source paragraphs repair part of that (PHX-1114: 48.8% to 60.4% of the
questions) and accrued descriptions were built to repair more of it
(PHX-1118, off by default, not run here).

**Not finding costs the prior, on two corpora now.** 4 / 18 on 2Wiki, 18 / 42
here: shown fifty entities that do not carry the answer, the model gives up an
answer it would have given unaided more often than it gains one. Five passages
that do not carry it show no clear effect on either corpus (13 / 14 and
7 / 15). Nothing in the harness or in `mesh_ask` acts on this yet.

**For the open question of PHX-1114**, whether `mesh_ask` should carry source
paragraphs, this etappe adds a second corpus and no decision: here the
paragraphs are worth 3.9 points on the unnamed-answer questions and the arm
that has them is still 6.4 points behind five plain passages.

## What this does not show

- **One sitting.** One model name, one mesh, one set of 1,000 questions, no
  repeat. The rule was that the first sitting in which the named model answers
  is the one that is read, and it is. August's and November's passages arms
  agree to a tenth of a point, which says the instrument is steady on that
  arm and nothing about the others.
- **Two of the five are undecided**, both for the count of discordant pairs:
  47 and 33 against a floor of fifty. A repeat could move (2) across the
  floor in either direction; (5) is judged on 189 questions on which the two
  arms agree 156 times, and this sample cannot decide it as the rule is
  written.
- **The pools' names fit loosely here.** 142 of the 189 `comparison`
  questions name their answer or are answered yes or no, against 479 of 479
  on 2Wiki, and 15 of the 811 `bridge` questions do carry their gold. The
  mapping was fixed before the run and was not redrawn.
- **The passages arm is plain dense retrieval**, top-5 by cosine, and it is
  the leading arm. A retriever that follows a second hop would raise its
  ceiling further, not the Constellation's.
- **The settings are 2Wiki's.** Fifty entities grown from one seed, with no
  setting tuned to this corpus; a `comparison` question names two entities
  and the Constellation grows from one.
- **The mesh has the defects the section above lists**: the linker's naming
  guard (PHX-1122), seven paragraphs unread, accrual off. How much of the
  ceiling they cost was not measured.
- **`gold_in_context` is a string match.** It says the gold stood in the
  material, not that it stood there as the answer; for a yes or a no it says
  next to nothing.
- **Exact match on spans.** A gold such as *the State House in Augusta* is
  missed by a right answer worded otherwise. Token F1 pairs the same way on
  the three whole-pool comparisons (135 / 119, 107 / 221 and, on the named
  pool, 11 / 28); the cells were read on exact match only.
- **The split by node name is post hoc**, and so is every figure under
  "Beside the five". The five expectations are five tests chosen beforehand;
  the run's tables hold more than a hundred that were not.

## Decision

PHX-1128 is closed: (1) contradicted, (3) and (4) met, (2) and (5) undecided.

By the ticket, the reading of PHX-1127 is a property of 2Wiki's construction
and the documents that quote it say so:
[`question_types.md`](question_types.md) carries a dated note beneath its
abstract and beneath the two statements this run answers, and the sentences in
`README.md`, `llms.txt` and `AGENTS.md` that quote the lead on the
unnamed-answer questions now give HotpotQA's figures beside it. Nothing in the
harness changes; it reports every run by type and pool as before.

[`PHX-1129`](../../phoenix-backlog/PHX-1129.yaml), the defect that failed the
first replay, was fixed on the way and is closed.

Three things this run leaves, none of them filed as work here. The fall below
the prior has been measured twice and nothing acts on it. Seven cached
readings of HotpotQA are empty. And building the 5,000 prompts takes 24
minutes on this mesh, 1.4 seconds a question, of a sitting of 33 (timed in a
run that calls no model); why has not been looked into.

## How to re-run

The mesh needs no key: it is a replay of `kadmos_readings_hotpotqa.jsonl`, about
four and a half hours on a laptop and 1.1 GB. The sitting is 5,000 calls and
needs a DeepSeek key; it runs behind the spend limit of PHX-1124 at its
default of 5 USD. The reading needs neither.

```bash
python scripts/mesh_qa_mesh_ingest.py --dataset hotpotqa --root data/mesh-hotpotqa
python scripts/mesh_identity_controls.py --root data/mesh-hotpotqa --dataset hotpotqa \
    --json data/run_reports/phx1128/controls_hotpotqa.json

THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
python scripts/mesh_qa_constellation.py --root data/mesh-hotpotqa --dataset hotpotqa \
    --arms closed_book,passages,vector_only,constellation_typed,constellation_sources \
    --out data/run_reports/qa_constellation/hotpotqa_1000.json

python scripts/mesh_qa_by_type.py data/run_reports/qa_constellation/hotpotqa_1000.json \
    --json data/run_reports/phx1128/by_type.json
```

The first prints the replay's counts and the path of its `IngestRunReport`
(status `partial`, for the seven empty readings). The third prints the run by
type and pool and writes the run file with `by_type`, `paired_by_type` and
`paired_in_pool`; the five expectations are read from the cells named in the
table above. The last re-reads the file without calling a model.

Tickets: [`PHX-1128`](../../phoenix-backlog/PHX-1128.yaml),
[`PHX-1129`](../../phoenix-backlog/PHX-1129.yaml); from
[`PHX-1127`](../../phoenix-backlog/PHX-1127.yaml).
