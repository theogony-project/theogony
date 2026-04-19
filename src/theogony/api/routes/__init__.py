"""Public router registry for the FastAPI app."""

from __future__ import annotations

from theogony.api.routes.health import router as health_router
from theogony.api.routes.ingest import router as ingest_router
from theogony.api.routes.node import router as node_router
from theogony.api.routes.query import router as query_router

__all__ = ["health_router", "ingest_router", "node_router", "query_router"]
