"""`theogony mesh demo` — a real mesh with no key (PHX-1112, piece 2).

Three paragraphs through the real embedder, not all 95: the command's logic
(refusals, the demo marker, idempotence) is what a unit test can hold, and the
full build is measured by `scripts/fresh_clone_probe.sh`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner
from ulid import ULID

from theogony.cli import app
from theogony.mesh import cli as mesh_cli
from theogony.mesh.ingestion.replay import load_readings, paragraphs_of, reading_key
from theogony.mesh.runtime.oneiros_tick import MeshRuntime, mesh_workspace_exists
from theogony.mesh.schemas import Edge
from theogony.seeds import DEMO_CORPUS, demo_corpus_path


def test_the_demo_builds_marks_and_refuses_to_build_twice(
    cli_runner: CliRunner, cli_data_dir: Path
) -> None:
    root = cli_data_dir / "mesh"
    assert not mesh_workspace_exists(root)

    first = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "3"])
    assert first.exit_code == 0, first.output
    assert "3 paragraphs replayed (3 readings, 0 missing)" in first.output
    assert "theogony mcp" in first.output and "mesh ask" in first.output
    assert mesh_workspace_exists(root), "built into the default root"
    rt = MeshRuntime.open(root)
    state = rt.state()
    assert state["demo_corpus"] == DEMO_CORPUS.slug and state["demo_paragraphs"] == 3
    assert state["demo_readings_model_ids"], "the readings' provenance travels with the workspace"
    nodes_before = rt.nodes.consolidated_count()
    assert nodes_before > 3
    assert rt.semantic_dim == 384, (
        "built in the configured embedder's space, so `theogony mcp` can query it"
    )
    names = {n.tags[0] for n in rt.nodes.iter_consolidated() if n.tags and not n.is_source_anchor}
    assert "Muses" in names or "Zeus" in names, names
    anchors = [n for n in rt.nodes.iter_consolidated() if n.is_source_anchor]
    assert any(DEMO_CORPUS.anchor in (a.description or "") for a in anchors)

    again = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "3"])
    assert again.exit_code == 0, again.output
    assert "already here" in again.output and "3 of 95 paragraphs" in again.output
    assert MeshRuntime.open(root).nodes.consolidated_count() == nodes_before, "not rebuilt"

    # asked for more of the corpus than it holds, the demo is ours to rebuild
    more = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "4"])
    assert more.exit_code == 0, more.output
    assert "4 paragraphs replayed" in more.output
    assert MeshRuntime.open(root).state()["demo_paragraphs"] == 4

    # and so is the demo itself, when told
    replaced = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2", "--replace"])
    assert replaced.exit_code == 0, replaced.output
    assert MeshRuntime.open(root).state()["demo_paragraphs"] == 2

    # the marker survives the substrate's own maintenance pass
    ticked = MeshRuntime.open(root)
    ticked.run_minimal_tick()
    assert ticked.state()["demo_corpus"] == DEMO_CORPUS.slug and ticked.state()["last_tick_at"]


def test_a_workspace_that_is_not_the_demo_is_left_alone_unless_told(
    cli_runner: CliRunner, cli_data_dir: Path
) -> None:
    root = cli_data_dir / "mesh"
    foreign = MeshRuntime(root, semantic_dim=384, frame_dim=64)
    foreign.update_state({"note": "somebody's own mesh"})
    now = datetime.now(UTC)
    foreign.edges.append_edge(
        Edge(
            source_id=str(ULID()), target_id=str(ULID()), weight=1.0, born_at=now, last_fired_at=now
        )
    )
    assert mesh_workspace_exists(root)

    refused = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2"])
    assert refused.exit_code == 1, refused.output
    assert "not the demo" in refused.output
    assert MeshRuntime.open(root).state().get("note") == "somebody's own mesh", "untouched"

    replaced = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2", "--replace"])
    assert replaced.exit_code == 0, replaced.output
    state = MeshRuntime.open(root).state()
    assert state.get("demo_corpus") == DEMO_CORPUS.slug and "note" not in state


def test_root_names_another_directory(
    cli_runner: CliRunner, cli_data_dir: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    result = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2", "--root", str(elsewhere)])
    assert result.exit_code == 0, result.output
    assert mesh_workspace_exists(elsewhere)
    assert not mesh_workspace_exists(cli_data_dir / "mesh")


def test_an_initialised_but_empty_default_root_is_not_in_the_way(
    cli_runner: CliRunner, cli_data_dir: Path
) -> None:
    """`mesh status` or `mesh ask` before `mesh demo` leave a workspace with
    tables and no rows at the default root; nobody's content, so no refusal."""
    root = cli_data_dir / "mesh"
    MeshRuntime.open(root)
    assert mesh_workspace_exists(root)
    result = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2"])
    assert result.exit_code == 0, result.output
    assert MeshRuntime.open(root).state().get("demo_corpus") == DEMO_CORPUS.slug


def test_a_paragraph_without_a_reading_is_a_failure_that_leaves_nothing_behind(
    cli_runner: CliRunner, cli_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Honest failure: exit 1, no demo marker, and no half-built workspace that
    the next run would refuse as "not the demo" or `theogony mcp` would serve."""
    second = paragraphs_of(demo_corpus_path().read_text(encoding="utf-8"))[1]

    def without_second(path):  # type: ignore[no-untyped-def]
        readings = load_readings(path)
        del readings[reading_key(second)]
        return readings

    monkeypatch.setattr(mesh_cli, "load_readings", without_second)
    root = cli_data_dir / "mesh"
    result = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2"])
    assert result.exit_code == 1, result.output
    assert "1 missing" in result.output and "incomplete" in result.output
    assert not mesh_workspace_exists(root), "a build this command started is removed again"

    # Restore the real loader explicitly: `monkeypatch.undo()` would also undo the
    # data-dir fixture and send the next run into the developer's own data/mesh.
    monkeypatch.setattr(mesh_cli, "load_readings", load_readings)
    rebuilt = cli_runner.invoke(app, ["mesh", "demo", "--paragraphs", "2"])
    assert rebuilt.exit_code == 0, rebuilt.output
    assert "2 paragraphs replayed (2 readings, 0 missing)" in rebuilt.output
