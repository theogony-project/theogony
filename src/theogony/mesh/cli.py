"""Typer surface for ``theogony mesh`` (Step S1)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from theogony.config.settings import Settings
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

mesh_app = typer.Typer(
    name="mesh",
    no_args_is_help=True,
    help="MESH substrate commands (migration Step S1 — parallel to legacy path).",
)
_console = Console()

_MESH_ROOT_OPTION = typer.Option(
    None,
    "--root",
    help="Mesh workspace directory (defaults to {data_dir}/mesh from settings).",
)


def _default_mesh_root(settings: Settings) -> Path:
    return (settings.data_dir / "mesh").resolve()


@mesh_app.command("status")
def mesh_status(mesh_root: Path | None = _MESH_ROOT_OPTION) -> None:
    """Print node/edge counts, Lance location, and last tick timestamp."""
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_mesh_root(settings)
    rt = MeshRuntime.open(root)
    chunks = rt.nodes.chunk_count()
    consolidated = rt.nodes.consolidated_count()
    edges = rt.edges.count_rows()
    pending_delta = rt.edges.delta.pending()
    st = rt.read_state()
    last_tick = st.get("last_tick_at", "never")
    summary = {
        "mesh_root": str(root),
        "chunk_nodes": chunks,
        "consolidated_nodes": consolidated,
        "mesh_edges": edges,
        "delta_buffer_pending": pending_delta,
        "last_tick_at": last_tick,
        "lance_uri": str(root / "lance"),
    }
    _console.print(Panel.fit(json.dumps(summary, indent=2), title="mesh status"))
