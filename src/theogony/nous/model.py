"""
Nous-specific Pydantic models (nous_implementation_brief §3.2).

These models are scoped to the Nous reading session and are kept separate
from core/model.py (which belongs to the Chronicle) to maintain clear
domain boundaries.

None of these models modify the Chronicle schema — they are session-local
artefacts that reference Chronicle node/edge IDs but do not live in the store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChronicleHint(BaseModel):
    """One kNN hit offered to the LLM as context during a reading step."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    similarity: float = Field(ge=0.0, le=1.0)
    source: str
    tension: bool = False


class WorkingMemoryState(BaseModel):
    """Snapshot of working memory at a given reading step (after decay applied)."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    concepts: dict[str, float]
    pooled_embedding: list[float]
    open_tensions: list[tuple[str, str]] = Field(default_factory=list)


class ResolutionUpdate(BaseModel):
    """A within-session revision of a concept's Wikidata Q-ID assignment.

    ``extra="ignore"`` because DeepSeek may emit additional fields
    (``concept_label``, ``wikidata_id``, ``confidence``, ``evidence_span``).
    The normalisation pass in ``reader._normalise_llm_output`` handles
    ``concept_label`` → ``node_id`` remapping.
    """

    model_config = ConfigDict(extra="ignore")

    node_id: str
    previous_tier: int | None = Field(default=None, ge=0, le=4)
    new_tier: int = Field(default=1, ge=0, le=4)
    new_wikidata_id: str | None = None
    reason: str = ""


class SynthesisOutput(BaseModel):
    """A synthesis event emitted by the LLM at a paragraph/section boundary.

    ``extra="ignore"`` because non-schema-enforcing LLMs (e.g. DeepSeek) may
    emit extra fields (``synthesis_node_type``, ``synthesis_label``, etc.).
    The normalisation pass in ``reader._normalise_llm_output`` handles the
    common field-name variants; this setting catches the rest.
    """

    model_config = ConfigDict(extra="ignore")

    label: str
    description: str | None = None
    basis_node_ids: list[str] = Field(default_factory=list)
    diagonal_edges: list[tuple[str, str, str]] = Field(
        default_factory=list,
        description="[(source_id, relation_type, target_id)] — cross-level edges",
    )
    synthesis_level: Literal["paragraph", "chapter", "article"] = "paragraph"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RepairEvent(BaseModel):
    """A within-session revision triggered by detected tension.

    ``extra="ignore"`` for the same reason as ``SynthesisOutput``.
    """

    model_config = ConfigDict(extra="ignore")

    revised_node_id: str
    reason: str
    old_description: str | None = None
    new_description: str | None = None
    tension_source: Literal["llm_detected", "chronicle_contradicts"] = "llm_detected"


class LLMReadingOutput(BaseModel):
    """Structured output from one LLM reading step."""

    model_config = ConfigDict(extra="forbid")

    new_concepts: list[dict[str, Any]] = Field(default_factory=list)
    new_edges: list[dict[str, Any]] = Field(default_factory=list)
    chronicle_hits_used: list[str] = Field(default_factory=list)
    synthesis_event: SynthesisOutput | None = None
    repair_events: list[RepairEvent] = Field(default_factory=list)
    resolution_updates: list[ResolutionUpdate] = Field(default_factory=list)


class ReadingStep(BaseModel):
    """Full record of one paragraph's reading pass."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    paragraph_text: str
    section_title: str | None = None
    synthesis_level_context: Literal["sentence", "paragraph", "chapter", "article"]
    working_memory_before: WorkingMemoryState
    chronicle_hints_offered: list[ChronicleHint]
    llm_output: LLMReadingOutput
    nodes_written: list[str] = Field(default_factory=list)
    edges_written: list[str] = Field(default_factory=list)
    llm_cost_eur: float = Field(ge=0.0)
    llm_latency_ms: int = Field(ge=0)


class AnnotatedReading(BaseModel):
    """Full machine-readable record of one Nous reading session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    source_url: str
    article_title: str
    started_at: datetime
    finished_at: datetime
    steps: list[ReadingStep] = Field(default_factory=list)
    final_working_memory: WorkingMemoryState
    total_nodes_written: int = Field(ge=0)
    total_edges_written: int = Field(ge=0)
    total_synthesis_events: int = Field(ge=0)
    total_repair_events: int = Field(ge=0)
    chronicle_seeded: bool = Field(
        description="True if the Chronicle contained nodes before this session started. "
        "Monkey-1 comparison requires chronicle_seeded=True to show "
        "cross-document connection metrics."
    )
