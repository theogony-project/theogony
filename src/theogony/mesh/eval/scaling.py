"""Edge-density scaling sweep — the phase-transition experiment.

`TARGET_ARCHITECTURE.md` / README hypothesis 2 claims that Spreading Activation
beats geometric (kNN) retrieval *"once edge density crosses a regime where typed
multi-hop structure becomes legible to activation propagation."*  This module
turns that claim into a controlled experiment.

The test set is held **fixed**; only the amount of *training* structure varies.
Train edges are drawn as **nested prefixes** of one shuffle, so each denser level
is a superset of the sparser ones — the curve reflects added structure, not a
re-roll.  Because the ``knn`` ranker ignores edges entirely, its curve is flat:
the clean reference line against which any structural pick-up is read.  If the
``sa_raw`` / ``sa_degnorm`` curves cross or pull away from ``knn`` as mean degree
grows, that crossover is the phase transition the architecture bets on.
"""

from __future__ import annotations

import random
import time

import torch
from pydantic import BaseModel, ConfigDict, Field

from theogony.mesh.eval.link_prediction import (
    RANKERS,
    EdgeRow,
    RankerMetrics,
    build_context,
    build_csr_over_nodes,
    evaluate,
    split_edge_rows,
)


class ScalingLevel(BaseModel):
    """Metrics for all rankers at one training-edge-density level."""

    model_config = ConfigDict(extra="forbid")

    density: float
    train_edges: int
    mean_out_degree: float
    rankers: list[RankerMetrics] = Field(default_factory=list)


class ScalingReport(BaseModel):
    """Structured result of one edge-density scaling sweep."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    workspace: str
    node_count: int
    total_edges: int
    test_triples: int
    test_fraction: float
    hops: int
    damping: float
    seed: int
    densities: list[float] = Field(default_factory=list)
    levels: list[ScalingLevel] = Field(default_factory=list)
    timing_s: float = 0.0
    notes: str | None = None


def density_sweep(
    node_ids: list[str],
    all_edge_rows: list[EdgeRow],
    sem_unit: torch.Tensor,
    *,
    densities: list[float],
    test_fraction: float = 0.15,
    hops: int = 3,
    damping: float = 0.5,
    seed: int = 0,
    rankers: tuple[str, ...] = RANKERS,
    max_test: int | None = None,
) -> tuple[list[ScalingLevel], int]:
    """Sweep training-edge density with a fixed test set.

    Returns ``(levels, test_triples)``.  The test set is split off once and held
    constant; ``known_tails_by_head`` (the filtered-protocol mask) is computed
    from *all* edges so it, too, is constant across levels.
    """
    id_to_index = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)

    train_pool, test_rows = split_edge_rows(all_edge_rows, test_fraction=test_fraction, seed=seed)

    known_tails_by_head: dict[int, set[int]] = {}
    for source_id, target_id, _w in all_edge_rows:
        si = id_to_index.get(source_id)
        ti = id_to_index.get(target_id)
        if si is not None and ti is not None:
            known_tails_by_head.setdefault(si, set()).add(ti)

    test_pairs: list[tuple[int, int]] = []
    for source_id, target_id, _w in test_rows:
        si = id_to_index.get(source_id)
        ti = id_to_index.get(target_id)
        if si is not None and ti is not None:
            test_pairs.append((si, ti))
    if max_test is not None and len(test_pairs) > max_test:
        test_pairs = random.Random(seed).sample(test_pairs, max_test)

    shuffled = list(train_pool)
    random.Random(seed + 1).shuffle(shuffled)

    levels: list[ScalingLevel] = []
    for density in densities:
        k = int(round(density * len(shuffled)))
        subset = shuffled[:k]
        train_csr = build_csr_over_nodes(node_ids, subset)
        ctx = build_context(train_csr, sem_unit)
        metrics = evaluate(
            ctx,
            test_pairs,
            known_tails_by_head,
            rankers=rankers,
            hops=hops,
            damping=damping,
            seed=seed,
        )
        levels.append(
            ScalingLevel(
                density=density,
                train_edges=len(subset),
                mean_out_degree=len(subset) / max(1, n),
                rankers=[metrics[r] for r in rankers],
            )
        )
    return levels, len(test_pairs)


def run_sweep(
    *,
    run_id: str,
    workspace: str,
    node_ids: list[str],
    all_edge_rows: list[EdgeRow],
    sem_unit: torch.Tensor,
    densities: list[float],
    test_fraction: float = 0.15,
    hops: int = 3,
    damping: float = 0.5,
    seed: int = 0,
    max_test: int | None = None,
) -> ScalingReport:
    """Run :func:`density_sweep` and package the result as a :class:`ScalingReport`."""
    started = time.perf_counter()
    levels, test_triples = density_sweep(
        node_ids,
        all_edge_rows,
        sem_unit,
        densities=densities,
        test_fraction=test_fraction,
        hops=hops,
        damping=damping,
        seed=seed,
        max_test=max_test,
    )
    return ScalingReport(
        run_id=run_id,
        workspace=workspace,
        node_count=len(node_ids),
        total_edges=len(all_edge_rows),
        test_triples=test_triples,
        test_fraction=test_fraction,
        hops=hops,
        damping=damping,
        seed=seed,
        densities=densities,
        levels=levels,
        timing_s=time.perf_counter() - started,
        notes="relation-agnostic SA; fixed test set; nested train subsets. "
        "knn is edge-independent (flat reference). Crossover = phase transition.",
    )
