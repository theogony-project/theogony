"""Source anchors are provenance, not answers, and must not eat the answer budget.

Every entity in a paragraph is wired to that paragraph's anchor, which makes
anchors the highest-degree nodes in the mesh and makes propagation flood them.
Measured on the founding mesh across eight questions, they took 33 of 240 top-30
slots — 13.8% of the answer spent on rows that read "text paragraph: Theogony
batch_01". They still ride along, because the constellation reports a gap when no
provenance is reached; they just no longer count against `top_k` (PHX-1042).
"""

from __future__ import annotations

from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.retrieval.constellation import assemble_constellation
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge


def _mesh(runtime: MeshRuntime, *, entities: int, anchors: int) -> list[str]:
    now = datetime.now(UTC)
    nodes = []
    for i in range(entities + anchors):
        is_anchor = i >= entities
        nodes.append(
            ConsolidatedNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=[0.1] * runtime.semantic_dim,
                frame_vector=[0.0] * runtime.frame_dim,
                description=("text paragraph: source" if is_anchor else f"Entity {i}"),
                description_vector=[0.1] * runtime.semantic_dim,
                tags=["paragraph"] if is_anchor else ["entity"],
                is_source_anchor=is_anchor,
            )
        )
    runtime.nodes.append_consolidated_many(nodes)
    ids = [str(n.id) for n in nodes]

    def _edge(src: str, tgt: str, kind: str, descriptor: str) -> Edge:
        return Edge(
            source_id=src,
            target_id=tgt,
            weight=1.0,
            born_at=now,
            last_fired_at=now,
            relation_kind=kind,
            relation_descriptor=descriptor,
            creation_context="test",
        )

    # A connected entity chain, so the graph exists even with no anchors, plus
    # every entity wired to every anchor — the shape that makes anchors hubs.
    edges = [_edge(ids[i], ids[i + 1], "semantic", "next") for i in range(entities - 1)]
    edges += [
        _edge(ids[e], ids[entities + a], "attribution", "appears_in_source")
        for e in range(entities)
        for a in range(anchors)
    ]
    runtime.edges.append_edges(edges)
    runtime.invalidate_csr_cache()
    return ids


def test_anchors_do_not_consume_answer_slots(mesh_runtime: MeshRuntime) -> None:
    ids = _mesh(mesh_runtime, entities=40, anchors=8)
    csr = mesh_runtime.rebuild_csr()
    # Anchors carry the most activation, exactly as propagation leaves them.
    activation = torch.tensor(
        [
            2.0 if mesh_runtime.nodes.get_consolidated(nid).is_source_anchor else 1.0
            for nid in csr.node_ids
        ]
    )

    result = assemble_constellation(mesh_runtime, activation, csr, top_k=10)

    content = [n for n in result.nodes if not n.is_source_anchor]
    assert len(content) == 10, "the answer budget must be spent on content"
    assert all(n.description and "paragraph" not in n.description for n in content)
    assert ids  # the fixture built what we think it built


def test_provenance_still_reaches_the_constellation(mesh_runtime: MeshRuntime) -> None:
    """Anchors are kept, not culled — the assembly reports a gap without them.

    Activation is shaped the way propagation actually leaves it, with anchors
    ahead of entities. That is the case this change is about: before, that
    ordering pushed content out of the answer; now it must not, and the anchors
    must still be there for provenance.
    """
    _mesh(mesh_runtime, entities=40, anchors=8)
    csr = mesh_runtime.rebuild_csr()
    activation = torch.tensor(
        [
            2.0 if mesh_runtime.nodes.get_consolidated(nid).is_source_anchor else 1.0
            for nid in csr.node_ids
        ]
    )

    result = assemble_constellation(mesh_runtime, activation, csr, top_k=10)

    assert result.source_anchor_ids, "provenance was dropped along with the crowding"
    assert not any("provenance" in g for g in result.gaps)


def test_a_mesh_without_anchors_is_unaffected(mesh_runtime: MeshRuntime) -> None:
    _mesh(mesh_runtime, entities=20, anchors=0)
    csr = mesh_runtime.rebuild_csr()
    activation = torch.ones(len(csr.node_ids))

    result = assemble_constellation(mesh_runtime, activation, csr, top_k=10)

    assert len(result.nodes) == 10
    assert any("provenance" in g for g in result.gaps)
