"""Typer surface for ``theogony mesh`` (Step S1 + S2)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import MeshIngestionPipeline
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

mesh_app = typer.Typer(
    name="mesh",
    no_args_is_help=True,
    help="MESH substrate commands (Step S1 — parallel to legacy path).",
)
_console = Console()

_MESH_ROOT_HELP = "Mesh workspace directory (defaults to {data_dir}/mesh from settings)."
MESH_ROOT = typer.Option(None, "--root", help=_MESH_ROOT_HELP)


def _default_root(settings: Settings) -> Path:
    return (settings.data_dir / "mesh").resolve()


@mesh_app.command("status")
def mesh_status(
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Print node/edge counts, current Lance version, and last tick timestamp."""
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)
    summary = {
        "mesh_root": str(root),
        "chunk_nodes": rt.nodes.chunk_count(),
        "consolidated_nodes": rt.nodes.consolidated_count(),
        "mesh_edges": rt.edges.count_rows(),
        "delta_buffer_pending": rt.edges.delta.pending(),
        "lance_version": rt.current_lance_version(),
        "last_tick_at": str(rt.last_tick_at()),
        "lance_uri": str(root / "lance"),
    }
    _console.print(Panel.fit(json.dumps(summary, indent=2), title="mesh status"))


@mesh_app.command("ingest")
def mesh_ingest(
    book_id: str = typer.Argument(..., help="Project Gutenberg book id (e.g. 43497)."),
    sentence_count: int = typer.Option(
        0, "--sentences", "-n", help="Max sentences to ingest (0 = all)."
    ),
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Ingest a Gutenberg book into the MESH substrate (Step S2)."""
    import asyncio

    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)

    async def _run() -> dict:
        async with MeshIngestionPipeline(rt) as pipeline:
            return await pipeline.ingest_gutenberg(book_id, max_sentences=sentence_count)

    result = asyncio.run(_run())
    _console.print(Panel.fit(json.dumps(result, indent=2), title="mesh ingest result"))
