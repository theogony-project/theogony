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

When ``settings.llm.provider == "stub"``, production wiring uses
:class:`~theogony.retrieval.synthesize.OfflineAnswerSynthesizer` (PHX-0070)
instead of an LLM call — synthesis stays sub-millisecond. Unit tests that
need scripted :class:`~theogony.agents.llm.StubLLMProvider` prose still
construct :class:`~theogony.retrieval.synthesize.AnswerSynthesizer` directly.
The verdict heuristic (Plan §2.11.2 ``query_verdict``) downgrades reports
whose synthesis_latency_ms exceeds the configured threshold.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider, StubLLMProvider
from theogony.agents.mnemosyne_classifier import MetaQueryClassifier, build_mnemosyne_classifier
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.core.model import Constellation, Layer
from theogony.core.store import KnowledgeStore
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.region_descriptor import compute_region_descriptor
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.stub_detector import StubDetector
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import EmbeddingProvider, LocalSentenceTransformerEmbedder
from theogony.memory.edge_pheromone import EdgePheromoneTracker
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.models import (
    CitationQuality,
    MetaClassificationVerdict,
    MultiHopBreakdown,
    QueryRunReport,
    RegionDescriptor,
    StubVerdict,
    SynthesisBreakdown,
    new_run_id,
)
from theogony.reporting.verdict import query_verdict
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.chronicle_entry_planner import (
    merge_multi_hop_results,
    plan_chronicle_entry_queries,
)
from theogony.retrieval.chronicle_thinking import (
    build_thinking_context,
    plan_chronicle_thinking_refine,
)
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopResult, MultiHopRetriever
from theogony.retrieval.strategies.protocol import RetrievalStrategy
from theogony.retrieval.strategy_factory import build_retrieval_strategy
from theogony.retrieval.synthesize import Answer, AnswerSynthesizerLike
from theogony.retrieval.synthesizer_factory import build_synthesizer

log = get_logger("retrieval.pipeline")

#: Confidence floor above which a citation counts toward
#: ``CitationQuality.citations_with_high_confidence_source``. Mirrors
#: the brief's "node.confidence >= 0.7" rule and the existing
#: ``QueryVerdictThresholds`` semantics.
HIGH_CONFIDENCE_FLOOR = 0.7


async def _retrieve_merged_for_sub_pairs(
    retriever: MultiHopRetriever,
    sub_pairs: list[tuple[str, list[float]]],
    *,
    k: int,
    hops: int,
    layer: Layer | None,
    pheromone_mode: Literal["follow", "ignore", "invert"],
) -> MultiHopResult:
    """Parallel multi-hop retrieve per sub-query; merge by best score."""
    coros = [
        retriever.retrieve(
            emb,
            k=k,
            hops=hops,
            layer=layer,
            pheromone_mode=pheromone_mode,
        )
        for _, emb in sub_pairs
    ]
    partial = await asyncio.gather(*coros)
    return merge_multi_hop_results(list(partial), cap=k)


def compose_query_for_retrieval(
    query: str,
    expansion: str | None,
    *,
    max_chars: int = 14_000,
) -> str:
    """Blend optional dialogue into the text used for embed + chronicle entry planner.

    ``query`` stays the short user turn on ``Constellation.query``; this widens
    the *retrieval* surface so pronouns (e.g. \"he\") and ellipsis resolve against
    prior turns (Explorer chat).
    """
    q = (query or "").strip()
    exp = (expansion or "").strip()
    if not exp:
        return q
    body = f"{exp}\n\n---\nCurrent question:\n{q}"
    if len(body) <= max_chars:
        return body
    head = body[: max_chars - 120].rstrip()
    return f"{head}\n\n[… retrieval context truncated …]\n\nCurrent question:\n{q}"


def derive_cited_edge_ids(
    constellation: Constellation,
    cited_node_ids: Sequence[str],
) -> list[str]:
    """Edges whose both endpoints appear in ``cited_node_ids`` (W2 / PHX-0057)."""
    cited = set(cited_node_ids)
    seen: set[str] = set()
    ordered: list[str] = []
    for e in constellation.edges:
        if not e.edge_id:
            continue
        if e.source_id in cited and e.target_id in cited and e.edge_id not in seen:
            seen.add(e.edge_id)
            ordered.append(e.edge_id)
    return ordered


class QueryResult(BaseModel):
    """Top-level return of ``QueryPipeline.ask``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    answer: Answer
    constellation: Constellation
    report: QueryRunReport
    report_path: Path | None = None
    entry_plan: dict[str, Any] | None = None


class QueryPipeline:
    """End-to-end query orchestration."""

    def __init__(
        self,
        embedder: EmbeddingProvider,
        retriever: MultiHopRetriever,
        assembler: ConstellationAssembler,
        synthesizer: AnswerSynthesizerLike,
        relevance: RelevanceTracker,
        *,
        strategy: RetrievalStrategy | None = None,
        settings: Settings | None = None,
        report_writer: RunReportWriter | None = None,
        edge_pheromone: EdgePheromoneTracker | None = None,
        stub_detector: StubDetector | None = None,
        mnemosyne: MetaQueryClassifier | None = None,
        entry_planner_llm: LLMProvider | None = None,
        growth_bridge: GrowthBridge | None = None,
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
        self._edge_pheromone = edge_pheromone or EdgePheromoneTracker(
            retriever.store,
            delta=self._settings.relevance.edge_pheromone_delta,
        )
        self._stub_detector = stub_detector or StubDetector(
            self._settings.curiosity.stub_thresholds,
        )
        self._mnemosyne = mnemosyne or build_mnemosyne_classifier(self._settings, None)
        self._entry_planner_llm = entry_planner_llm
        self._growth_bridge = growth_bridge

    async def ask(
        self,
        query: str,
        *,
        layer: Layer | None = None,
        k: int = 10,
        hops: int = 2,
        strategy: Literal["fixed_depth", "edge_product", "cluster_narrow"] | None = None,
        pheromone_mode: Literal["follow", "ignore", "invert"] = "follow",
        thinking_max: int | None = None,
        synthesis_conversation_context: str | None = None,
        retrieval_query_expansion: str | None = None,
    ) -> QueryResult:
        """Run the retrieval loop for ``query`` and return answer + constellation + report.

        Optional ``thinking_max`` (0–8): after the first synthesize pass, the
        entry LLM may inspect the constellation and propose **new** search strings
        for up to that many **extra** retrieve+assemble+synthesize rounds (stub LLM
        disables thinking). When ``None``, uses
        ``settings.retrieval.chronicle_thinking.max_rounds``.

        Optional ``synthesis_conversation_context``: prepended to the synthesis user
        prompt for multi-turn chat (Explorer).

        Optional ``retrieval_query_expansion``: prior dialogue (same shape as the
        synthesis block) folded into the **embedding and chronicle entry planner**
        input via :func:`compose_query_for_retrieval` so follow-ups retrieve relevant
        nodes; ``Constellation.query`` remains the short ``query`` string.
        """
        run_id = new_run_id()
        started_at = datetime.now(UTC)
        run_perf = time.perf_counter()
        thinking_cfg = self._settings.retrieval.chronicle_thinking
        if thinking_max is None:
            effective_thinking = max(0, min(8, thinking_cfg.max_rounds))
        else:
            effective_thinking = max(0, min(8, int(thinking_max)))
        log.info(
            "ask start run_id=%s query=%r k=%d hops=%d strategy=%s thinking_max=%d",
            run_id,
            query,
            k,
            hops,
            strategy or "default",
            effective_thinking,
        )

        q_original = (query or "").strip()
        q_for_retrieval = compose_query_for_retrieval(q_original, retrieval_query_expansion)
        planner_cfg = self._settings.retrieval.chronicle_entry_planner
        planner_ms = 0
        plan_rationale = ""
        plan_used_llm = False
        sub_queries = [q_original]

        if (
            planner_cfg.enabled
            and self._entry_planner_llm is not None
            and not isinstance(self._entry_planner_llm, StubLLMProvider)
        ):
            t_pl = time.perf_counter()
            try:
                plan = await plan_chronicle_entry_queries(
                    llm=self._entry_planner_llm,
                    user_query=q_for_retrieval,
                    limits=planner_cfg,
                )
                sub_queries = plan.search_queries or [q_original]
                plan_rationale = plan.rationale
                plan_used_llm = plan.used_llm
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("chronicle entry planner failed: %s", exc)
                sub_queries = [q_original]
            planner_ms = int((time.perf_counter() - t_pl) * 1000)

        # ---- 1. embed (region / report vector — widened when ``retrieval_query_expansion`` set)
        embed_perf = time.perf_counter()
        query_embedding = await self._embedder.embed(q_for_retrieval)
        uniq_subs = list(dict.fromkeys(sub_queries))
        sub_pairs: list[tuple[str, list[float]]] = []
        if len(uniq_subs) == 1 and uniq_subs[0].casefold() == q_original.casefold():
            sub_pairs = [(q_original, query_embedding)]
        else:
            vecs = await self._embedder.embed_many(uniq_subs)
            sub_pairs = list(zip(uniq_subs, vecs, strict=True))
        embedding_duration_ms = int((time.perf_counter() - embed_perf) * 1000)

        # ---- 2. retrieve (parallel multi-hop per sub-query, merged by best score)
        retriever = self._retriever
        if strategy is not None:
            retriever = MultiHopRetriever(
                self._retriever.store,
                strategy=build_retrieval_strategy(
                    self._retriever.store, self._settings, override=strategy
                ),
            )
        retrieval_result = await _retrieve_merged_for_sub_pairs(
            retriever,
            sub_pairs,
            k=k,
            hops=hops,
            layer=layer,
            pheromone_mode=pheromone_mode,
        )
        retrieval_result.duration_ms += planner_ms

        tried_subqueries: list[str] = list(dict.fromkeys(uniq_subs))
        thinking_rounds: list[dict[str, Any]] = []
        synthesis_total_latency_ms = 0

        entry_plan: dict[str, Any] = {
            "used_llm_planner": plan_used_llm,
            "sub_queries": sub_queries,
            "rationale": plan_rationale,
            "planner_duration_ms": planner_ms,
            "thinking": {
                "max_rounds_requested": effective_thinking,
                "rounds": thinking_rounds,
            },
        }

        # ---- 3–4. assemble + synthesize (+ optional thinking rounds)
        constellation = await self._assembler.assemble(
            query, retrieval_result, query_embedding=query_embedding
        )
        synthesis_perf = time.perf_counter()
        answer = await self._synthesizer.synthesize(
            constellation,
            run_id=run_id,
            conversation_context=synthesis_conversation_context,
        )
        synthesis_total_latency_ms += int((time.perf_counter() - synthesis_perf) * 1000)

        for round_idx in range(effective_thinking):
            if self._entry_planner_llm is None or isinstance(
                self._entry_planner_llm,
                StubLLMProvider,
            ):
                break
            ctx = build_thinking_context(
                user_query=q_original,
                constellation=constellation,
                answer=answer,
                tried_subqueries=tried_subqueries,
                round_index=round_idx + 1,
            )
            decision = await plan_chronicle_thinking_refine(
                llm=self._entry_planner_llm,
                user_query=q_original,
                context=ctx,
                thinking_limits=thinking_cfg,
                planner_limits=planner_cfg,
            )
            if not decision.continue_retrieval or not decision.search_queries:
                thinking_rounds.append(
                    {
                        "round": round_idx + 1,
                        "continue": False,
                        "search_queries": [],
                        "rationale": decision.rationale,
                        "duration_ms": decision.duration_ms,
                        "used_llm": decision.used_llm,
                    }
                )
                break
            retrieval_result.duration_ms += decision.duration_ms
            new_queries = decision.search_queries
            for q in new_queries:
                if q.casefold() not in {x.casefold() for x in tried_subqueries}:
                    tried_subqueries.append(q)
            emb_extra = time.perf_counter()
            new_vecs = await self._embedder.embed_many(new_queries)
            embedding_duration_ms += int((time.perf_counter() - emb_extra) * 1000)
            new_pairs = list(zip(new_queries, new_vecs, strict=True))
            merged_more = await _retrieve_merged_for_sub_pairs(
                retriever,
                new_pairs,
                k=k,
                hops=hops,
                layer=layer,
                pheromone_mode=pheromone_mode,
            )
            retrieval_result = merge_multi_hop_results(
                [retrieval_result, merged_more],
                cap=k,
            )
            constellation = await self._assembler.assemble(
                query, retrieval_result, query_embedding=query_embedding
            )
            synthesis_perf = time.perf_counter()
            answer = await self._synthesizer.synthesize(
                constellation,
                run_id=run_id,
                conversation_context=synthesis_conversation_context,
            )
            synthesis_total_latency_ms += int((time.perf_counter() - synthesis_perf) * 1000)
            thinking_rounds.append(
                {
                    "round": round_idx + 1,
                    "continue": True,
                    "search_queries": new_queries,
                    "rationale": decision.rationale,
                    "duration_ms": decision.duration_ms,
                    "used_llm": decision.used_llm,
                }
            )

        entry_plan["thinking"]["rounds_completed"] = len(
            [r for r in thinking_rounds if r.get("continue") is True]
        )

        # ---- 5. finalize report (BEFORE the relevance write-back)
        finished_at = datetime.now(UTC)
        duration_s = time.perf_counter() - run_perf
        report = await self._finalize_report(
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
            query_embedding=query_embedding,
        )

        # ---- 6. persist (optional)
        report_path: Path | None = None
        if self._report_writer is not None:
            report_path = self._report_writer.write(report)

        # ---- 7. write-back (after the report is captured; follow-mode only)
        if pheromone_mode == "follow":
            cited_edge_ids = derive_cited_edge_ids(constellation, answer.cited_node_ids)
            await asyncio.gather(
                self._relevance.bump_all(answer.cited_node_ids),
                self._edge_pheromone.bump_all(cited_edge_ids),
            )

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
            entry_plan=entry_plan,
        )

    # ============================================================== finalize

    async def _finalize_report(
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
        query_embedding: list[float],
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

        stub_verdict: StubVerdict = self._stub_detector.detect(
            query=query,
            constellation=constellation,
            answer=answer,
            named_entities_in_query=None,
        )
        region_descriptor: RegionDescriptor = compute_region_descriptor(
            query_embedding=query_embedding,
            constellation=constellation,
            retrieval_result=retrieval_result,
        )

        # --- W7-A: emit a CuriosityRunReport when the growth bridge is wired
        # and the stub signal warrants it. The bridge is a pure decision; the
        # writer is the side effect. Default-off in ordinary settings; demo
        # path enables it explicitly via THEOGONY_CURIOSITY__GROWTH_BRIDGE__*.
        if self._growth_bridge is not None and self._report_writer is not None:
            trigger = self._growth_bridge.maybe_emit(
                origin_query=query,
                origin_query_run_id=run_id,
                stub_verdict=stub_verdict,
                region_descriptor=region_descriptor,
            )
            if trigger is not None:
                curiosity_report = CuriosityRunReport(
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_s=duration_s,
                    status="completed",
                    verdict="good",
                    verdict_reasoning="curiosity trigger emitted",
                    trigger=trigger,
                )
                self._report_writer.write(curiosity_report)

        meta_classification = await self._mnemosyne.classify(
            query=query,
            answer=answer,
            cited_node_ids=answer.cited_node_ids,
            constellation=constellation,
        )

        if (
            meta_classification.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
            and answer.cited_node_ids
        ):
            await self._retriever.store.mark_self_referential(answer.cited_node_ids, run_id)

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
            stub_verdict=stub_verdict,
            region_descriptor=region_descriptor,
            meta_classification=meta_classification,
            cited_node_ids=list(answer.cited_node_ids),
        )


async def build_pipeline_from_settings(
    settings: Settings,
    store: KnowledgeStore,
    *,
    audit_log: ExtractionAuditLog | None = None,
    report_writer: RunReportWriter | None = None,
    llm: LLMProvider | None = None,
) -> QueryPipeline:
    """Construct a production-shaped :class:`QueryPipeline` (PHX-0070 tests).

    Matches API/CLI/MCP wiring: sentence-transformer embedder (with warm-up),
    ``build_llm_from_settings`` + ``build_synthesizer``, default retrieval strategy.
    """
    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    await embedder.embed("warmup")
    resolved_llm = llm if llm is not None else build_llm_from_settings(settings)
    synthesizer = build_synthesizer(settings, resolved_llm, audit_log=audit_log)
    mnemosyne = build_mnemosyne_classifier(settings, resolved_llm)
    return QueryPipeline(
        embedder=embedder,
        retriever=MultiHopRetriever(
            store,
            strategy=build_retrieval_strategy(store, settings),
        ),
        assembler=ConstellationAssembler(store),
        synthesizer=synthesizer,
        relevance=RelevanceTracker(
            store,
            relevance_delta=settings.relevance.relevance_delta,
        ),
        settings=settings,
        report_writer=report_writer,
        edge_pheromone=EdgePheromoneTracker(
            store,
            delta=settings.relevance.edge_pheromone_delta,
        ),
        stub_detector=StubDetector(settings.curiosity.stub_thresholds),
        mnemosyne=mnemosyne,
        entry_planner_llm=resolved_llm,
        growth_bridge=GrowthBridge(settings.curiosity.growth_bridge),
    )


__all__ = ["HIGH_CONFIDENCE_FLOOR", "QueryPipeline", "QueryResult", "build_pipeline_from_settings"]
