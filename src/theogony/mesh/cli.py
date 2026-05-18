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
from theogony.mesh.seeds.wikidata5m import (
    Wikidata5mSeedImporter,
    build_default_embedder,
    build_embedder,
)
from theogony.mesh.seeds.wikidata5m.embedder import EdgesOnlyEmbedder, MeshEmbedder
from theogony.reporting.writer import RunReportWriter

mesh_app = typer.Typer(
    name="mesh",
    no_args_is_help=True,
    help="MESH substrate commands (Step S1 — parallel to legacy path).",
)
seed_app = typer.Typer(
    name="seed",
    no_args_is_help=True,
    help="Bootstrap seed pipelines for the MESH substrate.",
)
_console = Console()

_MESH_ROOT_HELP = "Mesh workspace directory (defaults to {data_dir}/mesh from settings)."
MESH_ROOT = typer.Option(None, "--root", help=_MESH_ROOT_HELP)
QID_FILE = typer.Option(
    None,
    "--qid-file",
    help=(
        "Seed only Q-IDs listed in this file (one per line; optional degree column). "
        "Overrides --max-entities file-order selection."
    ),
)
DATA_ROOT = typer.Option(
    None,
    "--data-root",
    help=(
        "Path containing wikidata5m_entity.txt, wikidata5m_text.txt, "
        "wikidata5m_relation.txt, and wikidata5m_all_triplet.txt."
    ),
)


def _default_root(settings: Settings) -> Path:
    return (settings.data_dir / "mesh").resolve()


def _default_seed_data_root(settings: Settings) -> Path:
    return (settings.data_dir / "raw" / "wikidata5m").resolve()


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


@seed_app.command("wikidata5m")
def mesh_seed_wikidata5m(
    max_entities: int = typer.Option(
        0,
        "--max-entities",
        help="Cap streamed entity/text pairs (0 = all).",
    ),
    max_triplets: int = typer.Option(
        0,
        "--max-triplets",
        help="Cap streamed triplets (0 = all).",
    ),
    qid_file: Path | None = QID_FILE,
    batch_size: int = typer.Option(
        8,
        "--batch-size",
        help="Embedding batch size (lower = less peak RAM on Apple Silicon).",
    ),
    max_embedding_chars: int = typer.Option(
        2048,
        "--max-embedding-chars",
        help="Clip wikipedia paragraphs before embedding (raw text is not stored on mesh).",
    ),
    embedder_name: str | None = typer.Option(
        None,
        "--embedder",
        help="Embedder id: bge-m3 or bge-small-en. Default = auto-select.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Parse and report without writing nodes, edges, or audit rows.",
    ),
    edges_only: bool = typer.Option(
        False,
        "--edges-only",
        help="Skip entity embedding; append edges to an existing seeded workspace.",
    ),
    mesh_root: Path | None = MESH_ROOT,
    data_root: Path | None = DATA_ROOT,
) -> None:
    """Seed the mesh from the wikidata5m KEPLER dataset."""
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    resolved_data_root = (
        data_root.resolve() if data_root is not None else _default_seed_data_root(settings)
    )

    async def _run() -> dict[str, object]:
        embedder: MeshEmbedder
        if edges_only:
            runtime = MeshRuntime.open(root)
            requested_name = "edges-only"
            embedder = EdgesOnlyEmbedder(runtime.semantic_dim)
        else:
            if embedder_name is None:
                requested_name, embedder = await build_default_embedder()
            else:
                requested_name = embedder_name
                embedder = build_embedder(embedder_name)
                await embedder.embed_many(["mesh seed smoke probe"], batch_size=1)

            runtime = MeshRuntime.open(root, semantic_dim=embedder.dim, frame_dim=64)
            if runtime.semantic_dim != embedder.dim:
                raise ValueError(
                    f"mesh workspace uses semantic_dim={runtime.semantic_dim}, "
                    f"but embedder {embedder.model_id} produces dim={embedder.dim}"
                )

        importer = Wikidata5mSeedImporter(
            runtime,
            data_root=resolved_data_root,
            embedder=embedder,
            embedder_requested=requested_name,
            batch_size=batch_size,
            max_embedding_chars=max_embedding_chars,
            report_writer=RunReportWriter(settings.run_reports_dir),
        )
        return await importer.run(
            max_entities=max_entities,
            max_triplets=max_triplets,
            qid_file=qid_file.resolve() if qid_file is not None else None,
            edges_only=edges_only,
            dry_run=dry_run,
        )

    result = asyncio.run(_run())
    _console.print(Panel.fit(json.dumps(result, indent=2), title="mesh seed wikidata5m"))


mesh_app.add_typer(seed_app, name="seed")
