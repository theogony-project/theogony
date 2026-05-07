"""Contract tests: KnowledgeNode/KnowledgeEdge → CSR → TensorMeshEngine."""

from __future__ import annotations

import math

import pytest
import torch

from theogony.core.knowledge_to_mesh import (
    MESH_RELATION_CODEBOOK_ORDER,
    TensorMeshCSRInputs,
    build_csr_inputs,
    default_edge_codebook,
    deterministic_unit_vector,
    relation_type_index,
    tensor_mesh_engine_from_knowledge,
)
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.extraction.embedding import EmbeddingProvider


def _src() -> SourceRef:
    return SourceRef(source_type="test", identifier="doc:1", location="chunk:0")


class _Dim8Embedder:
    """Deterministic tiny embedder — no torch/sentence-transformers."""

    model_id = "test-dim8@v1"
    dim = 8

    async def embed(self, text: str) -> list[float]:
        return deterministic_unit_vector(f"node:{text}", self.dim)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def _assert_protocol(x: object) -> None:
    assert isinstance(x, EmbeddingProvider)


def test_relation_type_index_unknown() -> None:
    assert relation_type_index("BINDS_TO") == 0
    assert relation_type_index("not-a-real-type") == MESH_RELATION_CODEBOOK_ORDER.index("UNKNOWN")


def test_deterministic_unit_vector_normalised() -> None:
    v = deterministic_unit_vector("seed-a", 16)
    assert len(v) == 16
    n = math.sqrt(sum(x * x for x in v))
    assert abs(n - 1.0) < 1e-6


def test_default_edge_codebook_matches_relation_slots() -> None:
    book = default_edge_codebook(8)
    assert len(book) == len(MESH_RELATION_CODEBOOK_ORDER)
    for row in book:
        assert len(row) == 8
        n = math.sqrt(sum(x * x for x in row))
        assert abs(n - 1.0) < 1e-6


def test_build_csr_inputs_simple_chain() -> None:
    src = _src()
    n0 = KnowledgeNode(
        id="AKA-aaaaaaaaaaaa",
        label="A",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
        embedding=deterministic_unit_vector("n:A", 8),
        embedding_dim=8,
    )
    n1 = KnowledgeNode(
        id="AKA-bbbbbbbbbbbb",
        label="B",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
        embedding=deterministic_unit_vector("n:B", 8),
        embedding_dim=8,
    )
    e0 = KnowledgeEdge(
        source_id=n0.id,
        target_id=n1.id,
        relation_type="BINDS_TO",
        weight=0.9,
        hebbian_strength=0.1,
        source_ref=src,
    )
    payload = build_csr_inputs([n0, n1], [e0])
    assert isinstance(payload, TensorMeshCSRInputs)
    assert payload.row_ptr == [0, 1, 1]
    assert payload.col_idx == [1]
    assert payload.edge_type_idx == [relation_type_index("BINDS_TO")]
    assert payload.base_weight == [0.9]
    assert payload.hebbian_strength == [0.1]


def test_build_csr_inputs_skips_dangling_edge() -> None:
    src = _src()
    n0 = KnowledgeNode(
        id="AKA-cccccccccccc",
        label="C",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
        embedding=deterministic_unit_vector("n:C", 4),
        embedding_dim=4,
    )
    bad = KnowledgeEdge(
        source_id=n0.id,
        target_id="AKA-missing",
        relation_type="BINDS_TO",
        weight=1.0,
        source_ref=src,
    )
    payload = build_csr_inputs([n0], [bad], skip_invalid_edges=True)
    assert payload.col_idx == []


@pytest.mark.asyncio
async def test_tensor_mesh_engine_from_knowledge_and_spread() -> None:
    _assert_protocol(_Dim8Embedder())
    src = _src()
    n0 = KnowledgeNode(
        id="AKA-dddddddddddd",
        label="photon",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
    )
    n1 = KnowledgeNode(
        id="AKA-eeeeeeeeeeee",
        label="light",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
    )
    e0 = KnowledgeEdge(
        source_id=n0.id,
        target_id=n1.id,
        relation_type="ABSTRACTION_OF",
        weight=0.85,
        hebbian_strength=0.2,
        source_ref=src,
    )
    embedder = _Dim8Embedder()
    engine = await tensor_mesh_engine_from_knowledge([n0, n1], [e0], embedder, device="cpu")
    assert n0.embedding and n0.embedding_model_id == embedder.model_id
    stim = torch.tensor(n0.embedding, dtype=torch.float32)
    idx, energy = engine.spreading_activation(stim, max_hops=2, top_k_seeds=2)
    assert idx.numel() >= 1
    assert energy.numel() == idx.numel()
    assert float(energy[0]) > 0.0
