"""Nemesis v0.1 structural auditor (Living Demo W16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from theogony.config.settings import NemesisSettings
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType
from theogony.core.store import KnowledgeStore
from theogony.curiosity.finding import Finding, flag_edges_for_finding
from theogony.curiosity.nemesis_report import (
    NemesisAuditKind,
    NemesisFindingRecord,
    NemesisRunSummary,
)

NEMESIS_POOL_ENTRY_ID = "nemesis-structural-audit"

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _source_count(node_properties: dict[str, object] | None) -> int:
    if not node_properties:
        return 1
    raw = node_properties.get("source_count", 1)
    if isinstance(raw, bool):
        return 1
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return 1
    return 1


def _finding_sort_key(f: Finding) -> tuple[int, str, str]:
    rank = _SEVERITY_RANK[f.severity]
    first = f.target_node_ids[0] if f.target_node_ids else ""
    return (-rank, f.finding_type, first)


class NemesisAuditor:
    """Read-only structural audits; writes Finding nodes and FLAGGED_BY edges."""

    def __init__(self, *, store: KnowledgeStore, settings: NemesisSettings) -> None:
        self._store = store
        self._settings = settings

    async def _export_ephemera_and_mneme(self) -> list[KnowledgeNode]:
        nodes: list[KnowledgeNode] = []
        async for n in self._store.export_layer(Layer.EPHEMERA):
            nodes.append(n)
        async for n in self._store.export_layer(Layer.MNEME):
            nodes.append(n)
        return nodes

    async def run_once(self) -> NemesisRunSummary:
        if not self._settings.enabled:
            return NemesisRunSummary(skipped_reason="nemesis disabled")

        summary = NemesisRunSummary(
            audits_run=[
                "confidence_inflation",
                "persistent_contradiction",
                "pheromone_autobahn",
            ]
        )

        nodes = await self._export_ephemera_and_mneme()
        node_ids = [n.id for n in nodes]
        id_set = set(node_ids)

        candidates: list[Finding] = []

        # Audit A — confidence inflation proxy
        for node in nodes:
            if node.node_type == NodeType.FINDING:
                continue
            if node.scores.confidence < self._settings.high_confidence_threshold:
                continue
            sc = _source_count(node.properties)
            if sc > self._settings.low_evidence_source_count:
                continue
            fid = f"FINDING-{uuid.uuid4()}"
            ev = [
                f"confidence={node.scores.confidence:.3f}",
                f"source_count={sc}",
                f"threshold_confidence={self._settings.high_confidence_threshold}",
            ]
            candidates.append(
                Finding(
                    finding_id=fid,
                    finding_type="confidence_inflation",
                    severity="medium",
                    cell="nemesis",
                    pool_entry_id=NEMESIS_POOL_ENTRY_ID,
                    target_node_ids=[node.id],
                    evidence=ev,
                    sampled_at=datetime.now(UTC),
                )
            )

        # Audit B — persistent contradiction (CONTRADICTS among exported nodes)
        edges_b = await self._store.get_edges_among(
            node_ids,
            min_weight=self._settings.contradiction_weight_threshold,
        )
        for edge in edges_b:
            if edge.relation_type != "CONTRADICTS":
                continue
            if edge.confidence < self._settings.contradiction_confidence_threshold:
                continue
            if edge.source_id not in id_set or edge.target_id not in id_set:
                continue
            fid = f"FINDING-{uuid.uuid4()}"
            ev = [
                f"edge_id={edge.id}",
                f"confidence={edge.confidence:.3f}",
                f"weight={edge.weight:.3f}",
            ]
            candidates.append(
                Finding(
                    finding_id=fid,
                    finding_type="persistent_contradiction",
                    severity="high",
                    cell="nemesis",
                    pool_entry_id=NEMESIS_POOL_ENTRY_ID,
                    target_node_ids=[edge.source_id, edge.target_id],
                    evidence=ev,
                    sampled_at=datetime.now(UTC),
                )
            )

        # Audit C — pheromone autobahn
        edges_c = await self._store.get_edges_among(node_ids, min_weight=0.0)
        for edge in edges_c:
            if abs(edge.pheromone_delta) < self._settings.autobahn_pheromone_delta_threshold:
                continue
            if edge.source_id not in id_set or edge.target_id not in id_set:
                continue
            fid = f"FINDING-{uuid.uuid4()}"
            ev = [
                f"edge_id={edge.id}",
                f"pheromone_delta={edge.pheromone_delta:.4f}",
            ]
            candidates.append(
                Finding(
                    finding_id=fid,
                    finding_type="pheromone_autobahn",
                    severity="medium",
                    cell="nemesis",
                    pool_entry_id=NEMESIS_POOL_ENTRY_ID,
                    target_node_ids=[edge.source_id, edge.target_id],
                    evidence=ev,
                    sampled_at=datetime.now(UTC),
                )
            )

        candidates.sort(key=_finding_sort_key)
        capped = candidates[: self._settings.max_findings_per_pass]

        all_edges: list[KnowledgeEdge] = []
        records: list[NemesisFindingRecord] = []
        for finding in capped:
            missing_here = 0
            present_targets: list[str] = []
            for tid in finding.target_node_ids:
                got = await self._store.get_node(tid)
                if got is None:
                    missing_here += 1
                else:
                    present_targets.append(tid)
            summary.missing_targets += missing_here

            await self._store.batch_upsert_nodes([finding.to_knowledge_node()])
            summary.findings_written += 1
            if finding.finding_type == "confidence_inflation":
                summary.confidence_inflation_count += 1
            elif finding.finding_type == "persistent_contradiction":
                summary.persistent_contradiction_count += 1
            elif finding.finding_type == "pheromone_autobahn":
                summary.pheromone_autobahn_count += 1

            records.append(
                NemesisFindingRecord(
                    finding_id=finding.finding_id,
                    finding_type=cast(NemesisAuditKind, finding.finding_type),
                    severity=finding.severity,
                    target_node_ids=list(finding.target_node_ids),
                    evidence=list(finding.evidence),
                )
            )

            if present_targets:
                flagged = finding.model_copy(update={"target_node_ids": present_targets})
                all_edges.extend(flag_edges_for_finding(flagged))

        if all_edges:
            await self._store.batch_upsert_edges(all_edges)

        summary.findings = records
        return summary


__all__ = ["NEMESIS_POOL_ENTRY_ID", "NemesisAuditor"]
