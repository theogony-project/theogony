"""
Atomic RunReport writer (Plan §2.11.3).

One method, ``write(report)``: serialise the Pydantic model to JSON,
write to ``data/run_reports/{type}/{run_id}.json.tmp`` first, then
``os.replace()`` to the final path. ``os.replace`` is atomic on every
POSIX filesystem and on Windows for paths on the same volume — readers
either see the previous version or the new one, never a half-written
file.

Optional retention cap (Plan §5 Week 3): for the ``oneiros`` directory,
keep only the N most recent files. Implemented as a generic
``prune_to`` method so the Reviewer agent can apply it to other report
kinds later if it wants.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from theogony.config.logging import get_logger
from theogony.reporting.models import (
    ClusteringRunReport,
    IngestRunReport,
    OneirosTickReport,
    QueryRunReport,
    RunReportBase,
)

log = get_logger("reporting.writer")

ReportType = (
    type[IngestRunReport]
    | type[QueryRunReport]
    | type[OneirosTickReport]
    | type[ClusteringRunReport]
)


class RunReportWriter:
    """Atomic JSON writer for the three RunReport kinds.

    Parameters
    ----------
    base_dir:
        Root directory under which the per-type subdirectories live.
        Typically ``settings.run_reports_dir``. Created on first
        write; existing directories are reused.
    indent:
        JSON indent passed to ``model_dump_json``. Default 2 (matches
        Plan §2.11.3: "model_dump_json(indent=2) produces a
        human-readable artefact that cat and jq both handle").
    """

    def __init__(self, base_dir: Path, indent: int = 2) -> None:
        self._base_dir = Path(base_dir)
        self._indent = indent

    def directory_for(self, report_type: str) -> Path:
        """Return ``{base_dir}/{report_type}/``, creating it if needed."""
        d = self._base_dir / report_type
        d.mkdir(parents=True, exist_ok=True)
        return d

    def path_for(self, report: RunReportBase) -> Path:
        """Final on-disk path for a given report."""
        return self.directory_for(report.report_type) / f"{report.run_id}.json"

    def write(self, report: RunReportBase) -> Path:
        """Serialise + atomic-replace. Returns the final path on success.

        Discipline (Plan §2.11.4): never abort on a "poor" verdict, never
        retry, never page anyone. Just write the report. Decisions about
        what to do with a poor verdict belong to the (future) Reviewer
        agent, not the writer.
        """
        final = self.path_for(report)
        tmp = final.with_suffix(".json.tmp")
        # Write payload first under .tmp; only after a clean write do we
        # rename to the final path. A crash mid-write leaves the .tmp
        # behind but the final path is never half-written.
        payload = report.model_dump_json(indent=self._indent)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, final)
        log.debug(
            "wrote run report type=%s run_id=%s path=%s",
            report.report_type,
            report.run_id,
            final,
        )
        return final

    def prune_to(self, report_type: str, keep: int) -> int:
        """Keep only the ``keep`` most recent reports of a given type.

        ULIDs sort lexicographically by timestamp prefix, so sorting
        filenames descending and dropping after ``keep`` is correct
        without touching mtimes (which would couple us to the
        filesystem's clock).

        Returns the number of files removed. Robust to non-ULID
        filenames in the directory: stray ``.tmp`` from a crashed
        write or unrelated files are left alone.
        """
        d = self.directory_for(report_type)
        candidates = sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
            key=lambda p: p.stem,  # ULID prefix sorts chronologically
            reverse=True,
        )
        to_remove = candidates[keep:]
        for stale in to_remove:
            try:
                stale.unlink()
            except OSError as exc:  # pragma: no cover - filesystem race / permission
                log.warning("failed to prune stale report %s: %s", stale, exc)
        return len(to_remove)

    def most_recent(self, report_type: str) -> RunReportBase | None:
        """Return the newest on-disk report of ``report_type``, or ``None``."""
        d = self.directory_for(report_type)
        candidates = sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix == ".json"),
            key=lambda p: p.stem,
            reverse=True,
        )
        if not candidates:
            return None
        raw = json.loads(candidates[0].read_text(encoding="utf-8"))
        rt = raw.get("report_type")
        if rt == "ingest":
            return IngestRunReport.model_validate(raw)
        if rt == "query":
            return QueryRunReport.model_validate(raw)
        if rt == "oneiros":
            return OneirosTickReport.model_validate(raw)
        if rt == "clustering":
            return ClusteringRunReport.model_validate(raw)
        return None
