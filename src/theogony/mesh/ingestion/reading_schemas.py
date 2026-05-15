"""Structured extraction schemas for the LLM reading step."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMQID(BaseModel):
    """Candidate Wikidata identity for a concept mention."""

    model_config = ConfigDict(extra="forbid")

    qid: str = Field(description="Wikidata Q-ID, e.g. Q336997")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


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
    qids: list[LLMQID] = Field(
        default_factory=list,
        description="Optional Wikidata identity candidates for this concept",
    )

    @field_validator("qids", mode="before")
    @classmethod
    def _coerce_qids(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            return value

        coerced: list[object] = []
        for item in value:
            if isinstance(item, str):
                coerced.append({"qid": item, "confidence": 1.0})
            else:
                coerced.append(item)
        return coerced


class LLMRelation(BaseModel):
    """A directed relation between two concepts within one paragraph."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Label of the source concept")
    target: str = Field(description="Label of the target concept")
    relation_descriptor: str = Field(
        description="Short verb, e.g. 'discovered', 'practiced_at', 'born_in'",
    )
    relation_kind: str = Field(
        default="semantic",
        description="Broader relation bucket such as causal, hierarchy, attribute, or semantic",
    )
    rationale: str = Field(default="", description="Why this relation exists")


class LLMParagraphConcept(BaseModel):
    """A Tier-1 paragraph concept node that unifies the paragraph."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Short label for the paragraph concept")
    description: str = Field(description="One-sentence summary for the paragraph concept")
    tags: list[str] = Field(
        default_factory=list,
        description="Helpful tags for the paragraph concept",
    )
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
    paragraph_concept: LLMParagraphConcept | None = Field(
        default=None,
        description="Optional paragraph-level concept node",
    )
