# The heartbeat on 2Wiki — the substrate learns from use, and displaces while doing so

> **Abstract.** *Setup.* The Kadmos graph of 2WikiMultihopQA from cache
> (6,119 passages, 32,499 entities, 283,144 edges); 300 questions split 150 used
> / 150 held out; hybrid seeding S = 2, the operating point of the project's one
> demonstrated result; 50 rounds, four policies, in memory on the substrate's
> real tick functions; no LLM, 61 minutes. *Result.* Uniform decay removes 72%
> of the weight and costs retrieval 0.4 points — the operator reads shares, not
> strengths. With the decay gate plus Hebbian credit, recall@5 on the used
> questions rises 0.777 → 0.790 (+1.3) in round one and holds for fifty rounds:
> the first time the verb *learns* moved on any measurement. And the held-out
> questions fall 0.813 → 0.798 (−1.5), monotonically, with or without credit:
> 5.4% of the edges stay at the cap while the rest decay to 0.28, so their share
> at every node they touch grows 3.5-fold and the random walk tilts towards what
> was used. **What is not used is not only forgotten, it is displaced.** That is
> the measured reason the doctrine provides for homeostatic renormalisation
> (PHX-1106). *Limits.* One to 1.5 points on 150 questions is one or two
> questions; `torch.topk` broke ties differently between policies in this run
> (stable sorting since); the propagation kernel is the benchmark's, not the
> substrate's PPR; credit only reaches existing edges. *Later.* PHX-1106 found
> the +1.3 to be one seed; the displacement held across datasets and seeds.

*2026-09-02. 2WikiMultihopQA, Kadmos graph from cache: 6,119 passages, 32,499
entities, 283,144 edges. 300 questions, 150 used / 150 held out,
hybrid seeding S=2 — the point at which the project has its one demonstrated
result. 50 rounds, four policies. No LLM, no money, 61 minutes.
`scripts/mesh_heartbeat_qa.py`, report
`data/run_reports/mesh_eval/heartbeat_2wikimultihopqa_01M1HKG6ZGGNPXXWEZ46VRZD4A.json`.
PHX-1104.*

## Why here

On the Founding Mesh the heartbeat could not become visible: recall 85%,
the gold hits pinned down by name anchors, ten rounds, no movement
([`hebbian_calibration.md`](hebbian_calibration.md)). PHX-1104 named three
conditions — a longer horizon, a corpus with room to move, renormalisation
as the counterforce. This run satisfies the first two and measures whether
the third is needed.

**In memory, on the substrate's real tick functions.** The graph is the
benchmark's, the propagation kernel the benchmark's (row-normalised
adjacency, 3 hops, damping 0.5 — the operating point at which +0.102 was
measured), the dynamics the substrate's: `merge_edge_deltas`,
`decay_edges_inplace(fired=…)`, `enforce_saturation`, `fired_pairs`. One
pass is the top-50 working set by activation, like a Constellation.
Nothing is written to a workspace.

**The weight regime is different from the Founding Mesh.** The cap
`w_max = 1,0` bites here from the start: containment edges arrive *at* 1.0,
relation counters above it. After the cap, **56.8% of all edges sit at
the cap**, the median is 1.0. On the raw graph SA@5 measures 0.777 / 0.818
(used / held out), after the cap 0.777 / 0.813 — the cap costs half a
point. kNN, the control that must never move: 0.650 / 0.717.

## The four policies

| Round | Policy | used@5 | Rank | held@5 | Rank | w median | at the cap | spared |
|---|---|---|---|---|---|---|---|---|
| 0 | — | 0.777 | 9.1 | 0.813 | 6.5 | 1.000 | 56.8% | — |
| 50 | **old decay** (everything decays) | 0.773 | 9.7 | 0.810 | 6.8 | 0.281 | 0% | 0 |
| 50 | **Gate** (only what did not fire decays) | 0.780 | 9.3 | **0.798** | 7.4 | 0.281 | 5.4% | 36,760 |
| 50 | **Gate + Hebb α=0.01**, normalised | **0.790** | **8.9** | 0.798 | 7.1 | 0.281 | 6.0% | 30,092 |
| 50 | **Gate + Hebb α=0.1**, normalised | 0.787 | 8.9 | 0.797 | 7.2 | 0.281 | 6.2% | 30,070 |

The complete trajectories at measurement points 1/2/3/5/10/20/30/50 are in
the report; the three movements that matter:

**Uniform decay is nearly invisible here too.** Under the old decay
the substrate loses 72% of its weight (median 1.000 → 0.281) and
retrieval loses 0.4 points. Second corpus, the same statement as on the
Founding Mesh: the operator reads shares, not strengths.

**With credit, the used rises — and holds.** Gate plus Hebb at
doctrine scale: used questions 0.777 → **0.790** (+1.3 points), rank 9.1 → 8.9.
The jump comes in round 1 (+1.0) and stays put over 50 rounds. That is the
first time the verb *learns* from "the mesh is alive" has moved on any
measurement at all. The size of α is nearly irrelevant here (0.790 versus
0.787): the credited edges sit at the cap, and more credit has nothing
to do there.

**And the held-out falls — under the gate, with or without credit.**
0.813 → **0.798** (−1.5 points), rank 6.5 → 7.4. Not as a jump but as a
drift: 0.813 · 0.813 · 0.813 · 0.810 · 0.813 · 0.812 · 0.805 · 0.798 across
the eight measurement points. The mechanism is visible in the *at the cap*
column: 5.4% of the edges — the ones around the used questions — stay at
1.0, while all the others fall to 0.28. Their *share* of every node they
touch thereby grows 3.5-fold, and the random walk tilts toward the used
regions. Questions whose paths run through mixed nodes lose share.

An observation I cannot explain and therefore only note: in round
1 the credit on the used questions **also lifts the held-out ones** —
0.813 → 0.828, rank 6.5 → 6.3. The gain decays away again by round 20. Most
plausibly: 2Wiki questions share entities, and strengthened bridges initially
help all questions through the same hubs, until the asymmetric displacement
outweighs that. That is a conjecture, not a measurement.

## What this means

The vision says *"fire together, wire together"* and *"edges that are not
fired weaken."* Both are now built, and on a corpus with room to move both do
what they are supposed to — used paths get better, unused ones fade. The
price stands right next to it, small and monotonic: **what is not used is
not only forgotten, it is displaced.** A substrate that answered a handful
of questions for a year would get worse on everything else, not just older.

This is not the gate's failure. It is the measured reason that the
doctrine in §6 provides for **global homeostatic renormalisation** — the
counterforce that keeps the total weight per node stable, so that "more
share for the used" does not mean "less for everything else." Until now
that was an argument. Now it is −1.5 points over 50 rounds on held-out
questions, and the next organ to be built (PHX-1106).

## Limits of this run

- **Effect sizes of 1–1.5 points on 150 questions** are one or two
  questions. The measurement is deterministic (no LLM), the drift is
  monotonic across eight points, the jump in round 1 reproduces in both
  growth runs — but they are two questions, and a second seed or a second
  dataset (HotpotQA, MuSiQue) would have to confirm them.
- **The working sets were not fully reproducible.** 56.8% of the
  weights at the cap produce exactly equal activations, and `torch.topk`
  breaks the tie between two policies from the same state differently
  (36,858 versus 30,214 spared edges in round 1). The top-5 ranking was
  unaffected by this, the edge of the working set was not. The script has
  sorted stably since this run; this run predates that.
- **Kernel and tick are two systems.** The propagation kernel is the
  benchmark's (damped diffusion), not the substrate's
  `Propagator.propagate(operator="ppr")` (restart PPR, 12 iterations). Both
  read the row-normalised adjacency; the statement about shares holds for
  both. The numbers are comparable with the seeding study, not with
  `mesh ask`.
- **Only Hebbian credit on existing edges.** The creation branch is
  unreachable in the substrate (PHX-1100); the same holds here. This run,
  too, did not produce a "denser mesh."
