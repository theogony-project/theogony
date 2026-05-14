"""Typer surface for ``theogony mesh`` (Step S1 + S2)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
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
    paragraphs: int = typer.Option(
        0,
        "--paragraphs",
        "-p",
        help="Number of paragraphs to read (0 = all).",
    ),
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Read a Gutenberg book paragraph by paragraph — extracts concepts,
    named relations, and syntheses via LLM and writes them directly into
    the MESH substrate as a fully connected knowledge network.
    """
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)
    llm = build_llm_from_settings(settings)
    reader = MeshParagraphReader(rt, llm=llm, max_paragraphs=paragraphs if paragraphs > 0 else 0)

    result = asyncio.run(reader.read_book(book_id))

    _console.print(Panel.fit(json.dumps(result, indent=2), title="mesh ingest result"))
