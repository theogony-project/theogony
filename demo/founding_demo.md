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

**Seed count matters more than anything else here — measured, not guessed.**
The Cockpit currently seeds 8 nodes, which on this mesh lets the generic
Theogony-poem node take 0.596 activation (3× the runner-up) and pushes *Iliad*
noise above the answer. Narrowing the seeds forces propagation to do the work:

| seeds | poem hub | what sits at ranks 2–4 |
|---:|---:|---|
| 8 (current default) | **0.596** | Iliad noise — "the god who cares for Aeneas" |
| 3 | 0.236 | Kypris epithet · **the white foam around the severed members** · the Hesiod source paragraph |
| 2 | 0.169 | **the Hesiod source paragraph at rank 2** — provenance surfaces on its own |

At 2–3 seeds the constellation shows the actual birth narrative and its source
anchor, which is what Beat 1 claims. This is the founding-mesh instance of the
benchmark's seeding-ceiling result ([`docs/etappes/qa_benchmark.md`](../docs/etappes/qa_benchmark.md)):
seeded as widely as the working set is deep, Spreading Activation can only
re-rank what the embedding already returned. Whether the product default should
change is PHX-1056; until then, run the CLI form with `--seeds 3` if you want the
strongest Beat 1:

```bash
theogony mesh ask "How was Aphrodite born?" --root data/mesh-founding --seeds 3 --top-k 8
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
