# The Latent Last Mile — the Constellation as Vectors Instead of Text (PHX-1109)

> **Abstract.** *Question.* The vision says the Constellation is handed
> to the agent as vectors, injectable into its latent space, with no translation
> into text. Can that be tested cheaply? *Method.* xRAG stage 1:
> Qwen2.5-3B-Instruct, frozen; a projector (768 → 2048 → 2048) maps each node's
> vectors to one soft token and is trained by paraphrase on 3,529 consolidated
> nodes with 186 held out; four arms over the 47 founding questions with the
> same reader; three projectors, one continued to 20 epochs; strict scoring that
> excludes gold names the question itself restates (39 questions). *Result: the
> vector arrives, the answer does not.* On held-out nodes the right vector
> prices the node's name at 2.4 nats per token against 6.8 for another node's
> vector (2.9 against 4.9 after five epochs) — identity flows, and generalises.
> The reader cannot answer from it: text 49%, prior 14%, soft tokens 9–11%,
> untrained projector 0%; better than text on 0 of 39 questions in every run,
> never worse than the untrained control. *The shipped scorer would have
> reported a tie* — after 20 epochs −2 points against text, 13 questions better
> and 17 worse, eleven complete answers against eight — because a
> paraphrase-trained arm answers in sentences that repeat the question, and 30
> of 111 gold names stood in their own question (repaired in PHX-1098).
> *Reading.* Stage 1 teaches decoding a token; using it under an instruction is
> stage 2 and needs question–answer data that is not the gold set. More epochs
> are not the lever: from epoch 15 the projector memorises. A null result, kept.
> Practical note: `generate(inputs_embeds=…)` returns garbage on Apple MPS with
> transformers 5.5, hence a hand-rolled greedy decode.

**Status:** 2026-09-12, measured. Branch `feat/phx-1109-latent-mile`.
**Prompted by:** [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) §Addendum 2026-09-11 — the reports on latent reasoning, and the observation that here everything runs through text.
**Tools:** `scripts/mesh_latent_mile.py train | answer | diagnose`, `src/theogony/mesh/eval/latent_mile.py`. Curves and summaries of all runs: [`latent_mile_runs.json`](latent_mile_runs.json).

**The result in one sentence: the vector arrives, the answer does not.** A
frozen 3B reader reads the node's identity out of a projected node vector —
measurably, growing with training, even for nodes the projector has never
seen. But from fifty such tokens and the relations between them it forms no
answer: strictly scored, the soft Constellation beats the text Constellation
on not a single one of 39 questions, in none of four runs, and sits at the
level of its prior knowledge. What it does reliably beat is the control: the
same prompt with an untrained projector scores zero. And the measurement
caught the scorer along the way: under the shipped substring scorer the
20-epoch run looked like a tie (−2 against text, 11 complete answers against
8), because the soft arm answers in sentences that restate the question, and
30 of the 111 gold names stand in their own question.

## The claim under test

VISION.md, line 44: *"The Constellation is returned to the agent in vector
form, directly injectable into its latent space — no text translation
required. The agent does not read context. It receives structure."* The
vision ledger carries the sentence as *untestable*. It has not been, since an
open small reader ran on a laptop and had an embedding input.

The test is deliberately the smallest one that meets the claim — xRAG (Cheng
et al. 2024), stage 1: retriever frozen, language model frozen, one small
trained projector in between, one document as one token. Here the retriever
is the substrate itself, and the document is a node.

## Setup

**Reader.** Qwen2.5-3B-Instruct, frozen, fp16 on MPS (fp32 answers
identically, measured on 8 questions). The 1.5B that the MNLM brief names as
the PoC target was tried first and dropped: it barely reads the text material
— on the first 8 gold questions, 24% against 33% with no material — while the
3B reads it well (55% against 27%). A reader that cannot use the text
Constellation cannot refute the soft one. (The 1.5B projector run, aborted
after three epochs: loss 3.06 → 2.57, held out 2.52 → 2.29, recognition 0%.)

**Projector.** Two layers (input → 2048 → 2048, GELU), one node vector →
one soft token, spliced into the chat prompt in place of a placeholder token.
Calibrated before training to the mean norm of a real token embedding, so
that the "untrained" control measures the absence of training and not a
scale that is an order of magnitude off.

**Input.** `both`: the `semantic_vector` (384-d, bge-small-en, the vector
that spreading activation runs over) ⊕ the `description_vector` (384-d, the
embedding of the regenerated description). The second is the analogue of
xRAG's document embedding, because the paraphrase target *is the
description*. `semantic` alone is the doctrine-faithful, harder variant and
was also measured.

**Training.** Paraphrase, as in xRAG stage 1: from the soft token the reader
is to produce the entry the text arm shows (`Label — Beschreibung`). Training
data is the 3,715 entity nodes of the consolidated founding mesh (median 13
words of description; the 1,219 source anchors excluded, their descriptions
are file names and the text arm does not show them either). In groups of 1–4
nodes per example, because the answer prompt shows fifty soft tokens in a
list and a projector that has only ever seen single tokens has never
experienced a token *after* another one. 5% of the nodes (186) held out. The
gold set does not touch the training. Batch 8, AdamW 1e-3,
gradient checkpointing through the frozen reader (without it the laptop went
23 GB into swap), about 14 minutes per epoch on an M4 Pro.

**Four arms, the same reader, the same Constellation per question**
(`k_seeds=1`, `top_k=50`, `record_firing=False`), the same scoring as the
answer instrument (PHX-1087, substring hits on the gold names), plus the
strict scoring (below):

| Arm | Material |
|---|---|
| `closed_book` | none |
| `constellation` | the shipped text rendering: `Label — Beschreibung` per node, relations as triples over the labels, only edges on one seed |
| `soft` | the same nodes as soft tokens, the same triples with soft tokens instead of labels |
| `soft_untrained` | the same prompt, the projector before training (fixed seed) |

A test proves that the soft prompt is the text rendering with the names cut
out: put the names back in, and the text arm reappears verbatim.
Greedy decoding is deterministic; a repetition measures nothing. The
scatter that exists is the one across training seeds.

**What did not work, and why it is hand-built.** `generate()` with
`inputs_embeds` returns nonsense on MPS under transformers 5.5.4
(`'OSTROPHE'` for "Who is the father of Zeus?"), with and without cache, in
fp16, bf16 and fp32, while the forward pass with the same embeddings is exact
to 0.0 and the CPU answers correctly. The decoder is therefore a greedy loop
over `past_key_values`, 30 lines.

## The training: what the vector carries

Loss in nats per token of the paraphrase target, `both`, seed 0, continued
from 5 to 20 epochs; the 30-sample recognition figures are coarse:

| Epoch | Training | held-out | Label recognised (training / held-out) |
|---|---|---|---|
| 1 | 3.03 | 2.46 | 0% / 0% |
| 2 | 2.51 | 2.21 | 0% / 0% |
| 5 | 2.23 | 2.01 | 0% / 7% |
| 10 | 1.90 | 1.84 | 7% / 10% |
| 15 | 1.67 | **1.72** | 10% / 10% |
| 20 | 1.46 | 1.79 | 13% / 13% |

From epoch 15 the curves separate: the projector begins to learn the
directory instead of the mapping. Seed 1 after 5 epochs: 2.19 / 2.10;
`semantic` after 5 epochs: 2.13 / 1.98 — the doctrine-faithful vector learns
the paraphrase no worse.

A single soft token rarely gets the reader to return the node's name: after
epoch 2 it answers *Tyndareus* with "Aesop — The Greek fabulist", and
*Briareos* with "Theodamas — A Spartan general". The register is right, the
identity is not. **Measured, what the token carries**
(`diagnose`, 60 nodes each, loss per token; *foreign* = the same projector
with another node's vector):

| Projector | Nodes | Name tokens right / foreign / control | Description tokens right / foreign / control |
|---|---|---|---|
| `both`, 5 ep. | training | 2.60 / 4.86 / 13.81 | 1.77 / 2.47 / 4.52 |
| `both`, 5 ep. | held-out | 2.91 / 4.88 / 14.51 | 1.84 / 2.44 / 4.86 |
| `semantic`, 5 ep. | training | 2.48 / 4.82 / 12.69 | 1.74 / 2.48 / 4.83 |
| `semantic`, 5 ep. | held-out | 2.85 / 4.80 / 13.03 | 1.83 / 2.44 / 5.22 |
| `both`, 20 ep. | training | **1.17** / 6.74 / 13.81 | 1.11 / 3.59 / 4.52 |
| `both`, 20 ep. | held-out | **2.42** / 6.80 / 14.51 | 1.78 / 3.71 / 4.86 |

The column that matters is *right against foreign* on held-out nodes: the
vector carries 2.0 nats per name token of identity after five epochs, 4.4
nats after twenty — and the semantic vector alone carries just as much as
both together. **The vector arrives.** Between training and held-out there
is almost nothing after five epochs (the projector learns a mapping), and a
factor of two after twenty (it begins to memorise them).

## The four arms

47 gold questions, the same reader, the same Constellation per question,
greedy. Two scorings: **shipped** = substring hits on all gold names, as in
PHX-1087; **strict** = without the gold names that stand in the question
itself (30 of 111; 8 questions drop out, 39 remain).

| Run | Arm | shipped | complete | strict | complete | Words per answer |
|---|---|---|---|---|---|---|
| all | `closed_book` | 16% | 4/47 | 14% | 3/39 | 2 |
| all | `constellation` (text) | **38%** | 8/47 | **49%** | 13/39 | 2 |
| all | `soft_untrained` | 9–11% | 1–2/47 | **0%** | 0/39 | 2 |
| `both`, seed 0, 5 ep. | `soft` | 19% | 6/47 | 9% | 2/39 | 3 |
| `both`, seed 1, 5 ep. | `soft` | 17% | 2/47 | 11% | 2/39 | 2 |
| `semantic`, seed 0, 5 ep. | `soft` | 8% | 4/47 | 1% | 1/39 | 19 |
| `both`, seed 0, 20 ep. | `soft` | **28%** | **11/47** | 11% | 4/39 | 6 |

Question by question, paired (better / worse / same):

| Run | Vectors against text | Vectors against untrained | Vectors against prior |
|---|---|---|---|
| `both` 0, 5 ep., shipped | −15 (7 / 22 / 18) | +10 (12 / 5 / 30) | +9 (10 / 4 / 33) |
| `both` 0, 5 ep., **strict** | −43 (**0** / 24 / 15) | +8 (5 / 0 / 34) | −2 (3 / 3 / 33) |
| `both` 1, 5 ep., shipped | −22 (4 / 20 / 23) | +4 (11 / 5 / 31) | +2 (10 / 5 / 32) |
| `both` 1, 5 ep., **strict** | −42 (**0** / 22 / 17) | +9 (7 / 0 / 32) | 0 (5 / 3 / 31) |
| `semantic` 0, 5 ep., shipped | −24 (6 / 25 / 16) | +3 (6 / 6 / 35) | 0 (9 / 9 / 29) |
| `semantic` 0, 5 ep., **strict** | −48 (**0** / 25 / 14) | +3 (1 / 0 / 38) | −7 (1 / 5 / 33) |
| `both` 0, 20 ep., shipped | **−2 (13 / 17 / 17)** | +23 (16 / 2 / 29) | +21 (18 / 5 / 24) |
| `both` 0, 20 ep., **strict** | −38 (**0** / 20 / 19) | +12 (7 / 0 / 32) | +3 (6 / 4 / 29) |

Text against prior, strict, in every run: +41 (23 / 1 / 15). By question
kind, strict, 20 epochs: genealogical (n = 24) text 47%, vectors 6%,
prior 7%; narrative (n = 15) text 57%, vectors 23%, prior 13%.

## Reading

**The vectors carry something, and it is not the dressing.** Against the
untrained projector the trained one wins strictly in every run and never
loses (5 / 0, 7 / 0, 1 / 0, 7 / 0). The untrained projector makes the reader
stutter (`ă, ă, ă, …`) or return `None`; the trained one answers with names
from the right universe.

**But the reader cannot form an answer from them.** Strictly scored, the
soft Constellation beats the text Constellation on *no* question, in no run,
and sits at the level of the prior (−2, 0, −7, +3). Where the text wins, it
is every question: the children of Cronus ("Titans, Cyclopes,
and Hecatoncheires"), the children of Night ("Night bore Time"), the children
of Strife ("Strife bore 10 children."). The reader knows *what* is being
talked about — the diagnosis shows that — but not *what* the fifty tokens say
about the question.

**The shipped scorer would have told a different story.** Under it the
20-epoch run looked like a tie: −2 against text, 13 questions better against
17, eleven complete answers against eight, and on narrative questions 50%
against 37%. All thirteen "wins" are questions whose gold names stand in the
question — *How were Chrysaor and Pegasus born?* expects Chrysaor and
Pegasus, *What measures the depth of Tartarus?* expects Tartarus — and the
soft arm, trained by paraphrase to *write out* entries, answers in sentences
that restate the question ("Chrysaor and Pegasus were born from the severed
head of Medusa"), while the text arm follows the "names only" instruction
("Medusa"). Six words per answer against two. The substring scorer pays for
that. **30 of the 111 gold names stand in their own question;** that is a
fault of the gold set that inflates every arm equally, unless it answers in
sentences — then unequally. The addendum is in PHX-1098; the strict scoring
is now in the harness.

**Why it fails here where it succeeds for xRAG.** xRAG has two stages:
paraphrase (*decoding* the token) and, after that, instruction tuning with
self-distillation from a text-RAG teacher (*using* the token under an
instruction). What was built is stage 1. It delivers what it promises — the
identity arrives — and it cannot deliver what stage 2 promises. More epochs
are not the lever: from epoch 15 the projector memorises the directory, and
strict does not change (9 → 11%). The lever is stage 2, and it needs
question–answer data that is not the gold set — synthetic questions from the
mesh, or HippoRAG.

**What this means for VISION:44.** The sentence has been measured for the
first time, and the measurement splits it in two. *"The agent receives
structure"* — yes, demonstrable at this scale: a frozen model reads the
node's identity out of the substrate vector, growing, generalising. *"No
text translation required"* — no, not with this recipe: translation into
text remains the mile on which the answer forms, and the gap is a training
recipe (stage 2), not proof that the medium cannot carry it. And the
instrument once again showed more than the object: without the strict
scoring, a false "tie after twenty epochs" would stand here.

## Limits

- One reader, one scale (3B). LOTUS says latent methods above 1B fell behind
  text through mid-2026; a null result here is a result about *this* scale
  and *this* recipe.
- 3,715 training vectors against millions for xRAG; one seed for `semantic`
  and for the 20 epochs.
- The gold set has no aliases (PHX-1098) and 30 names in their own question;
  the strict scoring strikes the second, not the first.
- The substrate is bge-small-en 384-d; whether a larger embedding space
  carries more across the mile is not measured.
- The relation identifiers (`co_mentions_in_paragraph` in many triples) are
  the same in both arms; in the soft arm they are visible to the reader as a
  pattern ("co_mentions_in_paragraph — Co-mentions: …"). Whether a prompt
  without structural edges lifts the soft arm is not measured.
