# What the tie with passages was made of (PHX-1127)

> **Abstract.** *Question.* PHX-1110 reported two totals over 1,000 questions
> of 2WikiMultihopQA: the edges of the mesh are worth 3.6 points of exact match
> over the same entities without them, and against five retrieved passages the
> typed Constellation is a tie. The dataset labels every question with a type.
> What do the totals look like by that label? *Method.* No new run: the answer
> rows of the five runs on record, from three sittings, joined to the dataset's
> `type` by question id, read by the four types and by two pools of them —
> `answer_unnamed` (compositional and inference, 521 questions: the answer is
> an entity or a date the question does not name) and `answer_named`
> (comparison and bridge-comparison, 479: the answer is one of two entities
> the question names, or yes or no). Exact match, the paired sign test; each
> pool read once more by which arm had the answer in its material and by the
> shape of the gold. *Result.* On the questions that do not name their answer
> the typed Constellation, which shows the reader no source text, beats five
> passages in every sitting: 29.6% against 23.0% in September (100 better, 66
> worse, p = 0.010), 30.3% against 21.3% in October (107 / 60, p = 0.0003).
> The lead is on entity answers (103 / 44) and reverses on the pool's 52 dates
> (4 / 16). The edges are worth 11 points on that pool (93 / 36 and 96 / 35,
> p < 10⁻⁶) and cost 10 on plain comparisons (13 / 39, p = 0.0004); the
> published +3.6 is the size-weighted mean of +10.9 on one pool and −4.4 on
> the other, and the −4.4 is not significant. The lead is one of finding, not
> of reading: where both materials hold the answer the two arms are even
> (17 / 19), and the Constellation's lead is the 178 questions only it found
> against the 65 only the passages did. In the one sitting that measured the
> prior, the Constellation scored below it where its material lacked the
> answer (4 / 18, p = 0.004). The questions that name their answer are
> answered right 58% of the time with no material at all, and the passages
> arm drifted seven points on them between September and October and under
> two on the others. *Limits.* The pools were chosen after the four types had
> been read, and of the figures above only the edges' effect stands clear of
> a bound for the number of tests looked at; one dataset, one set of
> questions, one mesh, one model name; the passages arm is top-5 by cosine,
> not a multi-hop retriever; 2Wiki's questions are built from Wikidata
> relations over a corpus of one paragraph per article, the ground a graph of
> entities is best on. *Decision.* The harness reports every run by type and
> pool from here on, with the unnamed-answer questions as the figure to read
> first; the same reading of HotpotQA is PHX-1128, with decision rules written
> down before the run.

*Read on HotpotQA 2026-11-12 (PHX-1128,
[`question_types_hotpotqa.md`](question_types_hotpotqa.md)): the same reading
on a corpus built another way, with five expectations written into the
ticket before the run. That the edges find did not carry. On HotpotQA's 811
questions that do not name their answer the typed Constellation holds the
gold less often than the entities without edges (48.8% against 52.9%) and is
not ahead of them (85 / 75), and the passages, which hold it on 77.1%, lead
by 10.7 points (155 / 68, p = 5 × 10⁻⁹). By the ticket's rule the lead
reported here is a property of 2Wiki's construction. Two things did carry:
the lead went to the arm whose material held the answer, and where the
Constellation did not hold it, it scored below the prior again (18 / 42).
Whether the two arms are read alike where both hold the answer stayed
undecided (21 / 26, on 47 discordant pairs against a floor of fifty), and so
did the named-answer questions (10 / 23, on 33).*

**Status:** 2026-11-11, read from runs on record; no model was called.
**Instrument:** `scripts/mesh_qa_by_type.py` over run files of
`scripts/mesh_qa_constellation.py` under `data/run_reports/qa_constellation/` —
`2wiki_1000.json` and `2wiki_1000_repeat.json` (2026-09-16, PHX-1110),
`2wiki_1000_yn_sources_v2.json` (2026-10-19, PHX-1113/1114),
`2wiki_1000_phx1118_off.json` and `_on.json` (2026-10-26, PHX-1118) — and
`scripts/mesh_qa_pair_runs.py` for one arm across two runs. Question types
from the `type` field of HippoRAG's 2WikiMultihopQA release. Everything else
is the earlier etappes': deepseek-chat at temperature 0, fifty entities grown
from one seed, five passages, SQuAD exact match against the answer key,
`gold_in_context` (the gold string stands in the material) as each arm's
ceiling, the exact paired sign test. Outputs: `data/run_reports/phx1127/`.

## Two populations under one total

2WikiMultihopQA has four question types.

| type | questions | asks for | example shape |
|---|---|---|---|
| compositional | 413 | an entity or a date reached through two relations | the place of birth of the director of a film |
| inference | 108 | an entity reached through a relation the corpus states in two steps | someone's paternal grandfather |
| comparison | 244 | one of two entities the question names, or yes or no | which of two people was born first |
| bridge_comparison | 235 | the same, after one hop from each named entity | which of two films has the older director |

They are pooled here by whether the question names its answer
(`qa_datasets.POOLED_TYPES`). In **`answer_unnamed`**, the first two types,
it does not: none of the 521 golds stands in its question. In
**`answer_named`**, the last two, it does: all 369 golds that are an entity or
a date stand in their question, and the other 110 are yes or no (a match of
the gold in the question, case and punctuation aside). With no material the
model answers
11.3% of the first pool and 58.2% of the second. All 110 yes/no questions of
the set are in the second pool, and 52 of its 54 dates are compositional.

The line is not how many paragraphs an answer takes. A bridge_comparison
takes a hop from each entity it names and then compares, and it behaves below
as a comparison does, not as a compositional question does.

## What was read

Exact match, in percent. September and October are the same mesh
(`data/mesh-2wiki`), the same questions and the same prompts. The October run
on the rebuilt mesh (`data/mesh-2wiki-off`) is left out of this table: it
differs from the one beside it by at most 0.4 on the pooled rows and 2.5 on a
single type.

| | questions | prior | passages | entities, no edges | typed Constellation | with sources |
|---|---|---|---|---|---|---|
| | | Sep | Sep / Oct | Sep / repeat | Sep / Oct | Oct |
| compositional | 413 | 10.9 | 21.1 / 19.4 | 15.7 / 15.0 | 27.4 / 28.1 | 36.1 |
| inference | 108 | 13.0 | 30.6 / 28.7 | 29.6 / 28.7 | 38.0 / 38.9 | 43.5 |
| comparison | 244 | 62.3 | 82.8 / 82.8 | 78.3 / 78.3 | 67.6 / 75.8 | 77.5 |
| bridge_comparison | 235 | 54.0 | 44.7 / 58.7 | 49.8 / 51.9 | 51.9 / 59.1 | 57.0 |
| **answer_unnamed** | 521 | 11.3 | 23.0 / 21.3 | 18.6 / 17.9 | 29.6 / 30.3 | 37.6 |
| **answer_named** | 479 | 58.2 | 64.1 / 71.0 | 64.3 / 65.3 | 59.9 / 67.6 | 67.4 |

### Against five passages

Question for question, the typed Constellation against the passages arm,
better / worse on exact match:

| | Sep 16 | Oct 19 | Oct 26, rebuilt mesh |
|---|---|---|---|
| answer_unnamed | 100 / 66, p = 0.010 | 107 / 60, p = 0.0003 | 108 / 62, p = 0.0005 |
| — its 469 entity answers | 97 / 50 | 103 / 44 | 104 / 46 |
| — its 52 dates | 3 / 16, p = 0.004 | 4 / 16, p = 0.012 | 4 / 16 |
| answer_named | 73 / 93, p = 0.14 | 69 / 85, p = 0.23 | 67 / 83, p = 0.22 |
| compositional | 74 / 48 | 78 / 42 | 79 / 43 |
| inference | 26 / 18 | 29 / 18 | 29 / 19 |
| comparison | 17 / 54, p = 10⁻⁵ | 22 / 39, p = 0.04 | 22 / 40, p = 0.03 |
| bridge_comparison | 56 / 39, p = 0.10 | 47 / 46 | 45 / 43 |

On the questions that do not name their answer that is +6.5, +9.0 and +8.8
points; the interval the discordant pairs give around October's figure is
roughly 4 to 14 points, around September's 2 to 11. **The lead is on entity
answers and reverses on dates**: the Constellation reaches the entity and does
not carry its date, which PHX-1110 had found on the total (9% against 33%). On
plain comparisons the passages are ahead in every sitting; on comparison
chains the Constellation was ahead in September, not significantly, and the
two arms are level in October. The tie PHX-1110 reported — +1.4, not
significant — is a lead of 6.5 on 521 questions and a deficit of 4.2 on 479.
Token F1 pairs the same way on the first pool (145 / 106, 154 / 96, 151 / 94).

With the source paragraphs laid beneath it (PHX-1114) the Constellation is
16.3 points ahead of the passages on the unnamed-answer questions (123 / 38
and 122 / 37), no longer behind on their dates (10 / 6), and about 3 behind
on the named-answer ones (65 / 82 and 66 / 80, neither significant); with the
yes/no sentence added it is a point ahead there (78 / 72, 78 / 73).

### What the edges are worth

`constellation_typed` against `vector_only`: the same node store, the same
embedding, the same fifty-entity budget, with and without the relations.

| | Sep 16 | repeat |
|---|---|---|
| answer_unnamed | 93 / 36, p = 5 × 10⁻⁷ (+10.9) | 96 / 35, p = 9 × 10⁻⁸ (+11.7) |
| answer_named | 54 / 75, p = 0.08 (−4.4) | 52 / 73, p = 0.07 (−4.4) |
| compositional | 74 / 26 (+11.6) | 76 / 25 (+12.3) |
| inference | 19 / 10 (+8.3) | 20 / 10 (+9.3) |
| comparison | 13 / 39, p = 0.0004 (−10.7) | 13 / 38, p = 0.0006 (−10.2) |
| bridge_comparison | 41 / 36 (+2.1) | 39 / 35 (+1.7) |

Weighted by the two pools' sizes, +10.9 and −4.4 give +3.6, and +11.7 and −4.4
give +4.0: the two figures PHX-1110 reported for the edges. That is
arithmetic, and it holds whatever the halves' significance; of the halves,
the gain stands and the pooled loss does not (p = 0.08 and 0.07). Inside the
loss, plain comparisons lose ten points, significantly, and comparison chains
gain two, not significantly. A third run at a budget of twenty-five entities
(`2wiki_1000_topk25.json`, the same sitting) reads +9.0 and −7.3 (80 / 33 and
52 / 87, the latter p = 0.004).

### A difference in finding

Each arm's material either holds the gold string or does not
(`gold_in_context`). On the unnamed-answer questions it holds it for 33.8% of
the questions with the entities without edges, 35.1% with five passages, 56.8%
with the typed Constellation, 69.7% with the Constellation and its sources.
Splitting each pairing by which of its two arms held the answer puts the two
arms on the same questions:

| answer_unnamed, better / worse | both hold it | only the first | only the second | neither |
|---|---|---|---|---|
| typed vs passages, Sep 16 | 17 / 19 (118) | 81 / 6 (178) | 2 / 33 (65) | 0 / 8 (160) |
| typed vs passages, Oct 19 | 17 / 19 (118) | 87 / 0 (178) | 2 / 35 (65) | 1 / 6 (160) |
| typed vs entities without edges, Sep 16 | 15 / 10 (137) | 76 / 3 (159) | 1 / 16 (39) | 1 / 7 (186) |
| sources vs passages, Oct 19 | 19 / 13 (149) | 102 / 3 (214) | 0 / 18 (34) | 2 / 4 (124) |

(In brackets, the questions in the cell.) Where both materials hold the answer
the Constellation and the passages are even, and so are the Constellation and
its own entities without the relations. The whole lead is that the
Constellation holds the answer on 178 questions where the passages do not,
against 65 the other way; the edges' eleven points are 159 against 39. What
these files cannot say is which paragraph was missing; the reading that fits is
that five passages by cosine hold the paragraph of the entity the question
names and seldom the second one, whose subject it does not name, and that
Spreading Activation reaches that one along an edge.

**Where its material lacked the answer, the Constellation scored below the
prior.** September is the one sitting with a closed-book arm. On the 225
unnamed-answer questions whose gold the typed Constellation did not hold, it
is 4 better and 18 worse than the same model with no material (p = 0.004);
the passages, on the 338 they did not hold it for, are 13 and 14, and the
entities without relations 12 and 23 (p = 0.09). One sitting, and a p-value
that does not pass the bound below; why a list of fifty entities should cost
the model what it knew, where five passages do not, is not tested here.

On the named-answer questions the split reads differently in one cell.
Where both hold the answer the Constellation is *ahead* of the passages
(62 / 31 in September, 53 / 30 in October, of 311) and of its own entities
without relations (46 / 22 of 312). It is behind on the pool for two reasons.
The passages hold the answer on 60 questions where it does not (0 / 36,
1 / 40), and the entities by cosine on 58 (0 / 31); the answer there is an
entity the question names, and why the Constellation should lack it is not
measured — a conjecture is that it grows from one seed (`k_seeds = 1` in
every run here) while such a question names two entities. And where neither
holds it — 105 questions, every one of them a yes/no question, whose gold
stands in no material but for a handful where the word occurs — the
Constellation was 9 better and 26 worse than the passages in September
(p = 0.006) and 14 and 15 in October: the yes/no collapse PHX-1110 found,
which is a matter of how the material is read, not of what it holds.

Each arm also has a rate at which the answer is read out where it stands — on
the unnamed-answer questions 50 to 51% for passages, 50 to 51% for the typed
Constellation, 52% with sources, 42 to 44% for the entities without edges.
These are over each arm's own found questions, which differ; the split above
is the comparison on common ground.

### The repairs and the structural edges, by pool

- **The yes/no sentence (PHX-1113) acts on the named-answer questions only.**
  On the typed Constellation 33 / 20 and 40 / 23 there (p = 0.10, 0.04),
  10 / 9 and 8 / 9 on the other pool; on the Constellation with sources
  41 / 18 and 34 / 15 (p = 0.004, 0.009) against 10 / 12 and 9 / 10.
- **The source paragraphs (PHX-1114) act on the unnamed-answer questions
  only**, and beyond the dates they were built for: 53 / 15 and 52 / 13 over
  the typed Constellation (+7.3, +7.5 points, p < 10⁻⁵) — 18 / 2 on the dates
  and 35 / 13 on the entity answers — against 34 / 35 and 32 / 30 on the
  named-answer questions.
- **The structural edges' cost (PHX-1110: 2.9 points) is a cost on the
  named-answer questions.** Without them the Constellation is 51 / 18 better
  there (p = 0.0001), 35 / 9 of it on bridge_comparison; on the other pool
  12 / 16.
- **Accrual (PHX-1118), the build with it against the build without, paired
  across the two runs:** the typed Constellation 61 / 27 on the unnamed-answer
  questions (30.3% to 36.9%, p = 0.0004) and 43 / 28 on the named-answer ones
  (p = 0.10); the passages arm 3 / 0 and 4 / 4. Its material then holds the
  answer on 67.2% of the unnamed-answer questions, and the reversal on dates
  shrinks to 5 / 11. Accrual is off by default and its identity cost is
  PHX-1120's and PHX-1121's subject; with it on, the typed Constellation is
  14.8 points ahead of the passages on the unnamed-answer questions
  (126 / 49) and level on the others (80 / 81).

### The drift between sittings is in the named-answer questions

PHX-1110 noted that whatever answers behind `deepseek-chat` is not the same
model from month to month, and PHX-1118 therefore pairs only within a sitting.
The passages arm is the control: same passages, same prompt, September 16
against October 19, question for question.

| passages, Sep → Oct | exact match | better / worse |
|---|---|---|
| answer_unnamed | 23.0 → 21.3 | 5 / 14, p = 0.06 |
| answer_named | 64.1 → 71.0 | 57 / 24, p = 0.0003 |
| — of which bridge_comparison | 44.7 → 58.7 | 47 / 14, p = 3 × 10⁻⁵ |

The typed Constellation moved alike (59.9 → 67.6 on the named-answer
questions, 50 / 13; 29.6 → 30.3 on the others, 14 / 10), but between the two
sittings the order in which the Constellation lists its seeds was changed
(the review of PHX-1114, 2026-10-19), so that arm's movement is not the
model's alone. In September the passages arm scored below the prior on
bridge_comparison (46 better, 68 worse, p = 0.049) and so did the shipped
Constellation (31 / 62, p = 0.002); no prior was measured in October. A
question whose answer is one of two names it carries is answered by the
model's disposition as much as by the material, and the disposition moved.

## What it means

**The mesh's measured advantage is in finding an answer the question does not
name.** That is the nearest thing on record to the bet the project is named
for — that structure carries what no single source states — and it is narrower
than the bet in three ways the figures themselves show. The second paragraph
is in the corpus, and a retriever that follows the first hop would find it
too. The advantage is not there wherever a hop is needed: a comparison chain
takes two and shows none. And it stops at the entity: on the dates of the
same questions the passages lead four to one.

*Read on HotpotQA 2026-11-12 (PHX-1128): not there. Five passages by cosine
hold the answer on 77% of HotpotQA's such questions, against 35% here, and
the typed Constellation on 49%; the passages lead. The advantage was in what
plain retrieval misses on 2Wiki.*

**Two of the project's headline figures were means over opposite signs.** The
tie with passages and the 3.6 points of the edges are both correct, and both
describe a population that does not exist: 521 questions on which the edges
are worth 11 points and the Constellation leads the passages by 6.5 to 9.0,
and 479 on which plain comparisons lose and comparison chains do not move.

**Not finding may cost more than the absence of a gain.** In the one sitting
that can show it, the Constellation fell below the prior where it did not hold
the answer. That is a single figure at p = 0.004; PHX-1128 asks it again.

*Read on HotpotQA 2026-11-12 (PHX-1128): it did again, 18 better and 42
worse than the prior on the 415 questions whose answer the typed
Constellation did not hold (p = 0.003).*

**The named-answer half is a poor instrument for this substrate.** Its prior
is 58%, the best arm clears it by six points in September, and it carries the
drift of the model. The two repairs of October each fixed one half: the
sentence the named-answer questions, the paragraphs the others.

**For the open question of PHX-1114** — whether `mesh_ask` should carry source
paragraphs, which the doctrine rules out ([`answer_quality.md`](answer_quality.md),
"Passages are not available, by doctrine") — this etappe adds figures and no
decision: on the unnamed-answer questions the paragraphs are worth 7 points on
top of the typed Constellation, they raise how often the answer is held from
57% to 70%, and they are what removes the reversal on dates.

## What this does not show

- **The pools are post hoc.** The four types are the dataset's; pooling them
  two and two was decided after their rows had been read, and the property the
  pools are named for was checked after that. More than a hundred paired
  tests were looked at — some eighteen pairings of arms across the runs, each
  by six groups, and the splits of this etappe on top. Against a bound for a
  hundred (p < 0.0005) the edges' effect on the unnamed-answer questions
  stands (p < 10⁻⁶, twice) and October 19's lead over passages is at the line
  (0.0003); October 26's lead (0.0005), September's (0.010), the reversal on
  dates (0.004 to 0.012) and the fall below the prior (0.004) do not pass it.
  The reversal on dates is at least not new: PHX-1110 found it on the total.
  No such bound accounts for the pools having been drawn with the data in
  view; PHX-1128 is what does.
- **Five runs are not five samples.** Three sittings, one set of 1,000
  questions, one mesh and a rebuild of it, one model name. The two October
  runs are near repeats of each other, as are the two of September. What
  varies between September and October is the model served under the name —
  and one change in the harness, above — which is why the agreement across
  them counts for something and why it is not a replication.
- **Two run files in the same directory are not in the tables.**
  `2wiki_1000_topk25.json` (September, twenty-five entities) is quoted above
  for the edges; `2wiki_1000_yn_sources.json` is the first October run, whose
  sources arm ranked its paragraphs wrongly (PHX-1114). Both are in
  `by_type.json`; the typed Constellation against passages reads 107 / 60 and
  68 / 81 in the second, as in its successor.
- **The passages arm is plain dense retrieval**: top-5 by cosine with
  bge-small-en, PHX-1089's kNN arm. A retriever that takes a second hop raises
  exactly the 35% this comparison turns on; PHX-1089's own graph-ranked
  passages were worth 5.0 points of exact match over kNN on this dataset and
  ten points of ceiling. The claim is against that baseline and no stronger
  one.
- **2Wiki is the favourable ground.** Its questions are generated from
  Wikidata relations, over a corpus of one paragraph per article. On HotpotQA
  PHX-1089 measured the kNN passages' ceiling at 77% over all questions,
  against 59% on 2Wiki by the same looser string match, so there is less
  finding left to gain there; PHX-1128 reads it.
- **`gold_in_context` is a string match.** It says the gold stood in the
  material, not that it stood there as the answer to this question; for a yes
  or a no it says next to nothing.
- **The level is low.** 30% on the unnamed-answer questions, 38% with sources;
  the lead is over an arm at 21 to 23%.
- **One answering model, exact match as the headline.** F1 agrees in direction
  where it was checked; a second model has not been asked.

## Decision

PHX-1127 is closed. `scripts/mesh_qa_constellation.py` writes `by_type`,
`paired_by_type` and `paired_in_pool` with every run and its answer rows carry
`question_type`; `scripts/mesh_qa_pair_runs.py` pairs two runs by type as well
as by kind; `scripts/mesh_qa_by_type.py` reads a finished run. The
unnamed-answer questions are the figure to read first in an answer run on this
dataset, with their entity answers and their dates apart; the total and the
named-answer questions stay beside it. The README, `llms.txt` and `AGENTS.md`
quote the reading next to the 3.6 points it takes apart, with its limits.

Next is the same reading where it can fail:
[`PHX-1128`](../../phoenix-backlog/PHX-1128.yaml), HotpotQA, whose 9,811
passages have been read since August and on which the Constellation has never
been asked a question (PHX-1089 ran passage arms there). HotpotQA labels its
questions `bridge` (811 of 1,000, pooled as `answer_unnamed`) and `comparison`
(189, `answer_named`); that pooling and five expectations, each with the
figure that would contradict it, are in the ticket, written before any answer
from a mesh of that corpus exists.

*Done 2026-11-12 (PHX-1128): one expectation contradicted, two met, two
undecided ([`question_types_hotpotqa.md`](question_types_hotpotqa.md)).*

## How to re-run

No key and no cost; the run files are the ones the earlier etappes wrote.

```bash
R=data/run_reports/qa_constellation
O=data/run_reports/phx1127
python scripts/mesh_qa_by_type.py $R/2wiki_1000.json $R/2wiki_1000_repeat.json \
    $R/2wiki_1000_topk25.json $R/2wiki_1000_yn_sources.json \
    $R/2wiki_1000_yn_sources_v2.json $R/2wiki_1000_phx1118_off.json \
    $R/2wiki_1000_phx1118_on.json --json $O/by_type.json
python scripts/mesh_qa_pair_runs.py --a $R/2wiki_1000_phx1118_off.json \
    --b $R/2wiki_1000_phx1118_on.json --json $O/accrual_off_on_by_type.json
python scripts/mesh_qa_pair_runs.py --a $R/2wiki_1000.json \
    --b $R/2wiki_1000_yn_sources_v2.json --json $O/sep_oct_by_type.json
```

The first prints, per run, exact match, the ceiling and the exact match under
the ceiling by type and pool, then every pair by type and pool and each pool
once more by which arm held the answer and by the shape of the gold. The
second pairs the two builds of PHX-1118, the third September against October.
The types of these older runs come from
`data/raw/qa_bench/2wikimultihopqa.json`, which the answer runs fetched. The
runs themselves are rebuilt as [`qa_constellation.md`](qa_constellation.md),
[`yes_no_and_sources.md`](yes_no_and_sources.md) and
[`description_accrual.md`](description_accrual.md) say, at about a euro a
sitting.

Tickets: [`PHX-1127`](../../phoenix-backlog/PHX-1127.yaml),
[`PHX-1128`](../../phoenix-backlog/PHX-1128.yaml); from
[`PHX-1110`](../../phoenix-backlog/PHX-1110.yaml).
