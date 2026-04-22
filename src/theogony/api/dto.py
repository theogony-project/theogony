"""
Request/response Pydantic DTOs for the FastAPI surface (E9).

Sit between the public HTTP boundary and the internal slim DTOs
(``ConstellationNode``, ``ConstellationEdge``, ``Constellation`` from
``core/model.py``). Two reasons for the layer rather than re-using
the slim DTOs directly:

1. **Defence-in-depth on the embedding-leak rule (Plan §9.1).** The
   slim DTOs already exclude embeddings; the API DTOs are a second
   filter. A regression in the slim layer never reaches the network.
2. **HTTP-shape evolution decoupled from the domain.** Future API
   versioning (``/v2/query``) can rev these schemas without
   churning the Chronik vocabulary.

All DTOs use ``model_config = ConfigDict(extra="forbid")`` so a
client typo (``"qq"`` instead of ``"q"``) returns 422 rather than
silently dropping data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.core.model import (
    ConstellationEdge,
    ConstellationNode,
    Layer,
    SourceRef,
)

# ---------------------------------------------------------------- /health


class HealthResponse(BaseModel):
    """``GET /health`` body — same shape ``theogony status`` prints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    version: str
    store: str = "neo4j"
    embedding_model: str
    embedding_dim: int = Field(ge=1)
    report_counts: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------- /query


class QueryRequest(BaseModel):
    """``POST /query`` body."""

    model_config = ConfigDict(extra="forbid")

    q: str = Field(..., min_length=1, max_length=2000)
    layer: Layer | None = None
    k: int = Field(default=10, ge=1, le=50)
    hops: int = Field(default=2, ge=0, le=4)
    strategy: Literal["fixed_depth", "edge_product", "cluster_narrow"] | None = None


class ConstellationDTO(BaseModel):
    """Public Constellation projection — second filter against embedding leaks."""

    model_config = ConfigDict(extra="forbid")

    query: str
    nodes: list[ConstellationNode] = Field(default_factory=list)
    edges: list[ConstellationEdge] = Field(default_factory=list)
    suggested_sources: list[SourceRef] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    path: str = "fast"


class QueryResponse(BaseModel):
    """``POST /query`` response. Mirrors ``QueryResult`` for the wire."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    cited_node_ids: list[str] = Field(default_factory=list)
    constellation: ConstellationDTO
    run_id: str
    verdict: str
    verdict_reasoning: str = ""
    # Gen-2 placeholder: when a /reports/{run_id} endpoint lands, the
    # client can fetch the full report. Today this is a sibling
    # convention with the on-disk path; document it as such.
    report_url: str | None = None


class ErrorResponse(BaseModel):
    """Used for 4xx + 5xx structured errors (especially 503 on LLM failure)."""

    model_config = ConfigDict(extra="forbid")

    error: str
    verdict: str = "failed"
    detail: str | None = None


# ---------------------------------------------------------------- /node/{id}


class NodeResponse(BaseModel):
    """``GET /node/{id}`` — Hover-Lupe substrate."""

    model_config = ConfigDict(extra="forbid")

    node: ConstellationNode
    neighborhood: ConstellationDTO


# ---------------------------------------------------------------- /ingest


class IngestRequest(BaseModel):
    """``POST /ingest`` body. ``options`` carries the same flags as the CLI."""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["gutenberg"] = "gutenberg"
    identifier: str = Field(..., min_length=1)
    sentences: int | None = Field(default=None, ge=1)
    relations: int | None = Field(default=None, ge=1)
    no_book_context: bool = False
    no_relations: bool = False
    no_embed: bool = False


class IngestAcceptedResponse(BaseModel):
    """``202 Accepted`` body. Operator polls ``theogony reports show <run_id>``."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    report_url: str
    status_message: str = (
        "ingest accepted; run is processing in the background. Poll: theogony reports show <run_id>"
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
]
