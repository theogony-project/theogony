# The answer arm on a corpus the model does not know (PHX-1110)

> **Abstract.** *Question.* Does the graph help a model answer on a
> corpus it does not know? The founding corpus could not say: the model's
> unaided prior there is 86% (PHX-1098). *Method.* All 6,119 passages of
> 2WikiMultihopQA read into a mesh by replaying cached Kadmos readings through
> the shipped write path (35,906 nodes, 38,746 read relations, no LLM call);
> five arms over 1,000 questions, deepseek-chat, SQuAD exact match and F1,
> paired exact sign test. *Result (exact match).* Prior 33.8%, five passages
> 42.7%, fifty entities without edges 40.5%, the Constellation as shipped 41.2%,
> the Constellation without structural edges 44.1%. The edges are worth +3.6 EM
> / +4.3 F1 over the same entities (p = 0.03; repeated: +4.0 / +4.9, p = 0.015)
> — but only once co-occurrence and provenance lines, 60% of the rendered
> relations, are left out; with them +0.7, and they cost 2.9 points (p = 0.004).
> Against plain passages it is a tie made of opposite parts: +5.6 on the 836
> entity answers, a collapse on yes/no questions (37% against a 57% prior) and
> on dates (9% against 33%). At half the budget (top_k 25) the gain shrinks to
> +1.2 EM. *Side finding, fixed.* Ingestion was quadratic — one Lance fragment
> per node, 98 ms against 10 ms per vector search — so a read now compacts its
> workspace every 200 paragraphs. *Limit.* The same model alias scored 24.8%
> closed-book three weeks earlier; compare within a run only. *Decision.* The
> harness rendering drops structural edges by default. Follow-ups: PHX-1113
> (yes/no), PHX-1114 (dates).

**Status:** 2026-09-16, measured. Track C of the plan, second and last piece.
**Tools:** `eval/qa_mesh.py` (replay ingestion, five arms, paired
sign test), `scripts/mesh_qa_mesh_ingest.py`, `scripts/mesh_qa_constellation.py`.

## Why this piece is now the only one

PHX-1098 closed the founding corpus as a control group: under the
corrected gold, deepseek-chat answers Hesiod at **86%** with no material
at all, and the Constellation sits below it at 75%. On a corpus the
model knows by heart, the answer arm measures the cost of binding to the
material, not the graph's added value. The question "does the graph help
with answering" can only be asked where prior knowledge is low.

2WikiMultihopQA is such a corpus. PHX-1089 measured prior knowledge there at
**24.8% EM** and retrieval at +11 to +23 points above it. But what
PHX-1089 handed the model were **passages**: whole paragraphs, selected
by kNN or by Spreading Activation over a cheap spaCy graph. The
substrate's own consumption format — the Constellation of entities and
typed relations that `mesh ask` renders — has never been measured on an
unfamiliar corpus.

## The setup

**A mesh from 2Wiki, without a single LLM call.** For PHX-1089,
`scripts/mesh_qa_kadmos.py` had each of the 6,119 passages read once by
Kadmos and cached the reading (key: blake2b-128 of the passage text). A
replay provider answers the reader's paragraph prompt from this cache,
and the shipped write path (`MeshParagraphReader`) builds a mesh from it
— the same linker, the same identity resolution, the same edges a user
corpus would get. A paragraph the cache does not hold counts as a read
failure, not a fabrication (on 2Wiki: 6,119 of 6,119 found). The result,
`data/mesh-2wiki`: 6,119 chunks, **35,906 consolidated nodes, 38,746
read relations**, 3,322 paragraph concepts, 616 MB after compaction; 81
minutes at 0.80 s per paragraph, 0 ticks.

**Five arms, one model, one scorer.** deepseek-chat, temperature 0, the
prompts from PHX-1089 (only "passages" becomes "material", because two
arms hand over entities instead of paragraphs). Scored with SQuAD EM/F1
against the answer key with aliases — not with the founding scorer,
which strips digits (the corpus carries footnote numbers), because half
of the 2Wiki answers are dates.

| Arm | Material | Question it answers |
|---|---|---|
| `closed_book` | none | the prior |
| `passages` | top-5 passages by cosine | plain RAG; the bridge to PHX-1089 (`knn`) |
| `vector_only` | top-50 mesh entities by cosine, as descriptions | what the node store alone carries |
| `constellation` | the same kind of entities plus the relations between them | the shipped rendering (`mesh ask`) |
| `constellation_typed` | the same without the structural edges | whether the structural edges cost the reader anything |

The claim that counts is `constellation` against `vector_only`: the
same node store, the same embedding, the only difference is whether the
edges are shown. Against `passages` the harder question is whether the
substrate's rendering form keeps up with plain RAG at all. Every arm
carries its own ceiling (`gold in ctx`: did the answer stand in the
material?), so a reading problem stays distinguishable from a retrieval
problem. Paired, question by question, with an exact sign test on the
discordant pairs, `k_seeds = 1`, `record_firing=False`, 0 ticks.

What the arms hand the model (measured on 20 questions, before the run):

| Arm | Characters per prompt | Lines | Answer stands in the material |
|---|---|---|---|
| `passages` | 3,216 | 5 passages | 50% |
| `vector_only` | 4,261 | 50 entities | 40% |
| `constellation` | 7,567 | 50 entities + ~50 relations | 45% |
| `constellation_typed` | 5,109 | 50 entities + ~15 relations | 45% |

The mesh arms hand over more characters and hit the answer less often:
an entity description carries what Kadmos wrote about the entity, not
every date in the paragraph. That is not a property of the harness but
of the substrate — it holds what it read.

## Two findings before the first answer

**A read turned quadratic.** Ingestion began at 0.55 s per paragraph
and stood above 6 s after 400 paragraphs. Cause: every node is its own
Lance fragment until something compacts it, and every vector search —
two per concept, for identity — reads all fragments. Measured: 2,617
nodes in 2,617 fragments, **98 ms per search against 10 ms** on the
same rows compacted. The tick compacts (`prune_history`, PHX-1060), but
a read does not tick. `MeshRuntime.compact()` makes the maintenance
callable outside the tick, and the reader now calls it every 200
paragraphs (`compact_every`). The founding corpus, at 1,206 paragraphs,
had never made this visible; a book-length corpus would have.

**60% of the rendered relations are structural edges.** On the 47
founding questions, a Constellation gets 65 relation lines on average,
60% of them `co_mentions_in_paragraph`, `appears_in_source` and kin; on
2Wiki, 61%. That is the shipped path, and every founding measurement
(PHX-1087/1096/1097/1098) measured it that way. `render_constellation`
now knows `typed_only`, and the fifth arm measures what the lines cost
before the default changes.

## Result

1,000 questions, five arms, deepseek-chat, 24.7 minutes
(`data/run_reports/qa_constellation/2wiki_1000.json`):

| Arm | EM | F1 | Answer stood in the material |
|---|---|---|---|
| `closed_book` (the prior) | 33.8% | 37.9% | — |
| `passages` (top-5, plain RAG) | 42.7% | 48.3% | 55.4% |
| `vector_only` (50 entities) | 40.5% | 45.5% | 54.6% |
| `constellation` (with structural edges) | 41.2% | 47.0% | 61.0% |
| `constellation_typed` (without) | **44.1%** | **49.8%** | 61.0% |

Paired, question by question (EM better / worse, sign test):

| Comparison | ΔEM | ΔF1 | better / worse | p (EM) |
|---|---|---|---|---|
| `constellation` against `vector_only` | +0.7 | +1.5 | 138 / 131 | 0.72 |
| `constellation_typed` against `vector_only` | **+3.6** | **+4.3** | 147 / 111 | **0.03** |
| `constellation_typed` against `constellation` | +2.9 | +2.8 | 63 / 34 | 0.004 |
| `constellation_typed` against `passages` | +1.4 | +1.6 | 173 / 159 | 0.48 |
| every material arm against `closed_book` | +6.7 to +8.9 | +7.6 to +10.4 | | < 0.001 |

### What that means

**The graph helps with answering — by about four points, and only
without the structural edges.** The same fifty entities, the same
embedding, the only difference is the relation lines: with the read
relations alone, 44.1% against 40.5%, significant, 147 questions better
and 111 worse. This is the first measurement of this claim on a corpus
the model does not know. The founding corpus's +11 (PHX-1097/1098) was
measured on a corpus with 86% prior knowledge; here, at 34%, +3.6 remains.

**The shipped rendering form gave away the gain.** With the structural
edges in (`co_mentions_in_paragraph`, `appears_in_source`, 60% of the
lines), less than one of the four points remains (+0.7, p = 0.72); the
structural lines cost 2.9 points, 63 questions better without them, 34
worse. Where they cost, the model answers with the wrong kind of
entity: asked about the film, it names the director; asked about the
place of death, another city from the list. `render_constellation` has
left the structural edges out by default since this measurement
(`typed_only=True`); every founding figure before PHX-1110 was measured
with them and stands as it is. `mesh ask` continues to show them to the
human.

**Against plain RAG: a tie made of two opposing pieces.** The typed
Constellation sits 1.4 points above five passages, not significant.
Behind it are two effects that cancel out:

| Subset | n | `closed_book` | `passages` | `vector_only` | `constellation` | `constellation_typed` |
|---|---|---|---|---|---|---|
| Yes/no questions | 110 | **57.3%** | 55.5% | 50.0% | 28.2% | 37.3% |
| Answer is a date | 54 | 7.4% | **33.3%** | 3.7% | 11.1% | 9.3% |
| all the rest | 836 | 32.4% | 41.6% | 41.6% | 44.9% | **47.2%** |

On the 836 questions with an entity as the answer, the typed
Constellation beats the passages by 5.6 points — these are the
comparison questions ("which film came out first", "whose director is
younger"), where the relations make visible the chain the answer needs.
On yes/no questions it collapses: a list of entities tempts the model to
answer with an entity ("Iran" instead of "yes"), and the Constellation
with structural edges falls to 28%, below prior knowledge. On date questions
the mesh mostly does not carry the answer: an entity description holds
what Kadmos wrote about the entity, not every date in the paragraph —
33% for the passages against under 12% for every mesh arm.

**The ceiling is higher, the yield is lower.** The mesh holds the
answer in the material for 61% of the questions, the passages for 55%:
retrieval over the graph finds more. Where the answer stands there, the
model turns the passages into a correct answer 62% of the time, the
typed Constellation 64%, the one with structural edges 60%. Where it
does not stand there, prior knowledge still helps with the passages 19% of
the time, with the Constellation only 12%: the larger material binds
the model to itself more strongly.

**Control runs.** The same two arms asked again
(`2wiki_1000_repeat.json`): `vector_only` 40.6%, `constellation_typed`
44.6%, **+4.0 EM / +4.9 F1, p = 0.015** (148 better / 108 worse). The
spread between two runs is under half a point per arm; the gap holds.

At half the budget (`top_k = 25`, `2wiki_1000_topk25.json`) the gap
shrinks: `vector_only` 41.1%, `constellation` 40.9%, `constellation_typed`
42.3% — **+1.2 EM (p = 0.49) / +2.7 F1 (p = 0.03)**, and the ceiling falls
from 61 to 53%. The graph's gain depends on the budget: it needs enough
entities in the working pool for relations between them to be rendered
at all, while the plain entity list tends to do better with less
material (41.1 against 40.5). On F1 the advantage stays significant at
both budgets, on EM only at fifty.

**Reservation about the control group.** PHX-1089 measured prior knowledge on
August 26 at 24.8% EM, same model name, same prompts, same 1,000
questions; today it stands at 33.8%. Whatever answers behind
`deepseek-chat` is not the same model as back then. The passages arm,
at 42.7%, sits almost exactly against the `knn` arm from back then
(43.4%). Every comparison here is within one run, one day, one model.

## What remains open

- **Yes/no questions.** A list of entities tempts the model into an
  entity answer; the passages do not. That is a property of the
  rendering form, not of retrieval, and a prompt that recognizes the
  question type, or a rendering that shows comparisons as comparisons,
  is the obvious test.
- **Dates.** The mesh holds no paragraph text, only `raw_text_ref`, and
  an entity's description carries what Kadmos wrote about it. An arm
  that adds to the Constellation's entities the paragraphs they came
  from would combine the passages' ceiling (dates) with the graph's
  ceiling (chains); it has not been measured.
- **`mesh ask`** still renders the structural edges for the human.
  Whether they cost anything there is not measured; that they cost a
  model 2.9 points is.
- **The control group moves.** Between August 26 and today, prior knowledge
  of the same model name has moved by nine points. Every claim of this
  instrument holds within one run.
