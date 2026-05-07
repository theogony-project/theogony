"""
Bridge from :class:`KnowledgeNode` / :class:`KnowledgeEdge` to :class:`TensorMeshEngine`.

Fills missing node embeddings via :class:`~theogony.extraction.embedding.EmbeddingProvider`,
builds CSR arrays (source row → target column), maps ``relation_type`` strings to a
fixed codebook index, and loads a :class:`TensorMeshEngine`.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from theogony.core.model import KnowledgeEdge, KnowledgeNode
from theogony.core.tensor_engine import TensorMeshEngine
from theogony.extraction.embedding import EmbeddingProvider

# Order is stable API: indices are stored per-edge; append-only extension adds rows at end.
MESH_RELATION_CODEBOOK_ORDER: tuple[str, ...] = (
    "BINDS_TO",
    "REINFORCES",
    "CAUSED_BY",
    "ABSTRACTION_OF",
    "MODULATES",
    "CONTRADICTS",
    "UNKNOWN",
)


class TensorMeshCSRInputs(BaseModel):
    """Dense Python lists ready for :meth:`TensorMeshEngine.load_from_arrays`."""

    model_config = ConfigDict(extra="forbid")

    row_ptr: list[int] = Field(min_length=1)
    col_idx: list[int]
    node_embeddings: list[list[float]]
    edge_type_idx: list[int]
    edge_codebook: list[list[float]]
    base_weight: list[float]
    hebbian_strength: list[float]


def relation_type_index(relation_type: str) -> int:
    """Map a relation label to a codebook row index (unknown → ``UNKNOWN``)."""
    try:
        return MESH_RELATION_CODEBOOK_ORDER.index(relation_type)
    except ValueError:
        return MESH_RELATION_CODEBOOK_ORDER.index("UNKNOWN")


def deterministic_unit_vector(seed: str, dim: int) -> list[float]:
    """L2-normalised pseudo-random unit vector derived from ``seed``.

    Used in tests and when no dedicated edge-vector embedder is configured.
    """
    if dim <= 0:
        raise ValueError("dim must be positive")
    buf = bytearray()
    cur = seed.encode("utf-8")
    need = dim * 4
    while len(buf) < need:
        cur = hashlib.sha256(cur).digest()
        buf.extend(cur)
    floats: list[float] = []
    for i in range(dim):
        chunk = bytes(buf[i * 4 : (i + 1) * 4])
        u = struct.unpack(">I", chunk)[0]
        floats.append((u / 2**32) * 2.0 - 1.0)
    norm = math.sqrt(sum(x * x for x in floats))
    if norm < 1e-12:
        out = [0.0] * dim
        out[0] = 1.0
        return out
    return [x / norm for x in floats]


def default_edge_codebook(embedding_dim: int) -> list[list[float]]:
    """One unit vector per entry in :data:`MESH_RELATION_CODEBOOK_ORDER`."""
    return [
        deterministic_unit_vector(f"mesh:edge_type:{name}", embedding_dim)
        for name in MESH_RELATION_CODEBOOK_ORDER
    ]


def _node_embedding_dim(nodes: Sequence[KnowledgeNode]) -> int:
    for n in nodes:
        if n.embedding:
            return len(n.embedding)
    raise ValueError("Cannot infer embedding dimension: no node carries a non-empty embedding.")


def build_csr_inputs(
    nodes: Sequence[KnowledgeNode],
    edges: Sequence[KnowledgeEdge],
    *,
    edge_codebook: list[list[float]] | None = None,
    skip_invalid_edges: bool = True,
) -> TensorMeshCSRInputs:
    """
    Assemble CSR lists for outgoing adjacency: row = source node index, entries = targets.

    Requires every ``nodes[i].embedding`` to be non-empty and all vectors same length.
    """
    if not nodes:
        raise ValueError("nodes must be non-empty")

    dim = _node_embedding_dim(nodes)
    for n in nodes:
        if not n.embedding or len(n.embedding) != dim:
            raise ValueError(
                f"Every node must have an embedding of length {dim}; "
                f"node id={n.id!r} has len={len(n.embedding) if n.embedding else 0}."
            )

    id_to_idx = {n.id: i for i, n in enumerate(nodes)}
    node_embeddings = [list(n.embedding) for n in nodes]

    outgoing: dict[int, list[tuple[int, KnowledgeEdge]]] = defaultdict(list)
    for e in edges:
        si = id_to_idx.get(e.source_id)
        ti = id_to_idx.get(e.target_id)
        if si is None or ti is None:
            if skip_invalid_edges:
                continue
            raise ValueError(f"Dangling edge {e.source_id!r} -> {e.target_id!r} not in node set.")
        outgoing[si].append((ti, e))

    for i in outgoing:
        outgoing[i].sort(key=lambda t: (t[0], t[1].relation_type, t[1].id))

    row_ptr: list[int] = [0]
    col_idx: list[int] = []
    edge_type_idx: list[int] = []
    base_weight: list[float] = []
    hebbian_strength: list[float] = []

    n_nodes = len(nodes)
    for i in range(n_nodes):
        for tgt, edge in outgoing[i]:
            col_idx.append(tgt)
            edge_type_idx.append(relation_type_index(edge.relation_type))
            base_weight.append(float(edge.weight))
            hebbian_strength.append(float(edge.hebbian_strength))
        row_ptr.append(len(col_idx))

    book = edge_codebook if edge_codebook is not None else default_edge_codebook(dim)
    if len(book) != len(MESH_RELATION_CODEBOOK_ORDER):
        raise ValueError(
            f"edge_codebook must have {len(MESH_RELATION_CODEBOOK_ORDER)} rows "
            f"(one per relation slot); got {len(book)}."
        )
    if any(len(row) != dim for row in book):
        raise ValueError(f"Every edge_codebook row must have length {dim}.")

    return TensorMeshCSRInputs(
        row_ptr=row_ptr,
        col_idx=col_idx,
        node_embeddings=node_embeddings,
        edge_type_idx=edge_type_idx,
        edge_codebook=book,
        base_weight=base_weight,
        hebbian_strength=hebbian_strength,
    )


async def ensure_node_embeddings(
    nodes: Sequence[KnowledgeNode], embedder: EmbeddingProvider
) -> None:
    """Fill ``embedding``, ``embedding_model_id``, and ``embedding_dim`` where missing."""
    pending_idx: list[int] = []
    pending_text: list[str] = []
    for i, n in enumerate(nodes):
        if not n.embedding:
            pending_idx.append(i)
            pending_text.append(n.label)
    if not pending_text:
        return
    vectors = await embedder.embed_many(pending_text)
    if len(vectors) != len(pending_text):
        raise RuntimeError("embed_many returned fewer vectors than inputs.")
    for j, vec in enumerate(vectors):
        if len(vec) != embedder.dim:
            raise ValueError(
                f"embedder.dim={embedder.dim} but vector length={len(vec)} "
                f"for label={pending_text[j]!r}."
            )
        node = nodes[pending_idx[j]]
        node.embedding = list(vec)
        node.embedding_model_id = embedder.model_id
        node.embedding_dim = embedder.dim


async def tensor_mesh_engine_from_knowledge(
    nodes: Sequence[KnowledgeNode],
    edges: Sequence[KnowledgeEdge],
    embedder: EmbeddingProvider,
    *,
    device: str = "cpu",
    edge_codebook: list[list[float]] | None = None,
    skip_invalid_edges: bool = True,
) -> TensorMeshEngine:
    """
    Embed missing nodes, build CSR payload, and return a loaded :class:`TensorMeshEngine`.
    """
    # Copy to list so mutating embeddings does not surprise callers on tuples.
    node_list = list(nodes)
    await ensure_node_embeddings(node_list, embedder)
    payload = build_csr_inputs(
        node_list,
        edges,
        edge_codebook=edge_codebook,
        skip_invalid_edges=skip_invalid_edges,
    )
    engine = TensorMeshEngine(device=device)
    engine.load_from_arrays(
        payload.row_ptr,
        payload.col_idx,
        payload.node_embeddings,
        payload.edge_type_idx,
        payload.edge_codebook,
        payload.base_weight,
        payload.hebbian_strength,
    )
    return engine
