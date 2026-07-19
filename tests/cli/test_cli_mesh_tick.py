"""End-to-end test for ``theogony mesh tick``.

The tick is the substrate's write-side dynamics driver (drain delta buffer ->
merge -> super-linear decay -> saturation cap -> Lance rewrite -> audit). Before
this command existed, ``MeshRuntime.run_minimal_tick`` had no production caller:
decay/saturation were tested library functions with no way to run them against a
real workspace. This test drives the command through the CLI and asserts the
dynamics actually land on disk and that a ``mesh_tick`` RunReport is emitted.

Note on the delta buffer: it is in-memory per ``EdgeStore`` instance, so a freshly
opened runtime (as the CLI opens) sees no pending Hebbian deltas from another
instance. The CLI tick therefore drains 0 here — populating the buffer from the
query path is a separate change. Delta draining itself is covered at the runtime
level in ``tests/mesh/test_oneiros_tick_minimal.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner
from ulid import ULID

from theogony.cli import app
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.reporting.models import MeshTickReport
from theogony.reporting.writer import RunReportWriter


def _seed_hub(root: Path, *, out_degree: int) -> str:
    """Create an edges-only workspace with one hub of ``out_degree`` weight-1 edges."""
    rt = MeshRuntime(root, semantic_dim=8, frame_dim=4)
    now = datetime.now(UTC)
    hub = str(ULID())
    for _ in range(out_degree):
        rt.edges.append_edge(
            Edge(
                source_id=hub,
                target_id=str(ULID()),
                weight=1.0,
                born_at=now,
                last_fired_at=now,
                decay_tier=0,
            )
        )
    return hub


def test_mesh_tick_applies_decay_and_saturation_and_writes_report(
    cli_runner: CliRunner,
    cli_data_dir: Path,
    tmp_path: Path,
) -> None:
    ws = tmp_path / "mesh_ws"
    hub = _seed_hub(ws, out_degree=5)

    result = cli_runner.invoke(
        app,
        [
            "mesh",
            "tick",
            "--root",
            str(ws),
            "--decay-lambda",
            "0.01",
            "--max-out-degree",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "mesh tick" in result.output

    # Saturation capped the hub 5 -> 3; decay reduced every surviving weight.
    reopened = MeshRuntime.open(ws)
    hub_edges = [e for e in reopened.edges.load_all_edges() if str(e.source_id) == hub]
    assert len(hub_edges) == 3
    assert all(e.weight < 1.0 for e in hub_edges)
    assert reopened.last_tick_at() is not None

    # A mesh_tick RunReport landed under the isolated data dir and round-trips.
    report = RunReportWriter(cli_data_dir / "run_reports").most_recent("mesh_tick")
    assert isinstance(report, MeshTickReport)
    assert report.report_type == "mesh_tick"
    assert report.status == "completed"
    assert report.edges_before == 5
    assert report.edges_after == 3
    assert report.delta_drained == 0
    assert report.max_out_degree == 3
    assert report.audit_id is not None


def test_mesh_tick_on_empty_workspace_does_not_error(
    cli_runner: CliRunner,
    cli_data_dir: Path,
    tmp_path: Path,
) -> None:
    ws = tmp_path / "empty_ws"
    MeshRuntime(ws, semantic_dim=8, frame_dim=4)  # materialise an empty workspace

    result = cli_runner.invoke(app, ["mesh", "tick", "--root", str(ws)])

    assert result.exit_code == 0, result.output
    report = RunReportWriter(cli_data_dir / "run_reports").most_recent("mesh_tick")
    assert isinstance(report, MeshTickReport)
    assert report.edges_before == 0
    assert report.edges_after == 0
