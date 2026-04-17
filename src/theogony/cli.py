"""
Typer CLI entry point (Plan §2.8 + §3.7).

Etappe C ships the **operational** subset of the seven-command CLI:
``status`` (read-only health snapshot — the first command a new
contributor runs after cloning), ``reports list``, and
``reports show``. The data-flow commands (``ingest``, ``ask``,
``node``, ``serve``, ``resolve``) need pipelines that don't exist
yet; they land in Etappe D and beyond.

The module satisfies the ``[project.scripts]`` declaration in
pyproject.toml (``theogony = "theogony.cli:app"``), which has pointed
at this module since the project was scaffolded; this commit closes
that gap noted in Plan §3.7.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from theogony import __version__
from theogony.config import Settings, setup_logging

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


if __name__ == "__main__":  # pragma: no cover
    app()
