"""Orchestrator for the wikidata5m bulk seed path."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ulid import ULID

from theogony.mesh.ingestion.concept_resolver import ConceptResolver
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge, PIDTag, QIDTag
from theogony.mesh.seeds.wikidata5m.embedder import MeshEmbedder
from theogony.mesh.seeds.wikidata5m.limits import (
    DEFAULT_SEED_EMBEDDING_BATCH_SIZE,
    DEFAULT_SEED_EMBEDDING_MAX_CHARS,
    seed_write_batch_size,
    truncate_seed_embedding_text,
)
from theogony.mesh.seeds.wikidata5m.loader import (
    EntityRecord,
    TextRecord,
    TripletRecord,
    iter_entity_text_pairs,
    iter_entity_text_pairs_bounded,
    iter_entity_text_pairs_for_qids,
    iter_triplet_records,
    iter_triplet_records_for_qids,
    load_qid_selection_file,
    load_relation_aliases,
)
from theogony.mesh.seeds.wikidata5m.relations import resolve_relation_mapping
from theogony.reporting.models import MeshSeedRunReport
from theogony.reporting.writer import RunReportWriter


def _entity_name(record: EntityRecord) -> str | None:
    if not record.aliases:
        return None
    name = record.aliases[0].strip()
    if not name:
        return None
    return name[:100]


def _zero_vector(dim: int) -> list[float]:
    return [0.0] * dim


@dataclass
class _SeedCounters:
    entities_streamed: int = 0
    entities_upserted: int = 0
    entities_skipped_duplicate_qid: int = 0
    entities_missing_text: int = 0
    entities_embedding_text_truncated: int = 0
    edges_streamed: int = 0
    edges_upserted: int = 0
    edges_skipped_duplicate: int = 0
    edges_skipped_missing_endpoint: int = 0
    loader_malformed_lines: int = 0


class Wikidata5mSeedImporter:
    """Stream wikidata5m rows into Q-ID anchored Tier-1 nodes and edges."""

    def __init__(
        self,
        runtime: MeshRuntime,
        *,
        data_root: Path,
        embedder: MeshEmbedder,
        embedder_requested: str | None = None,
        batch_size: int = DEFAULT_SEED_EMBEDDING_BATCH_SIZE,
        max_embedding_chars: int = DEFAULT_SEED_EMBEDDING_MAX_CHARS,
        report_writer: RunReportWriter | None = None,
    ) -> None:
        self.runtime = runtime
        self.data_root = data_root
        self.embedder = embedder
        self.embedder_requested = embedder_requested
        self.batch_size = batch_size
        self.max_embedding_chars = max_embedding_chars
        self.write_batch_size = seed_write_batch_size(batch_size)
        self.report_writer = report_writer or RunReportWriter(Path("data/run_reports"))
        self.resolver = ConceptResolver(runtime.nodes)
        self.counters = _SeedCounters()
        self.pid_unmapped: Counter[str] = Counter()
        self._edge_keys = {
            self._edge_key_from_edge(edge) for edge in self.runtime.edges.load_all_edges()
        }

    @property
    def entity_path(self) -> Path:
        return self.data_root / "wikidata5m_entity.txt"

    @property
    def text_path(self) -> Path:
        return self.data_root / "wikidata5m_text.txt"

    @property
    def relation_path(self) -> Path:
        return self.data_root / "wikidata5m_relation.txt"

    @property
    def triplet_path(self) -> Path:
        return self.data_root / "wikidata5m_all_triplet.txt"

    def _on_malformed(
        self, _file_name: str, _line_number: int, _reason: str, _raw_line: str
    ) -> None:
        self.counters.loader_malformed_lines += 1

    def _on_missing_text(self, _qid: str) -> None:
        self.counters.entities_missing_text += 1

    def _append_audit(self, action: str, detail: dict[str, object], *, dry_run: bool) -> str | None:
        if dry_run:
            return None
        return self.runtime.audit.append(action=action, detail=detail)

    def _append_audits(
        self,
        entries: list[tuple[str, dict[str, object]]],
        *,
        dry_run: bool,
    ) -> None:
        if dry_run or not entries:
            return
        self.runtime.audit.append_many(entries)

    @staticmethod
    def _edge_key(
        source_id: str, target_id: str, relation_descriptor: str | None
    ) -> tuple[str, str, str]:
        return (source_id, target_id, relation_descriptor or "")

    def _edge_key_from_edge(self, edge: Edge) -> tuple[str, str, str]:
        return self._edge_key(str(edge.source_id), str(edge.target_id), edge.relation_descriptor)

    async def _flush_entity_batch(
        self,
        batch: list[tuple[EntityRecord, TextRecord]],
        *,
        dry_run: bool,
    ) -> None:
        if not batch:
            return
        new_pairs: list[tuple[EntityRecord, TextRecord]] = []
        for entity, text in batch:
            self.counters.entities_streamed += 1
            if self.resolver.get_by_qid(entity.qid) is not None:
                self.counters.entities_skipped_duplicate_qid += 1
                continue
            new_pairs.append((entity, text))
        if not new_pairs:
            return

        embed_texts: list[str] = []
        for _entity, text in new_pairs:
            clipped, truncated = truncate_seed_embedding_text(
                text.description_text,
                max_chars=self.max_embedding_chars,
            )
            if truncated:
                self.counters.entities_embedding_text_truncated += 1
            embed_texts.append(clipped)

        embed_started = time.monotonic()
        semantic_vectors = await self.embedder.embed_many(
            embed_texts,
            batch_size=self.batch_size,
        )
        embedding_duration_s = time.monotonic() - embed_started
        self._embedding_duration_s += embedding_duration_s
        nodes: list[ConsolidatedNode] = []
        node_aliases: list[list[str]] = []
        audit_entries: list[tuple[str, dict[str, object]]] = []
        for (entity, _text), semantic_vector in zip(new_pairs, semantic_vectors, strict=False):
            now = datetime.now(UTC)
            name = _entity_name(entity)
            node = ConsolidatedNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                consolidation_tier=1,
                is_candidate=False,
                semantic_vector=semantic_vector,
                frame_vector=_zero_vector(self.runtime.frame_dim),
                description_vector=list(semantic_vector),
                description=name,
                tags=entity.aliases[:50],
                qids=[
                    QIDTag(
                        qid=entity.qid,
                        confidence=1.0,
                        attached_at=now,
                    )
                ],
            )
            nodes.append(node)
            node_aliases.append(entity.aliases)
            audit_entries.append(
                (
                    "mesh_seed_node_created",
                    {
                        "node_id": str(node.id),
                        "qid": entity.qid,
                        "alias_count": len(entity.aliases),
                    },
                )
            )
        if not dry_run:
            self.runtime.nodes.append_consolidated_many(nodes)
        for node, aliases in zip(nodes, node_aliases, strict=False):
            self.resolver.remember(node, aliases=aliases, qids=node.qids)
        self.counters.entities_upserted += len(nodes)
        self._append_audits(audit_entries, dry_run=dry_run)

    async def _seed_entities(
        self,
        *,
        max_entities: int,
        qid_file: Path | None,
        dry_run: bool,
    ) -> None:
        batch: list[tuple[EntityRecord, TextRecord]] = []
        if qid_file is not None:
            pair_iter = iter_entity_text_pairs_for_qids(
                self.entity_path,
                self.text_path,
                load_qid_selection_file(qid_file),
                on_malformed=self._on_malformed,
                on_missing_text=self._on_missing_text,
            )
        elif max_entities > 0:
            lookup_window_size = max(
                self.write_batch_size * 16,
                max_entities - self.counters.entities_upserted,
                self.write_batch_size,
            )
            pair_iter = iter_entity_text_pairs_bounded(
                self.entity_path,
                self.text_path,
                max_pairs=max_entities,
                lookup_window_size=lookup_window_size,
                on_malformed=self._on_malformed,
                on_missing_text=self._on_missing_text,
            )
        else:
            pair_iter = iter_entity_text_pairs(
                self.entity_path,
                self.text_path,
                on_malformed=self._on_malformed,
            )
        for entity, text in pair_iter:
            batch.append((entity, text))
            if len(batch) >= self.write_batch_size:
                await self._flush_entity_batch(batch, dry_run=dry_run)
                batch = []
        if batch:
            await self._flush_entity_batch(batch, dry_run=dry_run)

    def _seeded_qids(self, *, qid_file: Path | None = None) -> set[str]:
        if qid_file is not None:
            return set(load_qid_selection_file(qid_file))
        remembered = {qid.qid for node in self.resolver.iter_nodes() for qid in node.qids}
        if remembered:
            return remembered
        return {
            qid_tag.qid for node in self.runtime.nodes.iter_consolidated() for qid_tag in node.qids
        }

    def _iter_limited_triplets(
        self,
        *,
        max_triplets: int,
        seeded_qids: set[str],
    ) -> Iterable[TripletRecord]:
        if not seeded_qids:
            return []
        if max_triplets > 0:
            return iter_triplet_records_for_qids(
                self.triplet_path,
                seeded_qids,
                max_triplets=max_triplets,
                on_malformed=self._on_malformed,
            )
        return (
            record
            for record in iter_triplet_records(
                self.triplet_path,
                on_malformed=self._on_malformed,
            )
            if record.subject_qid in seeded_qids and record.object_qid in seeded_qids
        )

    def _pid_tag(self, pid: str, *, attached_at: datetime) -> list[PIDTag]:
        return [PIDTag(pid=pid, confidence=1.0, attached_at=attached_at)]

    def _seed_edges(
        self,
        *,
        max_triplets: int,
        qid_file: Path | None,
        dry_run: bool,
    ) -> None:
        edge_batch: list[Edge] = []
        audit_entries: list[tuple[str, dict[str, object]]] = []
        seeded_qids = self._seeded_qids(qid_file=qid_file)
        relation_aliases = load_relation_aliases(
            self.relation_path, on_malformed=self._on_malformed
        )
        for triplet in self._iter_limited_triplets(
            max_triplets=max_triplets,
            seeded_qids=seeded_qids,
        ):
            self.counters.edges_streamed += 1
            source_node = self.resolver.get_by_qid(triplet.subject_qid)
            target_node = self.resolver.get_by_qid(triplet.object_qid)
            if source_node is None or target_node is None:
                self.counters.edges_skipped_missing_endpoint += 1
                continue
            mapping = resolve_relation_mapping(
                triplet.predicate_pid,
                relation_aliases.get(triplet.predicate_pid, []),
            )
            if not mapping.mapped:
                self.pid_unmapped[triplet.predicate_pid] += 1
            edge_key = self._edge_key(
                str(source_node.id),
                str(target_node.id),
                mapping.relation_descriptor,
            )
            if edge_key in self._edge_keys:
                self.counters.edges_skipped_duplicate += 1
                continue
            now = datetime.now(UTC)
            edge = Edge(
                source_id=source_node.id,
                target_id=target_node.id,
                weight=1.0,
                born_at=now,
                last_fired_at=now,
                relation_kind=mapping.relation_kind,
                relation_descriptor=mapping.relation_descriptor,
                pids=self._pid_tag(triplet.predicate_pid, attached_at=now),
                creation_context="wikidata5m_seed",
            )
            edge_batch.append(edge)
            self._edge_keys.add(edge_key)
            self.counters.edges_upserted += 1
            audit_entries.append(
                (
                    "mesh_seed_edge_created",
                    {
                        "source_id": str(source_node.id),
                        "target_id": str(target_node.id),
                        "pid": triplet.predicate_pid,
                        "relation_descriptor": mapping.relation_descriptor,
                    },
                )
            )
            if len(edge_batch) >= self.write_batch_size:
                if not dry_run:
                    self.runtime.edges.append_edges(edge_batch)
                self._append_audits(audit_entries, dry_run=dry_run)
                edge_batch = []
                audit_entries = []
        if edge_batch:
            if not dry_run:
                self.runtime.edges.append_edges(edge_batch)
            self._append_audits(audit_entries, dry_run=dry_run)

    async def run(
        self,
        *,
        max_entities: int = 0,
        max_triplets: int = 0,
        qid_file: Path | None = None,
        edges_only: bool = False,
        dry_run: bool = False,
    ) -> dict[str, object]:
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        self._embedding_duration_s = 0.0

        if not edges_only:
            await self._seed_entities(
                max_entities=max_entities,
                qid_file=qid_file,
                dry_run=dry_run,
            )
        self._seed_edges(
            max_triplets=max_triplets,
            qid_file=qid_file,
            dry_run=dry_run,
        )

        finished_at = datetime.now(UTC)
        import_duration_s = time.monotonic() - started_monotonic
        anomalies: list[str] = []
        recommendations: list[str] = []
        status: Literal["completed", "partial", "failed", "aborted"] = "completed"
        verdict: Literal["good", "partial", "poor", "failed"] = "good"
        if self.counters.loader_malformed_lines > 0:
            verdict = "partial"
            anomalies.append("loader_malformed_lines")
            recommendations.append("Inspect malformed wikidata5m rows before scaling Smoke-1.")
        if self.counters.entities_missing_text > 0:
            anomalies.append("entities_missing_text")
            recommendations.append(
                "Inspect sparse wikidata5m text coverage before larger bounded seed runs."
            )
        if self.counters.edges_skipped_missing_endpoint > 0:
            anomalies.append("edges_skipped_missing_endpoint")
        if self.pid_unmapped:
            anomalies.append("unmapped_pids_present")
            recommendations.append(
                "Expand the hand-curated P-ID registry if unmapped relations matter downstream."
            )

        audit_run_id = self._append_audit(
            "mesh_seed_run",
            {
                "entities_streamed": self.counters.entities_streamed,
                "entities_upserted": self.counters.entities_upserted,
                "entities_missing_text": self.counters.entities_missing_text,
                "edges_streamed": self.counters.edges_streamed,
                "edges_upserted": self.counters.edges_upserted,
                "loader_malformed_lines": self.counters.loader_malformed_lines,
            },
            dry_run=dry_run,
        )
        report = MeshSeedRunReport(
            started_at=started_at,
            finished_at=finished_at,
            duration_s=finished_at.timestamp() - started_at.timestamp(),
            status=status,
            verdict=verdict,
            verdict_reasoning="Seed run completed without raw-text writes.",
            anomalies=anomalies,
            recommendations=recommendations,
            audit_log_run_id=audit_run_id,
            audit_run_id=audit_run_id,
            data_root=str(self.data_root),
            embedder_requested=self.embedder_requested,
            embedding_model_id=self.embedder.model_id,
            max_entities=max_entities,
            max_triplets=max_triplets,
            qid_file=str(qid_file) if qid_file is not None else None,
            edges_only=edges_only,
            batch_size=self.batch_size,
            write_batch_size=self.write_batch_size,
            embedding_text_max_chars=self.max_embedding_chars,
            dry_run=dry_run,
            entities_streamed=self.counters.entities_streamed,
            entities_upserted=self.counters.entities_upserted,
            entities_skipped_duplicate_qid=self.counters.entities_skipped_duplicate_qid,
            entities_missing_text=self.counters.entities_missing_text,
            entities_embedding_text_truncated=self.counters.entities_embedding_text_truncated,
            edges_streamed=self.counters.edges_streamed,
            edges_upserted=self.counters.edges_upserted,
            edges_skipped_duplicate=self.counters.edges_skipped_duplicate,
            edges_skipped_missing_endpoint=self.counters.edges_skipped_missing_endpoint,
            loader_malformed_lines=self.counters.loader_malformed_lines,
            pids_unmapped=dict(self.pid_unmapped),
            embedding_duration_s=self._embedding_duration_s,
            import_duration_s=import_duration_s,
        )
        report_path = self.report_writer.write(report)
        return {
            "entities_streamed": self.counters.entities_streamed,
            "entities_upserted": self.counters.entities_upserted,
            "entities_skipped_duplicate_qid": self.counters.entities_skipped_duplicate_qid,
            "entities_missing_text": self.counters.entities_missing_text,
            "edges_streamed": self.counters.edges_streamed,
            "edges_upserted": self.counters.edges_upserted,
            "edges_skipped_duplicate": self.counters.edges_skipped_duplicate,
            "edges_skipped_missing_endpoint": self.counters.edges_skipped_missing_endpoint,
            "loader_malformed_lines": self.counters.loader_malformed_lines,
            "embedding_model_id": self.embedder.model_id,
            "report_run_id": report.run_id,
            "report_path": str(report_path),
            "verdict": report.verdict,
        }
