"""Weight-class stratification — the S3 deliverable that was never built.

Lives here rather than at the `retrieval/stratification.py` the migration plan
names, for the same reason `relation_pids` and `typed_edges` do: the runtime
caches the class boundaries, `retrieval/__init__` imports `retrieve`, and
`retrieve` imports the runtime — so a module under `retrieval/` cannot be
imported by the runtime without closing that cycle.

`MESH_MIGRATION_PLAN.md` §"Step S3" lists this module and a test asserting
"seeds drawn from all four weight classes". Neither existed. What shipped instead
was a hub cap inside `diversified.select_seeds`, and it differed from the
doctrine in two ways that measurement makes concrete.

**The classes were local.** `weight_classes` took quantiles over whichever ≤64
candidates the ANN returned, so a node's class depended on who else happened to
be retrieved. Measured on the founding mesh: the pool's median p25 is 3.71
against a global 1.16, and its p95 is 47.14 against 17.13. The "hub" being capped
was a different set of nodes on every query, and never the doctrine's hub.

**There were no seats.** Only the hub class had a bound; the other three took
whatever the MMR order gave them. A query whose pool happened to be 80% medium
got 80% medium seeds, which is not stratification.

WHAT THE POPULATION HAD TO BE, and this is the part the doctrine does not say.
Quantiles over *every* node in the CSR put 1,560 nodes in the micro class, of
which only 354 could even be hydrated: **252 source anchors and 102 unconsolidated
fragments, and zero consolidated entities**. PHX-1042 removed source anchors from
the answer budget because they carry nothing to read, and seating them here would
have undone that. Classes are therefore computed over the *answerable* population
— consolidated, not a source anchor — which is 3,783 of 6,208 CSR nodes.

WHY A MINIMUM SEAT AND NOT AN EQUAL ONE. `MESH_RETRIEVAL` §B says "K seeds from
each class independently", and its stated purpose is that "rare-but-correct
knowledge must have a route to the answer … stratification guarantees that route
exists by construction". Equal seats and a guaranteed route are not the same
thing, and on this substrate they come apart. Measured over the 47 gold questions:

    class     nodes   gold answers   recall
    micro       951              2     100%
    medium    1,886             16      56%
    large       756             44      70%
    hub         190             49      88%

The micro class holds a quarter of the population and two of 111 answers, both of
which retrieval already finds. Equal seats would move a quarter of the budget to
it, out of the class that is actually starved — medium, at 56%. A guaranteed
*minimum* honours the doctrine's purpose without spending the budget on a route
nobody travels. The number is a lever, and the measurement above is what it
should be argued from.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch

# The doctrine's four classes, by percentile of node potential
# (MESH_RETRIEVAL §"Weight-class stratification").
CLASS_NAMES = ("micro", "medium", "large", "hub")
_QUANTILES = (0.25, 0.75, 0.95)


@dataclass(frozen=True)
class WeightClasses:
    """Global class boundaries for one substrate state.

    Computed over the answerable population and cached on the runtime by CSR
    generation, because a node's class is a property of the substrate rather than
    of one query's candidate pool.
    """

    p25: float
    p75: float
    p95: float
    population: int

    def of(self, potential: float) -> int:
        if potential <= self.p25:
            return 0
        if potential <= self.p75:
            return 1
        if potential <= self.p95:
            return 2
        return 3


def global_weight_classes(potentials: Sequence[float]) -> WeightClasses:
    """Class boundaries from the potentials of every answerable node."""
    if not potentials:
        return WeightClasses(p25=0.0, p75=0.0, p95=0.0, population=0)
    values = torch.tensor(list(potentials), dtype=torch.float32)
    p25, p75, p95 = torch.quantile(values, torch.tensor(_QUANTILES)).tolist()
    return WeightClasses(p25=p25, p75=p75, p95=p95, population=len(potentials))


def class_seats(
    classes: Sequence[int],
    order: Sequence[int],
    *,
    k: int,
    min_per_class: int = 1,
    hub_class: int = 3,
    max_hub_fraction: float = 0.5,
) -> list[int]:
    """Choose ``k`` candidate positions, guaranteeing each present class a seat.

    ``order`` is the MMR order — relevance and diversity are already decided by
    the caller. This only ensures the order does not shut a whole class out.

    Three passes, and the first one exists because a test caught its absence.

    **Relevance gets the first seat, always.** Guaranteeing the lowest class a
    seat before anything else means that at ``k=1`` the most query-relevant
    candidate can be shut out entirely — a query issued with a hub's own vector
    stopped seeding on that hub (PHX-1042's `test_hub_mask_never_masks_a_seed`).
    Stratification is meant to guarantee a route for rare knowledge, not to
    displace the answer when there is only one seat to give.

    Then up to ``min_per_class`` from each class the pool actually contains, in
    MMR order within the class; a class with no candidates gets none, because a
    seat cannot be filled from an empty class and leaving it empty is more honest
    than borrowing. Then the remainder by MMR order, so relevance decides
    everything the guarantee does not.

    **The hub class is excluded from the guarantee**, and that is not an
    oversight. The doctrine *caps* hubs — they are the class that wins retrieval
    by default and starves the rest — so giving them a floor as well is
    incoherent. It is also observable: guaranteeing the hub a seat made
    ``hub_mask_top_n`` inert, because the mask never masks a seed, so the lever
    that exists to demote a degree-attracted hub could no longer reach the one
    hub stratification had just seeded. A hub still takes seats whenever
    relevance earns them, up to ``max_hub_fraction``.

    The hub cap survives from the previous implementation and is measured: source
    anchors and high-degree hubs flood propagation, and PHX-1042 found them taking
    13.8% of the answer budget while carrying nothing to read.
    """
    if k <= 0 or not order:
        return []

    by_class: dict[int, list[int]] = {}
    for pos in order:
        by_class.setdefault(classes[pos], []).append(pos)

    hub_budget = max(1, int(round(max_hub_fraction * k)))
    chosen: list[int] = []
    seen: set[int] = set()
    hubs = 0

    def take(pos: int) -> bool:
        nonlocal hubs
        if pos in seen or len(chosen) >= k:
            return False
        if classes[pos] == hub_class and hubs >= hub_budget:
            return False
        if classes[pos] == hub_class:
            hubs += 1
        seen.add(pos)
        chosen.append(pos)
        return True

    take(order[0])
    for cls in sorted(by_class):
        if cls == hub_class:
            continue
        for pos in by_class[cls][:min_per_class]:
            take(pos)
    for pos in order:
        if len(chosen) >= k:
            break
        take(pos)
    # The hub cap can leave us short of k; relevance fills the gap rather than
    # returning fewer seeds than asked for.
    if len(chosen) < k:
        for pos in order:
            if len(chosen) >= k:
                break
            if pos not in seen:
                seen.add(pos)
                chosen.append(pos)
    return chosen
