"""MESH-native Kadmos v2 ingestion with dense paragraph topology."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from typing import Any, Literal

from ulid import ULID

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.mesh.ingestion.concept_resolver import ConceptResolver
from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.ingestion.reading_schemas import (
    LLMConcept,
    ParagraphReadingOutput,
    normalize_reading_payload,
)
from theogony.mesh.ingestion.source_anchor import (
    build_paragraph_anchor_title,
    build_source_anchor_node,
)
from theogony.mesh.ingestion.vectorizer import MeshTextVectorizer
from theogony.mesh.relation_pids import pid_for
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import (
    ChunkNode,
    ConsolidatedNode,
    Edge,
    PIDTag,
    QIDTag,
    SourceProvenance,
)
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    IngestStageReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
)
from theogony.reporting.verdict import ingest_verdict
from theogony.reporting.writer import RunReportWriter

log = get_logger("mesh.ingestion")

# Edges buffered before a Lance append (see MeshParagraphReader._append_edge).
_EDGE_FLUSH_BATCH = 512

# Structural (`shares_entities_with`) neighbours kept per paragraph — PHX-1049.
# Linking every entity-sharing pair is O(P^2): on the founding mesh the lattice
# alone was 51% of all edges, and a full read grew ~33% slower per 100-paragraph
# batch because the pass writes two edges and an audit row per qualifying pair.
# The doctrine wants connectivity carried by shared *concepts*, not by a chunk
# quasi-clique, so each paragraph keeps only its strongest partners.
_MAX_STRUCTURAL_NEIGHBOURS = 12

SYSTEM_PROMPT = """You are Kadmos, the cognitive reader for a MESH substrate.

Read the paragraph below and output valid JSON for this schema:

1. concepts:
   - every distinct person, place, object, organization, date, event, or idea
   - the paragraph's central figure(s) — whoever the passage is ABOUT — MUST
     appear here as named concepts. Never leave the protagonist implicit or
     fold them into the paragraph_concept alone; a passage about a goddess's
     birth must yield the goddess herself as a concept.
   - when the text uses a variant or translated name (e.g. Roman "Venus" for
     Greek Aphrodite, "Jove" for Zeus), use the text's name as the label and
     add the canonical variant names as tags
   - include a discriminating description
   - include optional Wikidata Q-IDs only when you are confident; for figures
     known under multiple names, the Q-ID of the canonical identity

2. relations:
   - directed edges between concepts from this paragraph
   - use short relation_descriptor values like crossed, mapped, discovered, located_in
   - use relation_kind values like semantic, hierarchy, causal, temporal, attribute

3. paragraph_concept:
   - optional single paragraph-level concept when the paragraph has a coherent unifying idea
   - the paragraph_concept never replaces the concepts it is about — its
     protagonists must still be listed in concepts
   - if absent, set paragraph_concept to null

Output only valid JSON. Do not add commentary."""

_SIGNAL_TO_TIER = {
    "qid": 4,
    "description": 3,
    "tag": 2,
    "emergent": 1,
}


@dataclass
class _ParagraphUnit:
    paragraph_number: int
    paragraph_anchor_id: str
    chunk_id: str
    entity_ids: set[str]
    paragraph_concept_id: str | None
    local_node_ids: set[str]
    local_edge_count: int


class MeshParagraphReader:
    """Paragraph reader that writes a dense, auditable local mesh per paragraph."""

    def __init__(
        self,
        mesh: MeshRuntime,
        llm: LLMProvider,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
        max_paragraphs: int = 0,
        settings: Settings | None = None,
        max_structural_neighbours: int = _MAX_STRUCTURAL_NEIGHBOURS,
    ) -> None:
        self.mesh = mesh
        self.llm = llm
        self.settings = settings or Settings()
        self.max_paragraphs = max_paragraphs
        self.max_structural_neighbours = max_structural_neighbours
        self.semantic_dim = mesh.semantic_dim if semantic_dim is None else semantic_dim
        self.frame_dim = mesh.frame_dim if frame_dim is None else frame_dim
        self.registry = ConceptResolver(mesh.nodes)
        self.linker = EagerLinker(
            mesh.nodes,
            mesh.edges,
            semantic_dim=self.semantic_dim,
            frame_dim=self.frame_dim,
            registry=self.registry,
        )
        self.vectorizer = MeshTextVectorizer(
            semantic_dim=self.semantic_dim,
            frame_dim=self.frame_dim,
            settings=self.settings,
        )
        self.report_writer = RunReportWriter(self.settings.run_reports_dir)
        self._pending_edges: list[Edge] = []

    async def read_book(self, book_id: str) -> dict[str, Any]:
        import httpx

        acquired_started = time.monotonic()
        async with httpx.AsyncClient(follow_redirects=True) as client:
            meta_resp = await client.get(f"https://gutendex.com/books/{book_id}", timeout=15)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            book_title = meta.get("title", f"Project Gutenberg Book {book_id}")
            formats = meta.get("formats", {})
            text_url = (
                formats.get("text/plain; charset=utf-8")
                or formats.get("text/plain")
                or formats.get("text/plain; charset=us-ascii")
                or next((value for key, value in formats.items() if "text/plain" in key), None)
            )
            if not text_url:
                raise ValueError(f"No plain-text format for book {book_id}")
            content_resp = await client.get(str(text_url), timeout=90)
            content_resp.raise_for_status()
            raw_text = content_resp.text
        acquired_duration_s = time.monotonic() - acquired_started

        return await self.read_text(
            text=raw_text,
            source_type="gutenberg",
            source_identifier=f"gutenberg_{book_id}",
            title=book_title,
            anchor=f"https://www.gutenberg.org/ebooks/{book_id}",
            acquired_duration_s=acquired_duration_s,
        )

    async def read_text(
        self,
        *,
        text: str,
        source_type: str = "text",
        source_identifier: str = "inline",
        title: str = "Untitled",
        anchor: str = "",
        acquired_duration_s: float = 0.0,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        source_anchor = anchor or source_identifier

        cleaned_started = time.monotonic()
        paragraphs = _split_paragraphs(text)
        if self.max_paragraphs > 0:
            paragraphs = paragraphs[: self.max_paragraphs]
        cleaned_duration_s = time.monotonic() - cleaned_started

        sentencized_started = time.monotonic()
        sentence_count = _count_sentences(" ".join(paragraphs))
        sentencized_duration_s = time.monotonic() - sentencized_started
        word_count = len(re.findall(r"\w+", " ".join(paragraphs)))

        nodes_upserted = 0
        firing_passes = 0
        edges_upserted = 0
        nodes_embedded = 0
        total_mentions = 0
        total_relations_attempted = 0
        total_relations_written = 0
        relation_drop_count = 0
        total_llm_calls = 0
        total_llm_cost_eur = 0.0
        llm_failure_count = 0
        llm_schema_failures = 0
        signal_counts: dict[str, int] = {key: 0 for key in _SIGNAL_TO_TIER}
        qid_claims_dropped = 0
        paragraph_units: list[_ParagraphUnit] = []
        entity_source_links: set[tuple[str, str]] = set()
        paragraph_anchor_count = 0
        paragraph_concept_count = 0
        paragraph_concept_node_ids: set[str] = set()
        llm_duration_s = 0.0
        relation_stage_duration_s = 0.0
        resolve_stage_duration_s = 0.0
        embed_stage_duration_s = 0.0
        store_stage_duration_s = 0.0
        cross_pass_link_count = 0

        text_anchor_description = f"{source_type}: {title} ({source_anchor})"
        text_anchor_semantic = await self.vectorizer.semantic(text_anchor_description)
        text_anchor_frame = await self.vectorizer.frame(text_anchor_description)
        text_anchor_description_vector = await self.vectorizer.description(text_anchor_description)
        nodes_embedded += 1
        text_anchor_node = build_source_anchor_node(
            source_type=source_type,
            title=title,
            anchor=source_anchor,
            semantic_vector=text_anchor_semantic,
            frame_vector=text_anchor_frame,
            description_vector=text_anchor_description_vector,
            tags=[source_type.lower(), "source_anchor", "text"],
        )
        self.mesh.nodes.append_consolidated(text_anchor_node)
        self.registry.remember(text_anchor_node)
        nodes_upserted += 1
        self._append_audit(
            "mesh_ingest_source_anchor_created",
            {
                "node_id": str(text_anchor_node.id),
                "source_type": source_type,
                "source_identifier": source_identifier,
            },
        )

        for paragraph_index, paragraph_text in enumerate(paragraphs, start=1):
            paragraph_text = paragraph_text.strip()
            if len(paragraph_text) < 10:
                continue

            log.info(
                "reading paragraph %d/%d (%d chars)",
                paragraph_index,
                len(paragraphs),
                len(paragraph_text),
            )

            paragraph_result, llm_meta = await self._read_paragraph(paragraph_text)
            total_llm_calls += 1
            total_llm_cost_eur += llm_meta["cost_eur"]
            llm_duration_s += llm_meta["duration_s"]
            llm_failure_count += int(llm_meta["failed"])
            llm_schema_failures += int(llm_meta["schema_failed"])

            embed_started = time.monotonic()
            paragraph_anchor_title = build_paragraph_anchor_title(
                title=title,
                paragraph_number=paragraph_index,
            )
            paragraph_anchor_identifier = f"{source_identifier}#p{paragraph_index}"
            paragraph_anchor_semantic = await self.vectorizer.semantic(paragraph_anchor_title)
            paragraph_anchor_frame = await self.vectorizer.frame(paragraph_anchor_title)
            paragraph_anchor_description_vector = await self.vectorizer.description(
                f"{source_type} paragraph: {paragraph_anchor_title} ({paragraph_anchor_identifier})"
            )
            chunk_semantic = await self.vectorizer.semantic(paragraph_text)
            chunk_frame = await self.vectorizer.frame(paragraph_text)
            nodes_embedded += 2
            embed_stage_duration_s += time.monotonic() - embed_started

            store_started = time.monotonic()
            paragraph_anchor = build_source_anchor_node(
                source_type=f"{source_type} paragraph",
                title=paragraph_anchor_title,
                anchor=paragraph_anchor_identifier,
                semantic_vector=paragraph_anchor_semantic,
                frame_vector=paragraph_anchor_frame,
                description_vector=paragraph_anchor_description_vector,
                tags=[source_type.lower(), "source_anchor", "paragraph"],
            )
            self.mesh.nodes.append_consolidated(paragraph_anchor)
            self.registry.remember(paragraph_anchor)
            nodes_upserted += 1
            paragraph_anchor_count += 1

            now = datetime.now(UTC)
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=chunk_semantic,
                frame_vector=chunk_frame,
                source=SourceProvenance(
                    source_type=source_type,
                    source_identifier=source_identifier,
                    extracted_at=now,
                ),
                raw_text_ref=paragraph_anchor_identifier,
            )
            self.mesh.nodes.append_chunk(chunk)
            nodes_upserted += 1
            self._append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=paragraph_anchor.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="kadmos_extraction",
                )
            )
            edges_upserted += 1
            self._append_edge(
                Edge(
                    source_id=paragraph_anchor.id,
                    target_id=text_anchor_node.id,
                    weight=0.9,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="hierarchy",
                    relation_descriptor="is_section_of",
                    creation_context="kadmos_source_hierarchy",
                )
            )
            edges_upserted += 1
            store_stage_duration_s += time.monotonic() - store_started

            resolved_by_label: dict[str, ConsolidatedNode] = {}
            resolved_entity_ids: set[str] = set()
            # Nodes this paragraph referenced that the substrate already had.
            # `MESH_SUBSTRATE.md` §"Second worked example" states the rule
            # outright: "Each new chunk attaches a *new* reference edge to the
            # *existing* Thomas Addison node — `fired_total` and `fired_recent`
            # increment, the node accumulates evidence." Doctrine's firing signal
            # therefore has two sources, and this is the one that carries the
            # "breadth of incoming references" half of the tier-promotion gate
            # (PHX-1101).
            referenced_existing: set[str] = set()
            local_node_ids = {
                str(text_anchor_node.id),
                str(paragraph_anchor.id),
                str(chunk.id),
            }
            local_edge_count = 2

            if paragraph_result is not None:
                total_mentions += len(paragraph_result.concepts)

                resolve_started = time.monotonic()
                concept_vectors = await self._vectorize_concepts(paragraph_result.concepts)
                nodes_embedded += len(paragraph_result.concepts)

                for concept, (semantic_vector, frame_vector, description_vector) in zip(
                    paragraph_result.concepts,
                    concept_vectors,
                    strict=False,
                ):
                    qids = [
                        QIDTag(
                            qid=qid.qid,
                            confidence=qid.confidence,
                            attached_at=datetime.now(UTC),
                        )
                        for qid in concept.qids
                    ]
                    decision = self.linker.link_reference(
                        label=concept.label,
                        description=_entity_description(concept.label, concept.description),
                        tags=_concept_tags(concept),
                        qids=qids,
                        semantic_vector=semantic_vector,
                        frame_vector=frame_vector,
                        description_vector=description_vector,
                        context_node_ids=resolved_entity_ids,
                        # The reading model asserts these; nothing corroborates
                        # them. They may still find a node the wikidata5m seed
                        # put there, but they must not be written (PHX-1063).
                        qids_are_authoritative=False,
                    )
                    qid_claims_dropped += len(qids)
                    signal_counts[decision.signal] += 1
                    resolved_by_label[concept.label] = decision.node
                    resolved_entity_ids.add(str(decision.node.id))
                    local_node_ids.add(str(decision.node.id))
                    if decision.is_new:
                        nodes_upserted += 1
                    else:
                        referenced_existing.add(str(decision.node.id))
                    self._stage_audit(
                        "mesh_ingest_link_decision",
                        {
                            "label": concept.label,
                            "node_id": str(decision.node.id),
                            "signal": decision.signal,
                            "score": round(decision.score, 4),
                            # Kept as a claim so it can be corroborated later.
                            "qid_claims": [q.qid for q in qids],
                            "paragraph": paragraph_index,
                            "source_identifier": source_identifier,
                        },
                    )

                    self._append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=decision.node.id,
                            weight=0.95,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="co_occurrence",
                            relation_descriptor="mentions",
                            creation_context="kadmos_mentions",
                        )
                    )
                    edges_upserted += 1
                    local_edge_count += 1

                    source_key = (str(decision.node.id), str(text_anchor_node.id))
                    if source_key not in entity_source_links:
                        self._append_edge(
                            Edge(
                                source_id=decision.node.id,
                                target_id=text_anchor_node.id,
                                weight=0.45,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="attribution",
                                relation_descriptor="appears_in_source",
                                creation_context="kadmos_source_attribution",
                            )
                        )
                        entity_source_links.add(source_key)
                        edges_upserted += 1
                        local_edge_count += 1

                resolve_stage_duration_s += time.monotonic() - resolve_started

                relation_started = time.monotonic()
                total_relations_attempted += len(paragraph_result.relations)
                for relation in paragraph_result.relations:
                    source_node = resolved_by_label.get(relation.source)
                    target_node = resolved_by_label.get(relation.target)
                    if source_node is None or target_node is None:
                        relation_drop_count += 1
                        continue
                    self._append_edge(
                        Edge(
                            source_id=source_node.id,
                            target_id=target_node.id,
                            weight=1.0,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind=relation.relation_kind,
                            relation_descriptor=relation.relation_descriptor,
                            description=relation.rationale,
                            # The Wikidata property naming this relation, when one
                            # reads the same way ours does. Curated and verified,
                            # never asked of the model — it confabulated 127 of 130
                            # Q-IDs on this corpus (PHX-1063, PHX-1072).
                            pids=(
                                [PIDTag(pid=pid, confidence=1.0, attached_at=now)]
                                if (pid := pid_for(relation.relation_descriptor))
                                else []
                            ),
                            creation_context="kadmos_relation",
                        )
                    )
                    edges_upserted += 1
                    total_relations_written += 1
                    local_edge_count += 1

                for left_id, right_id in combinations(sorted(resolved_entity_ids), 2):
                    left_node = self.registry.get_by_id(left_id)
                    right_node = self.registry.get_by_id(right_id)
                    if left_node is None or right_node is None:
                        continue
                    node_pairs = (
                        (left_node, right_node),
                        (right_node, left_node),
                    )
                    for source_node, target_node in node_pairs:
                        self._append_edge(
                            Edge(
                                source_id=source_node.id,
                                target_id=target_node.id,
                                weight=0.35,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="co_occurrence",
                                relation_descriptor="co_mentions_in_paragraph",
                                creation_context="kadmos_paragraph_density",
                            )
                        )
                        edges_upserted += 1
                        local_edge_count += 1

                paragraph_concept_id: str | None = None
                if paragraph_result.paragraph_concept is not None:
                    paragraph_concept = paragraph_result.paragraph_concept
                    concept_description = paragraph_concept.description or paragraph_concept.label
                    semantic_vector = await self.vectorizer.semantic(concept_description)
                    frame_vector = await self.vectorizer.frame(paragraph_concept.label)
                    description_vector = await self.vectorizer.description(concept_description)
                    nodes_embedded += 1
                    decision = self.linker.link_reference(
                        label=paragraph_concept.label,
                        description=concept_description,
                        tags=list(paragraph_concept.tags) + ["paragraph_concept"],
                        qids=[],
                        semantic_vector=semantic_vector,
                        frame_vector=frame_vector,
                        description_vector=description_vector,
                        context_node_ids=resolved_entity_ids,
                    )
                    paragraph_concept_id = str(decision.node.id)
                    local_node_ids.add(paragraph_concept_id)
                    paragraph_concept_node_ids.add(paragraph_concept_id)
                    if decision.is_new:
                        nodes_upserted += 1
                    else:
                        referenced_existing.add(str(decision.node.id))
                    paragraph_concept_count += 1

                    self._append_edge(
                        Edge(
                            source_id=paragraph_anchor.id,
                            target_id=decision.node.id,
                            weight=0.8,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="hierarchy",
                            relation_descriptor="has_paragraph_concept",
                            creation_context="kadmos_paragraph_concept",
                        )
                    )
                    self._append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=decision.node.id,
                            weight=0.7,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="hierarchy",
                            relation_descriptor="summarised_as",
                            creation_context="kadmos_paragraph_concept",
                        )
                    )
                    edges_upserted += 2
                    local_edge_count += 2

                    for basis_label in paragraph_concept.basis_concepts:
                        basis_node = resolved_by_label.get(basis_label)
                        if basis_node is None:
                            relation_drop_count += 1
                            continue
                        self._append_edge(
                            Edge(
                                source_id=decision.node.id,
                                target_id=basis_node.id,
                                weight=0.85,
                                born_at=now,
                                last_fired_at=now,
                                relation_kind="hierarchy",
                                relation_descriptor="abstracts_over",
                                creation_context="kadmos_paragraph_concept",
                            )
                        )
                        edges_upserted += 1
                        local_edge_count += 1
                relation_stage_duration_s += time.monotonic() - relation_started
            else:
                paragraph_concept_id = None

            # One row per paragraph, because the paragraph is the activation
            # context doctrine counts — "many distinct activation contexts", not
            # many mentions in one. Buffered like the query-path firings and
            # folded in by the tick; ingestion writes nodes directly but this is
            # a counter update on rows it is not otherwise rewriting.
            if referenced_existing:
                firing_passes += 1
                self.mesh.firings.append_firing(referenced_existing)

            paragraph_units.append(
                _ParagraphUnit(
                    paragraph_number=paragraph_index,
                    paragraph_anchor_id=str(paragraph_anchor.id),
                    chunk_id=str(chunk.id),
                    entity_ids=resolved_entity_ids,
                    paragraph_concept_id=paragraph_concept_id,
                    local_node_ids=local_node_ids,
                    local_edge_count=local_edge_count,
                )
            )

        cross_started = time.monotonic()
        structural_pairs, structural_dropped = _select_structural_pairs(
            paragraph_units, max_neighbours=self.max_structural_neighbours
        )
        if structural_dropped:
            # Doctrine: destruction is permitted under audit, never silently. The
            # capped pairs are recorded so a mesh can always account for the links
            # it chose not to make.
            self._append_audit(
                "mesh_ingest_structural_lattice_capped",
                {
                    "kept_pairs": len(structural_pairs),
                    "dropped_pairs": structural_dropped,
                    "max_neighbours": self.max_structural_neighbours,
                },
            )
        for left_unit, right_unit, shared_count in structural_pairs:
            weight = min(0.25 + (0.10 * shared_count), 0.70)
            for source_id, target_id in (
                (left_unit.paragraph_anchor_id, right_unit.paragraph_anchor_id),
                (right_unit.paragraph_anchor_id, left_unit.paragraph_anchor_id),
            ):
                self._append_edge(
                    Edge(
                        source_id=source_id,  # type: ignore[arg-type]
                        target_id=target_id,  # type: ignore[arg-type]
                        weight=weight,
                        born_at=datetime.now(UTC),
                        last_fired_at=datetime.now(UTC),
                        relation_kind="co_occurrence",
                        relation_descriptor="shares_entities_with",
                        creation_context="kadmos_cross_paragraph",
                    )
                )
                edges_upserted += 1
            cross_pass_link_count += 2
            self._append_audit(
                "mesh_ingest_cross_paragraph_link",
                {
                    "left_paragraph": left_unit.paragraph_number,
                    "right_paragraph": right_unit.paragraph_number,
                    "shared_entity_count": shared_count,
                },
            )

            if (
                left_unit.paragraph_concept_id is not None
                and right_unit.paragraph_concept_id is not None
                and left_unit.paragraph_concept_id != right_unit.paragraph_concept_id
            ):
                self._append_edge(
                    Edge(
                        source_id=left_unit.paragraph_concept_id,  # type: ignore[arg-type]
                        target_id=right_unit.paragraph_concept_id,  # type: ignore[arg-type]
                        weight=min(weight, 0.55),
                        born_at=datetime.now(UTC),
                        last_fired_at=datetime.now(UTC),
                        relation_kind="semantic",
                        relation_descriptor="develops_across_paragraphs",
                        creation_context="kadmos_cross_paragraph",
                    )
                )
                edges_upserted += 1
                cross_pass_link_count += 1

        relation_stage_duration_s += time.monotonic() - cross_started

        # Connectivity metrics read the edge table — the buffer must land first.
        self._flush_edges()
        self.mesh.audit.flush()

        metrics = self._compute_connectivity_metrics(paragraph_units)
        anomalies, recommendations = self._build_connectivity_observations(
            metrics,
            cross_pass_link_count,
        )
        status: Literal["completed", "partial", "failed", "aborted"] = (
            "completed" if llm_failure_count == 0 else "partial"
        )

        resolution_summary = ResolutionSummary(
            qid_claims_dropped=qid_claims_dropped,
            tier_counts={
                _SIGNAL_TO_TIER[signal]: count
                for signal, count in signal_counts.items()
                if count > 0
            },
        )
        parse_error_rate = relation_drop_count / max(
            1,
            total_relations_attempted + llm_failure_count,
        )
        quality_flags = QualityFlags(
            low_tier_ratio=resolution_summary.low_tier_ratio,
            schema_violation_rate=llm_schema_failures / max(1, total_llm_calls),
            parse_error_rate=parse_error_rate,
        )
        verdict, reasoning = ingest_verdict(
            status=status,
            parse_error_rate=quality_flags.parse_error_rate,
            low_tier_ratio=quality_flags.low_tier_ratio,
            anomalies=anomalies,
            thresholds=self.settings.report.thresholds.ingest,
        )

        finished_at = datetime.now(UTC)
        stages = [
            IngestStageReport(name="acquired", duration_s=acquired_duration_s, status="ok"),
            IngestStageReport(name="cleaned", duration_s=cleaned_duration_s, status="ok"),
            IngestStageReport(
                name="sentencized",
                duration_s=sentencized_duration_s,
                status="ok",
            ),
            IngestStageReport(
                name="mentions_extracted",
                duration_s=llm_duration_s,
                status="ok",
            ),
            IngestStageReport(
                name="mentions_resolved",
                duration_s=resolve_stage_duration_s,
                status="ok",
            ),
            IngestStageReport(
                name="relations_extracted",
                duration_s=relation_stage_duration_s,
                status="ok",
            ),
            IngestStageReport(
                name="embedded",
                duration_s=embed_stage_duration_s,
                status="ok",
            ),
            IngestStageReport(
                name="stored",
                duration_s=store_stage_duration_s,
                status="ok",
            ),
        ]

        audit_run_id = self._append_audit(
            "mesh_ingest_run",
            {
                "paragraphs": len(paragraph_units),
                "mentions": total_mentions,
                "relations_written": total_relations_written,
                "cross_paragraph_links": cross_pass_link_count,
                "metrics": metrics,
            },
        )

        report = IngestRunReport(
            started_at=started_at,
            finished_at=finished_at,
            duration_s=finished_at.timestamp() - started_at.timestamp(),
            status=status,
            verdict=verdict,
            verdict_reasoning=reasoning,
            anomalies=anomalies,
            recommendations=recommendations,
            audit_log_run_id=audit_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
            word_count=word_count,
            sentence_count=sentence_count,
            chapter_count=None,
            stages=stages,
            ner=NerSummary(
                total_mentions=total_mentions,
                by_type={},
            ),
            resolution=resolution_summary,
            relations=RelationSummary(
                attempted=total_relations_attempted,
                parsed_ok=total_relations_written,
                dropped_schema_violation=llm_schema_failures,
                dropped_evidence_span_violation=relation_drop_count,
                llm_cost_eur=round(total_llm_cost_eur, 6),
            ),
            embedding=EmbeddingSummary(
                nodes_embedded=nodes_embedded,
                embedding_model_id=self.vectorizer.semantic_model_id,
                duration_s=embed_stage_duration_s,
            ),
            store=StoreSummary(
                nodes_upserted=nodes_upserted,
                edges_upserted=edges_upserted,
                idempotent_skips=0,
            ),
            quality_flags=quality_flags,
        )
        report_path = self.report_writer.write(report)

        elapsed = time.monotonic() - started_monotonic
        return {
            "paragraphs": len(paragraph_units),
            "concepts": total_mentions,
            "relations": total_relations_written,
            "paragraph_concepts": paragraph_concept_count,
            "paragraph_concept_nodes": len(paragraph_concept_node_ids),
            # Paragraphs that referenced a node the substrate already had. Zero
            # would mean every reference minted a fresh node — the fragmentation
            # PHX-1097 had to clean up after the fact (PHX-1101).
            "firing_passes": firing_passes,
            "llm_calls": total_llm_calls,
            "llm_cost_eur": round(total_llm_cost_eur, 6),
            "elapsed_s": round(elapsed, 1),
            "source_anchor_id": str(text_anchor_node.id),
            "paragraph_anchor_count": paragraph_anchor_count,
            "cross_paragraph_links": cross_pass_link_count,
            "connectivity": metrics,
            "report_run_id": report.run_id,
            "report_path": str(report_path),
            "verdict": report.verdict,
        }

    async def _vectorize_concepts(
        self,
        concepts: list[LLMConcept],
    ) -> list[tuple[list[float], list[float], list[float]]]:
        # Same text the node will carry, so the stored description and the
        # vector that matches against it cannot drift apart.
        descriptions = [_entity_description(c.label, c.description) for c in concepts]
        labels = [concept.label for concept in concepts]
        semantic_vectors = await self.vectorizer.semantic_many(descriptions)
        frame_vectors = await self.vectorizer.frame_many(labels)
        description_vectors = await self.vectorizer.description_many(descriptions)
        return list(zip(semantic_vectors, frame_vectors, description_vectors, strict=False))

    async def _read_paragraph(
        self,
        text: str,
    ) -> tuple[ParagraphReadingOutput | None, dict[str, Any]]:
        user_prompt = (
            f"PARAGRAPH:\n{text}\n\nExtract the concepts, relations, and paragraph concept."
        )
        started = time.monotonic()
        try:
            result = await self.llm.complete(
                prompt=user_prompt,
                system=SYSTEM_PROMPT,
                json_schema=ParagraphReadingOutput.model_json_schema(),
                temperature=0.1,
                timeout_s=45,
            )
            # Providers differ in how strictly they honour a JSON schema. DeepSeek
            # returns name/wikidata_id/subject/object, which failed validation
            # outright — every paragraph became a schema failure and ingestion
            # produced nothing but source anchors. Normalising known aliases first
            # keeps a good extraction that merely disagrees on spelling; anything
            # structurally unusable still fails validation below.
            payload = normalize_reading_payload(json.loads(result.text))
            output = ParagraphReadingOutput.model_validate(payload)
            return output, {
                "cost_eur": result.cost_eur,
                "duration_s": time.monotonic() - started,
                "failed": False,
                "schema_failed": False,
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM paragraph reading failed: %s", exc)
            return None, {
                "cost_eur": 0.0,
                "duration_s": time.monotonic() - started,
                "failed": True,
                "schema_failed": True,
            }

    def _append_edge(self, edge: Edge) -> None:
        """Buffer an edge; the batch is flushed by :meth:`_flush_edges`.

        Each Lance append is a transaction whose cost grows with the table, so
        per-edge writes dominated ingestion: measured at 119 ms/edge on a
        27.8k-edge mesh (~21 s for one paragraph's ~180 edges) versus 0.01 s for
        the same edges appended as one batch — a ~2000x difference, and the real
        reason a full read collapsed (PHX-1050, and the cost attributed to
        PHX-1047). `append_edge` is literally `append_edges([edge])`, so batching
        changes throughput and nothing else.

        The linker is told about each edge immediately: its adjacency is in-memory
        and feeds context scoring during this same run, so it must not wait for
        the flush.
        """
        self._pending_edges.append(edge)
        self.linker.remember_edge(edge)
        # Bounded so a book-length read neither holds every edge in memory nor
        # loses a whole run's writes to one crash. The batch is what matters, not
        # its exactness: 512 appends in one transaction is already ~2000x cheaper
        # than 512 transactions.
        if len(self._pending_edges) >= _EDGE_FLUSH_BATCH:
            self._flush_edges()

    def _flush_edges(self) -> None:
        """Write the buffered edges as one Lance append."""
        if not self._pending_edges:
            return
        self.mesh.edges.append_edges(self._pending_edges)
        self._pending_edges = []

    def _append_audit(self, action: str, detail: dict[str, Any]) -> str:
        return self.mesh.audit.append(action=action, detail=detail)

    def _stage_audit(self, action: str, detail: dict[str, Any]) -> str:
        """Stamp a per-item audit row now, write it with the batch.

        Only the hot path uses this. The run-level entries keep writing straight
        through, so a crash mid-paragraph still leaves a record of what the run
        was. Measured at 269.8 ms per unbatched write inside a real ingest —
        the largest single term in the resolution stage (PHX-1061).
        """
        return self.mesh.audit.stage(action=action, detail=detail)

    def _compute_connectivity_metrics(
        self,
        paragraph_units: list[_ParagraphUnit],
    ) -> dict[str, float | int]:
        edges = self.mesh.edges.load_all_edges()
        adjacency: dict[str, set[str]] = {}
        node_ids: set[str] = set()
        for edge in edges:
            source_id = str(edge.source_id)
            target_id = str(edge.target_id)
            node_ids.add(source_id)
            node_ids.add(target_id)
            adjacency.setdefault(source_id, set()).add(target_id)
            adjacency.setdefault(target_id, set()).add(source_id)

        components: list[set[str]] = []
        unvisited = set(node_ids)
        while unvisited:
            start = unvisited.pop()
            stack = [start]
            component = {start}
            while stack:
                current = stack.pop()
                for neighbour in adjacency.get(current, set()):
                    if neighbour in unvisited:
                        unvisited.remove(neighbour)
                        component.add(neighbour)
                        stack.append(neighbour)
            components.append(component)

        largest_component_ratio = 0.0
        if components and node_ids:
            largest_component_ratio = len(max(components, key=len)) / len(node_ids)

        consolidated_ids = {str(node.id) for node in self.mesh.nodes.load_all_consolidated()}
        isolated_consolidated_nodes = sum(
            1 for node_id in consolidated_ids if not adjacency.get(node_id)
        )
        paragraph_degrees = []
        for unit in paragraph_units:
            local_degree_sum = sum(
                len(adjacency.get(node_id, set()) & unit.local_node_ids)
                for node_id in unit.local_node_ids
            )
            paragraph_degrees.append(local_degree_sum / max(1, len(unit.local_node_ids)))

        return {
            "largest_connected_component_ratio": round(largest_component_ratio, 4),
            "edge_to_node_ratio": round(len(edges) / max(1, len(node_ids)), 4),
            "paragraph_local_average_degree": round(
                sum(paragraph_degrees) / max(1, len(paragraph_degrees)),
                4,
            ),
            "isolated_consolidated_nodes": isolated_consolidated_nodes,
        }

    def _build_connectivity_observations(
        self,
        metrics: dict[str, float | int],
        cross_paragraph_links: int,
    ) -> tuple[list[str], list[str]]:
        anomalies: list[str] = []
        recommendations: list[str] = []
        if float(metrics["largest_connected_component_ratio"]) < 0.75:
            anomalies.append("graph_fragmented")
            recommendations.append(
                "Inspect paragraph co-mention density and cross-paragraph linking thresholds."
            )
        if int(metrics["isolated_consolidated_nodes"]) > 3:
            anomalies.append("isolated_consolidated_nodes")
            recommendations.append(
                "Review concept extraction and source-anchor attachment for orphan nodes."
            )
        if cross_paragraph_links == 0:
            anomalies.append("no_cross_paragraph_links")
            recommendations.append(
                "Use a longer source or lower cross-paragraph overlap thresholds for smoke checks."
            )
        return anomalies, recommendations


def _entity_description(label: str, description: str) -> str:
    """Compose the doctrine's Tier-1 description: name **plus** discriminators.

    MESH_SUBSTRATE §"Tier-1+ — Consolidated Node" specifies `description` as
    "short discriminating text — for entities: name + key discriminators". The
    reading model returns those two apart: a label ("Zeus") and a bare
    discriminator ("King of the gods, god of the sky and thunder, son of
    Cronos"). Storing only the discriminator throws the identity away.

    Measured before this change: 8 of 8 concepts lost their name on the way in.
    No node in a 6,816-node Theogony mesh was called Cronus, three distinct
    nymphs all read "A nymph whose name derives from a land over which she
    presides", and eight separate nodes described Zeus as son of Cronos without
    any of them saying Zeus. Identity matching, deduplication and name queries
    all ran on text that had had the name removed (PHX-1065).

    The name goes at the head so every mention of one entity shares a prefix —
    that is what makes two descriptions of the same figure land near each other
    under `description_vector`, which is the identity-matching surface.
    """
    name = (label or "").strip()
    body = (description or "").strip()
    if not name:
        return body
    if not body:
        return name
    if body.lower().startswith(name.lower()):
        return body
    return f"{name} — {body}"


def _concept_tags(concept: LLMConcept) -> list[str]:
    """Tags for a concept, with its name first.

    The label is a discriminating feature and belongs in the keyword cloud; it
    is also what makes the node findable by name, since the label index is built
    from description plus tags. Without it, `find_consolidated_by_labels("Zeus")`
    could only match nodes whose *description text* happened to contain the word.
    """
    tags = [concept.label.strip()] if concept.label and concept.label.strip() else []
    for tag in dict.fromkeys(concept.tags):
        if tag and tag not in tags:
            tags.append(tag)
    if concept.entity_type and concept.entity_type not in tags:
        tags.append(concept.entity_type)
    return tags or ["concept"]


def _select_structural_pairs(
    units: list[_ParagraphUnit], *, max_neighbours: int
) -> tuple[list[tuple[_ParagraphUnit, _ParagraphUnit, int]], int]:
    """Keep each paragraph's strongest entity-sharing partners (PHX-1049).

    Returns ``(kept_pairs, dropped_count)`` where each kept pair carries its
    shared-entity count, so the caller still weights edges by overlap strength.

    Selection is **union, not intersection**: a pair survives if *either*
    endpoint ranks it in its top ``max_neighbours``. That is what preserves the
    property the lattice was there for — the founding mesh is one connected
    component with no isolated nodes — because a paragraph with few partners
    keeps all of them even when its partners are individually popular.

    ``max_neighbours <= 0`` disables the cap and restores the previous
    all-pairs behaviour, which the A/B in PHX-1049 needs as its control arm.
    """
    scored: list[tuple[int, int, int]] = []
    for left_index, right_index in combinations(range(len(units)), 2):
        shared = units[left_index].entity_ids & units[right_index].entity_ids
        if shared:
            scored.append((left_index, right_index, len(shared)))

    if max_neighbours <= 0 or not scored:
        return [(units[i], units[j], n) for i, j, n in scored], 0

    partners: dict[int, list[tuple[int, int]]] = {}
    for left_index, right_index, count in scored:
        partners.setdefault(left_index, []).append((count, right_index))
        partners.setdefault(right_index, []).append((count, left_index))

    keep: set[tuple[int, int]] = set()
    for index, candidates in partners.items():
        # Strongest overlap first; index breaks ties so the choice is deterministic.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        for _count, other in candidates[:max_neighbours]:
            keep.add((min(index, other), max(index, other)))

    kept = [(units[i], units[j], n) for i, j, n in scored if (i, j) in keep]
    return kept, len(scored) - len(kept)


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs, stripping Gutenberg boilerplate."""
    start_markers = [
        "*** START OF THE PROJECT GUTENBERG EBOOK",
        "*** START OF THIS PROJECT GUTENBERG EBOOK",
    ]
    end_markers = [
        "*** END OF THE PROJECT GUTENBERG EBOOK",
        "*** END OF THIS PROJECT GUTENBERG EBOOK",
    ]
    for marker in start_markers:
        idx = text.find(marker)
        if idx >= 0:
            nl = text.find("\n", idx)
            if nl >= 0:
                text = text[nl + 1 :]
            break
    for marker in end_markers:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
            break

    import re

    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def _count_sentences(text: str) -> int:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    return len(parts)
