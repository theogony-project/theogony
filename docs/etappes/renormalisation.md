# Renormalisation — the counterforce the gate needs (PHX-1106)

> **Abstract.** *Question.* Use makes the substrate displace what it
> does not use (PHX-1104). Does the doctrine's global homeostatic
> renormalisation (MESH_SUBSTRATE §6) stop that? *Method.* The heartbeat
> protocol in memory on the substrate's real tick functions: Kadmos graphs of
> 2WikiMultihopQA and HotpotQA, 300 questions split 150 used / 150 held out, 50
> rounds, recall@5, two datasets and two seeds, no LLM. *Result.* The decay gate
> displaces in every run (held-out −1.5 / −2.3 / −2.3). Global renormalisation
> *with the weight cap* removes it every time (+1.5 / −0.7 / +0.7; mean +0.5
> against −2.0) for about half a point on the used questions. What does not hold
> is the gain: the +1.3 of PHX-1104 was one seed (+0.3 on HotpotQA, −0.7 on seed
> 1), so the plan's condition is met by no policy, the baseline included. *§6 as
> written, without a cap,* is invisible for ten rounds — a row-normalised
> operator is scale-invariant, measured to the third decimal — and then an
> amplifier: credited edges grow without bound (strongest weight 41.9), scaling
> shrinks everything else, held-out falls −3.8 against −2.0. The counterforce is
> scaling *and* cap, not scaling. *Decision.* `mesh tick` renormalises globally
> by default at a set point of 0.9 of entry mass. The verb "learns" stays at
> "holds without displacing"; whether it ever gains depends on the edge-creating
> branch, which is unreachable (PHX-1100).

**Status:** 2026-09-12, measured. Branch `feat/phx-1106-renormalisation`.
**Prompted by:** [`heartbeat_2wiki.md`](heartbeat_2wiki.md) — under the gate the substrate learns from use (+1.3 on used questions) and displaces while doing so (−1.5 on held-out, monotonic over 50 rounds). MESH_SUBSTRATE §6 provides for global homeostatic renormalisation as the counterforce; the inventory found it not built.
**Tools:** `renormalise_edges_inplace` in `storage/edges.py`, the tick step in `run_minimal_tick(renormalise=…)`, `mesh tick --renormalise`, the policies `renorm_*` in `scripts/mesh_heartbeat_qa.py`.

## What §6 says, and what an operator sees of it

The doctrine: once per tick, every edge is scaled by the same factor until the
total weight per node is back at `R_ideal`. "The correction is
multiplicative across all edges — uniform across tiers, weights, ages — so
relative ordering is preserved."

What is preserved is more than the ordering: **every share.** The operator
that builds the Constellation reads the row-normalised adjacency — PPR in the
substrate, damped diffusion in the benchmark core — and that is invariant
against any global scaling. What moved the heartbeat was never the absolute
strength of an edge, but its share of the node: 5.4% of edges stay at the
ceiling under the gate, all others fall to 0.28, and the share of the spared
edges in each node grows by a factor of 3.5. A scaling that treats every edge
the same changes nothing about this ratio. §6, as written, is invisible to
the operator.

It only becomes visible through what comes after it in the tick: the cap.
Fired edges sit at `w_max = 1,0`; if the renormalisation lifts all edges,
they get clipped, while the unfired ones beneath them get lifted back up. The
share that the gate gave the used edges is taken back from them by the cap.
That is the counterforce — not the scaling, but scaling *and* cap. And it is
also the warning from the inventory: "a correct implementation must be
landed together with a rethink of w_max, or the first correction destroys
every weight distinction in the substrate" — an edge at 0.7 gets lifted by
the global factor every tick and loses only its own decay; it creeps toward
the cap.

## Three readings, built

| Mode | Rule | What the operator sees |
|---|---|---|
| `global` | one factor across all edges, set point = total weight per node at first activation (`homeostatic_ratio` in `mesh_state.json`) | only the cap: fired edges get clipped, unfired ones lifted |
| `out` | per source node: the sum of outgoing weights back to the value before the tick | per row the same as `global`, but complete rather than on average |
| `in` | per target node: the sum of incoming weights back to the value before the tick | synaptic scaling in the literal sense (Turrigiano & Nelson, the source §6 cites): a target that receives only fired edges gets scaled down and loses share in every row that points to it |
| `free` | `global`, but after the cap: weights may live above 1 | nothing — the control that tells whether the others do more than the cap |

All three sit at the spot that MESH_IMPLEMENTATION §"Oneiros — implementation
order" names: step 3 decay, step 4 renormalisation, steps 8–9 saturation. The
per-node modes hold the value *before credit is mixed in*, so that credit
shifts the distribution within the node and decay does not empty it — that is
the sentence from the ticket, taken literally. The tier-aware moderation from
§6 is built as an option and is off here, because `decay_tier` is 0 on every
edge (PHX-1095).

**The ticket's hypothesis:** used +1.3 stays, held-out no longer falls. And
the alternatives it names itself: if both fall, the set point is wrong; if
used falls, the renormalisation eats the credit.

## Measurement

The same heartbeat as PHX-1104: 2WikiMultihopQA, 300 questions, 150 used /
150 held out, hybrid seeding S=2, 3 hops, damping 0.5, `w_max` 1.0, λ 0.05,
50 rounds, credit α = 0.01 normalised. Five policies from the same state:
`grow01` (gate + credit, the baseline from PHX-1104) and the four readings on
top of it. Then the same on HotpotQA, then 2Wiki with a second seed — the
condition from the plan, before an effect of one or two questions counts as
an effect.

### 2Wiki, seed 0

Report `data/run_reports/mesh_eval/heartbeat_2wikimultihopqa_01M2A4JCFDXAR60DFJ97E7Q5Q8.json`,
62 minutes. kNN control 0.650 / 0.717, raw graph 0.777 / 0.818, after the cap
0.777 / 0.813 — the baseline `grow01` reproduces PHX-1104 to the third
decimal. Recall@5 at measurement points 0 / 1 / 2 / 3 / 5 / 10 / 20 / 30 / 50:

| Policy | used | held-out | Δ50 used | Δ50 held-out | w mean / median, round 50 | at ceiling |
|---|---|---|---|---|---|---|
| `grow01` (baseline) | .777 .787 .787 .787 .787 .787 .787 .790 .790 | .813 .828 .828 .828 .827 .827 .807 .805 .798 | **+1.3** | **−1.5** | 0.336 / 0.281 | 6.0% |
| `renorm_global` | .777 .787 .790 .787 .787 .788 .788 .788 .788 | .813 .833 .833 .833 .828 .823 .825 .827 .828 | **+1.2** | **+1.5** | 0.950 / 0.950 | 12.1% |
| `renorm_out` | .777 .790 .790 .790 .790 .790 .790 .790 .783 | .813 .828 .828 .828 .827 .823 .818 .813 .813 | +0.7 | ±0.0 | 0.868 / 0.995 | 49.7% |
| `renorm_in` | .777 .783 .783 .783 .783 .783 .788 .788 .788 | .813 .828 .828 .828 .827 .825 .823 .815 .802 | +1.2 | −1.2 | 0.867 / 0.995 | 49.7% |
| `renorm_free` | .777 .787 .787 .790 .787 .788 .788 .788 .788 | .813 .828 .828 .830 .827 .828 .825 .823 .825 | +1.2 | +1.2 | 0.956 / 0.955 | 12.1% |

**The ticket's hypothesis holds, with the global reading.** Under
`renorm_global` the gain on the used questions stays (+1.2 against +1.3),
and the held-out ones no longer fall — after 50 rounds they sit 1.5
points *above* round 0. The rank of the held-out gold passages goes from
6.5 to 6.7 instead of to 7.1.

**What becomes visible here is the mechanism of displacement, in reverse.**
The credit lifts both halves in round 1 — used +1.0, held-out +1.5, the
same across all five policies, because 2Wiki questions share entities and
strengthened bridges help everyone at first (the observation from PHX-1104
that stayed unexplained there). In the baseline, the gate's drift eats this
gain back up from round 20 on: the unfired edges fall to 0.28, the spared
ones stay at 1.0, and the held-out questions lose three points against
round 1. Under global renormalisation, the unfired edges get lifted back
every tick and the fired ones get clipped at the cap: the mean stays at
0.95 instead of falling to 0.34, the drift does not take place, and the
gain from round 1 holds.

**The three other readings, one sentence each:** `out` holds every row so
strictly that the gain gets halved too (+0.7 / ±0) — the credit gets
scaled straight back out within the row. `in` (synaptic scaling) holds the
gain and only slows the drift (−1.2 instead of −1.5; the drop starts at
round 30 instead of 20). `free` is not a clean control: the cap kicks back
in at the start of the next round, and the numbers are those of the global
reading — the real control, with no cap at all, is below.

### HotpotQA, seed 0

Report `heartbeat_hotpotqa_01M2A84TFEQHWBGQ5ED3M7Q8DK.json`, 9,811 passages,
61,540 entities, 525,576 edges, 125 minutes. A corpus with less room to
move: kNN 0.837 / 0.827, spreading activation 0.850 / 0.840 — the graph's
lead here is one point, not ten.

| Policy | used | held-out | Δ50 used | Δ50 held-out | w mean, round 50 |
|---|---|---|---|---|---|
| `grow01` (baseline) | .850 .853 .857 .857 .857 .857 .857 .857 .853 | .840 .830 .827 .830 .830 .837 .830 .823 .817 | +0.3 | **−2.3** | 0.319 |
| `renorm_global` | .850 .850 .847 .843 .847 .843 .843 .843 .843 | .840 .827 .830 .830 .830 .830 .830 .830 .833 | −0.7 | −0.7 | 0.970 |
| `renorm_out` | .850 .843 .843 .843 .843 .843 .847 .847 .847 | .840 .833 .833 .833 .833 .837 .827 .823 .823 | −0.3 | −1.7 | 0.896 |
| `renorm_in` | .850 .847 .850 .850 .847 .843 .843 .843 .843 | .840 .823 .823 .823 .823 .823 .823 .820 .813 | −0.7 | −2.7 | 0.896 |
| `renorm_free` | .850 .853 .850 .847 .843 .847 .847 .843 .843 | .840 .830 .827 .827 .827 .833 .830 .830 .833 | −0.7 | −0.7 | 0.975 |

**Here there is nothing to preserve, and the renormalisation preserves it
anyway.** The credit in round 1 barely helps the used (+0.3, later +0.7)
and costs the held-out immediately (−1.0) — on HotpotQA the questions do
not share their bridges the way 2Wiki questions do. After that the gate's
drift keeps eating: −2.3 after 50 rounds, stronger than on 2Wiki. Under
`global` the held-out stands still from round 2 on (0.830 → 0.833), the
drift is gone; the price is the used, which falls from +0.7 to −0.7,
because levelling the weights on this graph costs something that the
shares do not replace. The plan's condition — used ≥ +1 *and* held-out ≥
0 — cannot be met by any policy on HotpotQA, because even the baseline has
no +1: this heartbeat has no room here, as on the Founding-Mesh. What can
be measured is the displacement, and that `global` takes from −2.3 to
−0.7.

### 2Wiki, seed 1

Report `heartbeat_2wikimultihopqa_01M2AF9A6G64V5XFBE90FPDTSZ.json`, 69 minutes.
The same graph, different halves: kNN 0.708 / 0.715, spreading activation
0.808 / 0.800.

| Policy | used | held-out | Δ50 used | Δ50 held-out |
|---|---|---|---|---|
| `grow01` (baseline) | .808 .807 .805 .803 .803 .803 .805 .805 .802 | .798 .805 .808 .807 .805 .797 .787 .782 .775 | −0.7 | **−2.3** |
| `renorm_global` | .808 .807 .803 .803 .797 .793 .793 .793 .793 | .798 .803 .800 .802 .807 .803 .807 .807 .805 | −1.5 | **+0.7** |
| `renorm_out` | .808 .807 .803 .803 .803 .803 .797 .797 .797 | .798 .800 .805 .805 .803 .793 .788 .780 .777 | −1.2 | −2.2 |
| `renorm_in` | .808 .802 .802 .802 .802 .795 .793 .793 .793 | .798 .803 .803 .807 .817 .807 .813 .808 .803 | −1.5 | +0.5 |
| `renorm_free` | .808 .807 .807 .803 .800 .793 .793 .793 .793 | .798 .805 .807 .807 .808 .795 .808 .815 .805 | −1.5 | +0.7 |

**The gain from seed 0 does not repeat, the displacement does.** With
these halves the credit brings the used nothing (−0.7 after 50 rounds),
and the held-out falls −2.3, as on HotpotQA. The +1.3 from PHX-1104 were
what the report there itself named as a possibility: one or two questions
of one seed. Under `global` the held-out again does not fall (+0.7), and
the used pays −1.5.

### All three runs side by side

Δ50 in points of Recall@5, used / held-out:

| Policy | 2Wiki seed 0 | HotpotQA seed 0 | 2Wiki seed 1 | mean used | mean held-out |
|---|---|---|---|---|---|
| `grow01` (baseline) | +1.3 / −1.5 | +0.3 / −2.3 | −0.7 / −2.3 | +0.3 | **−2.0** |
| `renorm_global` | +1.2 / +1.5 | −0.7 / −0.7 | −1.5 / +0.7 | −0.3 | **+0.5** |
| `renorm_out` | +0.7 / ±0 | −0.3 / −1.7 | −1.2 / −2.2 | −0.3 | −1.3 |
| `renorm_in` | +1.2 / −1.2 | −0.7 / −2.7 | −1.5 / +0.5 | −0.3 | −1.1 |
| `renorm_free` | +1.2 / +1.2 | −0.7 / −0.7 | −1.5 / +0.7 | −0.3 | +0.4 |

What holds across datasets and seeds: **the gate displaces** (−1.5, −2.3,
−2.3), and **global renormalisation takes the displacement away every
time** (+1.5, −0.7, +0.7 — on average 2.5 points better than the baseline
on the held-out). What does not hold: that the substrate robustly *gains*
from use — the baseline sits on the used at +1.3, +0.3, −0.7 —, and the
renormalisation costs on average 0.6 points there against the baseline,
about one point in two of three runs. The plan's condition (used ≥ +1 and
held-out ≥ 0, on both datasets and both seeds) is met by no policy,
because even its first half is met by the baseline in only one run. The
question that remains is the price on the used, and whether it hangs on
the levelling — for that, the set-point sweep below.

### The control without a cap: §6, as written

Report `heartbeat_2wikimultihopqa_01M2AK99P0RBXSZ5H1MCZQ676V.json`, 2Wiki
seed 0, 29 minutes. No cap on entry, on mixing in credit, on saturation:
the raw graph (weights up to 9.0), weights are allowed to grow, and global
scaling is the only homeostasis — the regime that §6 describes.

| Policy | used | held-out | Δ50 used | Δ50 held-out | w mean / median / max, round 50 |
|---|---|---|---|---|---|
| `grow01_uncapped` | .777 .793 .793 .793 .793 .793 .793 .793 .790 | .818 .835 .832 .832 .828 .827 .807 .805 .798 | +1.3 | −2.0 | 0.340 / 0.281 / 9.0 |
| `renorm_uncapped` | .777 .793 .793 .793 .793 .793 .793 .793 .792 | .818 .835 .832 .830 .827 .827 .802 .798 .780 | +1.5 | **−3.8** | 0.968 / 0.568 / 41.9 |

Up to round 10 the two are the same to the third decimal — the operator's
scale invariance, measured. After that they part ways, and in the wrong
direction: **§6, as written, amplifies the displacement.** The fired
edges grow with the credit without bound (the strongest weight after 50
rounds: 41.9), the global scaling shrinks everything else so that the mass
holds, and the share of the unused falls faster than under decay alone:
−3.8 against −2.0. That is exactly what the doctrine promises — "an edge
that fires more often than average grows; one that fires less shrinks" —
and exactly the opposite of what the ticket hoped from it. The small
deviation before round 10 comes from the quadratic decay, which is not
scale-invariant: lifted weights lose more in absolute terms.

The counterforce that works in the runs above is thus not §6. It is §6
*with the cap*: the scaling lifts the unused back up, the cap keeps the
used from running away. Without the cap, the renormalisation would be an
amplifier.

**The price, named:** under `global` with set point 1.0, after 50 rounds
all weights sit at 0.95 ± a little (median 0.950, mean 0.950). The
inventory's warning applies — the weight differences of the ingested
graph are largely levelled after 50 ticks. That retrieval on 2Wiki does
not suffer under this says something about this graph: its shares carry
more than its strengths. On HotpotQA it costs 0.7 on the used.

### The set point: `R_ideal` is a tuning parameter

§6 calls `R_ideal` a tuning parameter. The tick anchors it at first
activation to the mass the mesh then carries; the question is whether it
should sit *below* that, so the lifted edges do not land at the cap.
Reports `heartbeat_2wikimultihopqa_01M2AN1Q0G15B0VFEZHNKRTDCP.json` and
`heartbeat_hotpotqa_01M2AQXJMQNEHDSFDC1TJSKGK4.json`, seed 0, set point as
a share of entry mass:

| Set point | 2Wiki Δ50 used / held-out | 2Wiki w median, round 50 | HotpotQA Δ50 used / held-out | HotpotQA w median |
|---|---|---|---|---|
| 1.0 | +1.2 / +1.5 | 0.950 | −0.7 / −0.7 | 0.972 |
| **0.9** | **+1.2 / +1.2** | **0.851** | **−0.3 / −0.7** | **0.873** |
| 0.8 | +1.2 / +1.2 | 0.745 | −0.3 / −1.0 | 0.769 |
| 0.7 | +1.5 / −0.2 | 0.640 | −0.3 / −1.0 | 0.665 |

At 0.9 the counterforce does the same as at 1.0, the median stays at 0.85
instead of 0.95, and on HotpotQA the price on the used is halved. At 0.7
the gain on the held-out is gone: the lifted edges stay so far below the
cap that the fired ones run away from them again. **0.9 is the operating
point**, and `DEFAULT_RENORM_SCALE` carries it.

## What ships, and why

`mesh tick` now runs with `--renormalise global --renorm-scale 0.9`; the
set point gets anchored in `mesh_state.json` on the first tick
(`homeostatic_ratio`) and held afterward, `--renormalise off` switches it
off. `run_minimal_tick` itself stays at `renormalise=None`: the function
is the primitive from which harnesses and tests build their compositions;
the command is the measured composition.

The justification in three numbers: across two datasets and two seeds,
the gate displaces the unused by −1.5, −2.3, −2.3; global renormalisation
with the cap undoes that (+1.5, −0.7, +0.7) and costs, on average, half a
point on the used in exchange, whose gain was there in only one of the
three runs anyway. A substrate that answers a handful of questions for a
year does not thereby get worse at everything else. That was the sentence
PHX-1104 ended with, and it is now a setting.

What the doctrine has to learn from this is in PHX-1108: §6, as written —
uniform, without a cap, "relative ordering is preserved" — is invisible
to an operator that reads shares, and with growing weights is an
amplifier of displacement (−3.8). The counterforce is the cap, which the
doctrine provides for elsewhere (§3, as saturation per node) and which is
built here as `w_max` per edge. The tier ladder (PHX-1100, pattern 3)
stays untouched: the weights continue to live below 1, and `decay_tier`
is 0 on every edge.

## Limits

- Effect sizes of one to two points on 150 questions; deterministic, but
  one to three questions. Three runs, two datasets, two seeds — the sign
  change on the held-out holds in all three, the size varies.
- The heartbeat core is the benchmark's damped diffusion, not the
  substrate's PPR; both read shares, the claim holds for both, the
  numbers are not comparable with `mesh ask`.
- Only credit on existing edges; the edge-creating branch stays
  unreachable (PHX-1100).
- The Founding-Mesh (median 0.31, wide spread, retrieval pinned to name
  anchors) is a different weight regime than the benchmark graphs with
  57% of edges at the ceiling; the measurement there is below.

## On the Founding-Mesh, with the real tick

`scripts/mesh_heartbeat.py --policies grow,renorm --rounds 10` on copies
of `data/mesh-founding`, 24 used / 23 held-out gold questions,
`k_seeds = 1`, credit α = 0.1 normalised, the substrate's tick
(`run_minimal_tick`, set point 0.9 anchored on the first tick):

| Round | baseline used / held-out | w median | renorm used / held-out | w median | w max |
|---|---|---|---|---|---|
| 0 | 87.9% / 86.7% | 0.311 | 87.9% / 86.7% | 0.311 | 1.000 |
| 1 | 86.4% / 84.4% | 0.306 | 86.4% / 84.4% | 0.281 | 0.917 |
| 5 | 87.9% / 84.4% | 0.293 | 87.9% / 84.4% | 0.286 | 1.000 |
| 10 | 87.9% / 84.4% | 0.276 | 87.9% / 84.4% | 0.293 | 1.000 |

At every measurement point, the same numbers: on a mesh whose weights
live below the cap, the renormalisation is, for retrieval, what the
theory says — invisible. What it does is hold the mass: under the
baseline the median falls in ten ticks from 0.311 to 0.276 (the
"substrate that can only forget" from PHX-1100) and under the
renormalisation stands at 0.293. The price on the used that the
benchmark graphs show does not occur here, because the cap does not clip
anything; nor does the gain on the held-out, for the same reason. As the
default for `mesh tick`, it is thus measured harmless on the mesh that
the demo shows, and measured necessary on a mesh that lives at the cap.
