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

### The answer: no change, and the instrument is noisier than it was quoted at

Six answer runs, `deepseek-chat`, temperature 0:

| mesh | k_seeds | closed_book | constellation | complete |
|---|---|---|---|---|
| before | 5 | 51% | 53% | 17/47 |
| after | 5 | 50% | 50% | 17/47 |
| before | 1 | 52% | 53% | 17/47 |
| after | 1 | 51% | 51% | 17/47 |
| before | 1 | 50% | 52% | 16/47 |
| after | 1 | **43%** | 52% | 18/47 |

**The closed-book arm swung from 43% to 52% across runs that differ in nothing
it can see** — it gets no material, so it is mesh-independent and seed-independent
by construction. That is **9 points of noise on the control**, and it is the most
useful number in this table: it says the instrument cannot resolve the
three-point differences this repo has been quoting from it. PHX-1096 hedged its
~3 points as "the spread is nearly the size of the effect". The spread is larger
than that, and the hedge was too generous.

The paired form avoids the control entirely — same 47 questions, same model, one
mesh against the other:

> **post better on 7 questions, worse on 6, equal on 34.**

That is a wash, and the individual moves are large in both directions:
`hundred-handed` 0/3 → 3/3 and `geryones-oxen` 1/3 → 3/3 against `tethys-rivers`
4/4 → 0/4 and `pegasus-birth` 2/3 → 0/3.

On the discriminating slice — the 33 questions the model failed to answer fully
from memory in *both* runs, so the question set is identical for both meshes —
the constellation arm scores 49.4% before and 44.2% after, 9 complete against 8.
The graph is worth roughly +19 points over pretraining before and +15 after, on
33 questions; the difference between those two is smaller than what the control
just demonstrated this instrument can invent.

**So: retrieval improves, the answer does not.** Retrieval delivers three more
fully-covered questions at k=1 and the answer step converts none of them. That is
consistent with everything since PHX-1087 and it now has a cleaner statement: the
loss is not in what the substrate holds, not in what it is called, and not in
what reaches the working set.

### The regressions are propagation, not bookkeeping

`tethys-rivers` losing all four rivers is the largest single move, so it was
traced rather than assumed: **the Tethys node and all four river nodes were
untouched by the merge** — no cluster contained any of them, and Tethys's
description is byte-identical. What changed is the graph around them. Absorbing
68 nodes and coalescing 1,080 edges redistributes PPR mass, and a node that sat
just inside a top-50 budget can fall just outside it without anything having gone
wrong with it.

That is worth stating plainly because the alternative explanation — a rewiring
bug — is the one this pass is most likely to have, and it is the one that was
checked first.

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
