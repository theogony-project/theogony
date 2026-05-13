"""MESH ingestion pipeline — Kadmos v2 writes into the new substrate (Step S2).

Takes raw text + entity metadata, emits ``ChunkNode`` s, reference ``Edge`` s,
and eager-linked Tier-1 nodes into the new MESH substrate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.ingestion.source_anchor import build_source_anchor_description
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance


class MeshIngestionPipeline:
    """Text + entity metadata → MESH substrate.

    In S2 this pipeline:
    1. Splits text into sentence chunks.
    2. Embeds each sentence as a ``ChunkNode``.
    3. Creates a ``SourceProvenance`` on each chunk.
    4. Creates/retrieves the source-anchor entity.
    5. For each chunk, runs the eager linker on any **entity references**
       present in the input data (Q-ID, description, tag).
    6. Writes edges (chunk → source-anchor, chunk → entity).
    """

    def __init__(
        self,
        mesh: MeshRuntime,
        *,
        semantic_dim: int | None = None,
        frame_dim: int | None = None,
    ) -> None:
        self.mesh = mesh
        self.semantic_dim = semantic_dim or mesh.semantic_dim
        self.frame_dim = frame_dim or mesh.frame_dim
        self.linker = EagerLinker(
            mesh.nodes, frame_dim=self.frame_dim, semantic_dim=self.semantic_dim
        )

    def ingest(
        self,
        *,
        text: str,
        entities: list[dict[str, Any]] | None = None,
        source_type: str = "text",
        source_identifier: str = "inline",
        title: str = "Untitled",
        anchor: str = "",
    ) -> dict[str, Any]:
        """Run the ingestion pipeline for a text with optional entity references.

        *entities* is a list parallel to sentences (by index) or a flat list of
        all entity references. Each entry supports:

            ``qids``: list[dict] with keys ``qid``, ``confidence``, ``attached_at``
            ``label``: str
            ``tags``: list[str]
            ``semantic_vector``: list[float] | None (auto-generated if missing)
            ``description_vector``: list[float] | None

        Returns a structured summary.
        """
        now = datetime.now(UTC)

        # 1. Create or retrieve source-anchor entity.
        sa_node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_source_anchor=True,
            source_url=anchor or source_identifier,
            semantic_vector=[0.0] * self.semantic_dim,
            frame_vector=[0.0] * self.frame_dim,
            description=build_source_anchor_description(
                source_type=source_type,
                title=title,
                anchor=anchor or source_identifier,
            ),
            tags=[source_type.lower()],
        )
        self.mesh.nodes.append_consolidated(sa_node)

        # 2. Split text into sentences.
        raw_sentences = _split_sentences(text)
        chunk_count = 0
        edge_count = 0

        for i, raw in enumerate(raw_sentences):
            s = raw.strip()
            if not s:
                continue

            # Embed this sentence.
            sem_vec = _mock_vec(s, self.semantic_dim)
            frm_vec = _mock_vec(s, self.frame_dim)

            src = SourceProvenance(
                source_type=source_type,
                source_identifier=source_identifier,
                extracted_at=now,
            )
            chunk = ChunkNode(
                id=ULID(),
                born_at=now,
                last_fired_at=now,
                semantic_vector=sem_vec,
                frame_vector=frm_vec,
                source=src,
                raw_text_ref=f"{source_identifier}#s{i}",
            )
            self.mesh.nodes.append_chunk(chunk)
            chunk_count += 1

            # Edge: chunk → source-anchor
            self.mesh.edges.append_edge(
                Edge(
                    source_id=chunk.id,
                    target_id=sa_node.id,
                    weight=1.0,
                    born_at=now,
                    last_fired_at=now,
                    relation_kind="extraction",
                    relation_descriptor="extracted_from",
                    creation_context="kadmos_extraction",
                )
            )
            edge_count += 1

            # 3. Run eager linker on entity references that belong to this chunk.
            if entities and i < len(entities) and entities[i]:
                ref_results = self.linker.link_chunk_entities(chunk_entities=entities[i])
                for ref in ref_results:
                    target_id = ref["node_id"]
                    self.mesh.edges.append_edge(
                        Edge(
                            source_id=chunk.id,
                            target_id=target_id,
                            weight=1.0,
                            born_at=now,
                            last_fired_at=now,
                            relation_kind="co_occurrence",
                            relation_descriptor="mentions",
                            creation_context="kadmos_extraction",
                        )
                    )
                    edge_count += 1

        return {
            "chunks": chunk_count,
            "edges": edge_count,
            "source_anchor_id": str(sa_node.id),
            "source_anchor_description": sa_node.description,
        }


# ---- Internal helpers ----


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter — production should use spaCy sentencizer."""
    import re

    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _mock_vec(text: str, dim: int) -> list[float]:
    """Deterministic hash-based mock vector for S2."""
    import hashlib

    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [b / 255.0 - 0.5 for b in h[:dim]]
    if len(raw) < dim:
        raw.extend([0.0] * (dim - len(raw)))
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw] if norm > 0 else raw[:dim]
