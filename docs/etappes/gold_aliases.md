# The gold set repaired: aliases, and nothing left that gives away the question (PHX-1098)

> **Abstract.** *Question.* Can the founding gold set be trusted as an
> instrument? *Found.* Two defects in one file: no answer aliases ("Eos, Selene,
> Helios, Helius" scored 3/3 for naming one god twice, the correct "Helios, Eos,
> Selene" 2/3), and 30 of 111 gold names standing in their own question, which
> pays any arm that restates the question. Cleaning up exposed three
> expectations that were simply wrong against the corpus. *Repair.* 92 names
> with 130 aliases, the canonical name counted once, the retrieval matcher reads
> aliases too, and two tests hold the rule. *Re-measured on the same stored
> answers* (423 answers, deepseek-chat, three repeats), old gold against new:
> closed-book 47% → 86%, vector-only 47% → 63%, Constellation 61% → 75%. Graph
> over vector search, +11, holds under every scorer. Graph over prior flips from
> +11 to −11: the old gold had systematically under-scored the control, and its
> nine-point spread across repeats shrinks to two — part of the "model noise"
> was the scorer. Retrieval recall falls from 87% to 80%, because restated names
> were free hits. *Consequence.* A corpus the model knows by heart at 86% cannot
> measure the graph's value for answering; that question moved to a corpus it
> does not know (PHX-1110). Historical figures stay in their tickets as
> measured.

**Status:** 2026-09-16, measured. Track C of the plan, first piece.
**Tools:** `eval/gold/founding_corpus.json` (`aliases` per question), `corpus_answers._score(…, aliases)`, `corpus_qa.GoldQuestion.names_for`, two new hygiene tests.

## Two defects in one file

**No aliases.** The scorer compared the gold string literally. The gold said
`Helius`, the translation and the models also say `Helios`, and so "Eos,
Selene, Helios, Helius" scored 3 of 3 for naming one god twice, while the
correct "Helios, Eos, Selene" scored 2 of 3. A gold set that could be
satisfied by a duplication that the substrate is meant to remove (found in
PHX-1097, deliberately not fixed there, because an instrument correction that
lands on the result that flatters it is worth nothing).

**The question gave away the answer.** 30 of the 111 gold names stood in
their own question — "What measures the depth of Tartarus?" expected
`Tartarus`, "How were Chrysaor and Pegasus born?" expected Chrysaor and
Pegasus. A substring scorer pays for that the moment an answer echoes the
question, and pays the arm that answers in sentences the most: the soft arm
of the latent mile (PHX-1109) came out at 28% that way, where a strict count
gave 11%.

Cleaning up exposed **three expectations that were simply wrong**, each
checked against the corpus:

| Question | stood in the gold | stands in the text |
|---|---|---|
| Whom did Hermaon beget with Thronia? | Thronia, Belus | **Arabus** — Belus is Thronia's father (Fr. 15) |
| What offspring did Echidna bear to Orthus? | Echidna, Orthus | **Sphinx** and **Nemean lion** (Theog. 326) |
| Who are the sons of Iapetus? | Menoetius, Prometheus, Epimetheus | plus **Atlas** (Theog. 509) |

And several questions whose "answer" was only their own subject now expect
what they ask: `fifty` for the daughters of Nereus, `foam` for Aphrodite,
`anvil` for the depth of Tartarus, `fire` for the Chimaera, `flesh`/`bones`
for Prometheus's portions, `Earth`/`Heaven` for the reason Cronus swallowed
his children.

## What changed

- **92 gold names instead of 111, with 130 aliases.** Every name carries the
  spellings that this translation and the models use (Helius/Helios,
  Heaven/Uranus, Sea/Pontus, Eunomia/Order). The scorer accepts any of them
  and counts the canonical name once.
- **The retrieval matcher** reads the aliases too: a node that the substrate
  names `Helios` answers a gold entry `Helius`.
- **Two tests hold this in place:** no expected name and no alias stands in
  its own question; every alias belongs to an expected name. The counts are
  pinned exactly (92, 65 genealogical), because a lower bound does not notice
  when a published number stops matching the file.

## The re-scoring — the effect of the instrument, separated from the model

Tickets PHX-1087, 1096 and 1097 were measured on the old scorer. Their
numbers are not silently replaced here; instead the change itself is
measured: **the same stored answers, three scorings.**

### The latent mile (PHX-1109), stored answers from the 3B reader

| Arm | old gold, 111 names | old gold without the echoed ones | new gold, 92 names with aliases |
|---|---|---|---|
| `closed_book` | 16% (4/47) | 14% (3/39) | 15% (6/47) |
| `constellation` (text) | 38% (8/47) | 49% (13/39) | **47% (16/47)** |
| `soft`, 20 epochs | 28% (11/47) | 11% (4/39) | **14% (6/47)** |
| `soft`, 5 epochs | 19% (6/47) | 9% (2/39) | 10% (3/47) |
| `soft_untrained` | 11% (2/47) | 0% (0/39) | 0% (0/47) |

The new gold reproduces the strict count from PHX-1109 almost exactly — and
does so over all 47 questions instead of the 39 the strict count left over.
The text arm rises (the aliases pay off, and the questions now demand answers
it gives), the soft arm falls to what it actually carries. The two
corrections — in the harness and in the file — say the same thing,
independently of each other.

### Retrieval on the founding mesh (`k_seeds=1`, `top_k=50`, 14 ticks)

| | old gold | new gold |
|---|---|---|
| Recall | 87% | **80%** (72 of 90 present) |
| complete | 39/47 | 34/47 |
| genealogical / narrative | — | 86% / 65% |

The drop is the correction itself: the echoed names were free to retrieve,
because the question names them and the name anchors seed them. What is
missing now are real answers, and two of them are not entities (`fifty`,
`anvil` — coverage 98%) and a few more are common nouns that the substrate
holds but does not activate (`foam`, `fire`, `stone`, `Sea`, `Hecate`, the
three shield figures, `flesh`/`bones`). That is a more honest number for the
narrative part: 65% instead of the 86% PHX-1080 reported for it.

### The answer arm (deepseek-chat, three repeats, `data/mesh-founding`, 14 ticks)

423 answers, generated once, scored three times:

| Arm | old gold, 111 names | old gold without the echoed ones | new gold, 92 names with aliases |
|---|---|---|---|
| `closed_book` (the prior) | 47% (13/47) | 65% (21/39) | **86% (39/47)** |
| `vector_only` | 47% (13/47) | 57% (20/39) | 63% (29/47) |
| `constellation` (graph) | 61% (18/47) | 72% (24/39) | **75% (31/47)** |

Spread across the three repeats under the new gold: the prior 85–87%,
vector search 63–64%, graph 73–76%. **The old scorer had spread nine points
on the control group** (43–51%, PHX-1087); with aliases it is two. Part of
what counted as model noise was the scorer, which counted or did not depending
on spelling.

**Two claims, one holds and one flips.**

*Graph against pure vector search: +11, and it holds.* 63% against 75%, under
each of the three scorers, with the same number as in PHX-1097. The edges
under the same nodes carry something that cosine neighbourhood does not
carry.

*Graph against the prior: +11 flips to −11.* Under the old gold, the prior
stood at 47%, under the new one at 86%, and the Constellation falls
below it. The reason is the scorer, not the model: the old gold expected the
subject of the question for 30 names — "Cerberus" for *what offspring did
Echidna bear to Orthus* was a correct answer and scored zero, because the
gold wanted Echidna and Orthus. The prior answers correctly and was
systematically under-scored for it. And the new gold demands what the
question asks: `foam`, `fire`, `anvil`, `fifty`, `flesh`/`bones` — things a
model knows about Hesiod that are not entities in the substrate, or are not
activated.

Question by question: the graph wins 5, loses 11, ties 31. The eleven losses
are of two kinds. **Instructional:** the graph arm may use only the material
and says "I don't know" to the stone Cronus swallowed, and "no entity or
relation that measures" to the depth of Tartarus — the prior answers "a
stone" and "anvil". **Retrieval:** the Constellation does not carry Coeus,
Crius and Mnemosyne, nor Eunomia, Dike and Eirene, nor Briareos, and a model
bound to the material cannot name them. The five wins are what the corpus
says idiosyncratically and a model cannot know by heart: Eosphorus, the
tortoise, the children of Strife, the parents of Typhoeus.

**The consequence for the instrument.** On a corpus the model knows by heart
at 86%, the answer arm does not measure the graph's added value, but the
price of binding to it. PHX-1087 had seen the prior at 50% and
concluded from it that the corpus was fit as a control group; the 50% was the
scorer. What remains is the comparison against vector search — and the
second piece of Track C, the answer arm on a corpus the model does not know,
is thereby no longer a supplement but the only way to ask the question "does
the graph help with answering" at all.

The numbers from PHX-1087, 1096, 1097 and 1099 stand in their tickets as they
were measured; this table is the re-scoring, not their replacement. The
decision `k_seeds = 1` (PHX-1099) rests on the retrieval tune/test, not on
the answer arm, and stands.
