"""
Public API of the FastAPI surface (E9).

Re-exports the app + lifespan + DTOs that callers (tests, deployments,
future API clients) need.
"""

from __future__ import annotations

from theogony.api.app import app, create_app, lifespan
from theogony.api.dto import (
    ConstellationDTO,
    ErrorResponse,
    HealthResponse,
    IngestAcceptedResponse,
    IngestRequest,
    NodeResponse,
    QueryRequest,
    QueryResponse,
)

__all__ = [
    "ConstellationDTO",
    "ErrorResponse",
    "HealthResponse",
    "IngestAcceptedResponse",
    "IngestRequest",
    "NodeResponse",
    "QueryRequest",
    "QueryResponse",
    "app",
    "create_app",
    "lifespan",
]
