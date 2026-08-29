"""One row per node pair, ordered by what the query activated.

Two nodes may be joined by several distinct relations — `Theogony -> Homer`
carries nine on the founding mesh — and the CSR holds a position for each. The
descriptor index is keyed by pair, so emitting a row per position printed the
pair's single winning descriptor once per position. Measured over the 47 gold
questions at a 200-edge budget: **4,105 of 9,400 slots (44%) went to repetitions
of the same pair**, and 59% on the worst single question (PHX-1088).

Ordering was worse than wasteful. Edges were sorted by CSR weight, which sums a
pair's parallel edges, so pairs ranked by *how many ways* they were connected
rather than by their bearing on the question. `Theogony -> Homer` summed to 6.382
across nine relations and outranked `Theia -> Helius` at 0.859 — on the question
"What children did Theia bear to Hyperion?", whose answer is exactly that edge.
"""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.retrieval.constellation import assemble_constellation
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge


def _node(runtime: MeshRuntime, name: str) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * runtime.semantic_dim,
        frame_vector=[0.0] * runtime.frame_dim,
        description=name,
        tags=[name.lower()],
    )


def _edge(source: str, target: str, descriptor: str, weight: float) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=source,
        target_id=target,
        weight=weight,
        relation_descriptor=descriptor,
        born_at=now,
        last_fired_at=now,
    )


def test_a_pair_joined_nine_ways_takes_one_row_not_nine(mesh_runtime: MeshRuntime) -> None:
    """The defect, in its measured shape."""
    chatty_a, chatty_b = _node(mesh_runtime, "Theogony"), _node(mesh_runtime, "Homer")
    mesh_runtime.nodes.append_consolidated_many([chatty_a, chatty_b])
    mesh_runtime.edges.append_edges(
        [
            _edge(str(chatty_a.id), str(chatty_b.id), d, 0.7)
            for d in ("was jealous of", "competed with", "addresses", "conquered", "later than")
        ]
    )
    mesh_runtime.invalidate_csr_cache()
    csr = mesh_runtime.rebuild_csr()

    activation = torch.zeros(len(csr.node_ids))
    for node in (chatty_a, chatty_b):
        activation[csr.id_to_index[str(node.id)]] = 1.0

    constellation = assemble_constellation(mesh_runtime, activation, csr, top_k=10)
    pairs = [(e.source_id, e.target_id) for e in constellation.edges]
    assert len(pairs) == len(set(pairs)), f"a pair appears more than once: {pairs}"
    assert len(constellation.edges) == 1, "five relations between one pair is one row"


def test_both_directions_of_one_join_collapse_to_the_claiming_one(
    mesh_runtime: MeshRuntime,
) -> None:
    """`A --bare--> B` and `B --co_mentions_in_paragraph--> A` are one join.

    They sat next to each other at the top of a Constellation, the second saying
    nothing the first had not.
    """
    theia, helius = _node(mesh_runtime, "Theia"), _node(mesh_runtime, "Helius")
    mesh_runtime.nodes.append_consolidated_many([theia, helius])
    mesh_runtime.edges.append_edges(
        [
            _edge(str(theia.id), str(helius.id), "bare", 0.5),
            _edge(str(helius.id), str(theia.id), "co_mentions_in_paragraph", 0.9),
        ]
    )
    mesh_runtime.invalidate_csr_cache()
    csr = mesh_runtime.rebuild_csr()
    activation = torch.zeros(len(csr.node_ids))
    for node in (theia, helius):
        activation[csr.id_to_index[str(node.id)]] = 1.0

    edges = assemble_constellation(mesh_runtime, activation, csr, top_k=10).edges
    assert len(edges) == 1
    assert edges[0].relation_descriptor == "bare", (
        "the direction carrying the judged relation must win over the bookkeeping one, "
        "even though the bookkeeping edge is heavier"
    )


def test_edges_are_ordered_by_what_the_query_activated(mesh_runtime: MeshRuntime) -> None:
    """Not by weight, which ranks pairs by how many ways they are connected.

    The heavy pair here stands for `Theogony -> Homer`: many parallel relations
    summing high, and nothing to do with the question.
    """
    subject, answer = _node(mesh_runtime, "Theia"), _node(mesh_runtime, "Helius")
    noisy_a, noisy_b = _node(mesh_runtime, "Theogony"), _node(mesh_runtime, "Homer")
    mesh_runtime.nodes.append_consolidated_many([subject, answer, noisy_a, noisy_b])
    mesh_runtime.edges.append_edges(
        [
            _edge(str(subject.id), str(answer.id), "bare", 0.4),
            _edge(str(noisy_a.id), str(noisy_b.id), "was jealous of", 0.95),
        ]
    )
    mesh_runtime.invalidate_csr_cache()
    csr = mesh_runtime.rebuild_csr()

    activation = torch.zeros(len(csr.node_ids))
    activation[csr.id_to_index[str(subject.id)]] = 1.0
    activation[csr.id_to_index[str(answer.id)]] = 0.9
    activation[csr.id_to_index[str(noisy_a.id)]] = 0.2
    activation[csr.id_to_index[str(noisy_b.id)]] = 0.2

    edges = assemble_constellation(mesh_runtime, activation, csr, top_k=10).edges
    assert edges[0].relation_descriptor == "bare", (
        "the edge the query lit up must come first, even though the other weighs more"
    )


def test_display_selection_does_not_touch_the_node_set(mesh_runtime: MeshRuntime) -> None:
    """Edges are read for display; changing their selection must not move recall.

    Verified on the founding mesh alongside this change: 77% recall and 36/47
    questions answered in full, before and after.
    """
    a, b = _node(mesh_runtime, "A"), _node(mesh_runtime, "B")
    mesh_runtime.nodes.append_consolidated_many([a, b])
    mesh_runtime.edges.append_edges(
        [_edge(str(a.id), str(b.id), d, 0.5) for d in ("bare", "co_mentions_in_paragraph")]
    )
    mesh_runtime.invalidate_csr_cache()
    csr = mesh_runtime.rebuild_csr()
    activation = torch.zeros(len(csr.node_ids))
    for node in (a, b):
        activation[csr.id_to_index[str(node.id)]] = 1.0

    constellation = assemble_constellation(mesh_runtime, activation, csr, top_k=10)
    assert {n.name for n in constellation.nodes} == {"A", "B"}


def test_edges_touching_a_seed_come_first(mesh_runtime: MeshRuntime) -> None:
    """A seed is where the query entered; an edge touching one is on a path from it.

    Everything else is scenery the propagation happened to light up. Measured on
    the 47 gold questions, answer recall through a language model, three runs per
    arm: every edge among the kept nodes scores 50/50/51 — **the worst arm, worse
    than showing no relations at all** — against 50/53/53 for the edges touching a
    seed and 57/52/52 for no relations (PHX-1096).

    This is a ranking and not a filter: the Constellation still carries the rest,
    because its contract is the activated subgraph rather than one reader's
    preferred slice. Cutting to the seed-touching ones is the consumer's job.
    """
    seed, near, far_a, far_b = (_node(mesh_runtime, n) for n in ("Seed", "Near", "FarA", "FarB"))
    mesh_runtime.nodes.append_consolidated_many([seed, near, far_a, far_b])
    mesh_runtime.edges.append_edges(
        [
            # The far pair is heavier and its endpoints are more activated, so
            # without the seed term it would outrank the edge the query reached.
            _edge(str(far_a.id), str(far_b.id), "co_mentions_in_paragraph", 0.99),
            _edge(str(seed.id), str(near.id), "father_of", 0.10),
        ]
    )
    mesh_runtime.invalidate_csr_cache()
    csr = mesh_runtime.rebuild_csr()

    activation = torch.zeros(len(csr.node_ids))
    activation[csr.id_to_index[str(seed.id)]] = 0.5
    activation[csr.id_to_index[str(near.id)]] = 0.5
    activation[csr.id_to_index[str(far_a.id)]] = 0.9
    activation[csr.id_to_index[str(far_b.id)]] = 0.9

    edges = assemble_constellation(
        mesh_runtime,
        activation,
        csr,
        top_k=10,
        seed_indices={csr.id_to_index[str(seed.id)]},
    ).edges
    assert edges[0].relation_descriptor == "father_of", (
        "the edge touching the seed must come first, even though the other pair is "
        "both heavier and more activated"
    )
    assert len(edges) == 2, "ranking, not filtering — the other edge is still carried"
