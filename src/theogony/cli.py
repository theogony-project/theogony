"""
Typer CLI entry point (Plan §2.8 + §3.7).

Commands available in this module:

- ``status``         — read-only health snapshot (E-C)
- ``reports list``   — list recent run reports (E-C)
- ``reports show``   — pretty-print one report's full JSON (E-C)
- ``ingest <id>``    — full end-to-end ingest of one Project
  Gutenberg book; runs acquisition + extraction + embedding +
  store + report persistence (E6/E7/E9)
- ``ask <query>``    — synthesised, citation-anchored answer (E9)
- ``node <id>``      — Hover-Lupe node + neighbourhood (E9)
- ``resolve [...]``  — manual-resolution surface (Plan §3.4); E9
- ``serve [...]``    — uvicorn wrapper for the FastAPI app (E9)

The single-file CLI is a deliberate E9-brief decision (1000-line
modules are still readable; cyclic-import cost of splitting is
zero benefit until we hit it).

Module satisfies the ``[project.scripts]`` declaration in
pyproject.toml (``theogony = "theogony.cli:app"``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager, nullcontext
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from theogony import __version__
from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.factory import build_llm_from_settings
from theogony.config import Settings, setup_logging
from theogony.core.store import KnowledgeStore
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline, IngestionResult
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import WikidataClient
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores.memory import InMemoryKnowledgeStore
from theogony.stores.neo4j_store import Neo4jKnowledgeStore

if TYPE_CHECKING:
    from theogony.acquisition.base import RawContent
    from theogony.core.model import Layer

#: Verdict-to-Rich-style mapping. Lifted to module level so ask / ingest /
#: reports list all share one source of truth.
VERDICT_STYLES: dict[str, str] = {
    "good": "green",
    "partial": "yellow",
    "poor": "red",
    "failed": "red",
    "inconclusive": "yellow",
    "incomplete": "yellow",
}

app = typer.Typer(
    name="theogony",
    no_args_is_help=True,
    add_completion=False,
    help="Theogony — a living vector-graph knowledge network.",
)

reports_app = typer.Typer(
    name="reports",
    no_args_is_help=True,
    help="Inspect run reports written by IngestionPipeline / QueryPipeline / OneirosWorker.",
)
app.add_typer(reports_app, name="reports")

_console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_settings() -> Settings:
    """Single place to load settings — keeps logging-init order obvious."""
    settings = Settings()
    setup_logging(settings)
    return settings


def _format_provider_summary(settings: Settings) -> Table:
    table = Table(title="Provider configuration", show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Value")
    table.add_row("LLM provider", settings.llm.provider)
    table.add_row("LLM model", settings.llm.model_id)
    table.add_row("LLM timeout (s)", str(settings.llm.timeout_s))
    key = settings.active_llm_api_key()
    table.add_row(
        "API key",
        "set" if key is not None else "[red]missing[/red]",
    )
    table.add_row("Embedding model", settings.embedding.model_id)
    table.add_row("Embedding dim", str(settings.embedding.dim))
    table.add_row("Neo4j URI", settings.neo4j.uri)
    table.add_row("Data dir", str(settings.data_dir))
    table.add_row("Run reports dir", str(settings.run_reports_dir))
    return table


def _format_paths_summary(settings: Settings) -> Table:
    table = Table(title="Filesystem", show_header=True, header_style="bold")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("Note")
    rows: list[tuple[Path, str]] = [
        (settings.data_dir, "data root"),
        (settings.run_reports_dir, "run reports root"),
        (settings.run_reports_dir / "ingest", "ingest reports"),
        (settings.run_reports_dir / "query", "query reports"),
        (settings.run_reports_dir / "oneiros", "oneiros reports"),
    ]
    for path, note in rows:
        status_marker = "[green]exists[/green]" if path.exists() else "[yellow]not yet[/yellow]"
        table.add_row(str(path), status_marker, note)
    return table


def _count_reports(settings: Settings, report_type: str) -> int:
    d = settings.run_reports_dir / report_type
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.suffix == ".json")


# ---------------------------------------------------------------------------
# `theogony status`
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Print Theogony's current configuration and report counts.

    First command a new contributor should run after cloning. Confirms
    the active LLM provider, embedding model, store backend, and
    where reports get written. Does NOT contact any external service —
    safe to run offline before any setup.
    """
    settings = _load_settings()
    _console.print(
        Panel.fit(
            f"[bold]Theogony[/bold] {__version__}\n"
            "[dim]A living vector-graph knowledge network.[/dim]",
            border_style="cyan",
        )
    )
    _console.print(_format_provider_summary(settings))
    _console.print(_format_paths_summary(settings))

    counts_table = Table(title="Run reports", show_header=True, header_style="bold")
    counts_table.add_column("Type")
    counts_table.add_column("Count", justify="right")
    for rtype in ("ingest", "query", "oneiros"):
        counts_table.add_row(rtype, str(_count_reports(settings, rtype)))
    _console.print(counts_table)


# ---------------------------------------------------------------------------
# `theogony reports list` / `reports show`
# ---------------------------------------------------------------------------


@reports_app.command("list")
def reports_list(
    report_type: str = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by report type: ingest | query | oneiros. Default: all.",
    ),
    last: int = typer.Option(
        20,
        "--last",
        "-n",
        min=1,
        help="Maximum number of reports to show, newest first.",
    ),
) -> None:
    """List recent run reports across types, newest first."""
    settings = _load_settings()
    types = [report_type] if report_type is not None else ["ingest", "query", "oneiros"]

    rows: list[tuple[str, str, str, str, str]] = []  # (run_id, type, verdict, status, duration)
    for rtype in types:
        d = settings.run_reports_dir / rtype
        if not d.exists():
            continue
        for path in sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
            key=lambda p: p.stem,
            reverse=True,
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _console.print(f"[yellow]warning[/yellow]: could not read {path}: {exc}")
                continue
            rows.append(
                (
                    payload.get("run_id", path.stem),
                    payload.get("report_type", rtype),
                    payload.get("verdict", "?"),
                    payload.get("status", "?"),
                    f"{payload.get('duration_s', 0.0):.2f}s",
                )
            )

    # Cross-type sort by run_id (ULID prefix is chronological)
    rows.sort(key=lambda r: r[0], reverse=True)
    rows = rows[:last]

    if not rows:
        _console.print("[dim]No reports found.[/dim]")
        _console.print(f"[dim]Looked under {settings.run_reports_dir}[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("run_id")
    table.add_column("type")
    table.add_column("verdict")
    table.add_column("status")
    table.add_column("duration")
    for run_id, rtype, verdict, status_val, duration in rows:
        style = VERDICT_STYLES.get(verdict, "white")
        table.add_row(
            run_id,
            rtype,
            f"[{style}]{verdict}[/{style}]",
            status_val,
            duration,
        )
    _console.print(table)


@reports_app.command("show")
def reports_show(run_id: str = typer.Argument(..., help="The run_id (ULID).")) -> None:
    """Pretty-print one report's full JSON.

    Searches all three subdirectories. If no exact match is found,
    falls back to prefix matching so you can paste the first few
    characters of a ULID and still find the file.
    """
    settings = _load_settings()
    matches: list[Path] = []
    for rtype in ("ingest", "query", "oneiros"):
        d = settings.run_reports_dir / rtype
        if not d.exists():
            continue
        exact = d / f"{run_id}.json"
        if exact.exists():
            matches = [exact]
            break
        # Prefix fallback within this directory
        for p in d.iterdir():
            if p.is_file() and p.suffix == ".json" and p.stem.startswith(run_id):
                matches.append(p)

    if not matches:
        _console.print(f"[red]No report found matching run_id={run_id}[/red]")
        _console.print(f"[dim]Looked under {settings.run_reports_dir}[/dim]")
        raise typer.Exit(code=1)

    if len(matches) > 1:
        _console.print(f"[yellow]Multiple reports match prefix '{run_id}':[/yellow]")
        for m in matches:
            _console.print(f"  {m.parent.name}/{m.stem}")
        _console.print("[dim]Pass a longer prefix to disambiguate.[/dim]")
        raise typer.Exit(code=1)

    path = matches[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    _console.print(
        Panel.fit(
            f"[bold]{payload.get('report_type', '?')}[/bold] "
            f"run_id={payload.get('run_id', path.stem)}",
            border_style="cyan",
        )
    )
    _console.print_json(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# `theogony ingest <book_id>`
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    book_id: str = typer.Argument(
        ...,
        help="Project Gutenberg book ID (e.g. 43497 for Hedin Trans-Himalaya Vol. I).",
    ),
    sentences: int | None = typer.Option(
        None,
        "--sentences",
        "-s",
        min=1,
        help=(
            "Limit NER + downstream stages to the first N sentences. "
            "Dev-mode shortcut: full ingest of a book typically runs ~7 000 "
            "sentences; --sentences 50 brings cold-cache wall-clock under a minute."
        ),
    ),
    relations: int | None = typer.Option(
        None,
        "--relations",
        "-r",
        min=1,
        help=(
            "Cap relation extraction to the first N (post-NER-limit) sentences. "
            "Each relation call is one Gemini round-trip; useful for budgeting."
        ),
    ),
    no_book_context: bool = typer.Option(
        False,
        "--no-book-context",
        help=(
            "Skip BookContextExtractor (E3). Saves one Gemini call; "
            "Stage 4 falls back to a no-context prompt."
        ),
    ),
    no_relations: bool = typer.Option(
        False,
        "--no-relations",
        help="Skip RelationExtractor entirely. Useful when validating just node resolution.",
    ),
    no_embed: bool = typer.Option(
        False,
        "--no-embed",
        help="Skip the embedder. Saves the BGE-small download / load on first run.",
    ),
    store_kind: str = typer.Option(
        "neo4j",
        "--store",
        help=(
            "Storage backend: 'neo4j' (default — persists across runs) or "
            "'memory' (process-local, for offline/CI tests)."
        ),
    ),
) -> None:
    """Ingest a Project Gutenberg book end-to-end into the chosen store.

    Pipeline (Plan §2.5): acquire → clean → sentencize → NER →
    book context → resolve → relations → embed → store. The
    IngestRunReport is persisted under ``settings.run_reports_dir/ingest/``;
    every LLM call is logged under ``settings.data_dir/audit.sqlite``.

    Default store is ``neo4j`` (Plan §3.1a — persistent across runs).
    Pass ``--store memory`` to use the process-local
    ``InMemoryKnowledgeStore`` for offline tests / CI matrices that
    don't have a Neo4j to talk to.
    """
    if store_kind not in ("neo4j", "memory"):
        _console.print(
            f"[red]Unknown --store value: {store_kind!r}. Use 'neo4j' or 'memory'.[/red]"
        )
        raise typer.Exit(code=2)
    asyncio.run(
        _run_ingest(
            book_id=book_id,
            ner_sentence_limit=sentences,
            max_relation_sentences=relations,
            include_book_context=not no_book_context,
            include_relations=not no_relations,
            include_embedder=not no_embed,
            store_kind=store_kind,
        )
    )


@contextlib.asynccontextmanager
async def _open_store(
    settings: Settings, store_kind: str, embedding_dim: int
) -> AsyncIterator[KnowledgeStore]:
    """Construct + open the requested ``KnowledgeStore`` as an async ctxmgr.

    ``neo4j`` opens a Bolt connection + bootstraps the schema; ``memory``
    is a no-op constructor. Both yield a fully initialised store the
    caller can use as ``KnowledgeStore``.
    """
    if store_kind == "neo4j":
        async with Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedding_dim) as store:
            yield store
    elif store_kind == "memory":
        yield InMemoryKnowledgeStore()
    else:  # pragma: no cover - validated upstream
        raise ValueError(f"unknown store_kind: {store_kind}")


async def _run_ingest(
    *,
    book_id: str,
    ner_sentence_limit: int | None,
    max_relation_sentences: int | None,
    include_book_context: bool,
    include_relations: bool,
    include_embedder: bool,
    store_kind: str = "neo4j",
) -> None:
    """Async core of the ``theogony ingest`` command.

    Wires GutenbergAdapter + WikidataClient + Gemini (or Stub) +
    audit log + InMemoryKnowledgeStore + RunReportWriter, runs one
    IngestionPipeline.ingest, persists the report, and prints a
    Rich-styled summary.

    Honest-failure: every blockable error (Gutenberg 404, missing
    Gemini key, etc.) is rendered as a clean Rich panel and exits
    with non-zero — never a raw stack trace.
    """
    settings = _load_settings()
    audit_path = settings.data_dir / "audit.sqlite"
    report_writer = RunReportWriter(settings.run_reports_dir)

    # ---- acquire ----
    try:
        async with GutenbergAdapter(inter_request_delay_s=0.0) as gutenberg:
            cand = await gutenberg.get_by_id(book_id)
            raw_content = await gutenberg.acquire(cand)
    except Exception as exc:
        _console.print(
            Panel.fit(
                f"[red]Acquisition failed[/red]: {exc}",
                title="theogony ingest",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc

    # ---- compose pipeline ----
    try:
        llm = build_llm_from_settings(settings)
    except (ValueError, NotImplementedError) as exc:
        _console.print(
            Panel.fit(
                f"[red]LLM provider unavailable[/red]: {exc}",
                title="theogony ingest",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc

    embedder = (
        LocalSentenceTransformerEmbedder(
            model_id=settings.embedding.model_id,
            dim=settings.embedding.dim,
        )
        if include_embedder
        else None
    )

    # Persistent Wikidata cache (W6, PR #33). The cache is opt-out via
    # ``THEOGONY_WIKIDATA_CACHE__ENABLED=false`` for cold-cache
    # measurements; default on so reruns of the same corpus stop
    # paying the full Wikidata round-trip cost.
    wd_cache_cm: AbstractContextManager[WikidataCache | None] = (
        WikidataCache(settings.wikidata_cache_path)
        if settings.wikidata_cache.enabled
        else nullcontext(None)
    )
    with ExtractionAuditLog(audit_path) as audit, wd_cache_cm as wd_cache:
        async with WikidataClient(cache=wd_cache) as wd_client:
            resolver = EntityResolver(client=wd_client, llm=llm, audit_log=audit)
            book_context_extractor: BookContextExtractor | None = (
                BookContextExtractor(llm=llm, audit_log=audit) if include_book_context else None
            )
            relation_extractor: RelationExtractor | None = (
                RelationExtractor(llm=llm, audit_log=audit) if include_relations else None
            )
            async with _open_store(settings, store_kind, settings.embedding.dim) as store:
                pipeline = IngestionPipeline(
                    entity_resolver=resolver,
                    relation_extractor=relation_extractor,
                    book_context_extractor=book_context_extractor,
                    embedder=embedder,
                    audit_log=audit,
                    store=store,
                    settings=settings,
                    ner_sentence_limit=ner_sentence_limit,
                    max_relation_sentences=max_relation_sentences,
                )
                result = await pipeline.ingest(raw_content)
                audit_rows = audit.count_for_run(result.run_id)
                audit_cost = audit.total_cost_for_run(result.run_id)

    # ---- persist report ----
    report_path = report_writer.write(result.report)

    _print_ingest_summary(
        result=result,
        raw_content=raw_content,
        report_path=report_path,
        audit_rows=audit_rows,
        audit_cost=audit_cost,
        store_kind=store_kind,
    )


def _print_ingest_summary(
    *,
    result: IngestionResult,
    raw_content: RawContent,
    report_path: Path,
    audit_rows: int,
    audit_cost: float,
    store_kind: str = "neo4j",
) -> None:
    """Render a Rich panel + summary table for the completed ingest."""
    report = result.report
    verdict_style = VERDICT_STYLES.get(report.verdict, "white")

    title = (
        f"theogony ingest [bold]{raw_content.source_type}:{raw_content.identifier}[/bold] "
        f"— [{verdict_style}]{report.verdict}[/{verdict_style}]"
    )
    _console.print(Panel.fit(title, border_style=verdict_style))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("run_id", report.run_id)
    table.add_row("source title", raw_content.title)
    table.add_row("status", report.status)
    reasoning = report.verdict_reasoning or "(no reasoning)"
    table.add_row(
        "verdict",
        f"[{verdict_style}]{report.verdict}[/{verdict_style}] — {reasoning}",
    )
    table.add_row("duration", f"{report.duration_s:.2f}s")
    table.add_row("sentences", str(report.sentence_count))
    table.add_row("ner mentions", str(report.ner.total_mentions))
    table.add_row("resolved nodes", str(len(result.resolved_mentions)))
    table.add_row("edges minted", str(len(result.edges)))
    tier_str = ", ".join(f"T{t}={c}" for t, c in sorted(report.resolution.tier_counts.items()))
    table.add_row("tier counts", tier_str or "(none)")
    table.add_row("manual resolution needed", str(report.resolution.manual_resolution_needed))
    table.add_row("relations attempted", str(report.relations.attempted))
    table.add_row("relations parsed_ok", str(report.relations.parsed_ok))
    table.add_row(
        "embedding",
        f"{report.embedding.nodes_embedded} nodes via {report.embedding.embedding_model_id}",
    )
    store_str = f"{report.store.nodes_upserted} nodes / {report.store.edges_upserted} edges"
    table.add_row("store", store_str)
    table.add_row("store backend", store_kind)
    table.add_row("audit rows", str(audit_rows))
    table.add_row("LLM cost (EUR)", f"{audit_cost:.5f}")
    table.add_row("report file", str(report_path))

    _console.print(table)
    _console.print(
        f"[dim]To re-read this report: [/dim][bold]theogony reports show {report.run_id}[/bold]"
    )


# ---------------------------------------------------------------------------
# `theogony ask <query>`  (E9)
# ---------------------------------------------------------------------------


@app.command()
def ask(
    query: str = typer.Argument(..., help="The question to ask the Chronik."),
    k: int = typer.Option(10, "--k", min=1, max=50, help="Number of seed nodes."),
    hops: int = typer.Option(2, "--hops", min=0, max=4, help="Graph expansion depth."),
    layer: str | None = typer.Option(
        None,
        "--layer",
        help="Restrict to a memory layer: ephemera | mneme. Default: all.",
    ),
    store_kind: str = typer.Option(
        "neo4j",
        "--store",
        help="Storage backend: 'neo4j' (default) or 'memory' (offline / CI tests).",
    ),
) -> None:
    """Ask the Chronik a question and render the cited answer.

    Wires the same components as the FastAPI ``POST /query`` route:
    embedder + Neo4j store + LLM + audit log + retrieval pipeline.
    Renders a Rich panel with the answer text, cited node ids,
    constellation summary, synthesis cost / latency, and the run_id
    for follow-up via ``theogony reports show``.
    """
    if store_kind not in ("neo4j", "memory"):
        _console.print(f"[red]Unknown --store value: {store_kind!r}[/red]")
        raise typer.Exit(code=2)
    layer_enum = _parse_layer(layer)
    asyncio.run(
        _run_ask(
            query=query,
            k=k,
            hops=hops,
            layer=layer_enum,
            store_kind=store_kind,
        )
    )


def _parse_layer(layer: str | None) -> Layer | None:
    """Coerce a CLI-string to a Layer enum, or None when omitted."""
    if layer is None:
        return None
    from theogony.core.model import Layer

    try:
        return Layer(layer.lower())
    except ValueError as exc:
        valid = ", ".join(sorted(layer_value.value for layer_value in Layer))
        _console.print(f"[red]Unknown --layer value: {layer!r}. Valid: {valid}[/red]")
        raise typer.Exit(code=2) from exc


async def _run_ask(
    *,
    query: str,
    k: int,
    hops: int,
    layer: Layer | None,
    store_kind: str,
) -> None:
    settings = _load_settings()
    audit_path = settings.data_dir / "audit.sqlite"
    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    try:
        llm = build_llm_from_settings(settings)
    except (ValueError, NotImplementedError) as exc:
        _console.print(
            Panel.fit(
                f"[red]LLM provider unavailable[/red]: {exc}",
                title="theogony ask",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc
    report_writer = RunReportWriter(settings.run_reports_dir)

    with ExtractionAuditLog(audit_path) as audit:
        async with _open_store(settings, store_kind, settings.embedding.dim) as store:
            pipeline = QueryPipeline(
                embedder=embedder,
                retriever=MultiHopRetriever(store),
                assembler=ConstellationAssembler(store),
                synthesizer=AnswerSynthesizer(llm, audit_log=audit),
                relevance=RelevanceTracker(store),
                settings=settings,
                report_writer=report_writer,
            )
            result = await pipeline.ask(query, layer=layer, k=k, hops=hops)

    _print_ask_result(query=query, result=result)


def _print_ask_result(*, query: str, result: object) -> None:
    """Render the verdict-coloured Rich panel for ``theogony ask``.

    ``result`` is a :class:`QueryResult` — typed as ``object`` only to
    avoid a public-API import cycle on the CLI's lazy boundary.
    """
    # Lazy import keeps the public CLI imports compact at module load.
    from theogony.retrieval.pipeline import QueryResult

    assert isinstance(result, QueryResult)
    report = result.report
    style = VERDICT_STYLES.get(report.verdict, "white")
    cited = result.answer.cited_node_ids
    high_conf = report.citation_quality.citations_with_high_confidence_source
    citation_line = (
        f"Cited: {', '.join(cited)} ({len(cited)} nodes, {high_conf} high-conf)"
        if cited
        else "Cited: (none — see verdict reasoning)"
    )
    constellation_line = (
        f"Constellation: {report.constellation_node_count} nodes / "
        f"{report.constellation_edge_count} edges / "
        f"{report.gaps_identified} gaps"
    )
    synthesis_line = (
        f"Synthesis: {report.synthesis.latency_ms} ms · "
        f"{report.synthesis.input_tokens} in / {report.synthesis.output_tokens} out tokens · "
        f"{report.synthesis.cost_eur:.6f} EUR"
    )
    run_line = f"Run: {report.run_id}  →  theogony reports show {report.run_id}"
    body = "\n\n".join(
        [
            result.answer.text or "(no answer text — verdict captured the failure)",
            citation_line,
            constellation_line,
            synthesis_line,
            run_line,
        ]
    )
    title = f"{query} — [{style}]{report.verdict}[/{style}]"
    _console.print(Panel.fit(body, title=title, border_style=style))


# ---------------------------------------------------------------------------
# `theogony node <id>`  (E9)
# ---------------------------------------------------------------------------


@app.command()
def node(
    node_id: str = typer.Argument(..., help="AKA-… node id (full or prefix)."),
    store_kind: str = typer.Option(
        "neo4j",
        "--store",
        help="Storage backend: 'neo4j' (default) or 'memory'.",
    ),
) -> None:
    """Print a node's record + its depth-1 neighbourhood (Hover-Lupe).

    On a missing id, prints up to three closest-prefix matches as a
    "did you mean…" hint. Honest-failure: never a stack trace.
    """
    if store_kind not in ("neo4j", "memory"):
        _console.print(f"[red]Unknown --store value: {store_kind!r}[/red]")
        raise typer.Exit(code=2)
    asyncio.run(_run_node(node_id=node_id, store_kind=store_kind))


async def _run_node(*, node_id: str, store_kind: str) -> None:
    settings = _load_settings()
    async with _open_store(settings, store_kind, settings.embedding.dim) as store:
        record = await store.get_node(node_id)
        if record is None:
            await _print_node_did_you_mean(store, node_id)
            raise typer.Exit(code=1)
        neighborhood = await store.get_neighborhood(node_id, depth=1, min_weight=0.3)
    _print_node_panel(record=record, neighborhood=neighborhood)


async def _print_node_did_you_mean(store: KnowledgeStore, missing_id: str) -> None:
    """Render a red 'no node + did-you-mean' panel.

    Pulls a small page of pending-resolution-or-not nodes via
    ``count_nodes`` + ``list_pending_resolution`` paths is overkill;
    instead we sample whatever the store exposes via the bulk export
    surface (limited to the first 200 ids — keeps the prefix-match
    ceiling sane).
    """
    sample_ids: list[str] = []
    from theogony.core.model import Layer

    with contextlib.suppress(Exception):
        count = 0
        async for n in store.export_layer(Layer.EPHEMERA):
            sample_ids.append(n.id)
            count += 1
            if count >= 200:
                break
    suggestions = get_close_matches(missing_id, sample_ids, n=3, cutoff=0.4)
    body_lines = [f"No node with id [bold]{missing_id}[/bold]."]
    if suggestions:
        body_lines.append("Did you mean:")
        for sid in suggestions:
            body_lines.append(f"  [cyan]{sid}[/cyan]")
    else:
        body_lines.append("[dim]No close matches in the first 200 sampled ids.[/dim]")
    _console.print(Panel.fit("\n".join(body_lines), title="theogony node", border_style="red"))


def _print_node_panel(*, record: object, neighborhood: object) -> None:
    """Render the green/cyan panel for a found node."""
    from theogony.core.model import Constellation, KnowledgeNode

    assert isinstance(record, KnowledgeNode)
    assert isinstance(neighborhood, Constellation)
    ext_id_pairs = ", ".join(f"{k}={v}" for k, v in sorted(record.external_ids.items()))
    body_top = (
        f"[bold]{record.label}[/bold]\n"
        f"confidence={record.scores.confidence:.2f} · "
        f"resolution_tier={record.resolution_tier} · "
        f"external_ids: {ext_id_pairs or '(none)'}"
    )
    if not neighborhood.edges:
        body = body_top + "\n\n[dim]No depth-1 edges (above min_weight=0.3).[/dim]"
    else:
        edge_lines = []
        nodes_by_id = {n.id: n for n in neighborhood.nodes}
        for edge in neighborhood.edges:
            other_id = edge.target_id if edge.source_id == record.id else edge.source_id
            arrow = "→" if edge.source_id == record.id else "←"
            other = nodes_by_id.get(other_id)
            other_label = other.label if other is not None else "(unknown)"
            edge_lines.append(
                f"  {arrow} {other_id}  {other_label} "
                f"({edge.relation_type}) confidence={edge.confidence:.2f}"
            )
        body = (
            body_top
            + f"\n\n[dim]Neighbourhood (depth=1, {len(neighborhood.edges)} edges):[/dim]\n"
            + "\n".join(edge_lines)
        )
    seen_source_keys: set[tuple[str, str]] = set()
    deduped_source_labels: list[str] = []
    for sr in neighborhood.suggested_sources:
        key = (sr.source_type, sr.identifier or "")
        if key in seen_source_keys:
            continue
        seen_source_keys.add(key)
        deduped_source_labels.append(f"{sr.source_type}:{sr.identifier or '?'}")
    sources_line = (
        "Sources: " + ", ".join(deduped_source_labels)
        if deduped_source_labels
        else "Sources: (none)"
    )
    body = body + f"\n\n[dim]{sources_line}[/dim]"
    title = f"{record.id} — {record.node_type.value}"
    _console.print(Panel.fit(body, title=title, border_style="cyan"))


# ---------------------------------------------------------------------------
# `theogony resolve [<mention>] [--list]`  (E9)
# ---------------------------------------------------------------------------


@app.command()
def resolve(
    mention: str | None = typer.Argument(
        None, help="A pending mention's node id (omit with --list)."
    ),
    list_: bool = typer.Option(
        False, "--list", help="Print the queue of nodes pending manual resolution."
    ),
    last: int = typer.Option(20, "--last", min=1, help="Cap --list output at this many rows."),
    pick: str | None = typer.Option(
        None,
        "--pick",
        help=(
            "Wikidata Q-ID to assign. Use '--pick none' to confirm "
            "no candidate fits (clears flag, leaves at tier 0)."
        ),
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Apply --pick directly without prompts. Required for scripting / CI.",
    ),
    store_kind: str = typer.Option(
        "neo4j",
        "--store",
        help="Storage backend: 'neo4j' (default) or 'memory'.",
    ),
) -> None:
    """Plan §3.4 manual-resolution surface.

    Two modes:

    * ``theogony resolve --list`` prints the queue (most-recent first).
    * ``theogony resolve <node-id> --non-interactive --pick=Q1234``
      assigns a Wikidata Q-ID to the node, bumps its resolution_tier
      to 1, and clears manual_resolution_needed. Pass ``--pick none``
      to confirm "none of the candidates fit" (flag clears, tier
      stays at 0).

    Detective Mode (the ``--detective`` flag) is **not** part of E9
    per the brief; it lands in a separate etappe gated on PHX-0041.
    """
    if store_kind not in ("neo4j", "memory"):
        _console.print(f"[red]Unknown --store value: {store_kind!r}[/red]")
        raise typer.Exit(code=2)
    if list_:
        asyncio.run(_run_resolve_list(store_kind=store_kind, last=last))
        return
    if mention is None:
        _console.print("[red]Pass either a node id or --list. See `theogony resolve --help`.[/red]")
        raise typer.Exit(code=2)
    asyncio.run(
        _run_resolve_pick(
            node_id=mention,
            pick=pick,
            non_interactive=non_interactive,
            store_kind=store_kind,
        )
    )


async def _run_resolve_list(*, store_kind: str, last: int) -> None:
    settings = _load_settings()
    async with _open_store(settings, store_kind, settings.embedding.dim) as store:
        pending = await store.list_pending_resolution(limit=last)
    if not pending:
        _console.print(
            Panel.fit(
                "[green]Queue is empty.[/green] No nodes need manual resolution.",
                title="theogony resolve --list",
                border_style="green",
            )
        )
        return
    table = Table(show_header=True, header_style="bold", title="Pending manual resolution")
    table.add_column("node id")
    table.add_column("label")
    table.add_column("type")
    table.add_column("tier", justify="right")
    table.add_column("source")
    for n in pending:
        src = f"{n.source_ref.source_type}:{n.source_ref.identifier or '?'}"
        table.add_row(n.id, n.label, n.node_type.value, str(n.resolution_tier), src)
    _console.print(table)
    _console.print(
        "[dim]Resolve one: [/dim]"
        "[bold]theogony resolve <node-id> --non-interactive --pick=Q1234[/bold]"
    )


async def _run_resolve_pick(
    *,
    node_id: str,
    pick: str | None,
    non_interactive: bool,
    store_kind: str,
) -> None:
    settings = _load_settings()
    async with _open_store(settings, store_kind, settings.embedding.dim) as store:
        record = await store.get_node(node_id)
        if record is None:
            _console.print(
                Panel.fit(
                    f"[red]No node with id {node_id!r}.[/red]",
                    title="theogony resolve",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        chosen_qid = _decide_resolve_pick(record=record, pick=pick, non_interactive=non_interactive)
        if chosen_qid is None and pick is None:
            # Operator pressed Ctrl-C / aborted the prompt.
            _console.print("[yellow]aborted; no change written.[/yellow]")
            raise typer.Exit(code=1)

        # The CLI translates the sentinel "none" → wikidata_id=None for
        # the protocol call. The protocol semantic: empty wikidata_id
        # means "operator confirmed no fit" (clears flag, tier stays 0).
        protocol_qid = None if chosen_qid in ("none", "", None) else chosen_qid
        ok = await store.resolve_node(node_id, protocol_qid)

    if not ok:
        _console.print("[red]resolve_node returned False (id vanished concurrently).[/red]")
        raise typer.Exit(code=1)

    if protocol_qid:
        _console.print(
            Panel.fit(
                f"[green]Resolved[/green] {node_id} → wikidata={protocol_qid}\n"
                "tier bumped to 1; manual_resolution_needed cleared.",
                title="theogony resolve",
                border_style="green",
            )
        )
    else:
        _console.print(
            Panel.fit(
                f"[yellow]Confirmed no candidate fits for[/yellow] {node_id}.\n"
                "manual_resolution_needed cleared; tier remains 0.",
                title="theogony resolve",
                border_style="yellow",
            )
        )


def _decide_resolve_pick(*, record: object, pick: str | None, non_interactive: bool) -> str | None:
    """Return the chosen Q-ID (or 'none') or None if aborted.

    Centralises the interactive vs. scripted branching so the test
    surface is just this function's pure behaviour.
    """
    from theogony.core.model import KnowledgeNode

    assert isinstance(record, KnowledgeNode)
    if non_interactive:
        if pick is None:
            _console.print("[red]--non-interactive requires --pick=<Q-ID> (or --pick=none).[/red]")
            raise typer.Exit(code=2)
        return pick
    # Interactive mode. Show the existing record and ask.
    _console.print(
        Panel.fit(
            f"[bold]{record.label}[/bold] ({record.node_type.value})\n"
            f"current tier: {record.resolution_tier} · external_ids: "
            f"{', '.join(f'{k}={v}' for k, v in record.external_ids.items()) or '(none)'}",
            title=f"resolve {record.id}",
            border_style="cyan",
        )
    )
    answer: str = typer.prompt(
        "Wikidata Q-ID (or 'none' to confirm no candidate fits, or '' to abort)",
        default="",
        show_default=False,
    )
    if not answer:
        return None
    return answer


# ---------------------------------------------------------------------------
# `theogony serve`  (E9)
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address. Defaults to localhost (local-first principle).",
    ),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    reload: bool = typer.Option(
        False,
        "--reload",
        help=(
            "Uvicorn reload mode for dev iteration. Note: --reload bypasses "
            "the lifespan (well-known uvicorn limitation)."
        ),
    ),
) -> None:
    """Run the FastAPI app under uvicorn.

    Default binds to 127.0.0.1 (local-first; never 0.0.0.0). The
    embedder + Neo4j driver + audit log open eagerly during the
    lifespan startup — first request arrives with a fully warm
    pipeline. Cold-start budget: ~5–15 s on a fresh BGE / spaCy /
    Neo4j cache.
    """
    _console.print(
        f"[bold]Theogony API[/bold] → http://{host}:{port}  "
        f"(try: [cyan]curl localhost:{port}/health[/cyan])"
    )
    uvicorn.run(
        "theogony.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# `theogony seed`  — Import a pre-built Chronicle dump into the live store
# ---------------------------------------------------------------------------


_SOURCE_OPT = typer.Option(
    None,
    "--from",
    help=(
        "Path to a Chronicle dump (JSONL.gz). "
        "Default: the bundled pantheon_self seed shipped with the wheel."
    ),
)
_STORE_KIND_OPT = typer.Option(
    "neo4j",
    "--store",
    help="Storage backend: 'neo4j' (default) or 'memory' (for tests / CI).",
)
_INFO_ONLY_OPT = typer.Option(
    False,
    "--info",
    help="Print the dump's header (counts, embedding model) and exit; do not import.",
)


@app.command()
def seed(
    source: Path | None = _SOURCE_OPT,
    store_kind: str = _STORE_KIND_OPT,
    info_only: bool = _INFO_ONLY_OPT,
) -> None:
    """Import a Chronicle dump into the configured KnowledgeStore.

    The default source is the bundled ``pantheon_self`` dump — Theogony's
    own vision / strategy / doctrine layer (README, AGENTS.md,
    PHILOSOPHY, all docs/, all prompts/). After seeding, the very first
    ``theogony ask`` against a fresh install returns a cited answer
    drawn from the project's own self-description; an MCP-connected
    agent can immediately learn what Theogony is by asking Theogony.

    Use ``--from PATH`` to import a different dump (useful for federated
    chronicles or for testing a regenerated seed before publishing).
    """
    if store_kind not in ("neo4j", "memory"):
        _console.print(f"[red]Unknown --store value: {store_kind!r}[/red]")
        raise typer.Exit(code=2)

    from theogony.docs_ingest.dump import DumpError, dump_metadata, read_dump
    from theogony.seeds import PANTHEON_SELF_FILENAME, pantheon_self_dump_path

    dump_path = source or pantheon_self_dump_path()
    if not dump_path.exists():
        hint = (
            f"The bundled {PANTHEON_SELF_FILENAME} is missing from this install. "
            "Reinstall Theogony, or regenerate it with "
            "`python -m theogony.docs_ingest.regenerate`."
        )
        _console.print(
            Panel.fit(
                f"[red]Dump not found:[/red] {dump_path}\n\n[dim]{hint}[/dim]",
                title="theogony seed",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    try:
        header = dump_metadata(dump_path)
    except DumpError as exc:
        _console.print(
            Panel.fit(
                f"[red]Dump unreadable:[/red] {exc}",
                title="theogony seed",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc

    _print_seed_header(dump_path=dump_path, header=header)
    if info_only:
        return

    try:
        _, nodes, edges = read_dump(dump_path)
    except DumpError as exc:
        _console.print(
            Panel.fit(
                f"[red]Dump body unreadable:[/red] {exc}",
                title="theogony seed",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc

    asyncio.run(_run_seed(nodes=list(nodes), edges=list(edges), store_kind=store_kind))


def _print_seed_header(*, dump_path: Path, header: dict[str, object]) -> None:
    table = Table(show_header=True, header_style="bold", title="Dump header")
    table.add_column("Field")
    table.add_column("Value")
    for key in (
        "schema_version",
        "written_at",
        "node_count",
        "edge_count",
        "embedding_model_id",
        "embedding_dim",
    ):
        table.add_row(key, str(header.get(key)))
    _console.print(Panel.fit(f"[bold]Dump:[/bold] {dump_path}", border_style="cyan"))
    _console.print(table)


async def _run_seed(
    *,
    nodes: list[object],
    edges: list[object],
    store_kind: str,
) -> None:
    """Import nodes + edges into the chosen KnowledgeStore.

    ``nodes`` and ``edges`` are typed as ``object`` only to avoid an
    import cycle on the CLI's lazy boundary; they are
    :class:`KnowledgeNode` / :class:`KnowledgeEdge` instances at runtime.
    """
    from theogony.core.model import KnowledgeEdge, KnowledgeNode

    settings = _load_settings()
    node_objs: list[KnowledgeNode] = [n for n in nodes if isinstance(n, KnowledgeNode)]
    edge_objs: list[KnowledgeEdge] = [e for e in edges if isinstance(e, KnowledgeEdge)]
    async with _open_store(settings, store_kind, settings.embedding.dim) as store:
        node_ids = await store.batch_upsert_nodes(node_objs)
        await store.batch_upsert_edges(edge_objs)
    _console.print(
        Panel.fit(
            f"[green]Imported[/green] "
            f"{len(node_ids)} nodes / {len(edge_objs)} edges into {store_kind}.\n"
            f'[dim]Try: [/dim][bold]theogony ask "What is the Pantheon?"[/bold]',
            title="theogony seed",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# `theogony mcp`  — Model Context Protocol server (AI-first surface)
# ---------------------------------------------------------------------------


@app.command()
def mcp(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="MCP transport. Only 'stdio' is supported in Gen 1.",
    ),
) -> None:
    """Run Theogony as an MCP (Model Context Protocol) server.

    Exposes the Chronik to any MCP-compatible host: Claude Desktop,
    Cursor, ChatGPT Desktop, Codex, and any other MCP client. Tools
    registered: pantheon_ask, pantheon_node, pantheon_status,
    pantheon_reports_list, pantheon_reports_show.

    Requires the ``mcp`` extra: ``pip install -e ".[mcp]"``.

    Register with Claude Desktop in
    ``~/Library/Application Support/Claude/claude_desktop_config.json``::

        {
          "mcpServers": {
            "theogony": {
              "command": "theogony",
              "args": ["mcp"]
            }
          }
        }

    Cursor and other MCP-compatible hosts use the same shape under
    their respective config locations.
    """
    if transport != "stdio":
        _console.print(f"[red]Unknown --transport: {transport!r}. Only 'stdio' is supported.[/red]")
        raise typer.Exit(code=2)
    try:
        from theogony.mcp.server import serve_stdio
    except ImportError as exc:
        _console.print(
            Panel.fit(
                "[red]Theogony MCP server requires the `mcp` extra.[/red]\n\n"
                'Install: [bold]pip install -e ".[mcp]"[/bold]\n\n'
                f"[dim]{exc}[/dim]",
                title="theogony mcp",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc
    try:
        asyncio.run(serve_stdio())
    except RuntimeError as exc:
        _console.print(
            Panel.fit(
                f"[red]MCP server failed to start[/red]\n\n[dim]{exc}[/dim]",
                title="theogony mcp",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()
