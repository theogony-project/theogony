"""
``GET /node/{id}`` — Hover-Lupe substrate (Plan §2.6, §9.1).

Returns the node (slim DTO — no embedding) + its depth-1 neighbourhood
projected as a ``Constellation`` with ``path="fast"``, no LLM
involvement, no synthesised answer, no gaps. 404 when the id is unknown.

Why a small projection helper here rather than a public
``Constellation.from_node_neighborhood`` method on ``core/model.py``:
the route's needs are exactly that one shape; promoting it to the
domain vocabulary would be premature API design (Plan §9 deliberately
keeps the slim DTOs minimal).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from theogony.api.dependencies import get_store
from theogony.api.dto import ConstellationDTO, NodeResponse
from theogony.core.model import Constellation, ConstellationNode
from theogony.core.store import KnowledgeStore

router = APIRouter(tags=["node"])


@router.get(
    "/node/{node_id}",
    response_model=NodeResponse,
    responses={404: {"description": "no node with that id"}},
)
async def node(
    node_id: str,
    store: Annotated[KnowledgeStore, Depends(get_store)],
) -> NodeResponse:
    record = await store.get_node(node_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no node with id {node_id!r}",
        )

    # depth=1 + min_weight=0.3 matches Plan §2.6 floor — the Hover-Lupe
    # is for "show me this node's immediate context", not "explain its
    # entire connected component".
    neighborhood = await store.get_neighborhood(node_id, depth=1, min_weight=0.3)
    # Project into the public DTO. The slim Constellation already
    # excludes embeddings; ConstellationDTO is the second filter.
    neighborhood_dto = ConstellationDTO(
        query=record.label,
        nodes=list(neighborhood.nodes),
        edges=list(neighborhood.edges),
        suggested_sources=list(neighborhood.suggested_sources),
        gaps=[],
        path="fast",
    )
    return NodeResponse(
        node=ConstellationNode.from_knowledge_node(record),
        neighborhood=neighborhood_dto,
    )


# Silences unused-import warning when re-exported types are dropped later.
_: type = Constellation

__all__ = ["router"]
