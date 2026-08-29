"""A second process must see the substrate, not the snapshot it opened at.

Without a read-consistency interval lancedb pins every table handle to the
version it was opened at. A long-lived reader is then not merely stale — it
breaks. Reproduced before the fix (PHX-1093):

    reader opens                     sees 1 edge
    writer appends two               writer sees 3, reader still sees 1
    writer runs prune_history        reader raises
        LanceError(IO): Not found — the data files it was pinned to are gone

The tick calls `prune_history`, so any process holding a runtime across a tick —
the Cockpit does — starts throwing rather than serving old answers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge


def _edge() -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=ULID(),
        target_id=ULID(),
        weight=1.0,
        relation_descriptor="r",
        born_at=now,
        last_fired_at=now,
    )


def test_a_reader_sees_a_writers_appends(tmp_path: Path) -> None:
    writer = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    writer.edges.append_edges([_edge()])
    reader = MeshRuntime.open(tmp_path / "ws")
    assert reader.edges.count_rows() == 1

    writer.edges.append_edges([_edge(), _edge()])
    assert reader.edges.count_rows() == 3, "the reader was pinned to its opening version"


def test_a_reader_survives_the_writers_prune(tmp_path: Path) -> None:
    """The failure mode that matters: not stale answers, an exception.

    `prune_history` deletes the data files an older version points at. A pinned
    handle then raises on its next uncached read, and the tick prunes on every
    run.
    """
    writer = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    writer.edges.append_edges([_edge()])
    reader = MeshRuntime.open(tmp_path / "ws")
    reader.edges.count_rows()

    writer.edges.append_edges([_edge(), _edge()])
    writer.edges.prune_history(retention=timedelta(0))

    assert len(reader.edges.load_all_edges()) == 3


def test_the_cockpit_index_follows_the_substrate(tmp_path: Path) -> None:
    """`ensure_index` returned early on "an index exists", so it froze at the first query.

    The Cockpit then served that graph until restart, however many ticks or
    ingests ran underneath it. Keyed on the runtime's own CSR fingerprint now —
    the same key `rebuild_csr` uses.
    """
    import asyncio

    from theogony.cockpit.mesh_explorer import MeshExplorerService

    writer = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    writer.edges.append_edges([_edge()])

    service = MeshExplorerService.__new__(MeshExplorerService)
    service._index_lock = asyncio.Lock()
    service._propagator = None
    service._csr = None
    service._index_fingerprint = None
    service.index_build_ms = 0
    service.runtime = lambda: MeshRuntime.open(tmp_path / "ws")  # type: ignore[method-assign]

    asyncio.run(service.ensure_index())
    assert service._csr is not None
    assert len(service._csr.node_ids) == 2

    writer.edges.append_edges([_edge(), _edge()])
    asyncio.run(service.ensure_index())
    assert len(service._csr.node_ids) == 6, "the index must be rebuilt after the substrate moves"
