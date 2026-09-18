# The first heartbeat — α against λ, and what retrieval sees of it

> **Abstract.** *Question.* The substrate could only forget (PHX-1100).
> Three knobs were on the table — raise α, lower λ, or restrict decay to edges
> that did not fire, which is what the doctrine literally says — and the ticket
> asked for the choice to be measured. *Simulation* over the real weights of the
> founding mesh (94,490 edges, 24 of the 47 gold questions, 20 ticks, five
> policies): even normalised, the median Hebbian credit is eight times smaller
> than one tick of decay. The gate is the only policy under which used edges
> hold (0.594 against 0.359 for the ten most-fired) while the unused fade
> exactly as before; scaling α is worth +0.004; λ/10 slows everything and
> separates nothing. *Shipped.* `decay_edges_inplace(fired=…)`, on by default,
> byte-identical to the old tick when no firing was recorded. *Live heartbeat*
> (24 used / 23 held-out questions, ten rounds, on copies): recall does not move
> under any policy, and growth at α = 0.1 makes the held-out questions worse
> while pinning the top weight at the cap — the side effect without the
> improvement. *Why retrieval is blind.* The shipped operator is PageRank over a
> row-normalised adjacency: it reads each edge's share of its node's out-weight,
> and near-uniform decay preserves shares (working-set Jaccard 0.963 after ten
> ticks). The verb "learns" moved from *no* to *holds*, not to *yes*.
> Adversarial review before merge found a double-sparing bug after a failed node
> fold, an O(k²) firing index and lost timestamps — all fixed. Continued on a
> corpus with headroom: `heartbeat_2wiki.md` (PHX-1104).

*2026-09-01. `data/mesh-founding` (94,490 edges, 6,208 nodes), the 47
gold questions, `k_seeds=1`. Simulation and live runs on copies; no LLM, no
money. PHX-1102.*

## Starting point

The inventory (PHX-1100) found that the substrate can only forget: 14 ticks
of decay, zero fired reinforcement, and the strongest Hebbian write-back of
a query 17 times smaller than one tick of decay at the median weight. Three
knobs were on the table in the ticket — raise α, lower λ, or restrict decay
to **unfired** edges, which is what MESH_SUBSTRATE §2 literally says ("edges
that are *not* fired weaken") and which has only been possible since
PHX-1101, because before that there was no firing signal.

The ticket demanded that the choice be **measured** rather than argued.
Here is the measurement, in two stages: a simulation over the real weights,
then the live proof on the substrate.

## Stage 1 — simulation over the real weight distribution

`scripts/mesh_hebbian_calibration.py`. For 24 of the 47 gold questions
(every second one), each is queried once against the unchanged mesh and it
is recorded: which edges fired (both endpoints in the working set) and
which pairs the Hebbian path would credit with which product — raw and
with activation normalised to the peak value. Then 20 ticks, one round of
all 24 questions each, under five policies. The constellations are frozen;
that is a first-order approximation, and stage 2 checks it live.

Up front, what the orders of magnitude are:

    Edges that at least one question fires         16,077 of 94,490 (17%)
    Edges that all 24 questions fire                0
    one tick of decay at the median weight 0.3112   4.84e-3
    Hebbian credit per edge, raw                    max 5.26e-4   Median 1.82e-5
    Hebbian credit per edge, normalised             max 9.38e-3   Median 6.33e-4

Even *normalised*, the median credit is eight times smaller than one tick
of decay. The size of the credit is not what holds a used edge.

| Policy | 10 most-fired | never fired | Median |
|---|---|---|---|
| Start | 0.594 | 0.387 | 0.311 |
| **A** shipped — raw, everything decays, λ=0.05 | 0.359 | 0.270 | 0.237 |
| **B** α at doctrine scale — normalised, everything decays | 0.363 | 0.270 | 0.237 |
| **C** gate — raw, only unfired decays | **0.594** | 0.270 | 0.242 |
| **D** B + C | 0.601 | 0.270 | 0.242 |
| **E** λ/10 — raw, everything decays, λ=0.005 | 0.558 | **0.370** | 0.302 |

Nothing reaches the cap, nothing falls below 0.05 — no pathology in this
regime.

**The gate is the knob.** It is the only policy under which the used edges
hold, and it lets the unused ones fade exactly as before. α scaling alone
is worth +0.004 (B against A), on top of that +0.007 (D against C). λ/10
slows everything and separates nothing: the never-fired edges barely lose
anymore, and the used ones fall anyway.

That is also the *doctrine-faithful* answer. The other two trade one
number for another; the gate implements the rule the document has
contained since day one, and which never held only because no one recorded
what had fired.

## What shipped

- **`decay_edges_inplace(…, fired=…)`** skips edges that fired this tick.
  `fired_pairs()` derives them from the node firings (both endpoints in the
  same pass, both directions, because edges are stored directed) and pulls
  in the Hebbian deltas alongside them. The tick now pulls in **both**
  sidecars before decay and restores both if the write fails.
  `decay_gate=True` is the default; without a firing record it spares
  nothing, and the tick behaves exactly as before — this is tested.
- **`append_hebbian_deltas(…, normalize=)`** and `retrieve(hebbian_normalize=)`:
  normalise activations to the peak value before the product, i.e. to the
  [0,1] scale for which α≈1e-2 was written in the doctrine. PPR is
  mass-conserving over the whole graph, its raw activations are ~100×
  smaller — the same scale confusion that PHX-1095 found for the threshold
  0.05. **Default off**, measured marginal; a lever with a number, not a
  default.
- λ stays at 0.05.

## Stage 2 — the heartbeat, live

`scripts/mesh_heartbeat.py`. The first falsifiable claim of *"the mesh is
alive"* as a protocol: 24 used questions, 23 held-out. Measure recall on
both; for ten rounds ask all used questions (firing gets recorded) and
tick; measure both again. If one rises without the other falling, the
heart beats.

**It does not beat.**

| | used | full | held-out | full | w median | w max | spared |
|---|---|---|---|---|---|---|---|
| Round 0 | 84.8% | 18 | 82.2% | 18 | 0.311 | 0.905 | — |
| shipped, round 10 | 84.8% | 18 | 82.2% | 18 | 0.269 | 0.616 | 0 |
| gate, round 10 | 84.8% | 18 | 82.2% | 18 | 0.276 | **0.905** | 15,732 |

Not a single gold hit moved in ten ticks, under any variant — neither
under the shipped decay, which pushes the strongest weight from 0.905 down
to 0.616, nor under the gate, which holds it exactly. The gate does on the
substrate exactly what the simulation says: ~15,700 edges spared per tick,
the peak unchanged, the median higher than without it. And retrieval is
blind to it.

Then the growth variant — gate *plus* Hebbian at doctrine scale with a
deliberately large α=0.1, plus a rank-sensitive measure (mean rank of the
gold entities in a 200-entry working set, because Recall@50 only moves
once an entity crosses the budget boundary):

| Round | used | rank | held-out | rank | w median | w max |
|---|---|---|---|---|---|---|
| 0 | 84.8% | 27.4 | 82.2% | 30.3 | 0.311 | 0.905 |
| 2 | 84.8% | 27.5 | 82.2% | 30.5 | 0.302 | **1.000** |
| 5 | 84.8% | 26.8 | 82.2% | 30.9 | 0.288 | 1.000 |
| 10 | 84.8% | 27.5 | **80.0%** | 31.0 | 0.276 | 1.000 |

The used questions do not get better (rank 27.4 → 27.5). The held-out ones
get **worse** — one question less complete, rank 30.3 → 31.0 — and the
strongest weight sits at the cap from round 2 on. That is not an
improvement with a side effect; it is the side effect without the
improvement. Growth without the weight-sum cap and without renormalisation
— neither built — is the hub pathology that the doctrine warns against in
§3 and §6, not the heartbeat.

## Why retrieval is blind

The shipped operator is PPR over the **row-normalised** adjacency
(`propagation.py`, `build_row_normalized_adjacency`, used in the `ppr`
branch). It does not read how strong an edge is, but what **share** it has
of its node's outgoing edges. Decay `w → w·(1 − λw)` is nearly uniform
across a node's edges — at λw between 0.015 and 0.045 — and therefore
almost invisible to PPR. Ten ticks of shipped decay change working-set
membership by 4% at the median (Jaccard 0.963), the ordering in 24 of 24,
and the gold hits not at all.

The gate creates a *difference* within a node — spared versus decaying
outgoing edges — of about 15% relative after ten ticks. That shifts ranks
(24/24 orderings changed, Jaccard median 1.000) and not a single gold hit
across the budget boundary.

This is not the gate's failure. It is proof that the question "does the
substrate learn from use" cannot be answered on this instrument, at this
horizon, with this operator — and that the three conditions are namable.

## What the review found before shipping

Two independent readers went over the diff, adversarially. One bug, two
risks, four documentation errors — all fixed before the merge:

- **Double sparing after a failed node fold.** The tick now pulls in the
  firings *before* writing the edges. If the node fold then failed, the
  passes went back into the buffer unmarked — and spared the same edges a
  second time for the next tick, for one use. One buffer fed two commits
  with no record of which one had consumed it. Reproduced, fixed (an
  `edges_applied` marker that `fired_pairs` skips), with a test.
- **O(k²) in the firing index.** The set of all ordered pairs per pass
  costs 2.45 million tuples and 204 MB for 1,000 passes of 50 nodes each,
  5.5 GB for 5,000 of 100 each — independent of mesh size. Now a node →
  passes index with an intersection test, linear in pass size.
- **Restored passes lost their timestamp** and got the restoration time
  instead — `last_fired_at` would have drifted forward incorrectly after
  every failed tick. Fixed, with a test.
- Smaller things: the restore now writes the firings back *before* the
  deltas (an append instead of a loop that can die partway through on a
  full disk); a delta with weight ≤ 0 no longer counts as a fire;
  `mesh tick` has `--no-decay-gate` and no longer says "every edge" in
  `--decay-lambda`; the module docstring of `retrieve` no longer claims
  "read-only by default"; "~100× smaller" was the rank-50 peak, not the
  peak (~0.2).

And one thing that had nothing to do with the gate and still held up the
PR: the first CI run failed with 40 tests, because CI resolves lancedb
0.38, whose SQL dialect reads `id = "…"` as an identifier. Ten filters in
the store were built that way. Reproduced locally, fixed with a
dialect-proof helper, pinned down (PHX-1105).

Confirmed: without a firing record, the gate is byte-identical to the old
tick; both orientations and all parallel typed relations of a pair are
spared together; the simulation mirrors the tick arithmetic; every flag of
both scripts is read.

## What now holds, and what does not

**Before**, the substrate could only forget. **Now it holds what it uses**
— measured, doctrine-faithful, with no side effect on the unused. This is
a real change to the substrate, and it has shipped.

**What still does not hold:** *"answers better on what it was used for."*
Recall is invariant over ten ticks under every policy. The verb *learns*
from the sentence "the mesh is alive" has thus moved from *no* to *holds*,
not to *yes*.

What would make the heartbeat visible, each with a reason:

1. **A longer horizon.** A 15% relative difference after 10 ticks becomes
   about 60% after 50. The simulation costs seconds; the live run one
   minute per tick.
2. **The weight-sum cap and the renormalisation**, so that growth does not
   saturate at `w_max` but shifts the *distribution* instead. As long as
   both are absent, any α > 0 at doctrine scale is a pathology generator
   (measured above).
3. **An instrument that measures ranks** — now in the heartbeat script —
   and a corpus on which `k_seeds=1` with name anchors does not already
   pin down gold membership on its own.

The third point is uncomfortable: on the founding mesh, retrieval at
`k_seeds=1` is so good that it does not need the dynamics. The heartbeat
has to be measured where retrieval has room to move.

Filed as PHX-1104 — and measured there on 2Wiki: [`heartbeat_2wiki.md`](heartbeat_2wiki.md).
