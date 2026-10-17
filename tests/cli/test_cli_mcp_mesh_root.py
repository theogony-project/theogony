"""`theogony mcp --mesh-root` resolution (PHX-1112, piece 1).

The resolver is the CLI's half of the rule that the server never creates a
workspace and never starts with one it was asked for but cannot find. Tested
directly — starting the server would load an embedder for a path check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from theogony.cli import _resolve_mesh_root


def _fake_workspace(root: Path) -> None:
    (root / "lance" / "consolidated_nodes.lance").mkdir(parents=True)


def test_an_explicit_root_without_a_workspace_exits_2_and_creates_nothing(
    tmp_path: Path, cli_data_dir: Path
) -> None:
    missing = tmp_path / "not-a-mesh"
    with pytest.raises(typer.Exit) as exc:
        _resolve_mesh_root(missing, title="theogony mcp")
    assert exc.value.exit_code == 2
    assert not missing.exists()


def test_an_explicit_root_with_a_workspace_is_served_as_given(
    tmp_path: Path, cli_data_dir: Path
) -> None:
    root = tmp_path / "my-mesh"
    _fake_workspace(root)
    assert _resolve_mesh_root(root, title="theogony mcp") == root.resolve()


def test_the_default_root_is_picked_up_only_when_a_workspace_is_there(cli_data_dir: Path) -> None:
    assert _resolve_mesh_root(None, title="theogony mcp") is None
    assert not (cli_data_dir / "mesh").exists(), "asking must not create one"
    _fake_workspace(cli_data_dir / "mesh")
    assert _resolve_mesh_root(None, title="theogony mcp") == (cli_data_dir / "mesh").resolve()
