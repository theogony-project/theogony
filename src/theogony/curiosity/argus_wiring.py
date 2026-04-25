"""
Argus wiring for the CLI / dispatcher (W7-B, W11).

Wraps audit log + Wikidata + embedder + :class:`IngestionPipeline` in an
async context manager so resource lifetimes stay correct while
:class:`~theogony.agents.argus.ArgusAgent` runs one or more ``process``
calls (``GutenbergAdapter`` is owned by the caller).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from typing import TYPE_CHECKING

from theogony.acquisition.base import AcquisitionAdapter
from theogony.acquisition.web_fetch import WebFetchAdapter
from theogony.acquisition.wikidata import WikidataAdapter
from theogony.acquisition.wikipedia import WikipediaAdapter
from theogony.agents.argus import ArgusAgent
from theogony.agents.argus_ingest_runner import IngestRunner, RealIngestRunner
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.llm import LLMProvider
from theogony.agents.research_evaluator import Evaluator
from theogony.agents.research_planner import ResearchPlanner
from theogony.clustering.cluster_index import ClusterIndex
from theogony.config.settings import Settings
from theogony.curiosity.research_executor import ResearchExecutor
from theogony.curiosity.verification_pool import VerificationPool
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import WikidataClient

if TYPE_CHECKING:
    from theogony.core.store import KnowledgeStore


def make_argus_agent(
    *,
    settings: Settings,
    adapter: AcquisitionAdapter,
    ingest_runner: IngestRunner,
    verification_pool: VerificationPool,
    llm: LLMProvider,
    wd_client: WikidataClient,
    wikipedia: AcquisitionAdapter | None = None,
    web_fetch: AcquisitionAdapter | None = None,
) -> ArgusAgent:
    """Build :class:`ArgusAgent` with W11 planner wiring when settings enable it."""
    use = settings.curiosity.research_planner.enabled and settings.curiosity.evaluator.enabled
    if not use:
        return ArgusAgent(
            adapter=adapter,
            ingest_runner=ingest_runner,
            verification_pool=verification_pool,
            settings=settings.curiosity.argus,
            use_research_planner=False,
        )
    wikidata = WikidataAdapter(client=wd_client)
    wiki = wikipedia if wikipedia is not None else WikipediaAdapter()
    web = web_fetch if web_fetch is not None else WebFetchAdapter()
    executor = ResearchExecutor(
        wikidata=wikidata,
        gutenberg=adapter,
        wikipedia=wiki,
        web_fetch=web,
    )
    planner = ResearchPlanner(llm=llm, settings=settings.curiosity.research_planner)
    evaluator = Evaluator(llm=llm, settings=settings.curiosity.evaluator)
    return ArgusAgent(
        adapter=adapter,
        ingest_runner=ingest_runner,
        verification_pool=verification_pool,
        settings=settings.curiosity.argus,
        use_research_planner=True,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        run_reports_dir=settings.run_reports_dir,
    )


@asynccontextmanager
async def argus_dispatch_session(
    settings: Settings,
    store: KnowledgeStore,
    adapter: AcquisitionAdapter,
) -> AsyncIterator[ArgusAgent]:
    """Hold ingest-side resources open for the lifetime of one dispatch batch."""
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
        async with (
            WikidataClient(cache=wd_cache) as wd_client,
            WikipediaAdapter() as wiki,
            WebFetchAdapter() as web,
        ):
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
            runner = RealIngestRunner(pipeline)
            verification_pool = VerificationPool(settings)
            yield make_argus_agent(
                settings=settings,
                adapter=adapter,
                ingest_runner=runner,
                verification_pool=verification_pool,
                llm=llm,
                wd_client=wd_client,
                wikipedia=wiki,
                web_fetch=web,
            )


__all__ = ["argus_dispatch_session", "make_argus_agent"]
