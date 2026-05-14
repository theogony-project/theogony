"""Structured extraction schemas for the LLM reading step."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMConcept(BaseModel):
    """A concept identified by the LLM in one paragraph."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Short label, e.g. 'Thomas Addison' or \"Addison's disease\"")
    entity_type: str = Field(
        default="concept",
        description="Category: person, place, org, disease, event, concept, date",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Discriminating tags for disambiguation",
    )
    description: str = Field(default="", description="One-sentence description")


class LLMRelation(BaseModel):
    """A directed relation between two concepts within one paragraph."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Label of the source concept")
    target: str = Field(description="Label of the target concept")
    relation_descriptor: str = Field(
        description="Short verb, e.g. 'discovered', 'practiced_at', 'born_in'",
    )
    rationale: str = Field(default="", description="Why this relation exists")


class LLMSynthesis(BaseModel):
    """A higher-level abstraction synthesising the paragraph's content."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Short label for the synthesis")
    description: str = Field(description="One-sentence synthesis")
    basis_concepts: list[str] = Field(
        default_factory=list,
        description="Labels of the concepts this synthesis abstracts over",
    )


class ParagraphReadingOutput(BaseModel):
    """Structured output from one LLM paragraph reading step."""

    model_config = ConfigDict(extra="forbid")

    concepts: list[LLMConcept] = Field(
        default_factory=list,
        description="Concepts identified in this paragraph",
    )
    relations: list[LLMRelation] = Field(
        default_factory=list,
        description="Relations between concepts within this paragraph",
    )
    synthesis: LLMSynthesis | None = Field(
        default=None,
        description="Optional paragraph-level synthesis",
    )
