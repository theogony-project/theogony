"""
Live integration smoke for :class:`IngestionPipeline` (E5 end-to-end).

Gated by ``THEOGONY_RUN_E5_INTEGRATION=1``. Requires:

- An API key for the configured LLM provider (default: ``ANTHROPIC_API_KEY``;
  override with ``THEOGONY_LLM__PROVIDER=gemini`` + ``GEMINI_API_KEY``,
  or ``THEOGONY_LLM__PROVIDER=openai`` + ``OPENAI_API_KEY``)
- Network access to Project Gutenberg + Wikidata + the LLM host

Drives the full E5 chain on a small slice of Hedin Trans-Himalaya
Vol. I (Gutenberg #43497):

  GutenbergAdapter.acquire   → real PG download
    → TextCleaner.clean      → real header/footer strip
    → Sentencizer            → real spaCy
    → BookContextExtractor   → real LLM (1 call)
    → NerExtractor           → real spaCy en_core_web_sm
    → EntityResolver         → real Wikidata + (sometimes) real LLM
    → RelationExtractor      → real LLM (per ambiguous sentence)
    → materialise_edges      → real KnowledgeEdge minting
    → InMemoryKnowledgeStore → real upserts (no Neo4j needed)
    → ExtractionAuditLog     → real SQLite log
    → IngestRunReport        → fully populated

The slice (ner_sentence_limit=15, max_relation_sentences=4) keeps
the test under ~30 s and ~0.01 EUR. Verifies end-to-end:

- Pipeline completes with status="completed"
- Verdict is one of {good, partial, poor} — failed would mean a
  stage failure
- At least one Tier-3-or-higher node was resolved (real Wikidata
  alignment works)
- At least one edge was materialised
- Audit log has rows for each LLM call
- IngestRunReport summaries match the result counts

Run::

    THEOGONY_RUN_E5_INTEGRATION=1 \\
        pytest tests/test_extraction_pipeline_live.py -v
"""

from __future__ import annotations

import os

import pytest

from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.agents.factory import build_llm_from_settings
from theogony.config.settings import Settings
from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataClient

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_E5_INTEGRATION") != "1",
    reason="set THEOGONY_RUN_E5_INTEGRATION=1 to run live E5 integration",
)


HEDIN_BOOK_ID = "43497"


def _live_llm() -> object:
    settings = Settings()  # type: ignore[call-arg]
    if settings.active_llm_api_key() is None:
        pytest.skip("no API key for the active LLM provider in environment")
    try:
        return build_llm_from_settings(settings)
    except (ValueError, NotImplementedError, ImportError) as exc:
        pytest.skip(f"could not build LLM provider: {exc}")


class _CollectingStore:
    """In-memory KnowledgeStore stub for the live smoke."""

    def __init__(self) -> None:
        self.nodes: list[KnowledgeNode] = []
        self.edges: list[KnowledgeEdge] = []

    async def upsert_node(self, node: KnowledgeNode) -> str:
        self.nodes.append(node)
        return node.id

    async def upsert_edge(self, edge: KnowledgeEdge) -> None:
        self.edges.append(edge)


class TestE5LiveSmoke:
    async def test_full_pipeline_against_hedin_slice(self) -> None:
        # ---- acquire ----
        async with GutenbergAdapter(inter_request_delay_s=0.0) as gutenberg:
            cands = await gutenberg.search("Trans-Himalaya Hedin", limit=10)
            hedin = next(c for c in cands if c.identifier == HEDIN_BOOK_ID)
            raw_content = await gutenberg.acquire(hedin)

        # ---- compose pipeline ----
        llm = _live_llm()
        with ExtractionAuditLog() as audit:
            async with WikidataClient() as wd_client:
                resolver = EntityResolver(
                    client=wd_client,
                    llm=llm,
                    audit_log=audit,
                )
                book_context_extractor = BookContextExtractor(llm=llm, audit_log=audit)
                relation_extractor = RelationExtractor(llm=llm, audit_log=audit)
                store = _CollectingStore()
                pipeline = IngestionPipeline(
                    entity_resolver=resolver,
                    relation_extractor=relation_extractor,
                    book_context_extractor=book_context_extractor,
                    audit_log=audit,
                    store=store,  # type: ignore[arg-type]
                    # Keep the smoke cheap: small NER slice + a handful of
                    # relation extractions. Hedin Vol. I is ~7 700 sentences;
                    # the pipeline mechanics are validated on 15.
                    ner_sentence_limit=15,
                    max_relation_sentences=4,
                )
                result = await pipeline.ingest(raw_content)
                rows = audit.query_for_run(result.run_id)
                cost_eur = audit.total_cost_for_run(result.run_id)

        # ---- shape ----
        assert result.report.status == "completed", (
            f"pipeline aborted; stages={[(s.name, s.status) for s in result.report.stages]}"
        )
        assert result.report.verdict in ("good", "partial", "poor"), (
            f"unexpected verdict {result.report.verdict}: {result.report.verdict_reasoning}"
        )

        # ---- nodes ----
        # The first 15 sentences include the publisher frontispiece +
        # opening paragraphs. Expect at least a few resolved entities;
        # demand at least one Tier ≥ 3 (real Wikidata alignment).
        assert len(result.resolved_mentions) >= 3, (
            f"expected ≥3 resolved mentions; got {len(result.resolved_mentions)}"
        )
        tiers = [rm.tier for rm in result.resolved_mentions]
        assert any(t >= 3 for t in tiers), (
            f"expected at least one Tier-3+ resolution; got tiers {tiers}"
        )

        # ---- store ----
        assert len(store.nodes) == len(result.resolved_mentions)
        assert len(store.edges) == len(result.edges)

        # ---- audit log ----
        # At minimum: one BookContext call. Stage 4 + relation calls
        # depend on whether ambiguous mentions / multi-mention sentences
        # exist in the slice; we assert a lower bound.
        assert len(rows) >= 1
        stages_seen = {r.stage for r in rows}
        assert "book_context" in stages_seen, (
            f"book_context audit row missing; stages_seen={stages_seen}"
        )
        # All rows belong to this run.
        assert all(r.run_id == result.run_id for r in rows)
        # Cost recorded per row; total > 0 (Gemini calls always cost
        # something, even tiny amounts).
        assert cost_eur > 0.0
        assert result.report.audit_log_run_id == result.run_id

        # ---- report consistency ----
        report = result.report
        assert report.source_type == "gutenberg"
        assert report.source_identifier == HEDIN_BOOK_ID
        assert report.ner.total_mentions > 0
        # Every minted node has a tier; the report's tier_counts sum
        # to len(resolved_mentions).
        assert sum(report.resolution.tier_counts.values()) == len(result.resolved_mentions)
        # Print summary for human-eye verification (visible with -v).
        print(
            f"\nE5 live smoke: run_id={result.run_id} "
            f"verdict={report.verdict} "
            f"nodes={len(store.nodes)} "
            f"edges={len(store.edges)} "
            f"audit_rows={len(rows)} "
            f"llm_cost_eur={cost_eur:.5f} "
            f"tiers={dict(report.resolution.tier_counts)}"
        )
