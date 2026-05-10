"""Cockpit-specific fixtures (PHX-0074)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.docs_ingest import read_dump
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


@pytest.fixture
def cockpit_client(api_app: FastAPI) -> Iterator[TestClient]:
    """TestClient with cockpit routes mounted (via ``api_app`` fixture)."""
    with TestClient(api_app) as client:
        yield client


async def load_truncated_pantheon_seed(
    store: InMemoryKnowledgeStore,
    *,
    embed_dim: int = 4,
) -> None:
    """Load ``pantheon_self`` with node embeddings truncated to ``embed_dim``.

    Shared ``api_app`` tests use a tiny constant embedder (dim=4) while the
    bundled seed ships 384-dim BGE vectors. Spreading activation requires
    query vectors and node matrix columns to match.
    """
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    truncated: list[KnowledgeNode] = []
    for n in nodes:
        if not isinstance(n, KnowledgeNode):
            continue
        if n.embedding and len(n.embedding) > embed_dim:
            truncated.append(
                n.model_copy(
                    update={
                        "embedding": list(n.embedding[:embed_dim]),
                        "embedding_dim": embed_dim,
                    }
                )
            )
        else:
            truncated.append(n)
    edge_objs = [e for e in edges if isinstance(e, KnowledgeEdge)]
    await store.batch_upsert_nodes(truncated)
    await store.batch_upsert_edges(edge_objs)
