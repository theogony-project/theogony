"""
Kadmos v2 — Pydantic models for the cognitive reading session.

These models represent the session-local state produced during a
KadmosReader reading pass.  They are NOT Chronicle (Chronik) models;
they represent the intermediate *text-oriented* product that will be
translated into vectors by the subsequent embedding pass.

Architecture position (TARGET_ARCHITECTURE.md):

    raw text → Kadmos v2 → (this) → embedding pass → vector mesh

The models here capture:

  - ``ActiveConcept``      — a concept warm in working memory
  - ``ActiveEdge``         — a connection between active concepts
  - ``SynthesisNode``      — a condensed abstraction over several concepts
  - ``RevisionEvent``      — a recorded change to an earlier concept/edge
  - ``ReadingHypotheses``  — similarity + traversal candidates fed to LLM
  - ``LLMReadingOutput``   — structured LLM response per step
  - ``ReadingStep``        — full record of one reading unit
  - ``ReadingState``       — live working memory (mutated across steps)
  - ``AnnotatedReading``   — complete session artefact written to disk

Separate from these: ``KadmosRunReport`` lives in
``theogony.reporting.models`` (pattern: all RunReports in one module).

Q1–Q7 decisions recorded in kadmos_v2_brief.md §9:
  Q1 paragraph granularity by default
  Q2 compress at capacity ≥50 OR section boundary
  Q3 top-5 similarity + top-3 traversal hypotheses
  Q4 revisions reach all active concepts + synthesis nodes
  Q5 two LanceDB tables: concepts + edges (revisions as superseding rows)
  Q6 AnnotatedReading contains full revision graph + final state
  Q7 edge embedding = embedding of connection description sentence
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Working memory atom types
# ---------------------------------------------------------------------------


class RevisionRecord(BaseModel):
    """One recorded revision of a concept or edge — stored as provenance."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    revision_type: Literal["update", "split", "merge", "invalidate"]
    reason: str
    triggering_passage: str
    old_understanding: str | None = None
    new_understanding: str | None = None


class ActiveConcept(BaseModel):
    """A concept that is currently active in working memory."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str | None = None
    activation: float = Field(ge=0.0, le=1.0, default=1.0)
    step_created: int = Field(ge=0)
    source_passage: str | None = None
    invalidated: bool = False
    revision_history: list[RevisionRecord] = Field(default_factory=list)
    wikidata_candidate: str | None = None


class ActiveEdge(BaseModel):
    """A connection between two active concepts."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    target_id: str
    relation_description: str
    weight: float = Field(ge=0.0, le=1.0, default=0.8)
    step_created: int = Field(ge=0)
    invalidated: bool = False
    revision_history: list[RevisionRecord] = Field(default_factory=list)


class SynthesisNode(BaseModel):
    """A condensed abstraction over several concepts (higher-level node)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    basis_concept_ids: list[str]
    synthesis_level: Literal["paragraph", "section", "article"]
    step_created: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


# ---------------------------------------------------------------------------
# Per-step inputs and outputs
# ---------------------------------------------------------------------------


class HypothesisCandidate(BaseModel):
    """One candidate connection proposed by kNN/traversal — not yet LLM-confirmed."""

    model_config = ConfigDict(extra="forbid")

    concept_id: str
    label: str
    score: float = Field(ge=0.0)
    hypothesis_type: Literal["similarity", "traversal"]


class ReadingHypotheses(BaseModel):
    """All hypothesis candidates for one reading step (Schritt A)."""

    model_config = ConfigDict(extra="forbid")

    similarity_candidates: list[HypothesisCandidate] = Field(default_factory=list)
    traversal_candidates: list[HypothesisCandidate] = Field(default_factory=list)


class RevisionRequest(BaseModel):
    """A revision emitted by the LLM in its reading output."""

    model_config = ConfigDict(extra="forbid")

    target_concept_id: str
    revision_type: Literal["update", "split", "merge", "invalidate"]
    reason: str
    triggering_passage: str
    old_understanding: str | None = None
    new_understanding: str | None = None
    split_into: list[dict[str, Any]] | None = Field(
        default=None,
        description="For split: list of new concept dicts to create.",
    )
    merge_with_id: str | None = Field(
        default=None,
        description="For merge: the other concept id to merge with.",
    )


class LLMNewConcept(BaseModel):
    """One new concept emitted by the LLM in its reading output."""

    model_config = ConfigDict(extra="forbid")

    label: str
    description: str | None = None
    source_passage: str | None = None
    wikidata_candidate: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class LLMNewEdge(BaseModel):
    """One new edge emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    source_label: str
    target_label: str
    relation_description: str
    weight: float = Field(ge=0.0, le=1.0, default=0.8)


class LLMSynthesisOutput(BaseModel):
    """A synthesis event emitted by the LLM."""

    model_config = ConfigDict(extra="forbid")

    label: str
    description: str
    basis_concept_ids: list[str]
    synthesis_level: Literal["paragraph", "section", "article"]
    confidence: float = Field(ge=0.0, le=1.0)


class LLMReadingOutput(BaseModel):
    """Structured output from one LLM reading step (Schritt B)."""

    model_config = ConfigDict(extra="forbid")

    new_concepts: list[LLMNewConcept] = Field(default_factory=list)
    new_connections: list[LLMNewEdge] = Field(default_factory=list)
    confirmed_hypotheses: list[str] = Field(
        default_factory=list,
        description="concept_ids from ReadingHypotheses that the LLM confirmed.",
    )
    rejected_hypotheses: list[str] = Field(
        default_factory=list,
        description="concept_ids from ReadingHypotheses that the LLM rejected.",
    )
    revisions: list[RevisionRequest] = Field(default_factory=list)
    synthesis: LLMSynthesisOutput | None = None
    open_tensions: list[str] = Field(
        default_factory=list,
        description="Short descriptions of unresolved tensions.",
    )
    next_granularity: Literal["sentence", "paragraph", "section", "skim"] = "paragraph"


# ---------------------------------------------------------------------------
# Session records
# ---------------------------------------------------------------------------


class ReadingStep(BaseModel):
    """Full record of one reading unit (Schritt A + B + C + D)."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    granularity: Literal["sentence", "paragraph", "section", "skim"]
    text: str
    section_title: str | None = None
    hypotheses: ReadingHypotheses
    llm_output: LLMReadingOutput
    concepts_added: list[str] = Field(default_factory=list)
    edges_added: list[str] = Field(default_factory=list)
    revisions_applied: list[str] = Field(
        default_factory=list,
        description="concept_ids that were revised in this step.",
    )
    synthesis_created: str | None = None
    wm_size_before: int = Field(ge=0)
    wm_size_after: int = Field(ge=0)
    llm_cost_eur: float = Field(ge=0.0, default=0.0)
    llm_latency_ms: int = Field(ge=0, default=0)
    parse_failed: bool = False


class ReadingState(BaseModel):
    """Live working memory — mutated across reading steps.

    This is the session-local state, not persisted between sessions.
    The LanceDB tables are the durable form; this is the in-memory view.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    active_concepts: dict[str, ActiveConcept] = Field(default_factory=dict)
    active_edges: dict[str, ActiveEdge] = Field(default_factory=dict)
    syntheses: dict[str, SynthesisNode] = Field(default_factory=dict)
    open_tensions: list[str] = Field(default_factory=list)
    current_step: int = 0
    current_granularity: Literal["sentence", "paragraph", "section", "skim"] = "paragraph"


class AnnotatedReading(BaseModel):
    """Complete machine-readable record of one KadmosReader session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    source_url: str
    article_title: str
    started_at: datetime
    finished_at: datetime
    steps: list[ReadingStep] = Field(default_factory=list)
    final_active_concepts: list[ActiveConcept] = Field(default_factory=list)
    final_syntheses: list[SynthesisNode] = Field(default_factory=list)
    total_concepts: int = Field(ge=0)
    total_edges: int = Field(ge=0)
    total_syntheses: int = Field(ge=0)
    total_revisions: int = Field(ge=0)
    total_llm_calls: int = Field(ge=0)
    total_llm_cost_eur: float = Field(ge=0.0)
    reading_units_total: int = Field(ge=0)
