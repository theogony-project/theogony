"""Chronos v0.1 — recycler / negative-knowledge response (Living Demo W15)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from theogony.config.settings import ChronosSettings
from theogony.core.model import ScoreUpdate
from theogony.core.store import KnowledgeStore
from theogony.curiosity.chronos_report import ChronosAction, ChronosRunSummary
from theogony.curiosity.finding import finding_from_node, resolved_finding_node
from theogony.curiosity.negative_knowledge import contradiction_edges_for_finding
from theogony.curiosity.verification_pool import PoolEntry, VerificationPool

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

_ResolutionAction = Literal["none", "annotated", "demoted", "deleted", "escalated_to_human"]
_ChronosActionKind = Literal[
    "cleared_no_issue",
    "annotated",
    "demoted",
    "negative_edge_written",
    "skipped_missing_finding",
]


class ChronosRecycler:
    """Consumes Athene findings from the pool; writes edges, demotions, clears pool."""

    def __init__(
        self,
        *,
        store: KnowledgeStore,
        pool: VerificationPool,
        settings: ChronosSettings,
    ) -> None:
        self._store = store
        self._pool = pool
        self._settings = settings

    def _eligible_entries(self) -> list[PoolEntry]:
        rows = [
            e
            for e in self._pool.entries()
            if e.lifecycle == "sampled_by_athene" and bool(e.finding_ids)
        ]

        def sort_key(e: PoolEntry) -> tuple[datetime, datetime]:
            sampled = e.sampled_at or e.acquired_at
            if sampled.tzinfo is None:
                sampled = sampled.replace(tzinfo=UTC)
            acq = e.acquired_at
            if acq.tzinfo is None:
                acq = acq.replace(tzinfo=UTC)
            return (sampled, acq)

        rows.sort(key=sort_key)
        return rows[: self._settings.max_entries_per_pass]

    async def run_once(self) -> ChronosRunSummary:
        if not self._settings.enabled:
            return ChronosRunSummary(skipped_reason="chronos disabled")

        eligible = self._eligible_entries()
        if not eligible:
            return ChronosRunSummary()

        summary = ChronosRunSummary()
        now = datetime.now(UTC)
        min_rank = SEVERITY_RANK[self._settings.min_severity_for_demotion]

        for entry in eligible:
            summary.processed_entries += 1
            any_missing_finding = False

            for finding_id in entry.finding_ids:
                summary.findings_seen += 1
                node = await self._store.get_node(finding_id)
                if node is None:
                    summary.missing_findings += 1
                    any_missing_finding = True
                    summary.actions.append(
                        ChronosAction(
                            pool_entry_id=entry.entry_id,
                            finding_id=finding_id,
                            finding_type="",
                            severity="",
                            action="skipped_missing_finding",
                            reason="finding node not in store",
                        )
                    )
                    continue

                finding = finding_from_node(node)

                if finding.finding_type == "no_issue_observed":
                    resolved = resolved_finding_node(
                        finding,
                        resolved_at=now,
                        resolution_action="annotated",
                    )
                    await self._store.batch_upsert_nodes([resolved])
                    summary.findings_resolved += 1
                    summary.actions.append(
                        ChronosAction(
                            pool_entry_id=entry.entry_id,
                            finding_id=finding.finding_id,
                            finding_type=finding.finding_type,
                            severity=finding.severity,
                            action="cleared_no_issue",
                            target_node_ids=list(finding.target_node_ids),
                        )
                    )
                    continue

                edges = contradiction_edges_for_finding(
                    finding,
                    confidence=self._settings.negative_edge_confidence,
                    weight=self._settings.negative_edge_weight,
                )
                if edges:
                    await self._store.batch_upsert_edges(edges)
                    summary.negative_edges_written += len(edges)

                finding_demoted = 0
                finding_rank = SEVERITY_RANK[finding.severity]
                if finding.target_node_ids and finding_rank >= min_rank:
                    updates: list[ScoreUpdate] = []
                    for target_id in finding.target_node_ids:
                        tnode = await self._store.get_node(target_id)
                        if tnode is None:
                            summary.missing_targets += 1
                            continue
                        new_confidence = max(
                            0.0,
                            tnode.scores.confidence - self._settings.confidence_demote_delta,
                        )
                        new_scores = tnode.scores.model_copy(update={"confidence": new_confidence})
                        updates.append(
                            ScoreUpdate(
                                node_id=target_id,
                                confidence=new_confidence,
                                vitality=new_scores.vitality(),
                            )
                        )
                        finding_demoted += 1
                    if updates:
                        await self._store.batch_update_scores(updates)
                        summary.nodes_demoted += finding_demoted

                res_action: _ResolutionAction = "demoted" if finding_demoted > 0 else "annotated"
                resolved = resolved_finding_node(
                    finding,
                    resolved_at=now,
                    resolution_action=res_action,
                )
                await self._store.batch_upsert_nodes([resolved])
                summary.findings_resolved += 1

                if edges:
                    action_kind: _ChronosActionKind = "negative_edge_written"
                elif finding_demoted > 0:
                    action_kind = "demoted"
                else:
                    action_kind = "annotated"

                summary.actions.append(
                    ChronosAction(
                        pool_entry_id=entry.entry_id,
                        finding_id=finding.finding_id,
                        finding_type=finding.finding_type,
                        severity=finding.severity,
                        action=action_kind,
                        target_node_ids=list(finding.target_node_ids),
                        edges_written=len(edges),
                        nodes_demoted=finding_demoted,
                    )
                )

            if not any_missing_finding:
                self._pool.mark_cleared(entry.entry_id)
                summary.pool_entries_cleared += 1

        return summary


__all__ = ["ChronosRecycler", "SEVERITY_RANK"]
