"""Cockpit Mesh Explorer (S4 preview): service + routes over a tiny MESH workspace.

Builds a controlled 8-dim "solar system" mesh on disk, points a MeshExplorerService at it
with an injected dim-matched embedder, and asserts (a) the service maps a mesh Constellation
onto the Explorer JSON shape, (b) the CSR is cached after the first ask, and (c) the
``/cockpit/api/mesh/*`` routes behave (200 when configured, 404 when not).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from ulid import ULID

from theogony.cockpit.mesh_explorer import MeshExplorerService
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge


class _FakeEmbedder:
    """Deterministic dim-matched embedder: every query maps to a fixed vector."""

    model_id = "fake-mesh-embedder@v1"

    def __init__(self, vector: list[float]) -> None:
        self.dim = len(vector)
        self._vector = vector

    async def embed_many(self, texts: list[str], *, batch_size: int = 8) -> list[list[float]]:
        return [list(self._vector) for _ in texts]


def _basis(i: int) -> list[float]:
    v = [0.0] * 8
    v[i] = 1.0
    return v


def _node(name: str, vec: list[float], *, anchor: bool = False) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=str(ULID()),
        born_at=now,
        last_fired_at=now,
        is_source_anchor=anchor,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=name,
        tags=[name.lower()],
    )


def _build_solar_system(root: Path) -> dict[str, str]:
    rt = MeshRuntime(root, semantic_dim=8, frame_dim=4)
    nodes = {
        "Sun": _node("Sun", _basis(0), anchor=True),
        "Earth": _node("Earth", _basis(1)),
        "Mars": _node("Mars", _basis(2)),
        "Moon": _node("Moon", _basis(3)),
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
            edge("Earth", "Moon", "has natural satellite"),
        ]
    )
    return ids


def test_service_ask_maps_constellation_and_caches_index(tmp_path: Path) -> None:
    root = tmp_path / "meshws"
    _build_solar_system(root)
    service = MeshExplorerService(root, embedder=_FakeEmbedder(_basis(0)))

    status = service.status()
    assert status["consolidated_nodes"] == 4
    assert status["mesh_edges"] == 3
    assert status["index_built"] is False

    outcome = asyncio.run(service.ask("what orbits the sun?", top_k=10, k_seeds=3))
    payload = outcome.payload

    names = {n["label"] for n in payload["constellation"]["nodes"]}
    assert "Sun" in names
    assert {"Earth", "Mars"} & names
    assert payload["constellation"]["edges"]
    assert any(e["relation_type"] == "orbited by" for e in payload["constellation"]["edges"])
    assert payload["synthesis_meta"]["mode"] == "mesh_constellation"
    # Explorer-shape contract: the d3 frontend consumes exactly these keys.
    for key in ("constellation", "retrieval", "timing_ms", "answer", "query_embedding_preview"):
        assert key in payload

    assert outcome.report.report_type == "mesh_query"
    assert outcome.report.constellation_node_count >= 1

    # The CSR/Propagator is cached after the first ask (PHX-1041 mitigation).
    assert service.status()["index_built"] is True


def test_mesh_routes_serve_constellation(cockpit_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "meshws_routes"
    _build_solar_system(root)
    cockpit_client.app.state.mesh_explorer = MeshExplorerService(
        root, embedder=_FakeEmbedder(_basis(0))
    )

    status = cockpit_client.get("/cockpit/api/mesh/status")
    assert status.status_code == 200
    assert status.json()["consolidated_nodes"] == 4

    resp = cockpit_client.post(
        "/cockpit/api/mesh/ask", json={"q": "sun", "top_k": 10, "operator": "ppr"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["constellation"]["nodes"]
    assert body["synthesis_meta"]["mode"] == "mesh_constellation"
    assert body["retrieval"]["strategy"] == "mesh:ppr"


def test_mesh_routes_404_when_unconfigured(cockpit_client: TestClient) -> None:
    cockpit_client.app.state.mesh_explorer = None
    assert cockpit_client.get("/cockpit/api/mesh/status").status_code == 404
    assert cockpit_client.post("/cockpit/api/mesh/ask", json={"q": "x"}).status_code == 404


def test_mesh_ask_rejects_bad_operator(cockpit_client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "meshws_badop"
    _build_solar_system(root)
    cockpit_client.app.state.mesh_explorer = MeshExplorerService(
        root, embedder=_FakeEmbedder(_basis(0))
    )
    resp = cockpit_client.post("/cockpit/api/mesh/ask", json={"q": "sun", "operator": "nonsense"})
    assert resp.status_code == 400


def test_ask_streaming_emits_activation_frames(tmp_path: Path) -> None:
    """Founding-demo Beat 1: the stream carries per-iteration SA frames, scoped
    to the constellation's working set, normalized to [0, 1], before complete."""
    root = tmp_path / "meshws_frames"
    _build_solar_system(root)
    service = MeshExplorerService(root, embedder=_FakeEmbedder(_basis(0)))

    async def _collect() -> list[dict]:
        return [e async for e in service.ask_streaming("what orbits the sun?", top_k=10, k_seeds=3)]

    events = asyncio.run(_collect())
    types = [e["type"] for e in events]
    assert "activation_frames" in types
    assert types.index("activation_frames") < types.index("complete")

    frames = next(e for e in events if e["type"] == "activation_frames")["frames"]
    assert frames
    complete = next(e for e in events if e["type"] == "complete")
    constellation_ids = {n["id"] for n in complete["payload"]["constellation"]["nodes"]}
    assert set(frames[0].keys()) <= constellation_ids
    assert all(0.0 <= v <= 1.0 for frame in frames for v in frame.values())
    assert any(v > 0.0 for v in frames[-1].values())
