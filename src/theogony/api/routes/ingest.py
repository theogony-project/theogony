"""
``POST /ingest`` — accept a Gutenberg book id, run ingest in a background task.

Plan §3.7. Returns ``202 Accepted`` immediately with the run_id; the
operator polls ``theogony reports show <run_id>`` for completion.

Why background rather than synchronous: an ingest is 30 s – 10 min
depending on book size. Holding an HTTP request open for that is
wrong UX (and breaks load balancers). Why no SSE/Websocket progress:
YAGNI; the report writer's per-stage updates are already on disk.

The background task uses the lifespan-owned ``app.state.store`` —
that store outlives the request, so the task can complete safely
even after the client disconnects.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status

from theogony.acquisition.gutenberg import GutenbergAdapter
from theogony.api.dependencies import get_settings
from theogony.api.dto import IngestAcceptedResponse, IngestRequest
from theogony.config.logging import get_logger
from theogony.config.settings import Settings
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.pipeline import IngestionPipeline
from theogony.extraction.relations import RelationExtractor
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataClient
from theogony.reporting.models import new_run_id

log = get_logger("api.routes.ingest")

router = APIRouter(tags=["ingest"])


async def _run_background_ingest(
    *,
    request_app_state: Any,
    settings: Settings,
    body: IngestRequest,
    run_id: str,
) -> None:
    """Background task body. Owns its own Wikidata client; reuses the
    lifespan-owned store / llm / audit / embedder / report_writer.
    """
    state = request_app_state
    audit = state.audit
    llm = state.llm
    store = state.store
    embedder = state.embedder
    report_writer = state.report_writer
    log.info("background ingest start run_id=%s identifier=%s", run_id, body.identifier)

    try:
        async with GutenbergAdapter(inter_request_delay_s=0.0) as gutenberg:
            cand = await gutenberg.get_by_id(body.identifier)
            raw = await gutenberg.acquire(cand)

        async with WikidataClient() as wd_client:
            resolver = EntityResolver(client=wd_client, llm=llm, audit_log=audit)
            book_ctx = (
                None if body.no_book_context else BookContextExtractor(llm=llm, audit_log=audit)
            )
            relation_extractor = (
                None if body.no_relations else RelationExtractor(llm=llm, audit_log=audit)
            )
            pipeline = IngestionPipeline(
                entity_resolver=resolver,
                relation_extractor=relation_extractor,
                book_context_extractor=book_ctx,
                embedder=None if body.no_embed else embedder,
                audit_log=audit,
                store=store,
                settings=settings,
                ner_sentence_limit=body.sentences,
                max_relation_sentences=body.relations,
            )
            result = await pipeline.ingest(raw)
        report_writer.write(result.report)
        log.info(
            "background ingest end run_id=%s status=%s verdict=%s",
            result.report.run_id,
            result.report.status,
            result.report.verdict,
        )
    except Exception:  # pragma: no cover - defensive logging
        # Plan §2.11.4: never abort the writer; the pipeline's own
        # report-writer path already persists a report with status
        # ="failed" before re-raising. Any exception here is logged
        # so the operator can see it in stdout / file logs.
        log.exception("background ingest raised; run_id=%s", run_id)


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestAcceptedResponse,
)
async def ingest(
    request: Request,
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestAcceptedResponse:
    # Mint the run_id at accept-time so the response can carry it; the
    # background task overwrites IngestRunReport.run_id with its own
    # (also a ULID) which is the canonical id the operator polls.
    # The accept-time id is informational — we surface both via the
    # status_message.
    accept_run_id = new_run_id()
    background_tasks.add_task(
        _run_background_ingest,
        request_app_state=request.app.state,
        settings=settings,
        body=body,
        run_id=accept_run_id,
    )
    return IngestAcceptedResponse(
        run_id=accept_run_id,
        report_url=f"/reports/{accept_run_id}",
        status_message=(
            f"ingest accepted; run_id={accept_run_id}; the actual report run_id "
            "is logged when the background task starts. Poll: "
            "theogony reports list  +  theogony reports show <run_id>"
        ),
    )


# Avoids the "imported but unused" trap if the asyncio re-export disappears.
_: type = asyncio.Task

__all__ = ["router"]
