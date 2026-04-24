"""
SSE growth stream for the Living Demo cockpit (W8).

Emits the locked ``event:`` vocabulary from ``docs/etappes/W8_growth_stream_brief.md``.
Forces GrowthBridge + Argus only inside this module; global
:class:`~theogony.config.settings.Settings` defaults are unchanged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from typing import Any

from theogony.acquisition.base import AcquisitionAdapter, RawContent
from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.argus import ArgusAgent, ArgusOutcome, ArgusResult
from theogony.agents.argus_ingest_runner import RealIngestRunner
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider
from theogony.clustering.cluster_index import ClusterIndex
from theogony.cockpit.explorer import run_explorer_query
from theogony.config.settings import GrowthBridgeSettings, Settings
from theogony.core.store import KnowledgeStore
from theogony.curiosity.argus_wiring import make_argus_agent
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import CuriosityTrigger, TriggerBudget
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import EmbeddingProvider, LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import WikidataClient
from theogony.reporting.models import IngestRunReport
from theogony.reporting.writer import RunReportWriter


def _force_argus_enabled_settings(base: Settings) -> Settings:
    """Argus forced on for the inline demo path only (W8 Knob 5)."""
    argus = base.curiosity.argus.model_copy(update={"enabled": True, "min_candidate_score": 0.0})
    curiosity = base.curiosity.model_copy(update={"argus": argus})
    return base.model_copy(update={"curiosity": curiosity})


class _PersistingIngestRunner(RealIngestRunner):
    """Writes :class:`~theogony.reporting.models.IngestRunReport` after each ingest (cockpit W8)."""

    def __init__(self, pipeline: IngestionPipeline, writer: RunReportWriter) -> None:
        super().__init__(pipeline)
        self._persist_writer = writer

    async def run_from_raw_content(self, raw: RawContent) -> str:
        result = await self._pipeline.ingest(raw)
        self._persist_writer.write(result.report)
        return result.run_id


@asynccontextmanager
async def _cockpit_argus_dispatch_session(
    settings: Settings,
    store: KnowledgeStore,
    adapter: AcquisitionAdapter,
    report_writer: RunReportWriter,
) -> AsyncIterator[ArgusAgent]:
    """Mirror ``argus_dispatch_session`` plus writing each ingest report to disk."""
    audit_path = settings.data_dir / "audit.sqlite"
    llm = build_llm_from_settings(settings)
    embedder = LocalSentenceTransformerEmbedder(
        model_id=settings.embedding.model_id,
        dim=settings.embedding.dim,
    )
    await embedder.embed("warmup")

    wd_cache_cm: AbstractContextManager[WikidataCache | None] = (
        WikidataCache(settings.wikidata_cache_path)
        if settings.wikidata_cache.enabled
        else nullcontext(None)
    )

    with ExtractionAuditLog(audit_path) as audit, wd_cache_cm as wd_cache:
        async with WikidataClient(cache=wd_cache) as wd_client:
            resolver = EntityResolver(client=wd_client, llm=llm, audit_log=audit)
            cluster_index = ClusterIndex()
            await cluster_index.rebuild_from_store(store)
            pipeline = IngestionPipeline(
                entity_resolver=resolver,
                audit_log=audit,
                store=store,
                settings=settings,
                cluster_index=cluster_index,
                embedder=embedder,
                ner_sentence_limit=200,
            )
            runner = _PersistingIngestRunner(pipeline, report_writer)
            yield make_argus_agent(
                settings=settings,
                adapter=adapter,
                ingest_runner=runner,
                llm=llm,
                wd_client=wd_client,
            )


def _sse_chunk(*, event: str | None, data: dict[str, Any]) -> bytes:
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, allow_nan=False))
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode()


@asynccontextmanager
async def _gutenberg_adapter() -> AsyncIterator[GutenbergAdapter]:
    """Real Gutenberg adapter; tests monkeypatch this symbol with a stub context manager."""
    async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
        yield adapter


def _load_curiosity_trigger_for_query_run(
    writer: RunReportWriter,
    query_run_id: str,
) -> CuriosityTrigger | None:
    curiosity_dir = writer.directory_for("curiosity")
    best: tuple[float, CuriosityTrigger] | None = None
    for path in curiosity_dir.glob("*.json"):
        try:
            report = CuriosityRunReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if report.trigger.origin_query_run_id != query_run_id:
            continue
        mtime = path.stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, report.trigger)
    return best[1] if best else None


def _load_ingest_report(writer: RunReportWriter, ingest_run_id: str) -> IngestRunReport | None:
    path = writer.directory_for("ingest") / f"{ingest_run_id}.json"
    if not path.is_file():
        return None
    try:
        return IngestRunReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _emit_argus_phases_from_result(
    *,
    result: ArgusResult,
    ingest: IngestRunReport | None,
) -> list[tuple[str, dict[str, Any]]]:
    """Build (event_name, data) tuples for ``argus_phase`` events after ``process`` returns."""
    out: list[tuple[str, dict[str, Any]]] = []
    oc = result.outcome

    if oc == ArgusOutcome.NO_CANDIDATES:
        out.append(("argus_phase", {"phase": "search", "count": 0, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "score", "count": 0, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "hestia_review", "count": None, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
        return out

    if oc == ArgusOutcome.UNSUPPORTED_SOURCE_TYPE:
        out.append(("argus_phase", {"phase": "search", "count": 0, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "score", "count": 0, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
        return out

    out.append(("argus_phase", {"phase": "search", "count": 1, "elapsed_ms": 0}))
    out.append(("argus_phase", {"phase": "score", "count": 1, "elapsed_ms": 0}))
    out.append(("argus_phase", {"phase": "hestia_review", "count": None, "elapsed_ms": 0}))

    if oc in (ArgusOutcome.REJECTED_BY_HESTIA, ArgusOutcome.NO_CANDIDATE_ABOVE_THRESHOLD):
        out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
        return out

    if oc == ArgusOutcome.DRY_RUN:
        out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
        return out

    if oc == ArgusOutcome.BUDGET_EXCEEDED:
        out.append(
            ("argus_phase", {"phase": "fetch", "count": result.bytes_acquired, "elapsed_ms": 0})
        )
        out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
        return out

    if result.bytes_acquired > 0:
        out.append(
            ("argus_phase", {"phase": "fetch", "count": result.bytes_acquired, "elapsed_ms": 0})
        )

    if ingest is not None and ingest.stages:
        for st in ingest.stages:
            if st.name == "mentions_extracted":
                out.append(
                    (
                        "argus_phase",
                        {
                            "phase": "extract_entities",
                            "count": ingest.ner.total_mentions,
                            "elapsed_ms": int(st.duration_s * 1000),
                        },
                    )
                )
            elif st.name == "relations_extracted":
                out.append(
                    (
                        "argus_phase",
                        {
                            "phase": "extract_relations",
                            "count": ingest.relations.parsed_ok,
                            "elapsed_ms": int(st.duration_s * 1000),
                        },
                    )
                )
            elif st.name == "embedded":
                out.append(
                    (
                        "argus_phase",
                        {
                            "phase": "embed_nodes",
                            "count": ingest.embedding.nodes_embedded,
                            "elapsed_ms": int(st.duration_s * 1000),
                        },
                    )
                )
            elif st.name == "stored":
                out.append(
                    (
                        "argus_phase",
                        {
                            "phase": "store",
                            "count": ingest.store.nodes_upserted,
                            "elapsed_ms": int(st.duration_s * 1000),
                        },
                    )
                )
    elif oc in (ArgusOutcome.APPROVED_AND_INGESTED, ArgusOutcome.APPROVED_INGEST_FAILED):
        # Ingest report missing or empty stages — coarse aggregate (W8 STOP / instrumentation gap).
        n_mentions = ingest.ner.total_mentions if ingest else None
        n_rel = ingest.relations.parsed_ok if ingest else None
        n_emb = ingest.embedding.nodes_embedded if ingest else None
        n_store = ingest.store.nodes_upserted if ingest else None
        out.append(
            ("argus_phase", {"phase": "extract_entities", "count": n_mentions, "elapsed_ms": 0})
        )
        out.append(("argus_phase", {"phase": "extract_relations", "count": n_rel, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "embed_nodes", "count": n_emb, "elapsed_ms": 0}))
        out.append(("argus_phase", {"phase": "store", "count": n_store, "elapsed_ms": 0}))

    out.append(("argus_phase", {"phase": "done", "count": None, "elapsed_ms": 0}))
    return out


async def stream_growth_run(
    *,
    settings: Settings,
    store: KnowledgeStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider | None,
    audit: ExtractionAuditLog | None,
    report_writer: RunReportWriter,
    query: str,
    k: int,
    hops: int,
    thinking_max: int,
    conversation_summary: str | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
) -> AsyncIterator[bytes]:
    """Stream one inline growth run (query + optional Argus) as SSE bytes."""
    forced_bridge = GrowthBridge(GrowthBridgeSettings(enabled=True))
    demo_budget = TriggerBudget(
        max_sources_to_fetch=1,
        max_total_bytes=2 * 1024 * 1024,
        max_llm_eur=0.50,
    )

    try:
        payload = await run_explorer_query(
            settings=settings,
            store=store,
            embedder=embedder,
            llm=llm,
            audit=audit,
            report_writer=report_writer,
            query=query,
            k=k,
            hops=hops,
            thinking_max=thinking_max,
            conversation_summary=conversation_summary,
            conversation_messages=conversation_messages,
            growth_bridge=forced_bridge,
        )
    except Exception as exc:  # pragma: no cover - surfaced as SSE
        yield _sse_chunk(
            event="error",
            data={"where": "query", "message": f"pipeline failed: {exc}"},
        )
        return

    if "error" in payload:
        yield _sse_chunk(
            event="error",
            data={"where": "query", "message": str(payload.get("error", "unknown"))},
        )
        return

    timing = payload.get("timing_ms") or {}
    # Legacy ``data:`` lines (same shape as :func:`stream_explorer_ask_sse`) so the
    # default Explorer script keeps working when growth mode wraps the submit path.
    for phase, key in (
        ("chat_compact", "chat_prep_ms"),
        ("embed", "embed_ms"),
        ("retrieve", "multi_hop_ms"),
        ("synthesize", "synthesis_ms"),
    ):
        legacy = {"type": "phase", "phase": phase, "ms": int(timing.get(key, 0))}
        yield ("data: " + json.dumps(legacy, allow_nan=False) + "\n\n").encode()
    legacy_done = {"type": "complete", "payload": payload}
    yield ("data: " + json.dumps(legacy_done, allow_nan=False) + "\n\n").encode()

    # Locked W8 vocabulary (typed ``event:`` lines) for curl / growth panel.
    for phase, key in (
        ("embed", "embed_ms"),
        ("retrieve", "multi_hop_ms"),
        ("synthesize", "synthesis_ms"),
    ):
        yield _sse_chunk(
            event="query_phase",
            data={"phase": phase, "elapsed_ms": int(timing.get(key, 0))},
        )

    yield _sse_chunk(event="query_complete", data=dict(payload))

    query_run_id = str(payload.get("run_id") or "")
    trigger = _load_curiosity_trigger_for_query_run(report_writer, query_run_id)
    if trigger is None:
        return

    trig = trigger.model_copy(update={"budget": demo_budget})
    yield _sse_chunk(
        event="trigger_emitted",
        data={
            "trigger_id": trig.trigger_id,
            "gap_class": trig.gap_class.value,
            "stub_signal_strength": trig.stub_signal_strength,
            "proposed_search_query": trig.proposed_acquisition_spec.search_query,
        },
    )

    argus_settings = _force_argus_enabled_settings(settings)
    try:
        async with (
            _gutenberg_adapter() as adapter,
            _cockpit_argus_dispatch_session(argus_settings, store, adapter, report_writer) as argus,
        ):
            result = await argus.process(trig)
    except Exception as exc:
        yield _sse_chunk(
            event="error",
            data={"where": "argus", "message": str(exc)[:500]},
        )
        return

    ingest: IngestRunReport | None = None
    if result.decision.ingest_run_id:
        ingest = _load_ingest_report(report_writer, result.decision.ingest_run_id)

    for ev, data in _emit_argus_phases_from_result(result=result, ingest=ingest):
        yield _sse_chunk(event=ev, data=data)

    yield _sse_chunk(
        event="argus_complete",
        data={
            "outcome": result.outcome.value,
            "bytes_acquired": result.bytes_acquired,
            "ingest_run_id": result.decision.ingest_run_id,
            "decision": result.decision.model_dump(mode="json"),
        },
    )


__all__ = ["stream_growth_run"]
