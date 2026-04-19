"""
``GET /health`` — same shape ``theogony status`` prints (Plan §3.7).

Read-only. Does **not** ping Gemini / Wikidata / any external service:
calling an LLM just to answer a healthcheck is wrong (cost + latency).
A future ``?deep=true`` query param can add provider connectivity if a
monitor needs it (Gen 2 — see PHX backlog when filed).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from theogony import __version__
from theogony.api.dependencies import get_settings, get_store
from theogony.api.dto import HealthResponse
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore

router = APIRouter(tags=["meta"])


def _count_reports(settings: Settings, report_type: str) -> int:
    d = settings.run_reports_dir / report_type
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.suffix == ".json")


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[KnowledgeStore, Depends(get_store)],
) -> HealthResponse:
    """Return store backend + embedding config + on-disk report counts."""
    health_dict = await store.health()
    backend_name = str(health_dict.get("backend", "unknown"))
    return HealthResponse(
        version=__version__,
        store=backend_name,
        embedding_model=settings.embedding.model_id,
        embedding_dim=settings.embedding.dim,
        report_counts={
            rtype: _count_reports(settings, rtype) for rtype in ("ingest", "query", "oneiros")
        },
    )


__all__ = ["router"]
