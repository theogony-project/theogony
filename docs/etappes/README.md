# Etappes — the record of what was measured

An *etappe* is one stage of work written up when it ends: the question, the
instrument, the numbers, what they do not show, and the decision taken. This
directory is the project's lab notebook. It holds results that went against the
project as readily as results that went for it, and it does not rewrite an
earlier page when a later one corrects it — the later page says so instead.

Two kinds of document live here. The **measurement etappes** below, newest
first. And the older **sprint briefs** (`W10_…` to `W18_…`, the Nous, Kadmos and
MNLM briefs), which are design documents for work that was planned; they are
indexed by intent in [`../INDEX.md`](../INDEX.md).

**Language.** Ten etappes from September 2026 are written in German. Each opens
with an English abstract — question, method, result with its figures, limits,
decision — so that nothing measured here is reachable only through one
language. Etappes written from 2026-09-17 on are in English.

| Etappe | Ticket | What was measured, in one line |
|---|---|---|
| [`arriving_agent.md`](arriving_agent.md) | PHX-1111, PHX-1115 | From a fresh clone with no API key, no documented path returned an answer or a constellation; seven defects no test could see. Fixed, and the entrance rewritten. |
| [`qa_constellation.md`](qa_constellation.md) | PHX-1110 | On a corpus the model does not know, the graph's edges are worth +3.6 exact match over the same entities — only without structural edges; a tie with plain passages; worse on yes/no and dates. |
| [`gold_aliases.md`](gold_aliases.md) | PHX-1098 | 30 of 111 gold names stood in their own question. Re-scoring the same answers moved the control from 47% to 86% and flipped a headline from +11 to −11. |
| [`contradiction.md`](contradiction.md) | PHX-1107 | Epistemic frames as axes, a contradiction pass, the corpus re-read: both sides of a known contradiction retrieved in 6 of 7 cases; routing on hashed frames cost 42 points. |
| [`renormalisation.md`](renormalisation.md) | PHX-1106 | Use displaces the unused in every run; renormalisation with a weight cap removes it; the doctrine's §6 as written, uncapped, amplifies it (−3.8). The earlier gain from use was one seed. |
| [`latent_mile.md`](latent_mile.md) | PHX-1109 | Handing the Constellation to a frozen reader as soft tokens: identity arrives (2.4 against 6.8 nats), the answer does not (better than text on 0 of 39). A null result, kept. |
| [`plan_from_the_vision_2026-09.md`](plan_from_the_vision_2026-09.md) | — | The vision as a ledger of 620 claims held against the measurements; four tracks in order, each with its result. The operative plan. |
| [`heartbeat_2wiki.md`](heartbeat_2wiki.md) | PHX-1104 | First time "learns from use" moved on a measurement: +1.3 on used questions, −1.5 on held-out ones. What is not used is displaced. |
| [`hebbian_calibration.md`](hebbian_calibration.md) | PHX-1102 | Decay restricted to unfired edges is the only knob under which used edges hold; on the founding mesh retrieval is blind to it, and why. |
| [`what_gen1_promises.md`](what_gen1_promises.md) | — | "The mesh is alive", verb by verb, against the inventory: one of five lifelike dynamics ran, and it was the one that takes away. |
| [`doctrine_inventory.md`](doctrine_inventory.md) | PHX-1100 | Of 119 mechanisms the doctrine prescribes, 9 run, 34 are inert, 42 absent; seventeen fields hold one value everywhere — the substrate kept no memory of its own activity. |
| [`consolidation.md`](consolidation.md) | PHX-1097 | The substrate's identity settled for the first time: 147 proposals, 78 merged as the same entity, 68 nodes absorbed; structural context rejected as an identity signal. |
| [`answer_quality.md`](answer_quality.md) | PHX-1087 | First answer measurement, on the founding corpus: all arms within four points, and one sentence of prompt ("reply UNKNOWN") worth 21. Its control group was later shown to be mis-scored (PHX-1098). |
| [`hipporag_answers.md`](hipporag_answers.md) | PHX-1089 | Retrieval is worth +11 to +23 exact match over the model's prior on three datasets; Spreading Activation ties kNN at the default and beats it by +5.0 on 2WikiMultihopQA at narrow hybrid seeding. |
| [`qa_benchmark.md`](qa_benchmark.md) | PHX-1056 and earlier | Spreading Activation against kNN and BM25 on passage recall: +0.102 recall@5 on held-out 2WikiMultihopQA. An earlier exact parity was a seeding artefact of the harness. |

Every figure above is the project's own, measured on the corpus and model named
in its etappe, and several were later qualified by another row of this table.
Read the limits section before quoting one.
