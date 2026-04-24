"""
Argus wiring for the CLI / dispatcher (W7-B).

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
from theogony.agents.argus import ArgusAgent
from theogony.agents.argus_ingest_runner import RealIngestRunner
from theogony.agents.factory import build_llm_from_settings
from theogony.agents.hestia_lite import HestiaLiteApproval
from theogony.clustering.cluster_index import ClusterIndex
from theogony.config.settings import Settings
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import WikidataClient

if TYPE_CHECKING:
    from theogony.core.store import KnowledgeStore


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
            runner = RealIngestRunner(pipeline)
            hestia = HestiaLiteApproval(settings.curiosity.hestia_lite)
            yield ArgusAgent(
                adapter=adapter,
                hestia=hestia,
                ingest_runner=runner,
                settings=settings.curiosity.argus,
            )


__all__ = ["argus_dispatch_session"]
