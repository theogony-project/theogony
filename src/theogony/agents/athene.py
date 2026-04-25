"""Athene v0.1 — post-hoc ingest-report verifier (Living Demo W14)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from theogony.config.settings import AtheneSettings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.finding import Finding, flag_edges_for_finding
from theogony.curiosity.verification_pool import PoolEntry, VerificationPool
from theogony.reporting.models import IngestRunReport


class AtheneRunSummary(BaseModel):
    """Outcome of a single :meth:`AtheneVerifier.run_once` pass."""

    model_config = ConfigDict(extra="forbid")

    sampled_count: int = 0
    findings_written: int = 0
    pool_entries_marked: int = 0
    skipped_reason: str | None = None


class AtheneVerifier:
    """Samples the verification pool and writes Finding nodes from ingest reports."""

    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        settings: AtheneSettings,
        run_reports_dir: Path,
    ) -> None:
        self._store = store
        self._pool = pool
        self._settings = settings
        self._run_reports_dir = run_reports_dir

    def _load_ingest_report(self, ingest_run_id: str) -> IngestRunReport | None:
        path = self._run_reports_dir / "ingest" / f"{ingest_run_id}.json"
        if not path.is_file():
            return None
        return IngestRunReport.model_validate_json(path.read_text(encoding="utf-8"))

    def _finding_for_entry(self, entry: PoolEntry, report: IngestRunReport | None) -> Finding:
        pool_id = entry.entry_id
        ingest_id = entry.ingest_run_id

        if ingest_id is None or report is None:
            return Finding(
                finding_type="ingest_report_missing",
                severity="medium",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[f"missing ingest report for pool_entry_id={pool_id}"],
            )

        status = report.status
        verdict = report.verdict
        reasoning = report.verdict_reasoning or ""

        if status == "failed" or verdict == "failed":
            return Finding(
                finding_type="ingest_failed",
                severity="high",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[
                    f"status={status}",
                    f"verdict={verdict}",
                    f"verdict_reasoning={reasoning}",
                ],
            )

        if status == "partial" or verdict in {"partial", "poor"}:
            return Finding(
                finding_type="ingest_partial",
                severity="medium",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[
                    f"status={status}",
                    f"verdict={verdict}",
                    f"verdict_reasoning={reasoning}",
                ],
            )

        qf = report.quality_flags
        low_thr = self._settings.low_resolution_ratio_threshold
        if qf.low_tier_ratio >= low_thr:
            return Finding(
                finding_type="low_resolution_quality",
                severity="low",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[
                    f"low_tier_ratio={qf.low_tier_ratio:.4f}",
                    f"threshold={low_thr:.4f}",
                ],
            )

        schema_thr = self._settings.schema_violation_rate_threshold
        if qf.schema_violation_rate >= schema_thr:
            return Finding(
                finding_type="high_schema_violation_rate",
                severity="medium",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[
                    f"schema_violation_rate={qf.schema_violation_rate:.4f}",
                    f"threshold={schema_thr:.4f}",
                ],
            )

        parse_thr = self._settings.parse_error_rate_threshold
        if qf.parse_error_rate >= parse_thr:
            return Finding(
                finding_type="high_parse_error_rate",
                severity="medium",
                pool_entry_id=pool_id,
                ingest_run_id=ingest_id,
                target_node_ids=list(entry.target_node_ids),
                evidence=[
                    f"parse_error_rate={qf.parse_error_rate:.4f}",
                    f"threshold={parse_thr:.4f}",
                ],
            )

        return Finding(
            finding_type="no_issue_observed",
            severity="info",
            pool_entry_id=pool_id,
            ingest_run_id=ingest_id,
            target_node_ids=list(entry.target_node_ids),
            evidence=[
                "Athene sampled this pool entry and observed no structural issue "
                "in the ingest report."
            ],
        )

    async def run_once(self, *, seed: int | None = None) -> AtheneRunSummary:
        if not self._settings.enabled:
            return AtheneRunSummary(skipped_reason="athene disabled")

        sampled = self._pool.sample_for_athene(
            sample_rate=self._settings.sample_rate,
            max_entries=self._settings.max_entries_per_pass,
            min_entries=self._settings.min_entries_per_pass,
            seed=seed,
        )
        if not sampled:
            return AtheneRunSummary()

        findings_written = 0
        pool_marked = 0

        for entry in sampled:
            report = self._load_ingest_report(entry.ingest_run_id) if entry.ingest_run_id else None
            finding = self._finding_for_entry(entry, report)
            node = finding.to_knowledge_node()
            await self._store.batch_upsert_nodes([node])
            findings_written += 1
            edges = flag_edges_for_finding(finding)
            if edges:
                await self._store.batch_upsert_edges(edges)
            self._pool.mark_sampled_by_athene(entry.entry_id, finding_ids=[finding.finding_id])
            pool_marked += 1

        return AtheneRunSummary(
            sampled_count=len(sampled),
            findings_written=findings_written,
            pool_entries_marked=pool_marked,
        )


__all__ = ["AtheneRunSummary", "AtheneVerifier"]
