"""
MNLM PoC — resumable Kadmos crawl coordinator.

Reads corpus_200.json, tracks progress in crawl_log.jsonl, and processes
articles in batches with graceful abort support.

Resume contract:
- Before crawling an article, check if its title appears in crawl_log.jsonl
  with a non-failed verdict (completed/partial). If found, skip it.
- After each article completes (success or failure), append to crawl_log.jsonl.
- On Ctrl+C / SIGINT: finish the current article, then exit.

See mnlm_poc_brief.md §4 (crawl strategy) and §5 (Track A).
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Column, Table

from theogony.config.logging import get_logger
from theogony.kadmos.reader import KadmosReader
from theogony.reporting.models import new_run_id

if __name__ == "__main__":
    # Safety: crawl must be run via ``theogony kadmos crawl``, not directly.
    raise SystemExit("Run via theogony kadmos crawl")

log = get_logger("kadmos.crawl")

# ---------------------------------------------------------------------------
# Crawl artifacts paths
# ---------------------------------------------------------------------------

CORPUS_PATH = Path("docs/research/mnlm/poc/corpus_200.json")
CRAWL_LOG_PATH = Path("docs/research/mnlm/poc/crawl_log.jsonl")
MESH_INPUTS_DIR = Path("docs/research/mnlm/poc/mesh_inputs")
DEFAULT_BATCH_SIZE = 20

# ---------------------------------------------------------------------------
# Per-article crawl result (written as one JSON line to crawl_log.jsonl)
# ---------------------------------------------------------------------------

CrawlVerdict = Literal["completed", "partial", "failed"]


def _article_slug(title: str) -> str:
    """Convert an article title to a filesystem-safe slug."""
    return (
        title.replace(" ", "_")
        .replace("/", "_")
        .replace("'", "")
        .replace("\u2013", "-")
        .lower()[:80]
    )


class CrawlCoordinator:
    """Resumable crawl coordinator for the 200-article MNLM PoC corpus.

    Usage::

        coordinator = CrawlCoordinator(llm_provider, embedder)
        await coordinator.run()
    """

    def __init__(
        self,
        llm_provider: object,
        embedder: object,
        *,
        corpus_path: Path = CORPUS_PATH,
        crawl_log_path: Path = CRAWL_LOG_PATH,
        mesh_inputs_dir: Path = MESH_INPUTS_DIR,
        kadmos_data_dir: Path | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_failures: int = 10,
    ) -> None:
        self._llm = llm_provider
        self._embedder = embedder
        self._corpus_path = corpus_path
        self._crawl_log_path = crawl_log_path
        self._mesh_inputs_dir = mesh_inputs_dir
        self._kadmos_data_dir = kadmos_data_dir or Path("data/kadmos")
        self._batch_size = batch_size
        self._max_failures = max_failures

        self._kadmos_data_dir.mkdir(parents=True, exist_ok=True)
        self._mesh_inputs_dir.mkdir(parents=True, exist_ok=True)

        # State
        self._consecutive_failures = 0
        self._total_articles = 0
        self._processed = 0
        self._skipped = 0
        self._failed = 0
        self._partial = 0
        self._total_cost_eur = 0.0
        self._total_duration_s = 0.0
        self._shutdown_requested = False

        # Install SIGINT handler for graceful abort
        self._original_sigint = signal.getsignal(signal.SIGINT)

        # Progress tracking (rich)
        self._console = Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[cyan]{task.completed}/{task.total}[/cyan]"),
            TimeElapsedColumn(),
        )
        self._task_id: int | None = None

        # Per-domain progress
        self._domain_counts: dict[str, int] = {}
        self._domain_progress: dict[str, tuple[int, int]] = {}  # done, total

    def _load_corpus(self) -> list[dict]:
        """Load the 200-article corpus from the locked JSON."""
        if not self._corpus_path.exists():
            raise FileNotFoundError(
                f"Corpus file not found at {self._corpus_path}. "
                "Run scripts/build_mnlm_corpus.py first."
            )
        with open(self._corpus_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_crawl_log(self) -> dict[str, dict]:
        """Load the crawl log, returning {title: entry} for already-processed articles.

        The crawl_log.jsonl has one JSON line per article:
        {"title": "...", "verdict": "...", "concept_count": ..., "edge_count": ...,
         "duration_s": ..., "cost_eur": ..., "session_id": "..."}
        """
        if not self._crawl_log_path.exists():
            return {}

        entries: dict[str, dict] = {}
        with open(self._crawl_log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    title = entry.get("title")
                    if title:
                        entries[title] = entry
                except json.JSONDecodeError:
                    log.warning("crawl: skipping unparseable log line: %s", line[:80])
        return entries

    def _append_to_crawl_log(self, entry: dict) -> None:
        """Append one line to the crawl log (atomic append, no read required)."""
        with open(self._crawl_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Also flush to disk so a crash doesn't lose the last entry
        self._crawl_log_path.exists()  # no-op, forces stat cache

    def _setup_signal_handler(self) -> None:
        """Install a SIGINT handler that requests graceful shutdown."""

        def _handler(signum: int, frame: object) -> None:
            if self._shutdown_requested:
                self._console.print(
                    "\n[bold red]Second SIGINT — forcing immediate exit.[/bold red]"
                )
                sys.exit(1)
            self._shutdown_requested = True
            self._console.print(
                "\n\n[bold yellow]SIGINT received. Finishing current article, then stopping..."
                " Press Ctrl+C again to force exit.[/bold yellow]\n"
            )

        signal.signal(signal.SIGINT, _handler)

    def _restore_signal_handler(self) -> None:
        signal.signal(signal.SIGINT, self._original_sigint)

    def _build_domain_table(self) -> Table:
        """Build a Rich Table showing per-domain progress."""
        table = Table(
            Column("Domain", style="cyan"),
            Column("Done", justify="right"),
            Column("Total", justify="right"),
            Column("Progress"),
            Column("Failed", justify="right", style="red"),
        )
        for domain, (done, total) in sorted(self._domain_progress.items()):
            ratio = done / total if total > 0 else 0
            bar_len = 20
            filled = int(ratio * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            fail_count = sum(
                1
                for e in self._load_crawl_log().values()
                if e.get("domain") == domain and e.get("verdict") == "failed"
            )
            table.add_row(domain, str(done), str(total), bar, str(fail_count))
        return table

    async def run(self) -> None:
        """Run the full crawl with graceful abort and live progress."""
        corpus = self._load_corpus()
        completed = self._load_crawl_log()
        self._total_articles = len(corpus)

        # Build domain counts
        for article in corpus:
            domain = article.get("domain", "unknown")
            self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1
            self._domain_progress.setdefault(domain, (0, self._domain_counts[domain]))

        # Compute per-domain progress from the log
        for _title, entry in completed.items():
            domain = entry.get("domain")
            if domain and domain in self._domain_progress:
                done, total = self._domain_progress[domain]
                self._domain_progress[domain] = (done + 1, total)

        # Count how many are already done
        already_done = sum(
            1
            for article in corpus
            if article["title"] in completed
            and completed[article["title"]].get("verdict") != "failed"
        )
        self._skipped = already_done

        if already_done == len(corpus):
            self._console.print(
                Panel.fit(
                    f"[green]All {len(corpus)} articles already processed.[/green]\n"
                    f"[dim]Nothing to do — crawl is complete.[/dim]",
                    title="Crawl complete",
                    border_style="green",
                )
            )
            return

        self._console.print(
            Panel.fit(
                f"[bold]Resumable MNLM PoC crawl[/bold]\n"
                f"  Total articles:  [cyan]{len(corpus)}[/cyan]\n"
                f"  Already done:    [green]{already_done}[/green] (skipped)\n"
                f"  Remaining:       [yellow]{len(corpus) - already_done}[/yellow]\n"
                f"  Batch size:      [cyan]{self._batch_size}[/cyan]\n"
                f"  Max failures:    [cyan]{self._max_failures}[/cyan]\n"
                f"  Log path:        [dim]{self._crawl_log_path}[/dim]",
                title="Crawl start",
                border_style="cyan",
            )
        )

        self._setup_signal_handler()
        self._task_id = self._progress.add_task("Crawling", total=max(1, len(corpus)))

        try:
            with Live(self._build_layout(), console=self._console, refresh_per_second=4) as live:
                for _batch_idx, batch in enumerate(self._iter_batches(corpus)):
                    if self._shutdown_requested:
                        self._console.print(
                            "\n[yellow]Shutdown requested — stopping after current batch.[/yellow]"
                        )
                        break

                    batch_lines: list[str] = []
                    for article in batch:
                        if self._shutdown_requested:
                            break

                        processed_so_far = self._processed + self._skipped

                        title = article["title"]
                        domain = article.get("domain", "unknown")
                        url = article.get("url", "")

                        # Check if already completed
                        if title in completed:
                            existing = completed[title]
                            if existing.get("verdict") != "failed":
                                self._progress.update(
                                    self._task_id,
                                    advance=1,
                                )
                                batch_lines.append(f"[dim]{title} — already done, skipped[/dim]")
                                continue
                            else:
                                # Previously failed — retry
                                batch_lines.append(
                                    f"[yellow]{title} — retrying after previous failure[/yellow]"
                                )

                        # Process the article
                        log.info(
                            "crawl: [%d/%d] starting %s (domain=%s)",
                            processed_so_far + 1,
                            self._total_articles,
                            title,
                            domain,
                        )
                        result = await self._process_one_article(
                            title=title,
                            domain=domain,
                            url=url,
                        )
                        log.info(
                            "crawl: [%d/%d] done %s — %s, %d concepts, %d edges, %.0fs, €%.4f",
                            processed_so_far + 1,
                            self._total_articles,
                            title,
                            result.verdict,
                            result.concept_count,
                            result.edge_count,
                            result.duration_s,
                            result.cost_eur,
                        )

                        # Every 5 articles, emit a progress summary line
                        if processed_so_far > 0 and processed_so_far % 5 == 0:
                            self._log_progress_summary()

                        # Record in crawl log
                        log_entry = {
                            "title": title,
                            "domain": domain,
                            "url": url,
                            "verdict": result.verdict,
                            "concept_count": result.concept_count,
                            "edge_count": result.edge_count,
                            "duration_s": round(result.duration_s, 1),
                            "cost_eur": round(result.cost_eur, 6),
                            "session_id": result.session_id,
                        }
                        self._append_to_crawl_log(log_entry)

                        # Also update the in-memory completed dict
                        completed[title] = log_entry

                        # Update domain progress
                        done, total = self._domain_progress.get(domain, (0, 1))
                        self._domain_progress[domain] = (done + 1, total)

                        # Update global counters
                        self._processed += 1
                        self._total_cost_eur += result.cost_eur
                        self._total_duration_s += result.duration_s

                        if result.verdict == "failed":
                            self._failed += 1
                            self._consecutive_failures += 1
                        else:
                            self._consecutive_failures = 0
                            if result.verdict == "partial":
                                self._partial += 1

                        self._progress.update(self._task_id, advance=1)

                        # Check max consecutive failures
                        if self._consecutive_failures >= self._max_failures:
                            self._console.print(
                                f"\n[bold red]Stopping: {self._max_failures} consecutive "
                                f"failures.[/bold red]"
                            )
                            batch_lines.append(
                                f"[red]{title} — {result.verdict} "
                                f"({self._consecutive_failures}/"
                                f"{self._max_failures} consecutive)[/red]"
                            )
                            live.update(self._build_layout(batch_lines))
                            await asyncio.sleep(0.1)  # let live render
                            return

                        # Build status line
                        verdict_style = {
                            "completed": "green",
                            "partial": "yellow",
                            "failed": "red",
                        }.get(result.verdict, "white")
                        batch_lines.append(
                            f"[{verdict_style}]{title}[/{verdict_style}] — "
                            f"{result.verdict}, "
                            f"{result.concept_count} concepts, "
                            f"{result.edge_count} edges, "
                            f"{result.duration_s:.0f}s, "
                            f"€{result.cost_eur:.4f}"
                        )

                    live.update(self._build_layout(batch_lines))
                    await asyncio.sleep(0.1)  # let live render

                    # Brief pause between batches to let rate limits settle
                    if not self._shutdown_requested:
                        await asyncio.sleep(1)

        finally:
            self._restore_signal_handler()
            self._print_summary()

    def _build_layout(self, batch_lines: list[str] | None = None) -> Table:
        """Build the Rich layout for Live display."""
        layout = Table.grid(padding=1)
        layout.add_column()

        # Summary
        remaining = self._total_articles - self._processed - self._skipped
        summary = (
            f"[bold]Processed:[/bold] {self._processed}   "
            f"[bold]Skipped:[/bold] {self._skipped}   "
            f"[bold]Remaining:[/bold] {remaining}   "
            f"[bold]Failed:[/bold] [red]{self._failed}[/red]   "
            f"[bold]Cost:[/bold] €{self._total_cost_eur:.4f}   "
            f"[bold]Duration:[/bold] {self._total_duration_s:.0f}s"
        )
        layout.add_row(Panel(summary, title="Overall", border_style="blue"))

        # Domain table
        layout.add_row(Panel(self._build_domain_table(), title="Per domain"))

        # Progress bar
        self._progress.update(
            self._task_id, total=(self._total_articles if self._total_articles > 0 else 1)
        )
        layout.add_row(Panel(self._progress, title="Progress"))

        # Last batch results
        if batch_lines:
            batch_text = "\n".join(batch_lines)
            layout.add_row(
                Panel(
                    batch_text,
                    title=f"Last batch ({len(batch_lines)} articles)",
                    border_style="dim",
                )
            )

        return layout

    def _print_summary(self) -> None:
        """Print final summary after crawl completes or is aborted."""
        style = "green" if self._failed == 0 else "yellow"
        self._console.print(
            Panel.fit(
                f"[bold]Crawl finished[/bold]\n"
                f"  Processed:  [cyan]{self._processed}[/cyan]\n"
                f"  Skipped:    [green]{self._skipped}[/green]\n"
                f"  Partial:    [yellow]{self._partial}[/yellow]\n"
                f"  Failed:     [red]{self._failed}[/red]\n"
                f"  Total cost: €{self._total_cost_eur:.4f}\n"
                f"  Wall clock: {self._total_duration_s:.0f}s\n"
                f"  Log:        [dim]{self._crawl_log_path}[/dim]",
                title="Crawl summary",
                border_style=style,
            )
        )
        if self._failed > 0:
            self._console.print(
                f"[yellow]{self._failed} article(s) failed. "
                f"Run again to retry failed articles.[/yellow]"
            )

    def _log_progress_summary(self) -> None:
        """Emit a one-line progress summary at INFO level."""
        remaining = self._total_articles - self._processed - self._skipped
        domain_parts = []
        for domain, (done, total) in sorted(self._domain_progress.items()):
            domain_parts.append(f"{domain}={done}/{total}")
        log.info(
            "crawl: PROGRESS processed=%d skipped=%d failed=%d "
            "partial=%d remaining=%d cost=€%.4f domains=[%s]",
            self._processed,
            self._skipped,
            self._failed,
            self._partial,
            remaining,
            self._total_cost_eur,
            " ".join(domain_parts),
        )

    def _iter_batches(self, corpus: list[dict]) -> list[list[dict]]:
        """Split the corpus into domain-sequential batches."""
        # Group by domain (preserving order from corpus)
        domains: dict[str, list[dict]] = {}
        for article in corpus:
            domain = article.get("domain", "unknown")
            domains.setdefault(domain, []).append(article)

        # Yield batches: process one domain at a time, batch_size per batch
        batches: list[list[dict]] = []
        for _domain, articles in domains.items():
            for i in range(0, len(articles), self._batch_size):
                batches.append(articles[i : i + self._batch_size])

        return batches

    async def _process_one_article(
        self,
        title: str,
        domain: str,
        url: str,
    ) -> CrawlArticleResult:
        """Run KadmosReader.read() on one article and return the result.

        Uses a fresh LanceDB session directory per article so concurrent or
        restarting crawls never interfere.
        """
        log.info("crawl: processing article title=%s domain=%s", title, domain)

        session_id = new_run_id()
        lancedb_dir = self._kadmos_data_dir / "lancedb" / session_id

        reader = KadmosReader(
            llm=self._llm,
            embedder=self._embedder,
            max_sections=None,
            db_path=str(lancedb_dir),
        )

        start_time = time.monotonic()

        try:
            annotated, report = await reader.read(url)
        except asyncio.CancelledError:
            return CrawlArticleResult(
                title=title,
                verdict="failed",
                concept_count=0,
                edge_count=0,
                duration_s=time.monotonic() - start_time,
                cost_eur=0.0,
                session_id=session_id,
                error="Cancelled",
            )
        except Exception as exc:
            log.warning("crawl: article failed title=%s error=%s", title, exc)
            return CrawlArticleResult(
                title=title,
                verdict="failed",
                concept_count=0,
                edge_count=0,
                duration_s=time.monotonic() - start_time,
                cost_eur=0.0,
                session_id=session_id,
                error=str(exc)[:200],
            )

        elapsed = time.monotonic() - start_time

        # Persist AnnotatedReading JSON
        ar_dir = self._kadmos_data_dir / "readings"
        ar_dir.mkdir(parents=True, exist_ok=True)
        ar_path = ar_dir / f"{session_id}.json"
        ar_path.write_text(annotated.model_dump_json(indent=2), encoding="utf-8")

        # Crosslink into the global Chronicle
        try:
            from theogony.kadmos.crosslink import ChronikCrosslinker

            # Collect synthesis nodes (meta-concepts) first, then concepts
            crosslink_nodes: list[dict] = []
            for synth in annotated.final_syntheses:
                emb = list(self._embedder.embed(synth.label + ": " + synth.description))
                emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))
                crosslink_nodes.append(
                    {
                        "id": f"SYNTH-{synth.id[:20]}",
                        "label": synth.label,
                        "embedding": emb_vec,
                        "node_type": "synthesis",
                        "source_anchor": f"{annotated.source_url}#synthesis-{synth.synthesis_level}",
                    }
                )
            for concept in annotated.final_active_concepts:
                text = concept.label
                if concept.description:
                    text += " " + concept.description
                emb = list(self._embedder.embed(text))
                emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))
                crosslink_nodes.append(
                    {
                        "id": f"CONC-{concept.id[:20]}",
                        "label": concept.label,
                        "embedding": emb_vec,
                        "node_type": "concept",
                        "source_anchor": f"{annotated.source_url}#step-{concept.step_created}",
                    }
                )

            crosslinker = ChronikCrosslinker(
                db_path=self._kadmos_data_dir / "chronicle",
            )
            crosslink_result = crosslinker.ingest_and_link(
                embedder=self._embedder,
                new_nodes=crosslink_nodes,
                new_edges=[],
                source_domain=domain,
            )
            log.info(
                "crawl: crosslink session=%s %d nodes written, %d crosslinks",
                session_id,
                crosslink_result["nodes_written"],
                crosslink_result["crosslinks_created"],
            )
        except Exception as exc:
            log.warning("crawl: crosslink failed session=%s error=%s", session_id, exc)

        # Export MeshInput (post-embedding pass, §7 amendment)
        try:
            from theogony.kadmos.mesh_export import annotated_reading_to_mesh_input

            mesh_input = annotated_reading_to_mesh_input(
                annotated,
                self._embedder,
                role="generic",
                run_id=session_id,
            )
            mi_dir = self._mesh_inputs_dir
            mi_dir.mkdir(parents=True, exist_ok=True)
            mi_path = mi_dir / f"{session_id}.json"
            mi_path.write_text(mesh_input.model_dump_json(indent=2), encoding="utf-8")
            log.info(
                "crawl: mesh_input exported session=%s path=%s (%d nodes, %d edges)",
                session_id,
                mi_path,
                len(mesh_input.nodes),
                len(mesh_input.edges),
            )
        except Exception as exc:
            log.warning("crawl: mesh_input export failed session=%s error=%s", session_id, exc)

        # Map KadmosRunReport status to crawl verdict
        report_verdict = report.status  # "completed", "partial", "failed"

        return CrawlArticleResult(
            title=title,
            verdict=report_verdict,
            concept_count=report.total_concepts,
            edge_count=report.total_edges,
            duration_s=elapsed,
            cost_eur=report.total_llm_cost_eur,
            session_id=session_id,
            error=None,
        )


# ---------------------------------------------------------------------------
# Standalone status summary (used by ``theogony kadmos crawl-status``)
# ---------------------------------------------------------------------------


def print_crawl_status(
    *,
    corpus_path: Path = CORPUS_PATH,
    crawl_log_path: Path = CRAWL_LOG_PATH,
) -> None:
    """Print a human-readable crawl progress summary to stdout.

    Reads the locked corpus and the append-only crawl log, then computes
    per-domain and overall progress.  Safe to call while a crawl is running.
    """
    if not corpus_path.exists():
        print(f"[!] Corpus not found: {corpus_path}")
        return

    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    entries: dict[str, dict] = {}
    if crawl_log_path.exists():
        with open(crawl_log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("title"):
                        # Keep only the latest entry per title
                        entries[entry["title"]] = entry
                except json.JSONDecodeError:
                    pass

    # Per-domain counts
    domain_total: dict[str, int] = {}
    domain_done: dict[str, int] = {}
    domain_failed: dict[str, int] = {}
    total_cost = 0.0
    total_duration = 0.0
    total_concepts = 0

    for article in corpus:
        domain = article.get("domain", "unknown")
        domain_total[domain] = domain_total.get(domain, 0) + 1

        entry = entries.get(article["title"])
        if entry:
            v = entry.get("verdict", "")
            if v != "failed":
                domain_done[domain] = domain_done.get(domain, 0) + 1
                total_cost += entry.get("cost_eur", 0)
                total_duration += entry.get("duration_s", 0)
                total_concepts += entry.get("concept_count", 0)
            if v == "failed":
                domain_failed[domain] = domain_failed.get(domain, 0) + 1

    done_total = sum(domain_done.values())
    failed_total = sum(domain_failed.values())
    remaining = len(corpus) - done_total

    # Build output
    lines: list[str] = []
    sep = "-" * 60
    lines.append("")
    lines.append("MNLM PoC Crawl Status")
    lines.append(sep)

    for domain in sorted(domain_total):
        total = domain_total[domain]
        done = domain_done.get(domain, 0)
        failed = domain_failed.get(domain, 0)
        pct = 100.0 * done / total if total > 0 else 0
        bar_len = 20
        filled = int(bar_len * done / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        flag = f"  {failed} failed" if failed else ""
        flag = f"\033[31m{flag}\033[0m" if failed else flag
        lines.append(f"  {domain:20s} {bar}  {done:3d}/{total:<3d} ({pct:5.1f}%){flag}")

    lines.append(sep)
    lines.append(
        f"  TOTAL       {done_total:3d}/{len(corpus):<3d} articles  "
        f"  failed={failed_total}  remaining={remaining}"
    )
    lines.append(f"  Concepts:   {total_concepts}")
    lines.append(f"  Cost:       \u20ac{total_cost:.4f}")
    lines.append(f"  Duration:   {total_duration:.0f}s")

    if failed_total:
        lines.append(sep)
        lines.append("  Failed articles (will be retried on next run):")
        for article in corpus:
            entry = entries.get(article["title"])
            if entry and entry.get("verdict") == "failed":
                lines.append(f"    - {article['title']}")

    lines.append("")
    print("\n".join(lines))


@dataclass
class CrawlArticleResult:
    """Result of crawling a single article."""

    title: str
    verdict: CrawlVerdict
    concept_count: int
    edge_count: int
    duration_s: float
    cost_eur: float
    session_id: str
    error: str | None = None
