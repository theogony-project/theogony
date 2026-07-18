"""PHX-1042 hub-bias levers: degree-aware damping + global hub mask.

Live 100k testing showed high-in-degree nodes absorbing PPR mass from every
seed set ("el panson" in the top-k of five unrelated queries). These tests pin
the two default-off levers on a synthetic in-hub:

- ``degree_beta`` (operator level): a hub fed by many activated nodes outranks
  the query-relevant chain under plain PPR and is demoted once incoming mass is
  divided by ``in_degree ** beta``,
- ``hub_mask_top_n`` (orchestrator level): the top-N in-degree nodes are zeroed
  before assembly, but a hub that *is* a seed is never masked.

Both levers default to off; ``degree_beta=0.0`` must be bit-identical to the
unchanged operator.
"""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.retrieval import retrieve
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.schemas import ConsolidatedNode, Edge
from theogony.mesh.storage.edges import build_csr_from_edges


def _edge(source_id: str, target_id: str) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=source_id, target_id=target_id, weight=1.0, born_at=now, last_fired_at=now
    )


def _hub_mesh() -> tuple[dict[str, str], object]:
    """Seed S fans out to five feeders that all point at hub H; S->A->B is the
    query-relevant chain. H accumulates mass from five paths, A/B from one."""
    names = ["S", "A", "B", "H", "F1", "F2", "F3", "F4", "F5"]
    ids = {name: str(ULID()) for name in names}
    edges = [_edge(ids["S"], ids["A"]), _edge(ids["A"], ids["B"])]
    for f in ["F1", "F2", "F3", "F4", "F5"]:
        edges.append(_edge(ids["S"], ids[f]))
        edges.append(_edge(ids[f], ids["H"]))
    return ids, build_csr_from_edges(edges)


def test_plain_ppr_lets_the_hub_outrank_the_relevant_neighbor() -> None:
    """Reproduces the PHX-1042 shape: without damping the in-hub beats node A,
    which sits one query-relevant hop from the seed."""
    ids, csr = _hub_mesh()
    prop = Propagator(csr)
    x = prop.propagate({csr.id_to_index[ids["S"]]: 1.0}, operator="ppr", ppr_iters=30)
    assert x[csr.id_to_index[ids["H"]]] > x[csr.id_to_index[ids["A"]]]


def test_degree_beta_demotes_the_hub() -> None:
    ids, csr = _hub_mesh()
    prop = Propagator(csr)
    seed = {csr.id_to_index[ids["S"]]: 1.0}
    plain = prop.propagate(seed, operator="ppr", ppr_iters=30)
    damped = prop.propagate(seed, operator="ppr", ppr_iters=30, degree_beta=1.0)
    hub = csr.id_to_index[ids["H"]]
    neighbor = csr.id_to_index[ids["A"]]
    # The hub loses mass, the ranking flips, and the relevant chain is untouched
    # in relative order (A still above B).
    assert damped[hub] < plain[hub]
    assert damped[hub] < damped[neighbor]
    assert damped[neighbor] > damped[csr.id_to_index[ids["B"]]]


def test_degree_beta_zero_is_the_unchanged_operator() -> None:
    ids, csr = _hub_mesh()
    prop = Propagator(csr)
    seed = {csr.id_to_index[ids["S"]]: 1.0}
    for operator in ("raw", "degnorm", "ppr"):
        default = prop.propagate(seed, operator=operator)
        explicit = prop.propagate(seed, operator=operator, degree_beta=0.0)
        assert torch.equal(default, explicit)


def _basis(i: int, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    v[i] = 1.0
    return v


def _consolidated(name: str, vec: list[float]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=str(ULID()),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=name,
        tags=[name.lower()],
    )


def _build_hub_runtime(rt) -> dict[str, str]:
    """Query target Q chained to C; hub H fed by five feeders and by Q."""
    nodes = {
        "Q": _consolidated("Query-Target", _basis(0)),
        "C": _consolidated("Chain", _basis(1)),
        "H": _consolidated("Hub", _basis(2)),
        "F1": _consolidated("Feeder-1", _basis(3)),
        "F2": _consolidated("Feeder-2", _basis(4)),
        "F3": _consolidated("Feeder-3", _basis(5)),
        "F4": _consolidated("Feeder-4", _basis(6)),
        "F5": _consolidated("Feeder-5", _basis(7)),
    }
    rt.nodes.append_consolidated_many(list(nodes.values()))
    ids = {name: str(node.id) for name, node in nodes.items()}
    edges = [_edge(ids["Q"], ids["C"]), _edge(ids["Q"], ids["H"])]
    for f in ["F1", "F2", "F3", "F4", "F5"]:
        edges.append(_edge(ids["Q"], ids[f]))
        edges.append(_edge(ids[f], ids["H"]))
    rt.edges.append_edges(edges)
    return ids


def test_hub_mask_removes_the_hub_from_the_constellation(mesh_runtime) -> None:
    ids = _build_hub_runtime(mesh_runtime)
    unmasked = retrieve(mesh_runtime, _basis(0), k_seeds=2, query="hub bias probe")
    masked = retrieve(mesh_runtime, _basis(0), k_seeds=2, hub_mask_top_n=1, query="hub bias probe")
    unmasked_ids = {node.node_id for node in unmasked.constellation.nodes}
    masked_ids = {node.node_id for node in masked.constellation.nodes}
    assert ids["H"] in unmasked_ids
    assert ids["H"] not in masked_ids
    assert ids["C"] in masked_ids


def test_hub_mask_never_masks_a_seed(mesh_runtime) -> None:
    ids = _build_hub_runtime(mesh_runtime)
    # Query with the hub's own vector: the hub becomes the seed and must survive
    # the mask — it was chosen by query relevance, not by degree.
    result = retrieve(mesh_runtime, _basis(2), k_seeds=1, hub_mask_top_n=1, query="hub as seed")
    assert ids["H"] in result.seed_node_ids
    assert ids["H"] in {node.node_id for node in result.constellation.nodes}
