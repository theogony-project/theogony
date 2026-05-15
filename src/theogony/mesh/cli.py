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
    source: str = typer.Argument(..., help="Project Gutenberg book id or local text file path."),
    paragraphs: int = typer.Option(
        0,
        "--paragraphs",
        "-p",
        help="Number of paragraphs to read (0 = all).",
    ),
    text_file: bool = typer.Option(
        False,
        "--text-file",
        help="Treat source as a local text file path instead of a Gutenberg id.",
    ),
    source_type: str = typer.Option(
        "text",
        "--source-type",
        help="Source type label used when ingesting a local text file.",
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Override title for local text ingestion.",
    ),
    anchor: str | None = typer.Option(
        None,
        "--anchor",
        help="Override anchor for local text ingestion.",
    ),
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Read a source into the MESH substrate with dense paragraph topology."""
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)
    llm = build_llm_from_settings(settings)
    reader = MeshParagraphReader(
        rt,
        llm=llm,
        max_paragraphs=paragraphs if paragraphs > 0 else 0,
        settings=settings,
    )

    if text_file:
        path = Path(source).resolve()
        raw_text = path.read_text(encoding="utf-8")
        result = asyncio.run(
            reader.read_text(
                text=raw_text,
                source_type=source_type,
                source_identifier=str(path),
                title=title or path.stem,
                anchor=anchor or str(path),
            )
        )
    else:
        result = asyncio.run(reader.read_book(source))

    _console.print(Panel.fit(json.dumps(result, indent=2), title="mesh ingest result"))
