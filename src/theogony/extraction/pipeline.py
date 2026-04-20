"""
IngestionPipeline — orchestrates the full extraction chain (Plan §2.5).

Composition order (Plan §2.5 verbatim):

    RawContent → TextCleaner → Sentencizer → NerExtractor →
        BookContextExtractor (optional, E3) →
        EntityResolver → RelationExtractor →
        edge materialisation → KnowledgeStore (optional)

Orchestration responsibilities:

1. **Run-id management.** One ULID per ingest call; threaded into
   every audit row, into the IngestRunReport, and (when present)
   into the KnowledgeStore writes via deterministic node / edge IDs.
2. **Stage timing.** Records per-stage durations (acquired, cleaned,
   sentencized, mentions_extracted, mentions_resolved,
   relations_extracted, embedded, stored) for IngestRunReport and
   for the ``stage_slow`` anomaly rule (Plan §2.11.2).
3. **Book context fan-in.** When configured with a
   :class:`BookContextExtractor`, runs it once at the start and
   pushes the result into ``EntityResolver.set_book_context`` so
   Stage 4 disambiguation has the context Plan §3.4 calls for.
4. **Edge materialisation.** Per central sentence with ≥ 2 mentions,
   calls the relation extractor and materialises edges via
   :func:`materialise_edges`, accumulating drop counts for the
   IngestRunReport.
5. **Optional store writes.** When a :class:`KnowledgeStore` is
   provided, upserts every minted node and edge. Without a store,
   results live only on the returned :class:`IngestionResult`
   (useful for dry-runs and tests).
6. **IngestRunReport finalisation.** Populates every required
   summary, computes the verdict via
   :func:`~theogony.reporting.verdict.ingest_verdict`, attaches
   anomalies and recommendations.

What this module deliberately does NOT do:

- It does not write the report to disk. The CLI (E6+) calls
  :class:`~theogony.reporting.writer.RunReportWriter` after
  ingest returns. Pipeline keeps single-responsibility (compute
  the report); persistence is a separate concern.
- It does not run the embedding stage. ``Embedder`` is E6 work;
  the report's ``embedding`` summary records ``nodes_embedded=0``
  and a placeholder model id when no embedder is configured.
- It does not retry on stage failure. A failure is recorded as
  ``stage.status="failed"``, the pipeline aborts further stages,
  and the report header reports ``status="failed"``. Retry policy
  belongs at the CLI / API layer.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.acquisition.base import RawContent
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, SourceRef
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContext, BookContextExtractor
from theogony.extraction.clean import TextCleaner
from theogony.extraction.edges import build_resolved_lookup, materialise_edges
from theogony.extraction.embedding import EmbeddingProvider
from theogony.extraction.ner import Mention, NerExtractor
from theogony.extraction.relations import ExtractedRelation, RelationExtractor
from theogony.extraction.resolve import EntityResolver, ResolvedMention
from theogony.extraction.sentence import Sentence, Sentencizer
from theogony.reporting.models import (
    EmbeddingSummary,
    IngestRunReport,
    IngestStageReport,
    NerSummary,
    QualityFlags,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
    new_run_id,
)
from theogony.reporting.verdict import ingest_verdict

if TYPE_CHECKING:
    from theogony.core.store import KnowledgeStore

log = get_logger("extraction.pipeline")


# Placeholder model id used in IngestRunReport.embedding when no
# embedder is configured (E5; the embedding stage lands in E6).
_EMBEDDER_NOT_CONFIGURED = "(not configured)"


class IngestionResult(BaseModel):
    """Full output of one ingest call.

    Holds the resolved nodes, materialised edges, the IngestRunReport,
    and the run id (for cross-referencing the audit log). Returned
    even when the pipeline aborted mid-stage — the partial report
    is the best signal callers have to triage failure modes.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    run_id: str
    resolved_mentions: list[ResolvedMention] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    book_context: BookContext | None = None
    report: IngestRunReport


class IngestionPipeline:
    """End-to-end ingest orchestrator (Plan §2.5)."""

    def __init__(
        self,
        *,
        entity_resolver: EntityResolver,
        text_cleaner: TextCleaner | None = None,
        sentencizer: Sentencizer | None = None,
        ner_extractor: NerExtractor | None = None,
        relation_extractor: RelationExtractor | None = None,
        book_context_extractor: BookContextExtractor | None = None,
        embedder: EmbeddingProvider | None = None,
        audit_log: ExtractionAuditLog | None = None,
        store: KnowledgeStore | None = None,
        settings: Settings | None = None,
        ner_sentence_limit: int | None = None,
        max_relation_sentences: int | None = None,
    ) -> None:
        self._entity_resolver = entity_resolver
        self._text_cleaner = text_cleaner or TextCleaner()
        self._sentencizer = sentencizer or Sentencizer()
        self._ner_extractor = ner_extractor or NerExtractor()
        self._relation_extractor = relation_extractor
        self._book_context_extractor = book_context_extractor
        self._embedder = embedder
        self._audit_log = audit_log
        self._store = store
        self._settings = settings or Settings()
        # Optional bounds for cheap dev / test runs against full books.
        # ``ner_sentence_limit`` clips the sentence list before NER;
        # ``max_relation_sentences`` clips the per-sentence relation
        # extraction loop. Both default to None (process everything).
        self._ner_sentence_limit = ner_sentence_limit
        self._max_relation_sentences = max_relation_sentences

    # =================================================================== ingest

    async def ingest(self, raw_content: RawContent) -> IngestionResult:
        """Run the full pipeline on ``raw_content`` and return the result.

        Always returns an :class:`IngestionResult` — even when a
        stage fails. Consumers should check
        ``result.report.status`` for the high-level outcome and
        ``result.report.stages`` for per-stage detail.
        """
        run_id = new_run_id()
        started_at = datetime.now(UTC)
        run_started_perf = time.perf_counter()
        stages: list[IngestStageReport] = []
        status: str = "completed"

        identifier = f"{raw_content.source_type}:{raw_content.identifier}"
        log.info("ingest start run_id=%s source=%s", run_id, identifier)

        # ---- acquired ----
        # Plan §2.11.1 reports the acquired stage even though the
        # acquisition adapter ran upstream — it gives the report a
        # baseline duration for ``bytes_acquired`` and a place to
        # record acquisition anomalies if any.
        stages.append(
            IngestStageReport(
                name="acquired",
                duration_s=0.0,
                status="ok",
                notes=f"{raw_content.bytes_acquired} bytes from {raw_content.source_type}",
            )
        )

        book_source_ref = raw_content.to_source_ref()

        # ---- cleaned ----
        cleaned, cleaned_status = await self._stage(
            stages,
            "cleaned",
            self._stage_cleaned,
            raw_content,
        )
        if cleaned_status != "ok":
            return self._abort(
                run_id,
                started_at,
                stages,
                raw_content,
                ner=NerSummary(total_mentions=0),
            )

        # ---- sentencized ----
        sentences, sent_status = await self._stage(
            stages,
            "sentencized",
            self._stage_sentencized,
            cleaned,
        )
        if sent_status != "ok":
            return self._abort(
                run_id,
                started_at,
                stages,
                raw_content,
                ner=NerSummary(total_mentions=0),
            )

        # ---- book context (optional, runs before NER) ----
        book_context: BookContext | None = None
        if self._book_context_extractor is not None:
            book_context, _ = await self._stage(
                stages,
                "cleaned",  # not a stage in the schema; record under existing tag
                self._stage_book_context,
                raw_content,
                sentences,
                run_id,
                stage_name_override="cleaned",
                track_in_stage=False,  # don't append a duplicate stage row
            )
            if book_context is not None:
                self._entity_resolver.set_book_context(book_context)

        # Cap sentences if a dev-mode limit is configured. Keeps live
        # smoke and test runs cheap on full-book inputs.
        active_sentences: list[Sentence] = (
            sentences[: self._ner_sentence_limit]
            if self._ner_sentence_limit is not None
            else list(sentences)
        )

        # ---- mentions_extracted (NER) ----
        mentions_per_sentence, ner_status = await self._stage(
            stages,
            "mentions_extracted",
            self._stage_ner,
            active_sentences,
        )
        if ner_status != "ok":
            return self._abort(
                run_id, started_at, stages, raw_content, ner=NerSummary(total_mentions=0)
            )
        all_mentions: list[Mention] = [m for sl in mentions_per_sentence for m in sl]
        ner_summary = _ner_summary_from(mentions_per_sentence)

        # ---- mentions_resolved ----
        # Snapshot the WikidataClient counters around the resolve stage
        # so the per-run ResolutionSummary reflects *this* run's
        # upstream / cache use, not the client's whole lifetime
        # (W6 §D / §E). Snapshot survives a stage failure: if resolve
        # threw, any partial network work it managed should still be
        # reported honestly.
        wd_counters_before = self._entity_resolver.wikidata_counters_snapshot()
        resolved_mentions, resolved_status = await self._stage(
            stages,
            "mentions_resolved",
            self._stage_resolve,
            all_mentions,
            book_source_ref,
            active_sentences,
            run_id,
        )
        wd_counters_after = self._entity_resolver.wikidata_counters_snapshot()
        if resolved_status != "ok":
            resolved_mentions = []
        resolution_summary = _resolution_summary_from(
            resolved_mentions,
            wd_counters_before=wd_counters_before,
            wd_counters_after=wd_counters_after,
        )
        resolved_lookup = build_resolved_lookup(resolved_mentions)

        # ---- relations_extracted + edge materialisation ----
        all_relations, all_edges, relation_summary = await self._run_relation_stage(
            stages=stages,
            sentences=active_sentences,
            mentions_per_sentence=mentions_per_sentence,
            resolved_lookup=resolved_lookup,
            book_source_ref=book_source_ref,
            run_id=run_id,
        )

        # ---- embedded ----
        embedding_summary, _ = await self._stage(
            stages,
            "embedded",
            self._stage_embed,
            resolved_mentions,
        )
        if embedding_summary is None:
            embedding_summary = EmbeddingSummary(
                nodes_embedded=0,
                embedding_model_id=_EMBEDDER_NOT_CONFIGURED,
                duration_s=0.0,
            )

        # ---- stored ----
        store_summary, store_status = await self._stage(
            stages,
            "stored",
            self._stage_store,
            resolved_mentions,
            all_edges,
        )
        if store_status != "ok" and store_status != "skipped":
            status = "partial"

        # ---- finalize report ----
        finished_at = datetime.now(UTC)
        duration_s = time.perf_counter() - run_started_perf

        # If any stage failed, downgrade the run status.
        if any(s.status == "failed" for s in stages):
            status = "partial" if any(s.status == "ok" for s in stages) else "failed"

        quality_flags = _quality_flags_from(
            resolution_summary=resolution_summary,
            relation_summary=relation_summary,
        )

        verdict, reasoning = ingest_verdict(
            status=status,  # type: ignore[arg-type]
            parse_error_rate=quality_flags.parse_error_rate,
            low_tier_ratio=quality_flags.low_tier_ratio,
            anomalies=[],  # Anomaly detection is a separate concern; pipeline does not invoke
            thresholds=self._settings.report.thresholds.ingest,
        )

        sentence_count = len(sentences)
        word_count = sum(len(sent.text.split()) for sent in sentences)

        report = IngestRunReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=duration_s,
            status=status,  # type: ignore[arg-type]
            verdict=verdict,
            verdict_reasoning=reasoning,
            anomalies=[],
            recommendations=[],
            audit_log_run_id=run_id if self._audit_log is not None else None,
            ingest_run_id=run_id,
            source_type=raw_content.source_type,
            source_identifier=raw_content.identifier,
            word_count=word_count,
            sentence_count=sentence_count,
            chapter_count=None,
            stages=stages,
            ner=ner_summary,
            resolution=resolution_summary,
            relations=relation_summary,
            embedding=embedding_summary,
            store=store_summary,
            quality_flags=quality_flags,
        )

        log.info(
            "ingest end run_id=%s status=%s verdict=%s nodes=%d edges=%d",
            run_id,
            status,
            verdict,
            len(resolved_mentions),
            len(all_edges),
        )

        return IngestionResult(
            run_id=run_id,
            resolved_mentions=resolved_mentions,
            edges=all_edges,
            relations=all_relations,
            book_context=book_context,
            report=report,
        )

    # ============================================================== stage runners

    async def _stage_cleaned(self, raw_content: RawContent) -> Any:
        # TextCleaner is pure / synchronous (Plan §2.5 docstring); call directly.
        return self._text_cleaner.clean(raw_content.content)

    async def _stage_sentencized(self, cleaned: Any) -> list[Sentence]:
        return await self._sentencizer.sentencize(cleaned)

    async def _stage_book_context(
        self,
        raw_content: RawContent,
        sentences: list[Sentence],
        run_id: str,
        stage_name_override: str = "",
        track_in_stage: bool = False,
    ) -> BookContext | None:
        if self._book_context_extractor is None:
            return None
        return await self._book_context_extractor.extract(
            raw_content=raw_content,
            opening_sentences=sentences,
            run_id=run_id,
        )

    async def _stage_ner(self, sentences: list[Sentence]) -> list[list[Mention]]:
        return await self._ner_extractor.extract(sentences)

    async def _stage_resolve(
        self,
        mentions: list[Mention],
        source_ref: SourceRef,
        sentences: Sequence[Sentence],
        run_id: str,
    ) -> list[ResolvedMention]:
        return await self._entity_resolver.resolve_many(
            mentions=mentions,
            source_ref=source_ref,
            sentences=sentences,
            run_id=run_id,
        )

    async def _stage_embed(
        self,
        resolved_mentions: list[ResolvedMention],
    ) -> EmbeddingSummary:
        """Embed the label of every minted node and stamp model-identity metadata.

        When no embedder is configured returns an empty-but-honest
        EmbeddingSummary (model_id="(not configured)", count=0). When
        configured but ``resolved_mentions`` is empty returns
        ``nodes_embedded=0`` with the real model_id — the next ingest
        with content can still re-use this pipeline instance.

        The embedder writes ``embedding`` + ``embedding_model_id`` +
        ``embedding_dim`` directly onto each ResolvedMention.node. The
        pipeline does NOT mint a fresh KnowledgeNode — Pydantic models
        permit attribute assignment and the ResolvedMention map is
        shared with the store stage that runs immediately after.
        """
        if self._embedder is None:
            return EmbeddingSummary(
                nodes_embedded=0,
                embedding_model_id=_EMBEDDER_NOT_CONFIGURED,
                duration_s=0.0,
            )
        if not resolved_mentions:
            return EmbeddingSummary(
                nodes_embedded=0,
                embedding_model_id=self._embedder.model_id,
                duration_s=0.0,
            )
        started_perf = time.perf_counter()
        labels = [rm.node.label for rm in resolved_mentions]
        vectors = await self._embedder.embed_many(labels)
        for rm, vec in zip(resolved_mentions, vectors, strict=True):
            rm.node.embedding = vec
            rm.node.embedding_model_id = self._embedder.model_id
            rm.node.embedding_dim = self._embedder.dim
        duration = time.perf_counter() - started_perf
        return EmbeddingSummary(
            nodes_embedded=len(vectors),
            embedding_model_id=self._embedder.model_id,
            duration_s=duration,
        )

    async def _stage_store(
        self,
        resolved_mentions: list[ResolvedMention],
        edges: list[KnowledgeEdge],
    ) -> StoreSummary:
        """Persist resolved nodes + minted edges via batched upserts.

        PHX-0046: chunks both lists into ``Settings.store.batch_size``
        slices and routes each through ``KnowledgeStore.batch_upsert_*``.
        Backends with bulk-write APIs (Neo4j UNWIND) collapse N
        round-trips to ⌈N/batch_size⌉; backends without (InMemory)
        loop per node — same idempotency contract, same return shape.

        ``nodes_count`` reflects the size of the input list (one
        ResolvedMention = one node, resolver-deduped). The store may
        return the same id back twice on rare ``KnowledgeNode`` ingest
        races; we trust the resolver's dedup and report the input
        count, matching the pre-batching semantics.
        """
        if self._store is None:
            return StoreSummary(nodes_upserted=0, edges_upserted=0)
        batch_size = self._settings.store.batch_size
        node_list = [rm.node for rm in resolved_mentions]
        for node_chunk in _chunks(node_list, batch_size):
            await self._store.batch_upsert_nodes(node_chunk)
        for edge_chunk in _chunks(edges, batch_size):
            await self._store.batch_upsert_edges(edge_chunk)
        return StoreSummary(
            nodes_upserted=len(node_list),
            edges_upserted=len(edges),
        )

    # =========================================================== relation stage

    async def _run_relation_stage(
        self,
        *,
        stages: list[IngestStageReport],
        sentences: list[Sentence],
        mentions_per_sentence: list[list[Mention]],
        resolved_lookup: dict[str, str],
        book_source_ref: SourceRef,
        run_id: str,
    ) -> tuple[list[ExtractedRelation], list[KnowledgeEdge], RelationSummary]:
        """Per-sentence relation extraction + edge materialisation.

        Aggregates per-sentence outputs into RelationSummary fields:
        ``attempted`` counts sentences with ≥ 2 mentions (potential
        relations); ``parsed_ok`` counts edges actually minted;
        ``dropped_evidence_span_violation`` is incremented per
        relation that was filtered by the materialiser's drop
        conditions; ``llm_cost_eur`` is summed from the audit log
        when available, else 0.0 (Plan §2.11 wires cost via
        ExtractionAuditLog rather than per-relation passthrough).
        """
        if self._relation_extractor is None:
            stages.append(
                IngestStageReport(
                    name="relations_extracted",
                    duration_s=0.0,
                    status="skipped",
                    notes="No relation_extractor configured",
                )
            )
            return [], [], RelationSummary()

        started_perf = time.perf_counter()
        all_relations: list[ExtractedRelation] = []
        all_edges: list[KnowledgeEdge] = []
        attempted = 0
        dropped_evidence = 0
        sentence_iter = (
            list(enumerate(sentences))[: self._max_relation_sentences]
            if self._max_relation_sentences is not None
            else list(enumerate(sentences))
        )
        for sent_idx, sent in sentence_iter:
            sent_mentions = mentions_per_sentence[sent_idx]
            if len(sent_mentions) < 2:
                continue
            attempted += 1
            prev = sentences[sent_idx - 1] if sent_idx > 0 else None
            nxt = sentences[sent_idx + 1] if sent_idx + 1 < len(sentences) else None
            try:
                relations = await self._relation_extractor.extract(
                    central_sentence=sent,
                    mentions=sent_mentions,
                    previous_sentence=prev,
                    next_sentence=nxt,
                    run_id=run_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.warning(
                    "relation extraction failed for sentence %d: %s — continuing",
                    sent_idx,
                    exc,
                )
                continue
            all_relations.extend(relations)
            edge_result = materialise_edges(
                relations=relations,
                resolved_lookup=resolved_lookup,
                book_source_ref=book_source_ref,
                central_sentence=sent,
            )
            all_edges.extend(edge_result.edges)
            dropped_evidence += edge_result.dropped_total

        duration = time.perf_counter() - started_perf
        stages.append(
            IngestStageReport(
                name="relations_extracted",
                duration_s=duration,
                status="ok",
                notes=f"{attempted} sentences attempted, {len(all_edges)} edges minted",
            )
        )
        cost_eur = (
            self._audit_log.total_cost_for_run(run_id) if self._audit_log is not None else 0.0
        )
        return (
            all_relations,
            all_edges,
            RelationSummary(
                attempted=attempted,
                parsed_ok=len(all_edges),
                dropped_schema_violation=0,
                dropped_evidence_span_violation=dropped_evidence,
                llm_cost_eur=cost_eur,
            ),
        )

    # =========================================================== infrastructure

    async def _stage(
        self,
        stages: list[IngestStageReport],
        stage_name: str,
        runner: Any,
        *args: Any,
        stage_name_override: str = "",
        track_in_stage: bool = True,
    ) -> tuple[Any, str]:
        """Run a stage runner with timing + error handling.

        Returns ``(result_or_None, status)`` where status is one of
        ``"ok"`` / ``"skipped"`` / ``"failed"``. A "failed" status
        appends an IngestStageReport with status="failed" and the
        exception message in notes.
        """
        if not track_in_stage:
            try:
                result = await runner(*args)
                return result, "ok"
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("stage %s failed: %s", stage_name, exc)
                return None, "failed"

        started_perf = time.perf_counter()
        try:
            result = await runner(*args)
        except Exception as exc:  # pragma: no cover - defensive
            duration = time.perf_counter() - started_perf
            log.warning("stage %s failed: %s", stage_name, exc)
            stages.append(
                IngestStageReport(
                    name=stage_name,  # type: ignore[arg-type]
                    duration_s=duration,
                    status="failed",
                    notes=str(exc)[:500],
                )
            )
            return None, "failed"
        duration = time.perf_counter() - started_perf
        stages.append(
            IngestStageReport(
                name=stage_name,  # type: ignore[arg-type]
                duration_s=duration,
                status="ok",
            )
        )
        return result, "ok"

    def _abort(
        self,
        run_id: str,
        started_at: datetime,
        stages: list[IngestStageReport],
        raw_content: RawContent,
        *,
        ner: NerSummary,
    ) -> IngestionResult:
        """Build a failed-status IngestionResult after an early-stage fault."""
        finished_at = datetime.now(UTC)
        report = IngestRunReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=(finished_at - started_at).total_seconds(),
            status="failed",
            verdict="failed",
            verdict_reasoning="early-stage failure; see stages for details",
            ingest_run_id=run_id,
            source_type=raw_content.source_type,
            source_identifier=raw_content.identifier,
            word_count=0,
            sentence_count=0,
            stages=stages,
            ner=ner,
            resolution=ResolutionSummary(),
            relations=RelationSummary(),
            embedding=EmbeddingSummary(
                nodes_embedded=0,
                embedding_model_id=_EMBEDDER_NOT_CONFIGURED,
                duration_s=0.0,
            ),
            store=StoreSummary(nodes_upserted=0, edges_upserted=0),
            quality_flags=QualityFlags(),
        )
        return IngestionResult(run_id=run_id, report=report)


# ============================================================ summary helpers


def _chunks[T](items: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield successive ``size``-sized chunks of ``items`` (last may be short).

    PHX-0046: used to slice the per-run node + edge lists into batches
    of ``Settings.store.batch_size`` for ``KnowledgeStore.batch_upsert_*``.
    Empty input yields nothing; ``size <= 0`` is a programmer error
    that surfaces as ValueError immediately rather than infinite loop.
    """
    if size <= 0:
        raise ValueError(f"chunk size must be positive; got {size}")
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def _ner_summary_from(mentions_per_sentence: list[list[Mention]]) -> NerSummary:
    """Aggregate the per-sentence NER output into the report's NerSummary."""
    by_type: dict[str, int] = {}
    total = 0
    for sl in mentions_per_sentence:
        for m in sl:
            by_type[m.label] = by_type.get(m.label, 0) + 1
            total += 1
    return NerSummary(total_mentions=total, by_type=by_type)


def _resolution_summary_from(
    resolved_mentions: list[ResolvedMention],
    *,
    wd_counters_before: dict[str, int] | None = None,
    wd_counters_after: dict[str, int] | None = None,
) -> ResolutionSummary:
    """Aggregate resolver output into ResolutionSummary.

    ``wd_counters_before`` / ``wd_counters_after`` are
    :meth:`EntityResolver.wikidata_counters_snapshot` snapshots taken
    around the resolve stage. Their delta populates the
    ``wikidata_api_requests`` / ``cache_hits`` / ``failures_after_retry``
    fields that PR #32 still hard-coded to zero (W6 §E).

    Both default to ``None`` for the convenience of the early-stage
    failure path (:meth:`IngestionPipeline._abort`), which builds a
    summary before any network work has been done; in that case the
    counters stay at zero — honestly so.
    """
    tier_counts: dict[int, int] = {}
    manual = 0
    for rm in resolved_mentions:
        tier_counts[rm.tier] = tier_counts.get(rm.tier, 0) + 1
        if rm.node.manual_resolution_needed:
            manual += 1
    if wd_counters_before is not None and wd_counters_after is not None:
        delta_api = max(0, wd_counters_after["api_requests"] - wd_counters_before["api_requests"])
        delta_hits = max(0, wd_counters_after["cache_hits"] - wd_counters_before["cache_hits"])
        delta_failures = max(
            0,
            wd_counters_after["failures_after_retry"] - wd_counters_before["failures_after_retry"],
        )
    else:
        delta_api = 0
        delta_hits = 0
        delta_failures = 0
    return ResolutionSummary(
        tier_counts=tier_counts,
        wikidata_api_requests=delta_api,
        cache_hits=delta_hits,
        failures_after_retry=delta_failures,
        manual_resolution_needed=manual,
    )


def _quality_flags_from(
    *,
    resolution_summary: ResolutionSummary,
    relation_summary: RelationSummary,
) -> QualityFlags:
    """Compute QualityFlags for the ingest verdict heuristics.

    ``low_tier_ratio`` comes from the resolution summary;
    ``schema_violation_rate`` and ``parse_error_rate`` are derived
    from the relation summary's drop counters. When the relation
    extractor was not configured, both rates are 0.0 (no opportunity
    for violations).
    """
    total_attempted = relation_summary.attempted
    schema_rate = (
        relation_summary.dropped_schema_violation / total_attempted if total_attempted > 0 else 0.0
    )
    # parse_error_rate proxies the rate of relations dropped at any
    # stage of materialisation (evidence_span violation + missing
    # endpoint resolution). The Reviewer agent (PHX-0035) will refine
    # this once the audit log surfaces parse_error tags directly.
    parse_rate = relation_summary.dropped_evidence_span_violation / max(
        total_attempted,
        relation_summary.parsed_ok + relation_summary.dropped_evidence_span_violation,
        1,
    )
    return QualityFlags(
        low_tier_ratio=resolution_summary.low_tier_ratio,
        schema_violation_rate=min(1.0, schema_rate),
        parse_error_rate=min(1.0, parse_rate),
    )


__all__ = [
    "IngestionPipeline",
    "IngestionResult",
]
