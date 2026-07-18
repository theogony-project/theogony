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
