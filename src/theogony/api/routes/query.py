"""
``POST /query`` — wrap :class:`QueryPipeline` for HTTP (Plan §3.7).

Returns the synthesized answer + cited node ids + the slim
Constellation + run_id + verdict. The full report stays on disk;
the ``report_url`` field is a Gen-2 placeholder (see ``theogony
reports show <run_id>`` for the supported readback path).

Honest failure: any provider / transport exception escaping the
pipeline becomes ``503 Service Unavailable`` with a structured
:class:`ErrorResponse`. The QueryPipeline already swallows
synthesizer transport errors into an empty Answer with verdict
``"failed"``, so a true 503 here means the embed / spreading /
assemble path itself failed (rare but possible: store or tensor layer).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from theogony.api.dependencies import get_query_pipeline
from theogony.api.dto import (
    ConstellationDTO,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from theogony.config.logging import get_logger
from theogony.retrieval.pipeline import QueryPipeline

log = get_logger("api.routes.query")

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        503: {"model": ErrorResponse, "description": "LLM / store transport failure"},
    },
)
async def query(
    request: QueryRequest,
    pipeline: Annotated[QueryPipeline, Depends(get_query_pipeline)],
) -> QueryResponse | JSONResponse:
    try:
        result = await pipeline.ask(
            request.q,
            layer=request.layer,
            k=request.k,
            hops=request.hops,
            strategy=request.strategy,
            pheromone_mode=request.pheromone_mode,
            thinking_max=request.thinking_max,
        )
    except Exception as exc:  # pragma: no cover - defensive 503 path
        # The retrieval stack's own honest-failure paths (synthesizer
        # transport error → empty Answer + verdict=failed) handle the
        # common case. A genuine exception escaping ask() means embed
        # or spreading retrieval or assemble itself raised, which is a 503.
        log.exception("query pipeline raised: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error="retrieval pipeline raised",
                detail=f"{type(exc).__name__}: {exc}",
                verdict="failed",
            ).model_dump(),
        )

    constellation_dto = ConstellationDTO(
        query=result.constellation.query,
        nodes=list(result.constellation.nodes),
        edges=list(result.constellation.edges),
        suggested_sources=list(result.constellation.suggested_sources),
        gaps=list(result.constellation.gaps),
        path=result.constellation.path,
    )
    # report_url is a Gen-2 placeholder: today the persisted JSON lives
    # at result.report_path; the documented readback is `theogony
    # reports show <run_id>`. We surface the URL anyway so a UI can
    # round-trip the run_id without inventing the path scheme.
    report_url = f"/reports/{result.report.run_id}" if result.report_path is not None else None
    return QueryResponse(
        answer=result.answer.text,
        cited_node_ids=list(result.answer.cited_node_ids),
        constellation=constellation_dto,
        run_id=result.report.run_id,
        verdict=result.report.verdict,
        verdict_reasoning=result.report.verdict_reasoning,
        report_url=report_url,
    )


# 422 (validation error) is handled automatically by FastAPI from the
# QueryRequest Pydantic schema — empty / oversized strings raise
# ValidationError which FastAPI translates to 422. No explicit handler.

# Re-export for cleaner intent at import sites.
_ = HTTPException  # silence "imported but unused" if the linter sees it that way

__all__ = ["router"]
