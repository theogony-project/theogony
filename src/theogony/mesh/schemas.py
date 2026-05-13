"""Pydantic substrate shapes for the MESH package (Step S1).

Field names and nesting follow ``docs/MESH_SUBSTRATE.md`` §"Node anatomy" and
§"Edge anatomy". ``SourceProvenance``, ``QIDTag``, and ``PIDTag`` are named in
that section but not expanded as full class bodies there; the shapes below are
the minimal faithful reading of the prose constraints ("who / where / when"
for provenance; ``(id, confidence, attached_at)`` for Q-IDs and analogously for
P-IDs).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceProvenance(BaseModel):
    """Who / where / when a Tier-0 chunk was extracted (immune-system anchor)."""

    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(description='Acquisition class, e.g. "gutenberg", "web".')
    source_identifier: str = Field(
        description="Opaque provider-native address (book id, URL stem, etc.).",
    )
    extracted_at: datetime = Field(description="Extraction timestamp (timezone-aware).")


class QIDTag(BaseModel):
    """Wikidata Q-ID attachment with audit trail."""

    model_config = ConfigDict(extra="forbid")

    qid: str = Field(description='Wikidata item id, e.g. "Q336997".')
    confidence: float = Field(ge=0.0, le=1.0)
    attached_at: datetime


class PIDTag(BaseModel):
    """Wikidata P-ID attachment with audit trail."""

    model_config = ConfigDict(extra="forbid")

    pid: str = Field(description='Wikidata property id, e.g. "P19".')
    confidence: float = Field(ge=0.0, le=1.0)
    attached_at: datetime


class ChunkNode(BaseModel):
    """Tier-0 observation chunk."""

    model_config = ConfigDict(extra="forbid")

    id: str
    born_at: datetime
    last_fired_at: datetime
    fired_total: int = 0
    fired_recent: int = 0

    semantic_vector: list[float]
    frame_vector: list[float]

    source: SourceProvenance
    raw_text_ref: str


class ConsolidatedNode(BaseModel):
    """Tier-1+ consolidated node."""

    model_config = ConfigDict(extra="forbid")

    id: str
    born_at: datetime
    last_fired_at: datetime
    fired_total: int = 0
    fired_recent: int = 0

    consolidation_tier: int = 1
    consolidation_history: list[datetime] = Field(default_factory=list)
    is_candidate: bool = False
    is_anchor: bool = False
    is_source_anchor: bool = False
    source_url: str | None = None

    semantic_vector: list[float]
    frame_vector: list[float]
    structural_vector: list[float] | None = None
    temporal_vector: list[float] | None = None
    description_vector: list[float] | None = None

    description: str | None = None
    description_generated_at: datetime | None = None
    description_source_chunks: list[str] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)

    qids: list[QIDTag] = Field(default_factory=list)

    activation_entropy: float | None = None
    node_potential_cache: float | None = None
    positive_feedback_total: int = 0
    negative_feedback_total: int = 0
    feedback_recent: int = 0


class Edge(BaseModel):
    """Directed weighted edge (quantitative core + optional descriptors)."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    weight: float
    born_at: datetime
    last_fired_at: datetime

    decay_tier: int = 0
    frame_consistency: float = 1.0

    eligibility: float = 0.0
    feedback_modulated_strength: float = 0.0

    relation_descriptor: str | None = None
    relation_kind: str | None = None
    description: str | None = None
    pids: list[PIDTag] = Field(default_factory=list)
    creation_context: str | None = None


class EdgeMetadata(BaseModel):
    """Optional semantic descriptors stored off the SpMV hot path."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    relation_descriptor: str | None = None
    relation_kind: str | None = None
    description: str | None = None
    pids: list[PIDTag] = Field(default_factory=list)
    creation_context: str | None = None
