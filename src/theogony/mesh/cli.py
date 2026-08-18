"""Typer surface for ``theogony mesh`` (Step S1 + S2)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.retrieval import RetrievalResult, retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m import (
    Wikidata5mSeedImporter,
    build_default_embedder,
    build_embedder,
)
from theogony.mesh.seeds.wikidata5m.embedder import EdgesOnlyEmbedder, MeshEmbedder
from theogony.mesh.storage.edges import DEFAULT_MAX_OUT_DEGREE
from theogony.reporting.models import MeshQueryRunReport, MeshTickReport
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
    structural_neighbours: int = typer.Option(
        12,
        "--structural-neighbours",
        help=(
            "PHX-1049: cap `shares_entities_with` partners kept per paragraph. "
            "0 restores the uncapped all-pairs lattice (the A/B control arm)."
        ),
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
        max_structural_neighbours=structural_neighbours,
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


@mesh_app.command("tick")
def mesh_tick(
    decay_lambda: float = typer.Option(
        0.05,
        "--decay-lambda",
        help="Super-linear decay rate applied to every edge (0 = no forgetting).",
    ),
    dt: float = typer.Option(
        1.0,
        "--dt",
        help="Time delta multiplied into the decay step.",
    ),
    max_out_degree: int = typer.Option(
        DEFAULT_MAX_OUT_DEGREE,
        "--max-out-degree",
        help=(
            "Saturation cap: keep only the strongest N outbound edges per node. "
            "Defaults to the doctrine's lowest tier cap (MESH_SUBSTRATE §3)."
        ),
    ),
    w_max: float = typer.Option(
        1.0,
        "--w-max",
        help="Weight ceiling for Hebbian delta merges and saturation.",
    ),
    keep_versions_hours: float = typer.Option(
        0.0,
        "--keep-versions-hours",
        help=(
            "Hours of Lance version snapshots to retain. These are one-per-write "
            "storage snapshots, not the substrate's record — that is the audit log "
            "— and keeping them makes every later append markedly slower "
            "(PHX-1060). Raise this to keep them anyway."
        ),
    ),
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Run one minimal Oneiros tick over the workspace.

    Drains the Hebbian delta buffer, merges deltas, applies super-linear decay,
    enforces saturation caps, rewrites the edge table, and commits a Lance
    version. This is the substrate's write-side dynamics driver — the loop that
    lets the Chronik consolidate strong co-activations and forget unused edges
    "without reading new text". Emits a MeshTickReport.
    """
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)

    started_at = datetime.now(UTC)
    result = rt.run_minimal_tick(
        lam=decay_lambda,
        dt=dt,
        max_out_degree=max_out_degree,
        w_max=w_max,
        version_retention=timedelta(hours=keep_versions_hours),
    )
    finished_at = datetime.now(UTC)

    report = MeshTickReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=(finished_at - started_at).total_seconds(),
        status="completed",
        verdict="good",
        verdict_reasoning=(
            f"drained {result.delta_drained} delta(s); "
            f"edges {result.edges_before} -> {result.edges_after}"
        ),
        edges_before=result.edges_before,
        edges_after=result.edges_after,
        delta_drained=result.delta_drained,
        decay_lambda=decay_lambda,
        dt=dt,
        max_out_degree=max_out_degree,
        w_max=w_max,
        audit_id=result.audit_id,
        new_lance_version=result.new_lance_version,
    )
    RunReportWriter(settings.run_reports_dir).write(report)

    summary = {
        "mesh_root": str(root),
        "edges_before": result.edges_before,
        "edges_after": result.edges_after,
        "delta_drained": result.delta_drained,
        "decay_lambda": decay_lambda,
        "max_out_degree": max_out_degree,
        "audit_id": result.audit_id,
        "new_lance_version": result.new_lance_version,
        "versions_pruned": sum(result.versions_pruned.values()),
        "run_report": report.run_id,
    }
    _console.print(Panel.fit(json.dumps(summary, indent=2), title="mesh tick"))


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


async def _query_embedder(target_dim: int, requested: str | None) -> MeshEmbedder:
    """Pick an embedder whose dimension matches the workspace's semantic_dim."""
    names = [requested] if requested else ["bge-m3", "bge-small-en"]
    for name in names:
        embedder = build_embedder(name)
        await embedder.embed_many(["mesh ask probe"], batch_size=1)
        if embedder.dim == target_dim:
            return embedder
        if requested is not None:
            raise ValueError(
                f"embedder {embedder.model_id} produces dim={embedder.dim}, "
                f"but mesh workspace uses semantic_dim={target_dim}"
            )
    raise ValueError(
        f"no known embedder matches workspace semantic_dim={target_dim}; pass --embedder explicitly"
    )


def _mesh_query_verdict(
    result: RetrievalResult,
) -> tuple[Literal["good", "partial", "poor"], str]:
    c = result.constellation
    if not c.nodes:
        return "poor", "no nodes activated"
    if not c.edges and c.operator != "vector-only":
        return "partial", "nodes activated but no edges in working set"
    if not c.source_anchor_ids:
        return "partial", "no source-anchored provenance reached"
    return "good", "connected, provenance-anchored working set"


def _render_constellation(result: RetrievalResult, *, max_nodes: int = 20) -> None:
    c = result.constellation
    node_table = Table(title="Constellation — activated nodes", show_lines=False)
    node_table.add_column("#", justify="right", style="dim")
    node_table.add_column("name", overflow="fold")
    node_table.add_column("qid", style="cyan")
    node_table.add_column("tier", justify="right")
    node_table.add_column("activation", justify="right")
    node_table.add_column("flags")
    for i, node in enumerate(c.nodes[:max_nodes], start=1):
        flags = []
        if node.is_seed:
            flags.append("seed")
        if node.is_source_anchor:
            flags.append("src")
        if node.is_candidate:
            flags.append("cand")
        node_table.add_row(
            str(i),
            node.name,
            node.qid or "-",
            str(node.tier),
            f"{node.activation:.4f}",
            ",".join(flags) or "-",
        )
    _console.print(node_table)

    if c.edges:
        edge_table = Table(title="Constellation — edges in working set")
        edge_table.add_column("source", overflow="fold")
        edge_table.add_column("relation", style="magenta")
        edge_table.add_column("target", overflow="fold")
        edge_table.add_column("weight", justify="right")
        for edge in c.edges[:max_nodes]:
            edge_table.add_row(
                edge.source_name,
                edge.relation_descriptor or "~",
                edge.target_name,
                f"{edge.weight:.3f}",
            )
        _console.print(edge_table)

    summary = {
        "operator": c.operator,
        "frame_routed": c.frame_routed,
        "seeds": len(c.seed_node_ids),
        "nodes": len(c.nodes),
        "edges": len(c.edges),
        "source_anchors": len(c.source_anchor_ids),
        "gaps": c.gaps,
        "hebbian_deltas": result.hebbian_deltas,
        "timings_ms": {k: round(v, 1) for k, v in result.timings_ms.items()},
    }
    _console.print(Panel.fit(json.dumps(summary, indent=2), title="mesh ask summary"))


@mesh_app.command("ask")
def mesh_ask(
    query: str = typer.Argument(
        ..., help="Natural-language query (embedded, then SA over the mesh)."
    ),
    operator: str = typer.Option(
        "ppr", "--operator", help="Propagation operator: ppr | degnorm | raw."
    ),
    top_k: int = typer.Option(30, "--top-k", help="Max nodes in the returned Constellation."),
    k_seeds: int = typer.Option(8, "--seeds", help="Diversified seed count (MMR + weight-class)."),
    hops: int = typer.Option(3, "--hops", help="Hops for raw/degnorm operators."),
    ann_limit: int = typer.Option(64, "--ann-limit", help="Vector-search candidates before MMR."),
    degree_beta: float = typer.Option(
        0.0,
        "--degree-beta",
        help="PHX-1042: divide incoming activation by in_degree**beta each hop (0 = off).",
    ),
    hub_mask_top_n: int = typer.Option(
        0,
        "--hub-mask-top-n",
        help="PHX-1042: zero the top-N in-degree hubs before assembly (0 = off; seeds survive).",
    ),
    embedder_name: str | None = typer.Option(
        None, "--embedder", help="bge-m3 | bge-small-en (default: match workspace dim)."
    ),
    vector_column: str = typer.Option(
        "semantic_vector",
        "--vector-column",
        help="ANN column: semantic_vector | description_vector.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the Constellation as JSON instead of tables."
    ),
    hebbian: bool = typer.Option(
        False,
        "--hebbian",
        help=(
            "Reinforce the traversed edges into the delta buffer (off by default: a "
            "query that mutates the mesh would make evaluations non-reproducible). "
            "Deltas are applied by the next `theogony mesh tick`."
        ),
    ),
    hebbian_learning_rate: float = typer.Option(
        0.01, "--hebbian-lr", help="Weight credited per unit of endpoint co-activation."
    ),
    mesh_root: Path | None = MESH_ROOT,
) -> None:
    """Query the MESH substrate: embed -> diversified injection -> Spreading Activation."""
    settings = Settings()
    root = mesh_root.resolve() if mesh_root is not None else _default_root(settings)
    rt = MeshRuntime.open(root)
    started_at = datetime.now(UTC)

    async def _embed() -> tuple[str, list[float], int]:
        embedder = await _query_embedder(rt.semantic_dim, embedder_name)
        t = time.perf_counter()
        vector = (await embedder.embed_many([query], batch_size=1))[0]
        return embedder.model_id, vector, int((time.perf_counter() - t) * 1000.0)

    model_id, query_vector, embed_ms = asyncio.run(_embed())

    result = retrieve(
        rt,
        query_vector,
        operator=operator,
        top_k=top_k,
        k_seeds=k_seeds,
        hops=hops,
        ann_limit=ann_limit,
        degree_beta=degree_beta,
        hub_mask_top_n=hub_mask_top_n,
        vector_column=vector_column,
        query=query,
        hebbian=hebbian,
        hebbian_learning_rate=hebbian_learning_rate,
    )
    finished_at = datetime.now(UTC)
    verdict, reasoning = _mesh_query_verdict(result)
    c = result.constellation
    report = MeshQueryRunReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_s=(finished_at - started_at).total_seconds(),
        status="completed",
        verdict=verdict,
        verdict_reasoning=f"{reasoning} (embedder={model_id})",
        query=query,
        query_length_chars=len(query),
        embedding_duration_ms=embed_ms,
        operator=result.operator,
        frame_routed=result.frame_routed,
        ann_hit_count=result.ann_hit_count,
        seed_count=len(result.seed_node_ids),
        seed_node_ids=result.seed_node_ids,
        constellation_node_count=len(c.nodes),
        constellation_edge_count=len(c.edges),
        source_anchor_count=len(c.source_anchor_ids),
        gaps_identified=len(c.gaps),
        csr_duration_ms=int(result.timings_ms.get("csr_ms", 0.0)),
        ann_duration_ms=int(result.timings_ms.get("ann_ms", 0.0)),
        propagate_duration_ms=int(result.timings_ms.get("propagate_ms", 0.0)),
        assemble_duration_ms=int(result.timings_ms.get("assemble_ms", 0.0)),
        cited_node_ids=[node.node_id for node in c.nodes],
    )
    RunReportWriter(settings.run_reports_dir).write(report)

    if json_out:
        _console.print_json(c.model_dump_json())
    else:
        _render_constellation(result)


mesh_app.add_typer(seed_app, name="seed")
