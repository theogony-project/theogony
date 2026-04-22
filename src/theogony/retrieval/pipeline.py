"""
QueryPipeline — orchestrates the retrieval stack from a user query to a cited answer.

Plan §4.2, §2.6, §2.11.1; E8 brief.

Composes the four E8 components (embedder → multi_hop → assembler →
synthesizer), then routes the cited node ids through ``RelevanceTracker``
for the post-answer write-back (Plan §4.3). Emits a ``QueryRunReport``
via ``_finalize_report()`` at the end of every ``ask`` call. The report
is **always** computed (so callers can inspect it on
``QueryResult.report`` even without a writer); it is **persisted** only
when a ``RunReportWriter`` was provided (CI tests skip; CLI/API
provide).

Latency budget (Plan §4.2 demo target). End-to-end p95 < 2 s on the
demo machine. Component shares (rough):

  embed query     <  50 ms (BGE-small CPU)
  multi_hop      ~100-500 ms (Neo4j HNSW + traversal)
  assemble       <100 ms
  synthesize    ~1.5-3 s with real Gemini

Against StubLLM (CI), synthesis is ~0 ms — so the StubLLM-based
``test_retrieval_pipeline.py`` p95 budget is much tighter than the
real-LLM one. The pipeline does not enforce the budget; the verdict
heuristic (Plan §2.11.2 ``query_verdict``) downgrades reports whose
synthesis_latency_ms exceeds the configured threshold.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.core.model import Constellation, Layer
from theogony.extraction.embedding import EmbeddingProvider
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.models import (
    CitationQuality,
    MultiHopBreakdown,
    QueryRunReport,
    SynthesisBreakdown,
    new_run_id,
)
from theogony.reporting.verdict import query_verdict
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopResult, MultiHopRetriever
from theogony.retrieval.strategies.protocol import RetrievalStrategy
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesize import Answer, AnswerSynthesizer

log = get_logger("retrieval.pipeline")

#: Confidence floor above which a citation counts toward
#: ``CitationQuality.citations_with_high_confidence_source``. Mirrors
#: the brief's "node.confidence >= 0.7" rule and the existing
#: ``QueryVerdictThresholds`` semantics.
HIGH_CONFIDENCE_FLOOR = 0.7


class QueryResult(BaseModel):
    """Top-level return of ``QueryPipeline.ask``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    answer: Answer
    constellation: Constellation
    report: QueryRunReport
    report_path: Path | None = None


class QueryPipeline:
    """End-to-end query orchestration."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        retriever: MultiHopRetriever,
        assembler: ConstellationAssembler,
        synthesizer: AnswerSynthesizer,
        relevance: RelevanceTracker,
        *,
        strategy: RetrievalStrategy | None = None,
        settings: Settings | None = None,
        report_writer: RunReportWriter | None = None,
    ) -> None:
        self._embedder = embedder
        if strategy is not None:
            self._retriever = MultiHopRetriever(retriever.store, strategy=strategy)
        else:
            self._retriever = retriever
        self._assembler = assembler
        self._synthesizer = synthesizer
        self._relevance = relevance
        self._settings = settings or Settings()
        self._report_writer = report_writer

    async def ask(
        self,
        query: str,
        *,
        layer: Layer | None = None,
        k: int = 10,
        hops: int = 2,
        strategy: Literal["fixed_depth", "edge_product"] | None = None,
    ) -> QueryResult:
        """Run the retrieval loop for ``query`` and return answer + constellation + report.

        Order of operations (matters for the report's "constellation as
        the user saw it" property):

            1. Embed query
            2. multi_hop retrieve
            3. Assemble Constellation
            4. Synthesize Answer (LLM)
            5. ``_finalize_report`` — captures pre-bump confidence /
               relevance values
            6. Persist report (if a writer was supplied)
            7. RelevanceTracker.bump_all on the cited ids

        Step 5 happens before step 7 on purpose. The report records the
        Chronik state *as observed* by this query — bumping first
        would have it record post-bump relevance, which is not what
        the user saw.
        """
        run_id = new_run_id()
        started_at = datetime.now(UTC)
        run_perf = time.perf_counter()
        log.info(
            "ask start run_id=%s query=%r k=%d hops=%d strategy=%s",
            run_id,
            query,
            k,
            hops,
            strategy or "default",
        )

        # ---- 1. embed
        embed_perf = time.perf_counter()
        query_embedding = await self._embedder.embed(query)
        embedding_duration_ms = int((time.perf_counter() - embed_perf) * 1000)

        # ---- 2. retrieve
        retriever = self._retriever
        if strategy is not None:
            retriever = MultiHopRetriever(
                self._retriever.store,
                strategy=build_retrieval_strategy(
                    self._retriever.store, self._settings, override=strategy
                ),
            )
        retrieval_result = await retriever.retrieve(query_embedding, k=k, hops=hops, layer=layer)

        # ---- 3. assemble
        constellation = await self._assembler.assemble(
            query, retrieval_result, query_embedding=query_embedding
        )

        # ---- 4. synthesize
        synthesis_perf = time.perf_counter()
        answer = await self._synthesizer.synthesize(constellation, run_id=run_id)
        synthesis_total_latency_ms = int((time.perf_counter() - synthesis_perf) * 1000)

        # ---- 5. finalize report (BEFORE the relevance write-back)
        finished_at = datetime.now(UTC)
        duration_s = time.perf_counter() - run_perf
        report = self._finalize_report(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=duration_s,
            query=query,
            embedding_duration_ms=embedding_duration_ms,
            retrieval_result=retrieval_result,
            constellation=constellation,
            answer=answer,
            synthesis_total_latency_ms=synthesis_total_latency_ms,
        )

        # ---- 6. persist (optional)
        report_path: Path | None = None
        if self._report_writer is not None:
            report_path = self._report_writer.write(report)

        # ---- 7. write-back (after the report is captured)
        await self._relevance.bump_all(answer.cited_node_ids)

        log.info(
            "ask end run_id=%s status=%s verdict=%s nodes=%d edges=%d cited=%d",
            run_id,
            report.status,
            report.verdict,
            report.constellation_node_count,
            report.constellation_edge_count,
            report.citation_quality.cited_node_count,
        )

        return QueryResult(
            answer=answer,
            constellation=constellation,
            report=report,
            report_path=report_path,
        )

    # ============================================================== finalize

    def _finalize_report(
        self,
        *,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        duration_s: float,
        query: str,
        embedding_duration_ms: int,
        retrieval_result: MultiHopResult,
        constellation: Constellation,
        answer: Answer,
        synthesis_total_latency_ms: int,
    ) -> QueryRunReport:
        """Compose ``QueryRunReport`` from accumulated observations.

        The report's ``status`` is ``"completed"`` unless the synthesizer
        returned an empty answer — that maps to ``"partial"``. We never
        emit ``"failed"`` here because synthesizer transport errors are
        already swallowed into an empty answer (Plan §2.11.4 — the
        writer never aborts; the verdict captures the failure mode).
        """
        # ---- multi_hop breakdown (PHX-0051: nodes_per_hop carries the
        # truthful "store does not expose per-hop visibility" None;
        # final_node_count is always populated.)
        multi_hop = MultiHopBreakdown(
            seed_count=retrieval_result.seed_count,
            nodes_per_hop=retrieval_result.nodes_per_hop,
            final_node_count=retrieval_result.final_node_count,
            duplicates_removed=retrieval_result.duplicates_removed,
            duration_ms=retrieval_result.duration_ms,
        )

        # ---- citation quality
        nodes_by_id = {n.id: n for n in constellation.nodes}
        cited_count = len(answer.cited_node_ids)
        high_conf = 0
        aka_only = 0
        for cid in answer.cited_node_ids:
            slim = nodes_by_id.get(cid)
            if slim is None:
                # Should not happen after the synthesizer's hallucination
                # filter, but be defensive: skip rather than raise.
                continue
            if slim.confidence >= HIGH_CONFIDENCE_FLOOR:
                high_conf += 1
            if slim.source_ref.source_type == "unknown":
                aka_only += 1
        citation_quality = CitationQuality(
            cited_node_count=cited_count,
            citations_with_high_confidence_source=high_conf,
            citations_aka_only=aka_only,
        )

        # ---- synthesis breakdown — copy from the synthesizer's record;
        #      the wall-clock total (including assembler / serialisation
        #      overhead) is captured separately for the verdict.
        synthesis = SynthesisBreakdown(
            input_tokens=answer.synthesis.input_tokens,
            output_tokens=answer.synthesis.output_tokens,
            cost_eur=answer.synthesis.cost_eur,
            latency_ms=answer.synthesis.latency_ms,
        )

        # ---- status: empty answer = partial; otherwise completed.
        # Literal narrowing for the QueryRunReport status field.
        status: Literal["completed", "partial", "failed", "aborted"] = (
            "completed" if answer.text else "partial"
        )
        raised = not bool(answer.text)

        verdict, reasoning = query_verdict(
            raised=raised,
            cited_node_count=cited_count,
            citations_with_high_confidence_source=high_conf,
            synthesis_latency_ms=synthesis_total_latency_ms,
            gaps_identified=len(constellation.gaps),
            thresholds=self._settings.report.thresholds.query,
        )

        return QueryRunReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=duration_s,
            status=status,
            verdict=verdict,
            verdict_reasoning=reasoning,
            anomalies=[],
            recommendations=[],
            audit_log_run_id=None,
            ingest_run_id=None,
            query=query,
            query_length_chars=len(query),
            embedding_duration_ms=embedding_duration_ms,
            multi_hop=multi_hop,
            constellation_node_count=len(constellation.nodes),
            constellation_edge_count=len(constellation.edges),
            suggested_source_count=len(constellation.suggested_sources),
            gaps_identified=len(constellation.gaps),
            synthesis=synthesis,
            citation_quality=citation_quality,
        )


__all__ = ["HIGH_CONFIDENCE_FLOOR", "QueryPipeline", "QueryResult"]
