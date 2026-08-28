# Founding Demo — operator script (PHX-1045 / F5)

Three beats, ~3 minutes, against the founding mesh (`data/mesh-founding`):
the Theogony (complete), Iliad Book V, and Ovid's Book-I cosmogony, read by
Kadmos v2 from Project Gutenberg primary sources. Every beat maps to a run
report — nothing is staged. Companion plan with exit criteria:
[`docs/plans/FOUNDING_DEMO_PLAN.md`](../docs/plans/FOUNDING_DEMO_PLAN.md).

## The one image

![Spreading Activation on the founding mesh](assets/founding_activation.gif)

Twelve frames, one per real SpMV iteration of Spreading Activation on the
founding mesh — rendered by [`scripts/render_founding_demo_gif.py`](../scripts/render_founding_demo_gif.py)
from `propagate_frames()`, not staged. Re-render after any full read.

## Setup

```bash
export THEOGONY_COCKPIT__MESH_ROOT=data/mesh-founding   # if your cockpit config needs it
theogony cockpit serve                                   # open the Explorer, backend: Mesh
```

The first mesh query pays the one-time activation-index build; every
subsequent query is sub-second (PHX-1041 mitigation).

## Beat 1 — Activation, not retrieval (~60s)

Ask in the Explorer (backend **Mesh**):

> How was Aphrodite born?

Watch the constellation light up **iteration by iteration** — each animation
frame is one real SpMV step of Spreading Activation (`activation_frames`
SSE events; the final frame equals the authoritative result). Point out:
real names and Kadmos descriptions on every node, source anchors from books
that never cite each other, and the relation descriptor on hover.

Honest note for the audience: the replay uses the retrieval's seed set with
uniform weights — hop order and spread are real; ranking comes from the
actual retrieval result.

**What the default actually returns.** This section used to claim that seed count
dominated Beat 1 — that at eight seeds the generic Theogony-poem node took 0.596
activation, "3× the runner-up", and pushed *Iliad* noise above the answer, so the
demo should be run with `--seeds 3`. None of it reproduces: the poem node sits
around rank 13 at a twentieth of that activation, and `--seeds 3` and `--seeds 2`
return node-for-node identical constellations. The claim predates the re-read that
kept entity names (PHX-1065, 6,816 → 5,002 nodes).

So run Beat 1 at the defaults, and point at the *property* rather than a rank
table. Exact ranks move a place or two whenever the Lance vector index is rebuilt
(PHX-1085), and a table of them is a claim that will rot again — which is what
happened to the last one. What holds:

- **The top three are the answer, and two of them were never named in the
  question**: Aphrodite, then *Cytherea* — the epithet, glossed "born from sea
  foam" — then *Cyprus*, the island she came ashore on. That is the substrate
  reaching an answer through relations rather than through resemblance to the
  words of the question.
- **The generic work-node does not win.** "Theogony — A poem by Hesiod" sits
  around rank 13. Hub suppression is doing its job (PHX-1042).
- **Provenance rides outside the answer budget**, at ranks 51–53, so the gap
  report can say where the answer came from without spending answer slots on it.
  The anchors read `text: Hesiod, the Homeric Hymns and Homerica (batch 1)
  (https://www.gutenberg.org/ebooks/348)` — repaired in PHX-1084, where they used
  to name the temp directory the corpus was read from.
- **The full birth narrative is reachable but not at the top**: the passage
  describing the foam and the severed members sits around rank 20. Say so. The
  honest state is the demo.

```bash
theogony mesh ask "How was Aphrodite born?" --root data/mesh-founding
```

## Beat 2 — Contradiction is first-class (~60s)

> Who are the parents of Aphrodite?

Hesiod's answer (born of the sea-foam of Uranus' severed members, near
Cyprus) and Homer's answer (daughter of Zeus and Dione, Iliad V) both live
in the mesh, each anchored to its source. Edges whose descriptor contains
*contradict* render red and dashed. If Oneiros has not yet linked the two
subgraphs with an explicit `contradicts` edge, show both source-anchored
subgraphs side by side and say so — the honest state is the demo.

## Beat 3 — The permanent dream (~60s)

```bash
theogony mesh status --root data/mesh-founding          # note edge count BEFORE
python scripts/mesh_oneiros_dream.py --root data/mesh-founding --rounds 3 --n-seeds 200
theogony mesh status --root data/mesh-founding          # edge count AFTER
```

Show one concrete new connection that stood in no single source text, plus
the dream run's report. Line for the audience: *"The chronicle grew wiser
without reading new text."*

## What this does NOT prove

- No emergent, non-obvious-but-correct inference (the MNLM bet, PHX-1035).
- No retrieval quality at 100k+ scale; no federation.
- No factual correctness of extracted claims beyond source anchoring.
