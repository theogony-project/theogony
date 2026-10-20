# Two repairs for the Constellation's reader (PHX-1113, PHX-1114)

> **Abstract.** *Question.* PHX-1110 left two losses on the table: handed a
> list of entities, the model answered a yes/no question with an entity (37%
> against a 57% prior on 110 questions), and the Constellation carried almost
> none of the dates its source paragraphs contain (9% against 33% for five
> passages on 54 questions). Can one sentence in the prompt repair the first,
> and can the paragraphs the seed-touching entities were read from, laid beside
> the typed Constellation, repair the second? *Method.* The same 1,000 questions
> of 2WikiMultihopQA, the same mesh, deepseek-chat, SQuAD exact match, the
> paired sign test, read by answer kind; two runs, because the review found a
> defect in the first version of the sources arm before its result was read.
> *Result.* The sentence takes the yes/no questions from 55.5% to 67.3% (16
> better, 3 worse, p = 0.004) and changes nothing on the other 890 (27 / 26).
> The paragraphs take the date questions from 13.0% to 42.6% (18 / 2,
> p = 0.0004) and the entity questions up 2.5 points; the Constellation with
> its sources beats five retrieved passages by 6.8 points of exact match
> (p = 0.0001), and by 8.9 (197 / 108, p = 4 × 10⁻⁷) once the sentence is
> added to it — the passages arm did not get the sentence. *Limits.* One
> model; the yes/no collapse of September (37%) had already shrunk by October
> in the unchanged arm (55.5%), so the sentence repairs what remained and
> lifts yes/no above the prior; the gain over passages on dates alone is not
> significant on 54 questions; the ranking of the paragraphs, which the review
> showed to be wrong in principle, moved the score by less than a point.
> *Decision.* Both tickets closed; `constellation_sources_yn` is the strongest
> arm measured on this benchmark, and the README says so with the limits.

**Status:** 2026-10-19, measured twice; both tickets closed.
**Instrument:** `scripts/mesh_qa_constellation.py` with the arms below on
`data/mesh-2wiki` (the mesh of PHX-1110: 6,119 passages replayed from cached
Kadmos readings, 35,906 nodes, 649,695 edges, 0 ticks), deepseek-chat at
temperature 0, 48 output tokens, SQuAD exact match and token F1 against the
answer key with aliases, `gold_in_context` as the ceiling of each arm, the
exact paired sign test on the questions both arms answered, read by answer kind
(`answer_kind`: 836 entity, 110 yes/no, 54 date). Each run 5,000 calls; the
two together cost under two euros.

## The two losses, and what was tried

**Yes/no (PHX-1113).** The system prompt of every material arm said: answer
with the shortest span, a name, a date, a phrase. Shown fifty entities and the
relations among them, the model took that literally on 31 of 110 yes/no
questions in September and on 13 to 16 in October, and answered with an entity
— "Iran" where the question asked whether two villages are in the same country
— and leaned to "No" where the material did not show the fact for both sides.
Passages have less of this effect (11 to 12 of 110), not none. The
variant, `constellation_typed_yn`, adds one sentence to the system prompt and
changes nothing else:

> If the question is a yes/no question — it begins with Are, Is, Do, Does, Did,
> Was, Were or Has — answer yes or no.

**Dates (PHX-1114).** An entity's description holds what Kadmos wrote about the
entity, not every fact of the paragraph it was read from, and the mesh keeps a
reference to the paragraph (`raw_text_ref`, `2wikimultihopqa#p<N>`), not its
text. The benchmark holds the texts. The arm `constellation_sources` renders
the typed Constellation as before and lays beneath it the source paragraphs of
the seed-touching entities — the seeds, then the other endpoints of the edges
that touch a seed — found through the mention edges from chunk to entity, five
paragraphs as in the passages arm. `constellation_sources_yn` is both repairs.

## What the review found before the result was read

The first version of the sources arm took the seeds in the order
`Constellation.seed_node_ids` listed them. That list was built from a Python
set, so it carried hash order and no rank: `retrieve()` ranks its seeds (the
MMR-selected ANN seed first, then the name anchors, narrowest span first), and
the Constellation threw the ranking away. With up to eight name-anchor seeds per
question and the paragraph budget filled greedily seed by seed, a hub that
hashed first — "Nile", read from eleven paragraphs, on a question about two
films — took all five slots with its earliest paragraphs in corpus order. The
review's replication over the 1,000 questions (a read-only script in the
review's own session, not an artefact this repository keeps): at least one gold
passage among the five attached for 615 questions in the shipped order against
791 in the order retrieval had already computed, with a ceiling of 815 over any
order.

Two changes followed, and the arm was measured again. The Constellation keeps
its seeds in rank order now, for every consumer. And within the budget the
paragraphs that mention several of the seed-touching entities come first — the
second hop of a comparison question is a paragraph both entities stand in — then
the first entity's paragraphs in the order the reader appended them. Both runs
are below; the first is kept because the difference between them is a result.

## What was measured

**Run 1** — the sources arm in its first version (seeds in set order, a seed's
paragraphs in corpus order); 42 minutes.

| arm | EM | F1 | answer in material | entity (836) | yes/no (110) | date (54) |
|---|---|---|---|---|---|---|
| passages | 45.3% | 50.5% | 55.4% | 44.0% | 60.9% | 33.3% |
| constellation_typed | 48.7% | 54.6% | 61.0% | 49.9% | 57.3% | 13.0% |
| constellation_typed_yn | 49.3% | 54.9% | 61.0% | 49.8% | 63.6% | 13.0% |
| constellation_sources | 51.0% | 57.2% | 67.3% | 51.3% | 50.9% | 46.3% |
| constellation_sources_yn | 53.6% | 59.7% | 67.3% | 52.8% | 63.6% | 46.3% |

**Run 2** — the arm as shipped (seeds in rank order, paragraphs that mention
several seed-touching entities first); 17 minutes. 951 of the 1,000 questions
received all five paragraphs, the rest between one and four.

| arm | EM | F1 | answer in material | entity (836) | yes/no (110) | date (54) |
|---|---|---|---|---|---|---|
| passages | 45.1% | 50.5% | 55.4% | 44.1% | 58.2% | 33.3% |
| constellation_typed | 48.2% | 54.2% | 61.0% | 49.5% | 55.5% | 13.0% |
| constellation_typed_yn | 49.6% | 55.2% | 61.0% | 49.6% | **67.3%** | 13.0% |
| constellation_sources | 51.9% | 57.8% | 68.0% | 52.0% | 55.5% | **42.6%** |
| constellation_sources_yn | **54.0%** | **59.8%** | 68.0% | **53.1%** | **67.3%** | 40.7% |

The last three columns are exact match on the subset. The totals of the two
reference arms sit above PHX-1110's (42.7% and 44.1% there): the model behind
the alias moved between September and October, which is why only the pairs
within one run are read. The move is largest on the very question kind
PHX-1113 was filed on: in September the unchanged typed Constellation scored
37.3% on the 110 yes/no questions and gave 31 entity answers; in October, with
nothing changed in that arm, it scored 57.3% and 55.5% — the prior's level —
and gave 16 and 13 entity answers. The collapse the ticket named did not
reproduce in full; what the sentence repairs is what remained of it, and it
lifts the arm above the prior (57–58%) and above the passages arm (58–61%)
rather than back to it.

The passages arm is not immune to the entity answer either — 12 and 11 of its
110 yes/no answers were neither yes nor no in the two runs — so PHX-1110's
"passages do not have this effect" was true of degree, not of kind.

F1 and the ceiling by kind, run 2 (PHX-1114 asked for all three by kind):

| arm | F1 entity | F1 yes/no | F1 date | in material entity | yes/no | date |
|---|---|---|---|---|---|---|
| passages | 50.1% | 58.2% | 40.4% | 62.8% | 3.6% | 46.3% |
| constellation_typed | 56.2% | 55.5% | 20.7% | 71.7% | 2.7% | 14.8% |
| constellation_typed_yn | 55.9% | 67.3% | 20.7% | 71.7% | 2.7% | 14.8% |
| constellation_sources | 58.5% | 55.5% | 51.4% | 77.0% | 5.5% | 55.6% |
| constellation_sources_yn | 59.4% | 67.3% | 50.4% | 77.0% | 5.5% | 55.6% |

The yes/no ceiling is near zero for every arm because a yes or a no never
stands in any material; the column says only that the scorer cannot see the
fact the model inferred.

Paired, run 2, exact match: better / worse and the sign test.

| comparison | overall | entity (836) | yes/no (110) | date (54) | not yes/no (890) |
|---|---|---|---|---|---|
| typed_yn vs typed | +1.4 (43/29, p=0.12) | +0.1 (27/26, p=1) | **+11.8** (16/3, p=0.004) | 0 (0/0) | +0.1 (27/26, p=1) |
| sources vs typed | +3.7 (87/50, p=0.002) | +2.5 (61/40, p=0.046) | 0 (8/8) | **+29.6** (18/2, p=0.0004) | +4.2 (79/42, p=0.001) |
| sources vs passages | +6.8 (188/120, p=0.0001) | +7.9 (160/94, p=4e-5) | −2.7 (17/20, p=0.74) | +9.3 (11/6, p=0.33) | +8.0 (171/100, p=2e-5) |
| sources_yn vs typed | +5.8 (98/40, p=9e-7) | +3.6 (64/34, p=0.003) | +11.8 (17/4, p=0.007) | +27.8 (17/2, p=0.0007) | +5.1 (81/36, p=4e-5) |
| sources_yn vs passages | **+8.9** (197/108, p=4e-7) | +9.0 (164/89, p=3e-6) | +9.1 (23/13, p=0.13) | +7.4 (10/6, p=0.45) | +8.9 (174/95, p=2e-6) |
| sources_yn vs sources | +2.1 (51/30, p=0.03) | +1.1 (33/24, p=0.29) | +11.8 (18/5, p=0.01) | −1.9 (0/1) | +0.9 (33/25, p=0.36) |

Run 1 gave the same picture with slightly different figures: the sentence
+6.4 on yes/no (12/5, p=0.14) and −0.1 on the rest; the paragraphs +33.3 on
dates (19/1, p=4e-5); both together +8.3 over passages (195/112, p=3e-6).

**What the sentence does**, counted on the 110 yes/no answers of run 2: the
typed arm gave 13 answers that were neither yes nor no, the sources arm 18;
with the sentence both gave 0. The gain on yes/no is the mechanism PHX-1113
named, and on the other 890 questions the sentence changes nothing (27 better,
26 worse).

**What the paragraphs do:** on the 54 date questions the typed Constellation's
ceiling is 14.8% and the sources arm's 55.6%, above the passages arm's 46.3% —
the dates were never in the entity descriptions and are in the paragraphs. On
the entity questions the ceiling rises from 71.7% to 77.0% and the score
follows (+2.5 over typed, +7.9 over passages). On yes/no the paragraphs cost
without the sentence in run 1 (−6.4) and nothing in run 2 (8/8); with the
sentence they are neutral.

**What the ranking did**, run 2 against run 1 on the same questions: the
sources arm +0.9 (48 better, 39 worse, p=0.39) and its ceiling 67.3% → 68.0%;
the typed arm, which did not change, moved −0.5 (12/17) between the runs, which
is the noise floor of this instrument. The review's replication showed the
allocation was wrong on 176 questions; the score shows the model's reading, not
the allocation, is where the arm loses what it loses. The fix stands because it
is right, not because it is worth a point.

## What this does not show

- **One model.** deepseek-chat read every arm; whether the yes/no sentence or
  the paragraph budget helps another reader is unmeasured. The sentence names
  the question form in English; a corpus in another language needs its own.
- **Dates against passages: not significant.** The sources arm's +9.3 over
  passages on the 54 date questions is 11 better against 6 worse (p=0.33); what
  is significant is the gain over the typed Constellation (18/2) and the
  ceiling (55.6% against 46.3%). The claim is "the paragraphs restore the
  dates", not "the mesh beats passages on dates".
- **The headline pairs a prompt-patched arm against an unpatched one.** The
  passages arm did not get the yes/no sentence; against it the fair figure is
  the sources arm without the sentence, +6.8 (188 / 120, p = 0.0001). The +8.9
  is the arm as a whole against plain retrieval as it was measured in PHX-1110.
- **Not what `mesh_ask` returns.** The sources arm needs the passage texts,
  which the benchmark holds and the mesh does not; `mesh_ask` ships the typed
  rendering and nothing else changed there.
- **The sources arm is a hybrid**, and so is the claim: the Constellation plus
  the paragraphs beats the paragraphs alone by 8.9 points at the same
  paragraph budget, which says the graph adds to retrieval, not that it
  replaces it. The arm reads more tokens than the passages arm.
- **No parameter was tuned.** The paragraph budget is the passages arm's five,
  the seed count the shipped one; the first configuration tried is the one
  reported, twice.
- **The prompt sentence is a patch**, not a reading. A list of yes/no verbs
  is the honest limitation of answering the question form by rule.

## Decision

PHX-1113 reached its finish line: 67.3% on the yes/no questions against the
55% asked for, +0.1 on the other 890 against the 1.0 point allowed, in one run
with both arms. PHX-1114's hypothesis held: the arm with the source paragraphs
takes the passages' result on dates and the graph's on comparison chains. Both
closed. `constellation_sources_yn` is the strongest arm measured on this benchmark
— +6.8 points of exact match over five retrieved passages without the
sentence, +8.9 with it, on 1,000 questions of a corpus the model does not know
— and the README and `llms.txt` quote it beside the figure of PHX-1110, with
the limits. The arms stay in
the harness; nothing in the shipped `mesh_ask` changes, since the MCP tool
returns the Constellation and its typed rendering and the caller holds no
passage list.

## How to re-run

```bash
THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \
  python scripts/mesh_qa_constellation.py --root data/mesh-2wiki \
    --arms passages,constellation_typed,constellation_typed_yn,constellation_sources,constellation_sources_yn \
    --out data/run_reports/qa_constellation/2wiki_1000_yn_sources_v2.json
```

The mesh is rebuilt without a key by `scripts/mesh_qa_mesh_ingest.py`; the
answer run costs about one euro and prints every figure above, the pairs by
kind included.

Tickets: [`PHX-1113`](../../phoenix-backlog/PHX-1113.yaml),
[`PHX-1114`](../../phoenix-backlog/PHX-1114.yaml); from
[`PHX-1110`](../../phoenix-backlog/PHX-1110.yaml)
([`qa_constellation.md`](qa_constellation.md)).
