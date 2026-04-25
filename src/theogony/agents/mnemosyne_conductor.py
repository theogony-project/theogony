"""Mnemosyne conductor: immune metrics, experiments, backlog drafts (W17)."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.config.settings import Settings
from theogony.core.model import Layer, NodeType
from theogony.core.store import KnowledgeStore
from theogony.curiosity.chronos_report import ChronosRunReport
from theogony.curiosity.eris_report import ErisCampaignReport
from theogony.curiosity.finding import finding_from_node
from theogony.curiosity.mnemosyne_conductor_report import (
    BacklogProposalDraft,
    ExperimentProposal,
    ImmuneMetricSnapshot,
    MetricDefinition,
    MnemosyneConductorSummary,
)
from theogony.curiosity.mnemosyne_experiment import MnemosyneExperiment
from theogony.curiosity.nemesis_report import NemesisRunReport
from theogony.curiosity.verification_pool import VerificationPool
from theogony.reporting.writer import RunReportWriter


class _LLMMetricRow(BaseModel):
    """One metric row from the LLM (no ``source`` field required in JSON)."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str
    name: str
    rationale: str
    numerator: str
    denominator: str
    desired_direction: Literal["increase", "decrease", "stabilize"]
    current_value: float | None = None
    target_value: float | None = None


class _LLMMetricEnvelope(BaseModel):
    """Structured LLM output for metric definitions."""

    model_config = ConfigDict(extra="forbid")

    metrics: list[_LLMMetricRow] = Field(default_factory=list, min_length=1, max_length=5)


@runtime_checkable
class MetricDefiner(Protocol):
    async def define_metrics(
        self, snapshot: ImmuneMetricSnapshot
    ) -> tuple[list[MetricDefinition], float]:
        """Return (definitions, cost_eur)."""


def _scan_verdicts(report_dir: Path, limit: int) -> tuple[int, dict[str, int]]:
    if not report_dir.is_dir():
        return 0, {}
    paths = sorted(
        (p for p in report_dir.iterdir() if p.is_file() and p.suffix == ".json"),
        key=lambda p: p.stem,
        reverse=True,
    )[:limit]
    counts: Counter[str] = Counter()
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        v = raw.get("verdict")
        if isinstance(v, str):
            counts[v] += 1
    return len(paths), dict(counts)


class FixtureMetricDefiner:
    """Deterministic metrics for CI and operator fixture mode."""

    async def define_metrics(
        self, snapshot: ImmuneMetricSnapshot
    ) -> tuple[list[MetricDefinition], float]:
        pool_total = snapshot.pool_total
        cleared = snapshot.pool_cleared
        cur_clear = (cleared / pool_total) if pool_total > 0 else None

        denom_findings = snapshot.pool_findings_total
        unresolved = snapshot.unresolved_finding_count
        cur_unres = (unresolved / denom_findings) if denom_findings > 0 else None

        failed = snapshot.latest_eris_failed
        cur_red = float(failed)

        metrics = [
            MetricDefinition(
                metric_id="pool_clearance_ratio",
                name="Pool clearance ratio",
                rationale="Higher clearance means Chronos is resolving sampled pool rows.",
                numerator="pool_cleared",
                denominator="pool_total",
                desired_direction="increase",
                current_value=cur_clear,
                target_value=0.8,
                source="fixture",
            ),
            MetricDefinition(
                metric_id="unresolved_finding_ratio",
                name="Unresolved finding ratio",
                rationale="Lower unresolved ratio means findings are being closed out.",
                numerator="unresolved_finding_count",
                denominator="pool_findings_total",
                desired_direction="decrease",
                current_value=cur_unres,
                target_value=0.2,
                source="fixture",
            ),
            MetricDefinition(
                metric_id="red_team_failure_count",
                name="Red team failure count",
                rationale="Eris probe failures indicate harness or grounding gaps.",
                numerator="latest_eris_failed",
                denominator="latest_eris_probes_run",
                desired_direction="decrease",
                current_value=cur_red,
                target_value=0.0,
                source="fixture",
            ),
        ]
        return metrics, 0.0


class LLMMetricDefiner:
    """LLM-authored metrics with JSON schema validation."""

    def __init__(self, *, llm: LLMProvider, timeout_s: float) -> None:
        self._llm = llm
        self._timeout_s = timeout_s

    async def define_metrics(
        self, snapshot: ImmuneMetricSnapshot
    ) -> tuple[list[MetricDefinition], float]:
        schema = _LLMMetricEnvelope.model_json_schema()
        prompt = snapshot.model_dump_json(indent=2)
        system = (
            "You are Mnemosyne. Define 1-5 success metrics for improving the immune system. "
            "Do not propose code changes. Output JSON only."
        )
        result = await self._llm.complete(
            prompt,
            system=system,
            json_schema=schema,
            max_output_tokens=1200,
            temperature=0.2,
            timeout_s=self._timeout_s,
        )
        envelope = _LLMMetricEnvelope.model_validate_json(result.text)
        out: list[MetricDefinition] = []
        for row in envelope.metrics:
            out.append(
                MetricDefinition(
                    metric_id=row.metric_id,
                    name=row.name,
                    rationale=row.rationale,
                    numerator=row.numerator,
                    denominator=row.denominator,
                    desired_direction=row.desired_direction,
                    current_value=row.current_value,
                    target_value=row.target_value,
                    source="llm",
                )
            )
        return out, float(result.cost_eur)


def _experiment_proposals_for_metrics(metrics: list[MetricDefinition]) -> list[ExperimentProposal]:
    proposals: list[ExperimentProposal] = []
    for m in metrics:
        eid = f"MNEMO-PROPOSAL-{uuid.uuid4()}"
        if m.metric_id == "pool_clearance_ratio":
            proposals.append(
                ExperimentProposal(
                    experiment_id=eid,
                    metric_id=m.metric_id,
                    hypothesis="Raising Athene sample rate may improve pool clearance.",
                    regime_a={"THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE": "0.02"},
                    regime_b={"THEOGONY_CURIOSITY__ATHENE__SAMPLE_RATE": "0.05"},
                    expected_effect=(
                        "Regime B should increase sampled findings and downstream clearance."
                    ),
                    risk="medium",
                    auto_apply_allowed=False,
                )
            )
        elif m.metric_id == "unresolved_finding_ratio":
            proposals.append(
                ExperimentProposal(
                    experiment_id=eid,
                    metric_id=m.metric_id,
                    hypothesis="Running Chronos more frequently may reduce unresolved findings.",
                    regime_a={"manual_frequency": "operator-run-after-athene"},
                    regime_b={"manual_frequency": "operator-run-twice-after-athene"},
                    expected_effect="Regime B should reduce backlog of unresolved findings.",
                    risk="low",
                    auto_apply_allowed=False,
                )
            )
        elif m.metric_id == "red_team_failure_count":
            proposals.append(
                ExperimentProposal(
                    experiment_id=eid,
                    metric_id=m.metric_id,
                    hypothesis="Adding a live answerer probe may change Eris failure profile.",
                    regime_a={"eris_fixture_campaign": "baseline"},
                    regime_b={"eris_fixture_campaign": "add-one-live-answerer-probe"},
                    expected_effect="Regime B explores additional adversarial coverage.",
                    risk="high",
                    auto_apply_allowed=False,
                )
            )
    return proposals


def _backlog_drafts_for_snapshot(snap: ImmuneMetricSnapshot) -> list[BacklogProposalDraft]:
    drafts: list[BacklogProposalDraft] = []
    if snap.latest_eris_failed > 0:
        drafts.append(
            BacklogProposalDraft(
                draft_id=f"DRAFT-{uuid.uuid4()}",
                title="Improve groundedness against Eris adversarial probes",
                rationale="Eris recorded at least one failed probe in the latest campaign.",
                suggested_category="feature",
                source_metric_ids=["red_team_failure_count"],
                source_report_ids=[],
                proposed_acceptance_criteria=[
                    "Document probe outcomes and mitigation in a Phoenix ticket.",
                ],
            )
        )
    if snap.latest_nemesis_findings_written > 0:
        drafts.append(
            BacklogProposalDraft(
                draft_id=f"DRAFT-{uuid.uuid4()}",
                title="Review structural hubris signals surfaced by Nemesis",
                rationale="Nemesis wrote at least one structural finding in its latest pass.",
                suggested_category="vision",
                source_metric_ids=["pool_clearance_ratio", "unresolved_finding_ratio"],
                source_report_ids=[],
                proposed_acceptance_criteria=["Triage Nemesis findings with domain owners."],
            )
        )
    ratio = (snap.pool_cleared / snap.pool_total) if snap.pool_total > 0 else 1.0
    if snap.pool_total > 0 and ratio < 0.5:
        drafts.append(
            BacklogProposalDraft(
                draft_id=f"DRAFT-{uuid.uuid4()}",
                title="Improve immune-system clearance rate",
                rationale=(
                    f"Only {ratio:.2f} of pool entries are cleared vs total {snap.pool_total}."
                ),
                suggested_category="ops",
                source_metric_ids=["pool_clearance_ratio"],
                source_report_ids=[],
                proposed_acceptance_criteria=["Increase Chronos cadence or reduce pool backlog."],
            )
        )
    return drafts


class ImmuneMetricCollector:
    """Build :class:`ImmuneMetricSnapshot` from pool, store, and on-disk reports."""

    def __init__(
        self, *, store: KnowledgeStore, pool: VerificationPool, writer: RunReportWriter
    ) -> None:
        self._store = store
        self._pool = pool
        self._writer = writer

    async def collect(self) -> ImmuneMetricSnapshot:
        st = self._pool.stats()
        snap = ImmuneMetricSnapshot(
            pool_total=st.total,
            pool_unobserved=st.unobserved,
            pool_sampled_by_athene=st.sampled_by_athene,
            pool_cleared=st.cleared,
            pool_findings_total=st.findings_total,
        )
        by_cell: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        by_severity: Counter[str] = Counter()
        unresolved = 0
        for layer in (Layer.EPHEMERA, Layer.MNEME):
            async for node in self._store.export_layer(layer):
                if node.node_type != NodeType.FINDING:
                    continue
                try:
                    fnd = finding_from_node(node)
                except ValueError:
                    continue
                by_cell[fnd.cell] += 1
                by_type[fnd.finding_type] += 1
                by_severity[fnd.severity] += 1
                if fnd.resolved_at is None or fnd.resolution_action == "none":
                    unresolved += 1
        snap.finding_count_by_cell = dict(by_cell)
        snap.finding_count_by_type = dict(by_type)
        snap.finding_count_by_severity = dict(by_severity)
        snap.unresolved_finding_count = unresolved

        cr = self._writer.most_recent("chronos")
        if isinstance(cr, ChronosRunReport):
            snap.latest_chronos_findings_seen = cr.findings_seen
            snap.latest_chronos_findings_resolved = cr.findings_resolved
            snap.latest_chronos_negative_edges_written = cr.negative_edges_written
            snap.latest_chronos_nodes_demoted = cr.nodes_demoted
            snap.latest_chronos_pool_entries_cleared = cr.pool_entries_cleared

        nr = self._writer.most_recent("nemesis")
        if isinstance(nr, NemesisRunReport):
            snap.latest_nemesis_findings_written = nr.findings_written

        er = self._writer.most_recent("eris")
        if isinstance(er, ErisCampaignReport):
            snap.latest_eris_probes_run = er.probes_run
            snap.latest_eris_failed = er.failed

        qn, qc = _scan_verdicts(self._writer.directory_for("query"), 200)
        snap.query_reports_scanned = qn
        snap.query_verdict_counts = qc
        in_n, in_c = _scan_verdicts(self._writer.directory_for("ingest"), 200)
        snap.ingest_reports_scanned = in_n
        snap.ingest_verdict_counts = in_c

        return snap


class MnemosyneConductor:
    """Post-hoc conductor: metrics, experiment nodes, backlog drafts (no auto-apply)."""

    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        writer: RunReportWriter,
        settings: Settings,
        metric_definer: MetricDefiner | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._store = store
        self._pool = pool
        self._writer = writer
        self._settings = settings
        self._metric_definer = metric_definer
        self._llm = llm

    async def run_once(self) -> tuple[MnemosyneConductorSummary, ImmuneMetricSnapshot]:
        collector = ImmuneMetricCollector(store=self._store, pool=self._pool, writer=self._writer)
        snapshot = await collector.collect()
        summary = MnemosyneConductorSummary()

        if not self._settings.mnemosyne.conductor_enabled:
            summary.skipped_reason = "mnemosyne conductor disabled"
            return summary, snapshot

        ms = self._settings.mnemosyne
        definitions: list[MetricDefinition] = []
        cost = 0.0
        fixture_fallback = False

        if self._metric_definer is not None:
            definitions, cost = await self._metric_definer.define_metrics(snapshot)
        elif ms.metric_definition_mode == "fixture":
            definitions, cost = await FixtureMetricDefiner().define_metrics(snapshot)
        elif (
            ms.metric_definition_mode == "llm"
            and self._llm is not None
            and not isinstance(self._llm, StubLLMProvider)
        ):
            try:
                llm_def = LLMMetricDefiner(llm=self._llm, timeout_s=ms.metric_definition_timeout_s)
                definitions, cost = await llm_def.define_metrics(snapshot)
            except Exception:
                definitions, cost = await FixtureMetricDefiner().define_metrics(snapshot)
                fixture_fallback = True
                cost = 0.0
        else:
            definitions, cost = await FixtureMetricDefiner().define_metrics(snapshot)
            if ms.metric_definition_mode == "llm":
                fixture_fallback = True

        definitions = definitions[: ms.max_metric_definitions_per_pass]
        summary.metric_definitions = definitions
        summary.metrics_defined = len(definitions)
        summary.llm_cost_eur = cost
        summary.fixture_fallback_used = fixture_fallback

        proposals = _experiment_proposals_for_metrics(definitions)[
            : ms.max_experiment_proposals_per_pass
        ]
        summary.experiment_proposals = proposals

        experiments: list[MnemosyneExperiment] = []
        for prop in proposals:
            mdef = next((d for d in definitions if d.metric_id == prop.metric_id), None)
            if mdef is None:
                continue
            experiments.append(
                MnemosyneExperiment(
                    experiment_id=prop.experiment_id,
                    metric_definition=mdef,
                    hypothesis=prop.hypothesis,
                    regime_a=dict(prop.regime_a),
                    regime_b=dict(prop.regime_b),
                    rationale=f"{prop.expected_effect} (risk={prop.risk})",
                )
            )
        if experiments:
            await self._store.batch_upsert_nodes([e.to_knowledge_node() for e in experiments])
            summary.experiment_nodes_written = len(experiments)

        drafts = _backlog_drafts_for_snapshot(snapshot)[: ms.max_backlog_drafts_per_pass]
        summary.backlog_drafts = drafts
        draft_root = self._settings.run_reports_dir / ms.backlog_draft_dir_name
        draft_root.mkdir(parents=True, exist_ok=True)
        for d in drafts:
            path = draft_root / f"{d.draft_id}.json"
            path.write_text(d.model_dump_json(indent=2), encoding="utf-8")
            summary.backlog_drafts_written += 1

        return summary, snapshot


__all__ = [
    "FixtureMetricDefiner",
    "ImmuneMetricCollector",
    "LLMMetricDefiner",
    "MetricDefiner",
    "MnemosyneConductor",
]
