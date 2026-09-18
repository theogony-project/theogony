# What Gen 1 promises — the vision held against the inventory

> **Abstract.** The doctrine inventory (PHX-1100) says which mechanisms
> run; this page says what that means for the vision. *"The mesh is alive: it
> grows, it links, it forgets, it consolidates, and it heals"* — verb by verb,
> as of 2026-08-31: it grows; it links, though 93% of edges are proximity rather
> than judgement and Q-IDs no longer exist (127 of 130 were confabulated); it
> forgets — *and only that*; it consolidates on request since PHX-1097; it does
> not heal; it does not learn from use. Of the README's five lifelike dynamics
> one runs, and it is the one that takes away. The "permanent dream" drives the
> Generation-1 store; the mesh tick has one caller outside the tests, the CLI,
> and the README's +34.8% MRR comes from an in-memory simulation that never
> writes. Of the three empirical questions one is answered, for retrieval:
> Spreading Activation beats kNN by +0.102 recall@5 on held-out 2WikiMultihopQA.
> Four doctrine sentences are contradicted by measurement — most sharply the
> tier ladder, inverted where weights live (for w < 1 a gentler exponent removes
> *more*: 2.5× at the median weight 0.3112). Five README sentences are listed
> with their evidence. The page closes by restating what Generation 1 honestly
> promises — a substrate that is read into and activated, that forgets,
> consolidates on request, remembers what it used, and says all of this itself.
> Two addenda from the following day move the verb "learns": to *holds what it
> uses* (PHX-1102), then, on 2Wiki, to *learns, and displaces* (PHX-1104).

*2026-08-31, after PHX-1097 (consolidation), PHX-1100 (inventory) and PHX-1101
(activation memory). Against `README.md`, `docs/VISION.md`, the MESH triplet,
and `ROADMAP.md`, with this session's measurements.*

## Why this page

The inventory ([`doctrine_inventory.md`](doctrine_inventory.md)) says which
mechanisms run. It does not say what that means for the vision — and the
vision is the reason everything else is built. This page holds the two
against each other and, at the end, restates what the substrate honestly
promises in Gen 1.

The doctrine demands this explicitly. `MESH_SUBSTRATE.md` §"Why the
substrate's mechanism is a system": *"Implementations should be honest about
which subset they realise and which failure modes are open as a result."*
This is that honesty, on one page.

## The vision has three layers, and the inventory reaches only one

**The civilisational layer** — rails instead of vehicles, a commons that
belongs to no one, provenance and contradiction as first-class citizens, a
foundation instead of an exit. Nothing in the inventory touches it. It is a
bet on governance, not on code, and it does not become wrong because a
counter stands at zero. This page leaves it alone.

**The empirical layer** — the three questions against which the README
measures the project. One of them is answered, two are open. More on this
below.

**The architectural layer** — the MESH triplet, the sentence *"The mesh is
alive"*, the five lifelike dynamics, the permanent dream. This is where the
inventory has its effect, and here the gap between what the documents say and
what runs is largest. The rest of this page is about that.

---

## "The mesh is alive" — verb by verb

The sentence MESH_SUBSTRATE condenses to: *"The mesh is alive: it grows, it
links, it forgets, it consolidates, and it heals."* After the inventory, with
the evidence per verb:

| it… | status | evidence |
|---|---|---|
| **grows** | yes | 1,210 paragraphs read, 5,002 nodes, 94,490 edges; ingestion runs and is audited (13,883 audit lines) |
| **links** | yes, with one caveat | the eager linker runs; but 93% of edges are proximity, not judgement (PHX-1066), and the strongest identity signal — Q-IDs — no longer exists on the mesh (127 of 130 were confabulated, PHX-1063) |
| **forgets** | **yes — and only that** | 14 ticks of super-linear decay, visible in the weight spectrum; unconditional, because no firing signal existed |
| **consolidates** | as of today, by hand | PHX-1097: 48 clusters, 68 nodes; as a script, not in the tick, because it needs a language model |
| **heals** | no | pathology monitoring, therapy, contradiction resolution, misinformation removal: none of it exists |
| *learns from use* | **no** | Hebbian reinforcement wired, never fired in 14 ticks, and 17–254× too weak against decay (PHX-1102) |

The last verb is not in the sentence. It is in the README ("The learning loop
closes"), in VISION.md ("amplified by Hebbian reactivation along
frequently-used paths"), and in the doctrine as the first of the five
primitives. It is the verb that distinguishes a substrate from a database —
and it is the one furthest from running.

The honest sentence for Gen 1, today: **The mesh is read, activated, and
forgets. It consolidates on instruction. As of today, it remembers what it
has used. It does not learn, it does not heal.**

## The five lifelike dynamics

The README, section 2: *"Lifelike dynamics — Hebbian strengthening,
super-linear decay, bounded saturation, atrophy decoupled from deletion,
homeostatic renormalisation."* Five mechanisms in one breath.

| | runs? | what the measurement says |
|---|---|---|
| Hebbian reinforcement | wired, never fired | strongest delta of one query 2.9e-4 against 4.8e-3 decay per tick; it cannot even *create* edges — the branch is unreachable from the production path |
| super-linear decay | **yes** | k=2, λ=0.05, every tick, every edge |
| bounded saturation | inert | cap 10,000 against a maximum out-degree of 1,093; never clipped anything in 14 ticks; the doctrine's weight-sum cap is absent |
| atrophy decoupled from deletion | absent | no health band, no pruner, no resource-pressure trigger |
| homeostatic renormalisation | absent | a single hit in the repo: the docstring saying it is not built |

**One of five.** And the one that runs is the one that takes away.

This is not a criticism of the doctrine. It says itself that a subsystem
*"fails differently than the full design"*. Super-linear decay without
renormalisation and without reinforcement is exactly such a subsystem, and
its failure mode can be named: **a substrate whose weights run monotonically
toward zero, slowed only by how often ticks happen.** Fourteen ticks over
eleven days moved the founding mesh from a weight mode of 0.4 to 0.31.
Nothing pushes back.

## The permanent dream

VISION.md: *"There is no nightly batch job. Instead, a continuous,
low-priority 'dreaming' process runs at all times."* README: *"a continuous
low-priority process that runs activation across existing knowledge, treats
the resulting constellations as new observations, and writes back denser
connections. The Chronik grows wiser without reading new text."*

Three things about this, each individually evidenced:

1. **The mesh tick has no schedule.** `run_minimal_tick` has exactly one
   caller outside the tests: the CLI. There is an `OneirosWorker` with
   `tick_interval_s` — it drives the **Gen-1 store** and imports
   `theogony.mesh` nowhere. The permanent dream is the old dream, over the
   old database.
2. **"Writes back denser connections"** — the Hebbian write-back cannot
   create an edge (the branch is unreachable), and it has never fired on the
   mesh. Every one of the 94,490 edges comes from ingestion.
3. **The README's "+34.8% MRR with no new text"** comes from
   `scripts/mesh_oneiros_dream.py`, which, by its own docstring, *"never
   writes to the workspace"*. It is a simulation over an in-memory copy,
   using the real tick functions — a legitimate experiment, but not a
   process that runs anywhere, and not a mesh that became denser through it.

The dream is real as a measurement and fiction as a process. That is a
different claim than the README's.

## The three empirical questions

The README calls them *"the line between believing in the substrate and
demonstrating it."*

**1. Does Kadmos v2 read denser than chunking?** Unanswered, and the question
is posed worse than it looks: there are **two** Kadmos v2's
(`kadmos/reader.py`, cognitive, with a dead similarity channel; and
`mesh/ingestion/kadmos_v2.py`, production, but *"paradigmatically v1:
stateless per paragraph"* — the July deep audit). What the founding mesh read
is the second one. `TARGET_ARCHITECTURE` lists the question as *Monkey 1*
with status *"Kadmos v1 baseline established (0.49 ratio). True Nous not yet
implemented."* That is still the status.

**2. Does Spreading Activation beat kNN at high edge density?** **Yes,
measured — the one demonstrated result of the project.** On held-out
HippoRAG questions, with a configuration chosen without looking at them:
**+0.102 recall@5 on 2Wiki**, +0.030 HotpotQA, no drop on PopQA. And the path
there was instructive: the first measurement found *exact parity*, and that
was a seeding artefact (seed retention 1.000, rescue rate 0.000). The
advantage lives at tight seeding — which this session confirmed on the
founding mesh (k_seeds=1: 87%, k_seeds=5: 78%, k_seeds=32: 59%).

Two caveats belong here. Retrieval on the founding mesh sits at 87% recall —
but the **answer step** does not move, no matter what retrieval delivers, and
the instrument meant to measure that has **nine points of spread** (43–52%)
on its mesh-independent control group, and a gold set that rewards a
duplication the substrate is supposed to remove (PHX-1098). The corpus is
Hesiod, and the model has read Hesiod; half of every answer result is prior
knowledge. **On this corpus, the second question can no longer be decided for
the answer step.** For retrieval, it is decided.

**3. Does the MNLM produce inferences that appear in no source?** Not tested.
Blocked on H100 compute time (PHX-1035). And the falsifier has a structural
false-positive channel that the deep audit named: the model writes into the
index the grader reads, and Llama knows Wikipedia. The ablation controls
(frozen-mesh, parametric-only) are now in the brief §6.2 — but the question
remains the only one of the three for which there is not a single number.

**Balance: one of three answered, for retrieval.** That is more than most
projects of this size can show, and less than the README suggests when it
lines the three questions up as *"next milestones"*.

## Where the doctrine itself needs correcting

The inventory found mostly implementation gaps. In four places it found
something else: sentences in the triplet that cannot stand as written,
because measurement contradicts them.

1. **Tier-modulated decay.** MESH_SUBSTRATE §2: higher tiers carry *"gentler
   decay exponents"* (k=2 → 1.5 → 1.2 → 1). For `0 < w < 1`, `w^1,2 > w^2`
   holds; the smaller exponent removes *more*. At the median weight 0.3112,
   k=1.2 loses 2.5× what k=2 loses. All weights sit below 1, because `w_max`
   holds them there. **The ladder runs backwards in the weight range the
   substrate actually inhabits.** Either weights are allowed to live above 1
   (renormalisation), or the modulation has to be formulated differently
   (e.g. λ per tier instead of k per tier).
2. **The activation threshold.** MESH_IMPLEMENTATION §"Damping and stop
   conditions" and ROADMAP: *"propagation halts at min_activation (~0.05)"*.
   The number is calibrated for `x_{t+1} = damping · A · x_t + injection`.
   What runs is PPR, mass-conserving, on a different scale: at the median, 9
   of 50 nodes reach 0.05. The number belongs to an operator that has not
   shipped.
3. **"Typically 10–30 % of edges have any descriptor populated."**
   (MESH_IMPLEMENTATION §"Edges"). Measured on every mesh in the repo:
   **100%** — 94,490 of 94,490, 984,070 of 984,070. The sentence describes an
   extraction that does not exist; the consequence is that the metadata
   table is as large as the edge tensor, and a cold `mesh ask` pays 352 ms
   to build it.
4. **`fired_recent` is a "rolling window counter"** with no window length,
   and nothing in the triplet says whether a source anchor fires. PHX-1101
   had to decide both (γ=0.9, unjustified; anchor yes, measured) — the
   doctrine should append this, rather than leaving the answer in a ticket.

In addition, from the July deep audit and still unchanged: the tier-1
arithmetic in `CHRONIK_SCALE` does not add up (CSR 95–250 GB against 80 GB
GPU), and MESH_IMPLEMENTATION contradicts itself on the edge count (10⁹
against 10¹⁰).

## What in the README is no longer true

The section *"Where we are — honestly"* is the README's strongest piece, and
exactly for that reason its sentences have to be true. Five of them no longer
are, or not as they stand. Here they are with the evidence — **not
changed**, because the README is Jakob's voice and because the scope of
this page was one document, not two.

| README says | Status | Proposal |
|---|---|---|
| *"Lifelike dynamics — Hebbian strengthening, super-linear decay, bounded saturation, atrophy decoupled from deletion, homeostatic renormalisation."* | one of five runs | *"Lifelike dynamics — super-linear decay runs; Hebbian strengthening is wired and at the shipped calibration cannot hold an edge against one tick of decay (PHX-1102); saturation, atrophy and renormalisation are specified and unbuilt (PHX-1100)."* |
| *"A continuous Oneiros process scores and promotes knowledge"* | Gen-1 worker; the mesh tick is unscheduled; nothing was ever promoted (`consolidation_tier` = 1 everywhere) | *"A continuous Oneiros process runs on the Gen-1 store; the mesh tick is invoked by hand (`mesh tick`), and tier promotion has an input only since PHX-1101."* |
| *"The learning loop closes … Query → reinforcement → tick → denser mesh now runs end to end"* | runs end-to-end, was never executed, cannot create an edge, and is 17–254× too weak | *"The learning loop is wired end to end and has never run on the founding mesh: all 14 ticks drained zero reinforcement, and at the shipped α/λ a single query's strongest delta is 17× smaller than one tick of decay (PHX-1102). It cannot create edges; the create branch is unreachable from the query path."* |
| *"one continuous Oneiros 'dream' pass improved held-out link-prediction MRR by +34.8 %"* | in-memory simulation, never writes back | *"an in-memory simulation of the dream pass, using the substrate's real tick functions on a copy, improved held-out MRR by +34.8 % — no mesh was changed by it."* |
| *"recall over them runs 74 % at the default 50-node constellation"* | 80% at default, 87% at k_seeds=1 (consolidated) | Update the number and name the seed finding (PHX-1099). |

And a sentence that is missing: **that consolidation exists** (PHX-1097) and
that the inventory is public. The first is the substrate clarifying its own
identity for the first time; the second is the most honest status line this
project has ever had.

`llms.txt` carries the same sentences in shorter form, and the same errors.

---

## What Gen 1 honestly promises

The vision has not become wrong. What the inventory showed is the gap
between the sentence *"the mesh is alive"* and the status quo — and that this
gap consists of **sensing**, not insight. Several organs are built and
connected to sensors that were never installed. As of today, the first one
is installed.

So, restated, what the substrate promises in Gen 1 — every sentence with
evidence:

> **Gen 1 is a substrate that is read into and activated from.**
> It holds knowledge as vectors and weighted edges, with no raw text as
> payload, and activation over it beats nearest-neighbour on multi-hop
> questions — measured on held-out questions, with a configuration chosen
> without looking at them.
>
> **It forgets.** Super-linearly, every tick, every edge.
>
> **It consolidates on instruction.** A pass that merges entity candidates
> with a language model, regenerates the description, and leaves every
> absorption in the audit.
>
> **It remembers what it has used.** As of today — and nothing reads from
> it yet.
>
> **It does not learn from use, it does not heal, it does not promote.**
> The organs for this are partly built, their calibration is not, and the
> doctrine they were built from needs correcting in four places.
>
> **And it says all of this itself.** Every claim about this substrate is
> measured against a control, every failure is filed as a ticket, and the
> inventory of what runs is public. That is the one promise Gen 1 fully
> keeps today.

That is less than *"a language model turned inside out"* and more than *"a
very good RAG"*. It is a reading substrate with the skeleton of a living
one, whose heartbeat has not yet been measured — and whose first heartbeat is
the next work ([`PHX-1102`](../../phoenix-backlog/PHX-1102.yaml)).

## Addendum, the day after

The line *learns from use — no* in the table above has been inaccurate since
PHX-1102, in both directions. Decay now spares what has fired; the substrate
**holds what it uses** — measured, with no side effect on what is unused. And
the heartbeat, "responds better to what has been used", was measured live and
**did not** appear: recall invariant over ten rounds, under every policy. The
verb moved from *no* to *holds*, not to *yes*. The reformulation above stays
as it stood on 31 August; the one sentence in it that has changed is "it does
not learn from use" → "it holds what it uses, and does not yet learn
visibly". Why, and what would make the heartbeat visible:
[`hebbian_calibration.md`](hebbian_calibration.md), PHX-1104.

## Addendum II, the day after

On 2Wiki, where retrieval has room to move, **the verb moves for the first
time**: with gate and Hebb at doctrine scale, the used questions improve by
+1.3 points and stay improved over 50 rounds. And the held-out ones get worse
by −1.5 — monotonically, with or without credit. *Learns* has thus moved from
*holds* to **"learns, and displaces while doing it"**. The counterforce the
doctrine provides for this is renormalisation (§6); it is the next organ
([`heartbeat_2wiki.md`](heartbeat_2wiki.md), PHX-1106).

## What this means for the order

Nothing new relative to the inventory, only confirmed from the vision's
side: the verb the vision misses most is *learns*. The path there is
activation memory (built) → decay only on what has not fired, and α against λ
(PHX-1102) → renormalisation, so the tier ladder does the right thing.
Splits, pathology and therapy after that — they read from a history that, as
of today, has only just begun being written.
