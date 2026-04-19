"""
Typer CLI entry point (Plan §2.8 + §3.7).

Commands available in this module:

- ``status``         — read-only health snapshot (E-C)
- ``reports list``   — list recent run reports (E-C)
- ``reports show``   — pretty-print one report's full JSON (E-C)
- ``ingest <id>``    — full end-to-end ingest of one Project
  Gutenberg book; runs acquisition + extraction + embedding +
  store + report persistence (E6)

The remaining Plan-§3.7 commands (``ask``, ``node``, ``resolve``,
``serve``) need retrieval / serve pipelines that are not yet
implemented; they land in E7+.

Module satisfies the ``[project.scripts]`` declaration in
pyproject.toml (``theogony = "theogony.cli:app"``).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from theogony import __version__
from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.factory import build_llm_from_settings
from theogony.config import Settings, setup_logging
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline, IngestionResult
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataClient
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore

if TYPE_CHECKING:
    from theogony.acquisition.base import RawContent

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
    verdict_style = {
        "good": "green",
        "partial": "yellow",
        "poor": "red",
        "failed": "red",
    }
    for run_id, rtype, verdict, status_val, duration in rows:
        style = verdict_style.get(verdict, "white")
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
) -> None:
    """Ingest a Project Gutenberg book end-to-end into the in-memory store.

    Pipeline (Plan §2.5): acquire → clean → sentencize → NER →
    book context → resolve → relations → embed → store. The
    IngestRunReport is persisted under ``settings.run_reports_dir/ingest/``;
    every LLM call is logged under ``settings.data_dir/audit.sqlite``.

    The InMemoryKnowledgeStore that this command uses is process-local —
    nodes and edges live only for the duration of the call. The
    Neo4jKnowledgeStore (E7) will replace it for persistence.
    """
    asyncio.run(
        _run_ingest(
            book_id=book_id,
            ner_sentence_limit=sentences,
            max_relation_sentences=relations,
            include_book_context=not no_book_context,
            include_relations=not no_relations,
            include_embedder=not no_embed,
        )
    )


async def _run_ingest(
    *,
    book_id: str,
    ner_sentence_limit: int | None,
    max_relation_sentences: int | None,
    include_book_context: bool,
    include_relations: bool,
    include_embedder: bool,
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

    with ExtractionAuditLog(audit_path) as audit:
        async with WikidataClient() as wd_client:
            resolver = EntityResolver(client=wd_client, llm=llm, audit_log=audit)
            book_context_extractor: BookContextExtractor | None = (
                BookContextExtractor(llm=llm, audit_log=audit) if include_book_context else None
            )
            relation_extractor: RelationExtractor | None = (
                RelationExtractor(llm=llm, audit_log=audit) if include_relations else None
            )
            store = InMemoryKnowledgeStore()
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
    )


def _print_ingest_summary(
    *,
    result: IngestionResult,
    raw_content: RawContent,
    report_path: Path,
    audit_rows: int,
    audit_cost: float,
) -> None:
    """Render a Rich panel + summary table for the completed ingest."""
    report = result.report
    verdict_styles = {
        "good": "green",
        "partial": "yellow",
        "poor": "red",
        "failed": "red",
    }
    verdict_style = verdict_styles.get(report.verdict, "white")

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
    table.add_row("audit rows", str(audit_rows))
    table.add_row("LLM cost (EUR)", f"{audit_cost:.5f}")
    table.add_row("report file", str(report_path))

    _console.print(table)
    _console.print(
        f"[dim]To re-read this report: [/dim][bold]theogony reports show {report.run_id}[/bold]"
    )


if __name__ == "__main__":  # pragma: no cover
    app()
