"""End-to-end retrieval (S3): consolidated mesh -> Constellation via the orchestrator.

Builds a tiny, fully-controlled "solar system" mesh on the fixture runtime, then drives
the real :func:`retrieve` path (ANN seeds -> diversified injection -> PPR -> assembly)
and asserts the Constellation shape, including relation-descriptor enrichment, source
anchors, and the honest-gap signals.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.retrieval import retrieve
from theogony.mesh.retrieval.constellation import assemble_constellation
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.schemas import ConsolidatedNode, Edge
from theogony.reporting.models import MeshQueryRunReport


def _node(name: str, vec: list[float], *, anchor: bool = False) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=str(ULID()),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        is_source_anchor=anchor,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=name,
        tags=[name.lower()],
    )


def _build_solar_system(rt) -> dict[str, str]:
    def basis(i: int) -> list[float]:
        v = [0.0] * 8
        v[i] = 1.0
        return v

    nodes = {
        "Sun": _node("Sun", basis(0), anchor=True),
        "Earth": _node("Earth", basis(1)),
        "Moon": _node("Moon", basis(2)),
        "Mars": _node("Mars", basis(3)),
        "Jupiter": _node("Jupiter", basis(4)),
        "Galaxy": _node("Galaxy", basis(5)),  # isolated (no edges)
    }
    rt.nodes.append_consolidated_many(list(nodes.values()))
    ids = {name: str(node.id) for name, node in nodes.items()}

    now = datetime.now(UTC)

    def edge(s: str, t: str, rel: str) -> Edge:
        return Edge(
            source_id=ids[s],
            target_id=ids[t],
            weight=1.0,
            born_at=now,
            last_fired_at=now,
            relation_descriptor=rel,
        )

    rt.edges.append_edges(
        [
            edge("Sun", "Earth", "orbited by"),
            edge("Sun", "Mars", "orbited by"),
            edge("Sun", "Jupiter", "orbited by"),
            edge("Earth", "Moon", "has natural satellite"),
        ]
    )
    return ids


def test_retrieve_returns_connected_anchored_constellation(mesh_runtime) -> None:
    ids = _build_solar_system(mesh_runtime)
    query_vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # ~ Sun

    result = retrieve(
        mesh_runtime,
        query_vec,
        operator="ppr",
        top_k=10,
        k_seeds=3,
        ann_limit=16,
        query="What orbits the Sun?",
    )
    c = result.constellation

    names = {node.name for node in c.nodes}
    assert "Sun" in names
    # Sun's neighbours light up through Spreading Activation.
    assert {"Earth", "Mars", "Jupiter"} & names

    # Sun is the dominant diversified seed.
    assert ids["Sun"] in result.seed_node_ids

    # Edges among the working set are present and relation-descriptor-enriched.
    assert c.edges
    assert any(edge.relation_descriptor == "orbited by" for edge in c.edges)

    # Sun is a source anchor -> provenance reached, so no "missing anchor" gap.
    assert ids["Sun"] in c.source_anchor_ids
    assert all("no source-anchored provenance" not in gap for gap in c.gaps)

    # The operational metadata serialises into a valid mesh query report.
    report = MeshQueryRunReport(
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_s=0.01,
        status="completed",
        verdict="good",
        query="What orbits the Sun?",
        query_length_chars=len("What orbits the Sun?"),
        operator=result.operator,
        ann_hit_count=result.ann_hit_count,
        seed_count=len(result.seed_node_ids),
        seed_node_ids=result.seed_node_ids,
        constellation_node_count=len(c.nodes),
        constellation_edge_count=len(c.edges),
        source_anchor_count=len(c.source_anchor_ids),
        gaps_identified=len(c.gaps),
        cited_node_ids=[node.node_id for node in c.nodes],
    )
    assert report.report_type == "mesh_query"
    assert report.constellation_node_count >= 1


def test_assemble_constellation_empty_mesh(mesh_runtime) -> None:
    import torch

    from theogony.mesh.storage.edges import build_csr_from_edges

    csr = build_csr_from_edges([])
    prop = Propagator(csr)
    activation = prop.propagate({}, operator="ppr")
    c = assemble_constellation(mesh_runtime, activation, csr, top_k=5)
    assert c.nodes == []
    assert c.gaps
    assert torch.equal(activation, torch.zeros(0))


def test_retrieve_vector_only_when_no_edges(mesh_runtime) -> None:
    """Nodes but no edges -> vector-only fallback (no Spreading Activation)."""

    def basis(i: int) -> list[float]:
        v = [0.0] * 8
        v[i] = 1.0
        return v

    mesh_runtime.nodes.append_consolidated_many([_node("Alpha", basis(0)), _node("Beta", basis(1))])
    result = retrieve(mesh_runtime, basis(0), query="alpha?")
    c = result.constellation
    assert any("vector-only" in gap for gap in c.gaps)
    assert result.seed_node_ids == []
    assert {node.name for node in c.nodes} <= {"Alpha", "Beta"}
