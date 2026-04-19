"""
Core data models for the Chronik.

These models represent the fundamental knowledge atoms of the system:
nodes (entities, events, concepts, claims), edges (typed weighted relations),
source references (provenance anchors), and lifecycle scores.

In the long view, nodes and edges are operational projections from richer
Chronese assertion frames. They remain the practical unit for retrieval,
indexing, and agent access.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Layer(StrEnum):
    """Memory layer within the Chronik."""

    EPHEMERA = "ephemera"  # raw, unverified, fresh
    MNEME = "mneme"  # verified, connected, permanent


class NodeType(StrEnum):
    """Semantic type of a knowledge node."""

    PERSON = "person"
    PLACE = "place"
    CONCEPT = "concept"
    EVENT = "event"
    CLAIM = "claim"
    WORK = "work"  # book, paper, article, film, ...
    ORGANIZATION = "organization"
    TIME = "time"
    QUANTITY = "quantity"
    SOURCE = "source"
    OTHER = "other"


class KnowledgeForm(StrEnum):
    """The epistemic form of knowledge — what kind of structure it belongs to."""

    CHRONOLOGICAL = "chronological"  # events, biographies, history
    STRUCTURAL = "structural"  # math, logic, formal systems
    MECHANISTIC = "mechanistic"  # causal processes, how things work
    NORMATIVE = "normative"  # law, ethics, values, rules


class EpistemicStatus(StrEnum):
    """How the system holds this knowledge."""

    OBSERVED = "observed"  # directly stated in a source
    REPORTED = "reported"  # stated by a source about another source
    INFERRED = "inferred"  # derived from existing knowledge
    HYPOTHESIZED = "hypothesized"  # proposed, not yet supported
    DISPUTED = "disputed"  # contradicted by at least one source
    DEPRECATED = "deprecated"  # superseded or retracted


class EdgeType(StrEnum):
    """Epistemic type of a relation — how the edge was created."""

    EXTRACTION = "extraction"
    INFERENCE = "inference"
    WIKIDATA = "wikidata"
    QUERY_COOCCURRENCE = "query_cooccurrence"
    AGENT = "agent"
    USER = "user"


class SourceRef(BaseModel):
    """
    Provenance anchor for a knowledge atom.

    Every node must trace back to its origin. This is not optional —
    it is enforced by the data model itself.
    """

    source_type: str  # gutenberg | web | wikidata | arxiv | library | user | ...
    url: str | None = None  # link to original
    identifier: str | None = None  # book ID, DOI, ISBN, call number
    location: str | None = None  # page, chapter, paragraph, char offset
    snippet: str | None = None  # short verbatim quote (1-3 sentences)
    language: str | None = None  # ISO 639-1 language code
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Deterministic ID helpers (Plan §9.2, §9.5, §9.5a)
# ---------------------------------------------------------------------------

_ID_HASH_LEN = 12  # 12 hex chars = 48 bits = ~281 trillion IDs per (source, label) bucket


def _normalise_label(label: str) -> str:
    """Lower-case + whitespace-collapse a label for ID hashing.

    Mirrors the alias-matching normalisation used by EntityResolver
    (Plan §3.4 Stage 2). Two mentions that differ only in case or
    whitespace produce the same ID — the correct, idempotent answer.
    """
    return " ".join(label.lower().split())


def compute_node_id(source_ref: SourceRef, label: str) -> str:
    """Compute the deterministic AKA-id for a node (Plan §9.5).

    Hash inputs: ``source_type:source_identifier:location:normalised_label``.
    Two nodes with the same source-anchor and label collide on purpose —
    that is the property OQ-7 (resumable ingest) needs from
    ``KnowledgeStore.upsert_node`` to be a true no-op on retry.
    """
    digest = hashlib.sha256(
        ":".join(
            (
                source_ref.source_type,
                source_ref.identifier or "",
                source_ref.location or "",
                _normalise_label(label),
            )
        ).encode()
    ).hexdigest()
    return f"AKA-{digest[:_ID_HASH_LEN]}"


def compute_edge_id(
    source_id: str,
    target_id: str,
    relation_type: str,
    evidence_span: str | None,
) -> str:
    """Compute the deterministic edge id (Plan §9.5, §9.5a).

    Disambiguator is ``(source_id, relation_type, target_id, sha256(evidence_span))``.
    The model id and prompt template id are explicitly NOT in the hash —
    re-extracting the same evidence span with a different model produces
    the same edge (idempotent), and provenance of which models touched
    the edge lives in ``properties["extracted_by"]`` and the
    ExtractionAuditLog (Plan §9.5a). When `evidence_span` is None the
    span hash is computed over the empty string, so two no-evidence
    edges with the same triple correctly collide.
    """
    span_hash = hashlib.sha256((evidence_span or "").encode()).hexdigest()
    digest = hashlib.sha256(
        f"{source_id}:{relation_type}:{target_id}:{span_hash}".encode()
    ).hexdigest()
    return f"EDGE-{digest[:_ID_HASH_LEN]}"


class NodeScores(BaseModel):
    """
    Lifecycle scores for a knowledge node.

    Vitality is computed from these scores and determines whether a node
    is promoted (Ephemera → Mneme), retained, or degraded.
    """

    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="How well-verified is this knowledge?"
    )
    relevance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="How often is this node accessed or linked?"
    )
    connectivity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="How well-connected is this node in the graph?"
    )
    freshness: float = Field(
        default=1.0, ge=0.0, le=1.0, description="How recent is this knowledge? Decays over time."
    )

    def vitality(
        self,
        w_confidence: float = 0.4,
        w_relevance: float = 0.25,
        w_connectivity: float = 0.2,
        w_freshness: float = 0.15,
    ) -> float:
        """Compute the vitality score as a weighted sum of component scores."""
        return (
            w_confidence * self.confidence
            + w_relevance * self.relevance
            + w_connectivity * self.connectivity
            + w_freshness * self.freshness
        )


class ScoreUpdate(BaseModel):
    """Partial-update payload for :meth:`KnowledgeStore.batch_update_scores` (PHX-0048).

    Only non-``None`` fields are written by the store; other fields keep
    their existing values. The bulk method exists primarily so the
    :class:`~theogony.memory.oneiros.OneirosWorker` can collapse N
    per-tick score writes into one Cypher round-trip; the partial-update
    shape lets the worker write only the three fields it actually
    recomputes (``connectivity``, ``freshness``, ``vitality``) without
    racing :meth:`RelevanceTracker.bump`'s ``relevance`` updates.

    The ``vitality`` value is **precomputed by the caller** — keeping
    the formula in :meth:`NodeScores.vitality` and out of Cypher so
    PHX-0009's eventual weight-tuning does not require store changes.

    Other callers (a future :meth:`RelevanceTracker.bump_all`, a
    Reviewer agent, manual fix-up scripts) can use any subset of
    fields. The model only requires ``node_id``.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    connectivity: float | None = Field(default=None, ge=0.0, le=1.0)
    freshness: float | None = Field(default=None, ge=0.0, le=1.0)
    vitality: float | None = Field(default=None, ge=0.0, le=1.0)


class KnowledgeNode(BaseModel):
    """
    A knowledge atom in the Chronik.

    Scope is unbounded: a node may represent a macro-concept (Quantum Mechanics),
    a historical event (The Lisbon Earthquake, 1755), a specific person
    (Heinrich Harrer), a place (Uttarkashi), a claim, or a digital twin of
    a living individual.

    In the long view, nodes are projections from richer Chronese assertion frames.
    """

    id: str = Field(
        default="",
        description=(
            "Always 'AKA-<12 hex>'. Wikidata identifiers live in "
            "external_ids['wikidata'], never in this field (Plan §9.2). "
            "When left blank, a deterministic id is computed from "
            "(source_type, source_identifier, location, normalised_label) "
            "via compute_node_id (Plan §9.5). Pass an explicit id to "
            "override — e.g. for agent-minted nodes that have no source "
            "anchor and need a UUID-based id."
        ),
    )
    embedding: list[float] = Field(
        default_factory=list,
        description=(
            "Primary semantic vector. Multiple embeddings (for different spaces) "
            "are stored externally."
        ),
    )
    embedding_model_id: str | None = Field(
        default=None,
        description=(
            "Identifier of the model that produced `embedding`, "
            "e.g. 'BAAI/bge-small-en-v1.5@v1'. Required by PHX-0005 "
            "(Embedding Model Independence) so future re-embedding "
            "passes can target only nodes from a stale model."
        ),
    )
    embedding_dim: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Dimensionality of `embedding`. Recorded explicitly so "
            "consumers do not have to call len() on a list field that "
            "may legitimately be empty for nodes still awaiting embedding."
        ),
    )
    node_type: NodeType = NodeType.OTHER
    knowledge_form: KnowledgeForm = KnowledgeForm.CHRONOLOGICAL
    epistemic_status: EpistemicStatus = EpistemicStatus.OBSERVED

    label: str = Field(
        description="Short human-readable label, e.g. 'Uttarkashi, temple city in Uttarakhand'"
    )
    description: str | None = None

    layer: Layer = Layer.EPHEMERA
    cluster_id: str | None = None  # knowledge region membership

    external_ids: dict[str, str] = Field(
        default_factory=dict, description="e.g. {'wikidata': 'Q806463', 'gutenberg': '12345'}"
    )
    source_ref: SourceRef
    scores: NodeScores = Field(default_factory=NodeScores)

    properties: dict[str, Any] = Field(
        default_factory=dict, description="Flexible additional properties for this node type."
    )

    manual_resolution_needed: bool = Field(
        default=False,
        description=(
            "True ↔ this node failed automatic Wikidata alignment and "
            "is awaiting human review (Plan §9.6, §3.4 honest-failure path). "
            "Surfaced via `theogony resolve --list`. Implies "
            "resolution_tier=0 and external_ids=={}."
        ),
    )
    resolution_tier: int | None = Field(
        default=None,
        ge=0,
        le=4,
        description=(
            "Five-tier confidence model from Plan §3.4 / §9.6: "
            "4=alias-match across ≥2 languages with unique candidate, "
            "3=alias+frequency disambiguation without LLM, "
            "2=LLM with biographical facts and book context, "
            "1=LLM with sentence context only, "
            "0=no Wikidata match (AKA-only). "
            "None for nodes not produced by EntityResolver "
            "(events, claims, agent-created)."
        ),
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified: datetime | None = None

    @model_validator(mode="after")
    def _populate_default_id(self) -> KnowledgeNode:
        if not self.id:
            self.id = compute_node_id(self.source_ref, self.label)
        return self

    @model_validator(mode="after")
    def _validate_resolution_consistency(self) -> KnowledgeNode:
        # Plan §9.6: manual_resolution_needed=True is consistent only with
        # tier 0 (no Wikidata match) — pretending tier 1+ nodes need
        # manual review collapses two distinct epistemic states.
        if self.manual_resolution_needed and self.resolution_tier not in (None, 0):
            raise ValueError(
                "manual_resolution_needed=True requires resolution_tier in "
                f"(None, 0); got {self.resolution_tier}"
            )
        return self

    @property
    def vitality(self) -> float:
        return self.scores.vitality()

    @property
    def wikidata_id(self) -> str | None:
        return self.external_ids.get("wikidata")

    def is_in_mneme(self) -> bool:
        return self.layer == Layer.MNEME

    def can_be_promoted(
        self,
        confidence_threshold: float = 0.65,
        connectivity_threshold: float = 0.2,
    ) -> bool:
        """A node can be promoted to Mneme when it is sufficiently verified and connected."""
        return (
            self.scores.confidence >= confidence_threshold
            and self.scores.connectivity >= connectivity_threshold
        )


class KnowledgeEdge(BaseModel):
    """
    A typed, weighted, provenance-anchored relation between two knowledge nodes.

    Relation types follow Wikidata P-ID conventions where applicable
    (e.g. P131 = located in, P31 = instance of) and use custom types
    for relations not in Wikidata.
    """

    id: str = Field(
        default="",
        description=(
            "Always 'EDGE-<12 hex>'. When left blank, a deterministic id "
            "is computed from (source_id, relation_type, target_id, "
            "sha256(evidence_span)) via compute_edge_id (Plan §9.5/§9.5a). "
            "The model id and prompt id are intentionally NOT part of the "
            "hash — re-extraction of the same evidence with a different "
            "model is the same edge with stronger provenance, not a new one."
        ),
    )
    source_id: str
    target_id: str

    relation_type: str = Field(
        description="P-ID style (e.g. 'P131', 'P31') or custom (e.g. 'REACHED', 'DESCRIBED_BY')"
    )
    weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Edge weight, strengthened or weakened over time."
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="How certain is this relation?"
    )
    bidirectional: bool = False
    epistemic_type: EdgeType = EdgeType.EXTRACTION
    source_ref: SourceRef | None = None
    evidence_span: str | None = Field(
        default=None,
        description=(
            "The substring of source text the LLM cited as justification "
            "for this relation. Required for the relation-extraction "
            "discipline in Plan §3.3 (every extracted edge must point at "
            "a verbatim span). Also part of the deterministic edge-ID "
            "disambiguator (Plan §9.5/§9.5a): two extractions of the same "
            "(source, relation, target) from different sentences are two "
            "edges, not one."
        ),
    )

    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _populate_default_id(self) -> KnowledgeEdge:
        if not self.id:
            self.id = compute_edge_id(
                source_id=self.source_id,
                target_id=self.target_id,
                relation_type=self.relation_type,
                evidence_span=self.evidence_span,
            )
        return self


class ConstellationNode(BaseModel):
    """
    Slim, citation-ready projection of a :class:`KnowledgeNode`.

    Plan §9.1: full ``KnowledgeNode`` records carry a 384–1536-dim
    ``embedding`` and other fields that have no business reaching the
    answer-synthesis prompt. A naive constellation serialisation would
    leak ~75 KB of float32 per response into the LLM context window.
    The synthesizer should only ever see the slim form. The full record
    is fetched separately via ``KnowledgeStore.get_node`` when the user
    drills into a citation (the Hover-Lupe).
    """

    id: str
    label: str
    node_type: NodeType
    layer: Layer
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: SourceRef

    @classmethod
    def from_knowledge_node(cls, node: KnowledgeNode) -> ConstellationNode:
        """Project a full :class:`KnowledgeNode` into its slim form."""
        return cls(
            id=node.id,
            label=node.label,
            node_type=node.node_type,
            layer=node.layer,
            confidence=node.scores.confidence,
            source_ref=node.source_ref,
        )


class ConstellationEdge(BaseModel):
    """
    Slim, citation-ready projection of a :class:`KnowledgeEdge`.

    Carries only the fields the answer synthesizer needs to reason
    about a relation. The full edge — with provenance, properties, and
    timestamps — stays in the store.
    """

    source_id: str
    target_id: str
    relation_type: str
    weight: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_knowledge_edge(cls, edge: KnowledgeEdge) -> ConstellationEdge:
        """Project a full :class:`KnowledgeEdge` into its slim form."""
        return cls(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type=edge.relation_type,
            weight=edge.weight,
            confidence=edge.confidence,
        )


class Constellation(BaseModel):
    """
    A structured, query-relevant working set returned by the Chronik to an agent.

    This is not a list of text chunks. It is a subgraph of knowledge:
    relevant nodes, relations between them, source anchors for citation,
    and identified gaps where knowledge is missing or weak.

    The LLM interprets a Constellation into human-readable output.
    Every entity mentioned in the answer can reference its node here —
    this is the foundation of the Hover-Lupe.

    Per Plan §9.1, ``nodes`` and ``edges`` use slim DTOs rather than
    full :class:`KnowledgeNode` / :class:`KnowledgeEdge` records to
    keep embeddings out of the synthesizer's context window.
    """

    query: str
    nodes: list[ConstellationNode] = Field(default_factory=list)
    edges: list[ConstellationEdge] = Field(default_factory=list)
    suggested_sources: list[SourceRef] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list, description="Identified knowledge gaps relevant to this query."
    )
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    path: str = Field(
        default="fast",
        description="'fast' (heuristic retrieval) or 'slow' (reasoning + opposition protocol)",
    )

    @property
    def is_sufficient(self) -> bool:
        """Rough heuristic: is there enough to synthesize a useful answer?"""
        return len(self.nodes) >= 3 and len(self.edges) >= 1
