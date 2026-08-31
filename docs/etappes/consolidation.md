# Oneiros consolidation — the substrate's identity, settled for the first time

*2026-08-31. `data/mesh-founding` at 14 ticks, 5,002 consolidated nodes, 94,490
edges. Adjudication by `claude-sonnet-4-6`; answers by `deepseek-chat`,
temperature 0, the 47-question founding gold set. Migration step S5.*

## What was missing

`MESH_SUBSTRATE.md` §"Why two tiers — and how identity actually gets committed"
specifies identity in two halves. Eager linking commits it when Q-ID,
description or tag evidence decides; when nothing decides, the reference becomes
an **entity candidate** and *"Oneiros, on its next tick, either consolidates
several candidates into a confirmed Tier-1 entity … or merges a candidate into
an existing entity"*.

Only the first half was ever built. What that looks like from inside the
substrate:

- **all 3,783 entity nodes carry `is_candidate = True`.** Not one had ever been
  confirmed, because nothing existed that could confirm one.
- **Zeus is six nodes** — `Zeus`, `son of Cronos`, `her father`, `father of men
  and gods`, `Son of Chronos`, and a paragraph concept.
- **Apollo and Athena have no canonical node at all.** Every node for them is an
  epithet: `Phoebus`, `Phoebus Apollo`, `Far-Shooter`, `Far-Worker`, `Pythian`;
  `Athene`, `Pallas Athene`, `Tritogeneia`, `bright-eyed daughter of a mighty
  father`.

That is the read surface PHX-1096 hit from the answer side and PHX-1064 from the
retrieval side. A Constellation answering *"the children of Cronus and Rhea"*
showed `her father`, `Host of Many`, `dear mother` and `Vesta` — four correct
retrievals, each displaying the name of a **mention** rather than of an entity.

## How the merge decides

    propose      pure substrate bookkeeping, no network
    adjudicate   one small LLM call per pair
    apply        rewire edges, fuse nodes, write the audit
    regenerate   one small LLM call per surviving cluster

**Star-shaped, never transitive.** For each discriminating name the node with the
strongest claim becomes the anchor, and a node that anchors any name can never be
absorbed by another. This is the whole safety argument, and the substrate shows
why it is needed: the node `Daughter of Cronos — A goddess, daughter of Cronos,
likely Athena or Hestia` carries **both** names as tags. Under a transitive
closure it is the bridge that fuses two goddesses into one node — which then
looks like the best-evidenced node in the mesh. A star forbids that by
construction rather than by threshold.

**Two category rules do the work a threshold was supposed to do.** The first dry
run proposed 23 paragraph concepts for absorption into `Theogony` under the tag
`Greek mythology`, and 16 numbered fragments into `Fragment #7`. Neither is a
confidence problem:

- a paragraph concept is a summary of a passage, not the entity it is about —
  excluded from the pass on both sides;
- `Fragment #3` and `Fragment #37` are one name only because the evaluator's name
  fold strips digits (it must: the corpus writes `Hestia 1618`). Identity keeps
  them. Measured: 63 of 2,453 capitalised tags contain a digit and **every one is
  a citation label**, so keeping digits costs nothing.

With those two in place the document-frequency ceiling is **inert** — 147
proposals at DF≤12 and the same 147 at DF≤100. It stays as a bound on fan-out for
meshes seeded from Wikidata, where type labels are capitalised, and the comment
in the code says it is doing nothing here rather than implying it is doing the
work.

## What the adjudicator did

147 proposals: **78 same, 34 different, 35 uncertain.** Only `same` merges;
doctrine's bar for a destructive operation is "beyond 'this might be wrong' into
'this is demonstrably wrong'".

It is not rubber-stamping. It refused `Trojan War ← Aethiopis / Little Iliad /
Iliou Persis / Nostoi / Telegony` (five epics of one cycle), `Salamis ← Battle of
Salamis`, `Erebus ← Chaos`, `Tethys ← Theia`, `Pallas ← Coeus / Crius /
Astraeus`. It missed some it should have taken — `Demeter ← dear mother` and
`Pluto ← Host of Many` came back `different`.

**The structural context score does not predict identity, and that is worth
writing down.** The doctrine offers "description similarity + structural context"
as identity signal 2. On these 147 pairs the highest context scores in the whole
set sit on *false* pairs: `Erebus ← Chaos` at 0.90, `Tethys ← Phoebe` at 0.89,
`Trojan War ← Iliou Persis` at 0.88. Two nodes that appear in the same passages
are related, not identical — and in a genealogy, being related is the normal case.

Result: **48 clusters, 68 nodes absorbed, 5 dropped as ambiguous**, 5,002 → 4,934
nodes, 94,490 → 93,370 edges (1,080 coalesced, 40 merge-created self-edges
dropped), 0 dangling endpoints.

## What the regenerated descriptions look like

    -  Zeus — King of the gods, son of Cronos, aegis-holder.
    +  Zeus — King of the gods, son of Cronos, aegis-holder, father of Persephone,
       who granted frogs their dual nature, freed the Hecatoncheires, and led the
       Olympians in the Titanomachy.

    -  Athene — Goddess of wisdom, daughter of Zeus, bright-eyed.
    +  Athena — Goddess of wisdom and war, daughter of Zeus, born from his head,
       daughter of Metis, bright-eyed, aegis-bearer.

    -  Aegyptus — The land of Egypt, near which Nysa is located.
    +  Egypt — A country in North Africa, near which Nysa is located.

**Does it invent?** Measured, because it looked like it did: `Hadrian — Roman
emperor from 117 to 138 AD` reads exactly like pretraining leaking into the
substrate. It is not — those years came from a second Hadrian node the pass
absorbed. Over all 48 clusters, **7.2% of content words in the regenerated
descriptions appear in no member description and no member tag (41 of 573), and
30 of 48 clusters have none at all**; the words that do appear are connective —
`including`, `epithets`, `referring`. The bound is honest but it is a bound, not
a proof: this counts words, not claims.

A regenerated name is refused unless the substrate already holds it. That guard
is PHX-1065's, at the moment it matters most: the label index and the eager
linker both key on the head of the description, so a plausible new name would
make the survivor unreachable under every name it had — in the same pass that
deletes the nodes which carried them. It fired 0 times in 48.

## What it did to the numbers

### Retrieval: better, once the seed count is off the wrong side of the curve

At the shipped `k_seeds=5` the merge costs two entities. The seed sweep says why,
and it is not something the merge did wrong:

| k_seeds | before | after |
|---|---|---|
| **1** | 84% · 36/47 | **87% · 39/47** |
| 2 | 82% · 35/47 | 81% · 37/47 |
| 3 | 78% · 36/47 | 78% · 38/47 |
| 5 *(shipped default)* | 80% · 38/47 | 78% · 38/47 |
| 8 | 77% · 37/47 | 78% · 36/47 |
| 16 | 71% · 33/47 | 76% · 31/47 |
| 32 | 64% · 27/47 | 59% · 24/47 |

**The shipped default sits on the wrong side of the curve for both meshes**, and
consolidation moves the peak rather than lowering it: at k=1 the consolidated
substrate reaches **87% recall and 39 of 47 questions fully answered** against
84% and 36 — the best either number has been on this gold set. PHX-1091 narrowed
the default from 10 to 5 on a split; the sweep says it should have gone further,
and that this was already true before the merge.

The mechanism is the one consolidation is for. Before, seeding on "Zeus" hit one
of six fragments and needed further seeds to cover the entity; the extra seeds
bought coverage of *the same entity*. After, one seed **is** the entity, and
every further seed spends the budget elsewhere.

Two controls, both at the default:

| variant | recall | complete |
|---|---|---|
| merge + regenerated description, edges summed | 78.4% | 38/47 |
| merge, description left alone | 76.6% | 37/47 |
| merge + regenerated description, edges by max | 77.5% | 37/47 |

Regenerating the description is worth two entities on its own — the name at the
head is what name-anchored seeding reads. Summing coalesced edge weights beats
taking the maximum by one.

### The answer: no change, and the instrument cannot resolve what was asked of it

Two things have to be said before the numbers, because both bear on how much
they are worth.

**A flag reached nothing.** `scripts/mesh_corpus_answers.py` declared `--seeds`
and never passed it to `answer_gold_set`. Two runs in this round were written
down as `k_seeds=1` and were the library default. Argparse accepts the flag, the
script runs, the output looks right — from the outside a flag that reaches
nothing is indistinguishable from one that works. It is wired now, the resolved
`k_seeds` is printed in the run header beside the model and the tick count, and
`tests/test_script_flags_reach_something.py` parses all 25 scripts and asserts
every declared flag is read somewhere. This was the only one.

**The control is nine points wide.** Across four runs of the same 47 questions
at temperature 0, the closed-book arm — which receives no material, so it cannot
see the mesh, the seed count or `top_k` — scored 50%, 51%, 51% and **43%**. That
is the arm that is constant by construction. Temperature 0 is not determinism at
any provider, and a mixture-of-experts model batched across tenants is not close
to it.

So the instrument now reports its own range (`--repeat N`), and the comparison
that matters is the **paired** one, which survives the model's mood because both
arms answer the same question in the same process:

*At `k_seeds = 1`, three runs each, `deepseek-chat`, temperature 0:*

| mesh | closed_book | constellation | complete | paired vs closed_book | slice recall |
|---|---|---|---|---|---|
| before | 49% [48–50] | **59%** [57–62] | 18.7/47 | 18 better / 10 worse / 19 equal | **56%** (36 q) |
| after | 47% [46–48] | 57% [56–58] | 15.0/47 | 13 better / 8 worse / 26 equal | 47% (35 q) |

Two readings, and the first one is not about consolidation at all.

**The seed count was costing the answer arm six points.** At the shipped
`k_seeds=5` the constellation arm scored 53% and beat prior knowledge by +2. At
k=1 it scores 59% and beats it by **+11**. The graph was contributing five times
as much as the default let it show, and this holds on the *unconsolidated* mesh
— it is not a consequence of anything in this PR. It is the largest single
finding of the round and it belongs to `DEFAULT_K_SEEDS`, not to S5.

**Consolidation costs the answer.** 57% against 59%, and 15.0 complete answers
against 18.7 — consistently, across three runs whose ranges do not overlap
(56–58 against 57–62), and on the discriminating slice 47% against 56%. Recall
went *up* over the same change: 87% against 84%, 39 fully-covered questions
against 36.

So the substrate delivers more of the right entities and the model answers worse
from them. That is the round's real result, and it is not the result that was
expected from a pass whose whole purpose was to make the read surface say
`Zeus` instead of `her father`.

**On the spread.** Within one process the three repeats sit 2–5 points apart —
much tighter than the 43%–52% the same arm spanned across separate invocations
hours apart. So the instrument is reasonably stable within a sitting and not
across them, which is the worse of the two possibilities for a repository that
compares a number measured today against one measured last week. Every figure in
this document is from one sitting.



**Retrieval improves, the answer does not.** At `k_seeds=1` retrieval delivers
three more fully-covered questions and the answer step converts none of them.
That is consistent with everything since PHX-1087, and it now has a cleaner
statement than "62% is lost": the loss is not in what the substrate holds, not in
what its nodes are called, and not in what reaches the working set.

It is also, honestly, at the edge of what this instrument can say. The founding
corpus is Hesiod and the model has read Hesiod; the aggregate cannot separate the
arms, and the discriminating slice is 33 questions, on which a single entity is
three points. A claim smaller than that should not be made from this gold set at
all — including the ones this repo has already made.

### Where the answer regression actually is

At `k_seeds=1` the merge costs **nothing** in retrieval and gains: 93 → 97
entities, 36 → 39 questions fully covered, one entity lost in total (`Dreams`).
And **every question whose answer got worse had identical or better retrieval**.
The regression is entirely in the answer step, on input that is the same or
better.

It is not dilution either: the constellation context is 7,699 chars before and
7,798 after, 127 lines before and 117 after, 50 entity lines in both. The merge
does not make the model read more.

What is left is *what the entries say*. Reading the answers themselves:

**One is a real failure, and it is the one the prompt already warns about.**

    themis-children   expected: Horae, Eunomia, Dike, Eirene
      before  "the Horae (the Seasons), including Eunomia, Dike, and Eirene"   4/4
      after   "Moerae, Horae"                                                  1/4

The model replaced the list with the name of the group — the exact failure `_ASK`
was written to prevent ("do not replace a list of names with the name of the
group they belong to"). The merged mesh surfaces the group node `Horae` more
prominently, and the model took the shortcut.

**Two are the scorer punishing a better answer.**

    hyperion-children  expected: Helius, Selene, Eos
      before  "Eos, Selene, Helios, Helius"    3/3
      after   "Helios, Eos, Selene"            2/3

The earlier answer names the same god twice, under both spellings, and scores
full marks because the gold string `Helius` appears literally. The later answer
is correct and non-redundant and loses a point. **`Helios ← Helius` is one of the
48 merges** — consolidation removed a duplicate from the substrate, the model
stopped repeating it, and the instrument charged for it.

    nereus-daughters   expected: Nereus
      before  "The fifty sea nymph daughters of Nereus and Doris…"   1/1
      after   "Thetis, Amphitrite, Eudora, Thoe, Cymatolege, …"      0/1

The gold answer is the single name `Nereus`; the later answer lists the Nereids
and never says the father's name.

**The founding gold set carries no answer aliases.** `qa_datasets.py` has had
`answer_aliases` since PHX-1089 for the HippoRAG sets; `founding_corpus.json` has
none, so `Helios` is not `Helius` and a correct answer in different words scores
zero. Adding them would raise the post-merge number — which is exactly why it is
**not** done in this change. An instrument fix that lands in the same commit as
the result it flatters is worth nothing. It is filed instead, and the numbers
above stand as measured, artefacts included.

## Which model decided

The pass was launched believing it ran on `deepseek-chat`. It ran on
`claude-sonnet-4-6`. `.env` pins `THEOGONY_LLM__MODEL_ID` independently of
`THEOGONY_LLM__PROVIDER`, so setting only the provider built a DeepSeek client
asking for `gpt-4o-mini`; DeepSeek rejected the model, and every call fell
through to the configured Anthropic fallback. The script printed the resolved
model before it started and nobody read it.

Two consequences, both recorded rather than papered over. The merge quality here
is a **frontier model's**, so a run on the cheap model doctrine actually
recommends ("Gen 1 should use whatever the operator's main extraction model is")
is unmeasured. And the audit record now carries `adjudicator_model` and
`describer_model`: a consolidated substrate has to be able to say who decided
what it is, and "some model, once" is not an answer.

`ReplayAdjudicator` exists for the same reason. It replays a recorded pass's
verdicts, which is what made the two controls above free — without it, changing
how edges coalesce would also have changed every identity decision underneath,
and the comparison would have measured both at once.

## What is not built

S5's deliverable list is consolidation **plus** splits, renormalisation, the
pruner, pathology surveillance, therapy and three-factor RL. This is
consolidation.

**Tier promotion cannot run, and that is a finding rather than a deferral.**
Doctrine earns Tier 1 → 2 → 3 on "number of distinct activation contexts, age,
breadth of incoming references". `fired_total` and `fired_recent` are **0 on
every node in the substrate** and have no writer anywhere in `src/`. Promotion
would be promotion by age alone. This is the same shape as PHX-1095's
`decay_tier` — a doctrinal mechanism whose input nothing produces — and it is why
this pass leaves `consolidation_tier` at 1.

**Anchor-to-anchor merges are deferred by design.** Hades, Pluto and Aidoneus are
three anchors for one god. `Host of Many` is genuinely the same entity as all
three, and the pass reads matching several anchors as ambiguity and drops it — 5
nodes on this mesh. Settling those needs anchors adjudicated against each other,
which is a second evidence bar and a second pass.
