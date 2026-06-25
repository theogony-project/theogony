"""FastAPI dependencies for the Iris cockpit (PHX-0074 Phase 1)."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request

from theogony.cockpit.mesh_explorer import MeshExplorerService
from theogony.config.settings import Settings
from theogony.core.store import KnowledgeStore
from theogony.extraction.embedding import EmbeddingProvider
from theogony.reporting.writer import RunReportWriter


class User:
    id: str
    display_name: str
    roles: list[str]

    def __init__(self, *, id: str, display_name: str, roles: list[str]) -> None:
        self.id = id
        self.display_name = display_name
        self.roles = roles


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_store_readonly(request: Request) -> KnowledgeStore:
    return cast(KnowledgeStore, request.app.state.store)


def get_report_writer(request: Request) -> RunReportWriter:
    return cast(RunReportWriter, request.app.state.report_writer)


def get_embedder(request: Request) -> EmbeddingProvider:
    return cast(EmbeddingProvider, request.app.state.embedder)


def get_mesh_explorer(request: Request) -> MeshExplorerService | None:
    """The mesh-backed Explorer service, or None when no mesh workspace is configured."""
    return cast("MeshExplorerService | None", getattr(request.app.state, "mesh_explorer", None))


def require_mesh_explorer(
    request: Request,
) -> MeshExplorerService:
    service = get_mesh_explorer(request)
    if service is None:
        raise HTTPException(status_code=404, detail="mesh explorer not configured")
    return service


def get_authenticated_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    if settings.cockpit.auth_provider == "none":
        return None
    raise NotImplementedError("Phase-2 auth")


def require_cockpit_access(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.cockpit.enabled:
        raise HTTPException(status_code=404, detail="cockpit disabled")
    if settings.cockpit.public:
        return
    raw = (request.headers.get("host") or "").strip().lower()
    host = raw.split(":")[0] if raw else ""
    if host in ("127.0.0.1", "localhost", "testclient", "testserver"):
        return
    if not host:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Cockpit is local-only; set THEOGONY_COCKPIT__PUBLIC=true and "
            "THEOGONY_COCKPIT__BIND_HOST=0.0.0.0 to allow off-host access."
        ),
    )
