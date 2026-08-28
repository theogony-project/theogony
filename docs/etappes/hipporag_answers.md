# The graph earns its place — on one dataset, at narrow seeding

*2026-08-26. HippoRAG_v2 shared-corpus protocol, 1,000 questions per dataset,
deepseek-chat at temperature 0, top-5 passages, SQuAD exact match and token F1.
20,000 LLM calls.*

PHX-1087 measured the answer for the first time, on the founding corpus, and
could not settle anything: 47 questions, a two-to-three point noise floor, and a
corpus of canonical Greek mythology the model answers at 50% with no context at
all. This is the measurement that can settle it.

Four arms over one shared corpus per dataset — `closed_book`, `bm25`, `knn`,
`sa_ppr` — so the comparison isolates the retrieval mechanism.

## Retrieval earns its place, everywhere

| dataset | closed_book | bm25 | knn | sa_ppr |
|---|---|---|---|---|
| 2WikiMultihopQA | 24.8% | 38.7% | **44.0%** | 43.5% |
| HotpotQA | 30.6% | 48.9% | **53.9%** | 53.8% |
| PopQA *(single-hop control)* | 33.7% | 42.8% | 43.2% | **44.3%** |

Exact match. Retrieval is worth **+19, +23 and +11 points** over what the model
already knows. Both dense methods beat BM25.

Unlike the founding corpus, these discriminate: closed-book at 25–34% rather than
50%, because the model has not memorised these questions as canon.

## And at this seeding, the graph adds nothing

Paired McNemar over the same 1,000 questions — the arms answer the *same*
questions, so a difference of proportions throws away most of the information:

| dataset | knn | sa_ppr | only SA right | only kNN right | p |
|---|---|---|---|---|---|
| 2WikiMultihopQA | 44.0% | 43.5% | 47 | 52 | 0.69 |
| HotpotQA | 53.9% | 53.8% | 45 | 46 | 1.00 |
| PopQA | 43.2% | 44.3% | 40 | 29 | 0.23 |

Statistically indistinguishable, three times over. They disagree on 70–100
questions each — genuinely different retrievals — and answer equally well.

**That would have been the headline, and it would have been wrong.**

## The configuration was the whole result

The seeding study (PHX-1057 line of work) established that Spreading Activation's
advantage on 2Wiki exists only at *narrow* seeding: the published +0.102 recall@5
was measured at **hybrid seeding, S=2**, and by S=5 SA merely re-ranks the hits
dense kNN already returned — rescue 0.000. The run above used the harness default,
`passage` seeding at S=10: SA measured at exactly the configuration where it is
known to add nothing.

Re-run at hybrid/S=2:

| dataset | arm | EM | F1 | gold in context |
|---|---|---|---|---|
| **2WikiMultihopQA** | knn | 43.4% | 48.4% | 59.0% |
| | **sa_ppr** | **48.4%** | **54.9%** | **69.4%** |
| HotpotQA | knn | 54.1% | 65.6% | 77.1% |
| | sa_ppr | 55.0% | 66.9% | 77.2% |

**2Wiki: +5.0 points exact match, +6.5 F1, +10.4 points of retrieval ceiling.**
Paired: 107 questions only SA answers correctly against 57 only kNN does,
**p < 0.001**.

HotpotQA: +0.9 points, p = 0.47, and an identical retrieval ceiling — not a
result.

## Noise floor, measured rather than assumed

kNN does not use seeding at all, so its two runs per dataset differ only by the
provider's non-determinism at temperature 0:

| dataset | run 1 | run 2 | difference |
|---|---|---|---|
| 2WikiMultihopQA | 44.0% | 43.4% | 0.6 points |
| HotpotQA | 53.9% | 54.1% | 0.2 points |

**0.2 to 0.6 points at n=1,000**, against 2–3 points at n=47 on the founding
corpus. The 5.0-point difference on 2Wiki is an order of magnitude above it; the
0.9 on HotpotQA is not.

## A defect this run found

PopQA's first run scored **0.0% in every arm, including closed-book**. PopQA has
no `answer` field — its gold lives in `obj`, with synonyms in `possible_answers`
and `o_aliases` — so `str(row.get("answer"))` produced the literal string
`"None"` as the gold for all 1,000 questions.

It had gone unnoticed because the recall benchmark next door reads only
`gold_idxs` and never touches the answer: the field was carried without a
consumer. Fixed, with the alias forms now accepted, which is why PopQA appears
above at all.

## What this supports, and what it does not

**Supports.** Retrieval over this substrate is worth 11–23 points of exact match
over a strong model's own knowledge. And on 2WikiMultihopQA, at the seeding where
the structure is legible, Spreading Activation over the graph is worth a further
**5.0 points end to end, at p < 0.001 on 1,000 questions** — the first
confirmation in this repo that the central bet survives past retrieval and into
an answer.

**Does not support.** That it generalises: HotpotQA shows +0.9 at p = 0.47 and
PopQA, the single-hop control, shows nothing — which is the same shape the recall
benchmark reports (+0.102 / +0.030 / −0.007). One dataset out of three, and it is
the one built for multi-hop reasoning over entity structure. That is a real result
and a narrow one.

**Says nothing about the founding substrate.** This harness builds its own graph
from spaCy NER and kNN edges and never touches `data/mesh-founding`. The founding
corpus answer measurement (PHX-1087) remains separate, and unsettled.
