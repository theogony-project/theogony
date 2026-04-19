"""
End-to-end E8 smoke: ingest Hedin (Gutenberg #43497) into Neo4j, then ask.

Plan §1 demo loop closes here. Used once at PR-time for the brief's
"Done when" verification:

    Capture the smoke output in the PR body.

Cost: ~0.10-0.20 EUR Gemini for the ingest (book_context + relations)
plus ~0.001 EUR for one synthesis call. Run from a clean working
directory:

    docker compose up -d neo4j
    python scripts/smoke_e8.py

The script wipes Neo4j first so repeated runs are reproducible.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataClient
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores import Neo4jKnowledgeStore


async def main() -> int:
    settings = Settings()
    embedder = LocalSentenceTransformerEmbedder()
    # Trigger model download / load once before timing-sensitive sections.
    _ = await embedder.embed("warmup")

    audit_path = Path("data/audit_smoke.sqlite")
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    with ExtractionAuditLog(audit_path) as audit:  # sync ctxmgr
        async with WikidataClient() as wd:
            llm = build_llm_from_settings(settings)
            async with Neo4jKnowledgeStore(settings.neo4j, embedding_dim=embedder.dim) as store:
                async with store._session() as session:  # noqa: SLF001 - smoke-script setup
                    await session.run("MATCH (n) DETACH DELETE n")

                async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
                    candidate = await adapter.get_by_id("43497")
                    raw = await adapter.acquire(candidate)

                book_ctx_extractor = BookContextExtractor(llm=llm, audit_log=audit)
                resolver = EntityResolver(client=wd, llm=llm, audit_log=audit)
                relation_extractor = RelationExtractor(llm=llm, audit_log=audit)
                pipeline = IngestionPipeline(
                    book_context_extractor=book_ctx_extractor,
                    entity_resolver=resolver,
                    relation_extractor=relation_extractor,
                    embedder=embedder,
                    store=store,
                    settings=settings,
                    audit_log=audit,
                    ner_sentence_limit=120,
                    max_relation_sentences=25,
                )
                print("[ingest] starting…")
                ingest_result = await pipeline.ingest(raw)
                print(
                    f"[ingest] status={ingest_result.report.status} "
                    f"verdict={ingest_result.report.verdict} "
                    f"nodes={len(ingest_result.resolved_mentions)} "
                    f"edges={len(ingest_result.edges)}"
                )

                # ---- ask -----------------------------------------------------------
                writer = RunReportWriter(settings.run_reports_dir)
                ask_pipeline = QueryPipeline(
                    embedder=embedder,
                    retriever=MultiHopRetriever(store),
                    assembler=ConstellationAssembler(store),
                    synthesizer=AnswerSynthesizer(llm, audit_log=audit),
                    relevance=RelevanceTracker(store),
                    settings=settings,
                    report_writer=writer,
                )
                print("\n[ask] Wer war Sven Hedin?")
                result = await ask_pipeline.ask("Wer war Sven Hedin?")

    print("\n--- Answer ---")
    print(result.answer.text)
    print("\n--- Cited node ids ---")
    print(result.answer.cited_node_ids)
    print("\n--- Report ---")
    print(
        f"  run_id={result.report.run_id} status={result.report.status} "
        f"verdict={result.report.verdict}"
    )
    print(f"  reasoning={result.report.verdict_reasoning!r}")
    print(
        f"  multi_hop: seed_count={result.report.multi_hop.seed_count} "
        f"duration_ms={result.report.multi_hop.duration_ms}"
    )
    print(
        f"  constellation: nodes={result.report.constellation_node_count} "
        f"edges={result.report.constellation_edge_count} "
        f"gaps={result.report.gaps_identified}"
    )
    print(
        f"  citation_quality: cited={result.report.citation_quality.cited_node_count} "
        f"high_conf={result.report.citation_quality.citations_with_high_confidence_source} "
        f"aka_only={result.report.citation_quality.citations_aka_only}"
    )
    print(
        f"  synthesis: in_tokens={result.report.synthesis.input_tokens} "
        f"out_tokens={result.report.synthesis.output_tokens} "
        f"cost_eur={result.report.synthesis.cost_eur:.6f} "
        f"latency_ms={result.report.synthesis.latency_ms}"
    )
    print(f"  report_path={result.report_path}")

    # Brief invariant: Answer.text contains at least one [AKA-…] citation
    # whose id is in the constellation.
    if not result.answer.cited_node_ids:
        print("\nFAIL: Answer carries no validated citations.", file=sys.stderr)
        return 2
    constellation_ids = {n.id for n in result.constellation.nodes}
    cited_in_constellation = [
        cid for cid in result.answer.cited_node_ids if cid in constellation_ids
    ]
    if not cited_in_constellation:
        print("\nFAIL: Cited ids do not resolve to constellation nodes.", file=sys.stderr)
        return 3
    print(
        f"\nOK: {len(cited_in_constellation)} of {len(result.answer.cited_node_ids)} "
        f"cited ids resolve to constellation nodes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
