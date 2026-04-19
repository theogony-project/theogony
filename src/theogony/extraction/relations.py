"""
RelationExtractor — LLM-based relation extraction (Plan §2.5, §3.3, §3a PID-2).

Plan §3a PID-2 locks sentence-level granularity: one LLM call per
sentence, evidence_span ⊆ central sentence. The default mode is
single-sentence; the optional ``expand_window`` mode includes the
previous and next sentences as **context only** (no relations may
be extracted from them) — for resolving pronouns and references
without giving up the substring guarantee.

Plan §3.3 specifies a fixed vocabulary of ~20 relation types (see
:mod:`theogony.extraction.relation_types`); the extractor enforces
the vocabulary by normalising the LLM's output to canonical form
and dropping anything that does not normalise cleanly. Unknown
types fall back to ``OTHER`` — preserves signal, flags for review.

Three reinforcing safeguards from Plan §3a PID-2 are enforced here:

1. **Structural prompt clarity.** Prompts use labelled sections
   ("PREVIOUS", "CENTRAL", "NEXT") with explicit "(context only)"
   vs "(extract from here)" annotations. We do not rely on the
   model inferring centrality from position.

2. **Schema enforcement.** JSON schema is supplied to the
   LLMProvider; on parse failure or missing required fields the
   relation is dropped, not invented.

3. **Substring validation.** After parsing, ``evidence_span`` is
   verified to be a substring of the central sentence (after the
   same Unicode normalisation used in §3.4 alias matching). On
   failure the relation is dropped and a warning logged. The
   future ExtractionAuditLog (E5+) will record these dropped
   parses with ``parse_error="evidence_span_outside_central"``
   so a spike can trigger prompt-tightening or expand_window flip.

What this module deliberately does NOT do:

- It does not look up node IDs for the subject / object surface
  forms. The IngestionPipeline (E5+) takes ``ExtractedRelation``
  DTOs and resolves them to ``KnowledgeEdge`` instances using the
  resolver's ResolvedMention map.
- It does not write to the audit log directly. ExtractionAuditLog
  is E5 work; for now the structured warnings are the audit trail.
- It does not retry the LLM. Plan §4.4 puts retry policy at the
  pipeline level; the extractor surfaces the failure honestly.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.extraction.alias_matcher import fully_normalise
from theogony.extraction.ner import Mention
from theogony.extraction.relation_types import (
    RELATION_TYPES_LIST,
    RelationType,
    is_known_relation_type,
    normalise_relation_type,
)
from theogony.extraction.sentence import Sentence

log = get_logger("extraction.relations")


_SYSTEM_PROMPT = (
    "You extract structured relations from prose. Each relation "
    "connects a subject entity to an object entity, has a relation "
    "type from a fixed vocabulary, and is anchored to a verbatim "
    "evidence span from the source sentence. You answer ONLY with "
    "JSON matching the supplied schema. You never invent relations "
    "that the source text does not explicitly support. When no "
    "relation is supported, you return an empty list."
)


_OUTPUT_SCHEMA: dict[str, object] = {
    # Deliberately minimal: descriptions, numeric bounds, and maxItems
    # are intentionally absent. Gemini's response_schema is OpenAPI-3-
    # flavoured and rejects "too many states for serving" when those
    # constraints stack — the live smoke caught this on the original
    # heavily-annotated schema. Field semantics live in the system
    # prompt; numeric / vocabulary / substring validation happens in
    # _validate_one after parsing — that is the authoritative check
    # anyway, since an LLM honouring the schema is best-effort, not
    # guaranteed.
    "type": "object",
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "object": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "evidence_span": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "subject",
                    "object",
                    "relation_type",
                    "evidence_span",
                    "confidence",
                ],
            },
        },
    },
    "required": ["relations"],
}


class ExtractedRelation(BaseModel):
    """One relation parsed from a single sentence's LLM extraction.

    Mirrors the JSON-schema shape but with Pydantic validation +
    the post-LLM normalisation we apply (relation_type canonicalised,
    is_other flagged, evidence_span verified as substring of central).

    The subject_text / object_text fields hold the verbatim surface
    forms the LLM picked. The IngestionPipeline (E5+) maps these to
    resolver-minted node IDs using the per-sentence Mention list.
    """

    model_config = ConfigDict(extra="forbid")

    subject_text: str = Field(min_length=1)
    object_text: str = Field(min_length=1)
    relation_type: str
    evidence_span: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    is_other: bool = Field(
        default=False,
        description=(
            "True when the LLM-supplied relation_type did not match the "
            "fixed vocabulary and was normalised to OTHER. Plan §3.3: "
            "OTHER edges are valid signal but should be flagged for "
            "human review before promotion."
        ),
    )


class RelationExtractor:
    """Extract relations from one sentence per LLM call (Plan §3a PID-2).

    Stateless after construction; safe to share across asyncio tasks.
    Concurrency is bounded by the underlying LLMProvider's
    ``max_concurrency`` setting, not by this class.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        expand_window: bool = False,
        llm_timeout_s: float = 30.0,
    ) -> None:
        self._llm = llm
        self._expand_window = expand_window
        self._llm_timeout_s = llm_timeout_s

    @property
    def expand_window(self) -> bool:
        return self._expand_window

    async def extract(
        self,
        *,
        central_sentence: Sentence,
        mentions: Sequence[Mention],
        previous_sentence: Sentence | None = None,
        next_sentence: Sentence | None = None,
    ) -> list[ExtractedRelation]:
        """Extract relations from ``central_sentence``.

        Short-circuits before the LLM call when fewer than two
        mentions are present (no possible relation). Returns an
        empty list on LLM transport / parse failure — relations are
        dropped honestly, never invented.

        ``mentions`` is the list of NER mentions that fall inside
        the central sentence. The extractor inlines them into the
        prompt so the LLM knows which entities are addressable;
        relations whose subject/object do not match a mention
        surface form are still kept (the LLM may have caught a
        fragment NER missed) — the IngestionPipeline drops them
        downstream when no resolved node matches.

        ``previous_sentence`` / ``next_sentence`` are consulted only
        when ``expand_window=True`` (constructor flag). Otherwise
        they are silently ignored.
        """
        if len(mentions) < 2:
            return []
        prompt = self._build_prompt(
            central_sentence=central_sentence,
            mentions=mentions,
            previous_sentence=previous_sentence if self._expand_window else None,
            next_sentence=next_sentence if self._expand_window else None,
        )
        try:
            result = await self._llm.complete(
                prompt,
                system=_SYSTEM_PROMPT,
                json_schema=_OUTPUT_SCHEMA,
                temperature=0.0,
                timeout_s=self._llm_timeout_s,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "relation extraction LLM call failed for sentence_index=%d: %s",
                central_sentence.index,
                exc,
            )
            return []

        return self._parse_relations(result.text, central_sentence=central_sentence)

    # ---------------------------------------------------------------- prompt

    def _build_prompt(
        self,
        *,
        central_sentence: Sentence,
        mentions: Sequence[Mention],
        previous_sentence: Sentence | None,
        next_sentence: Sentence | None,
    ) -> str:
        mentions_block = self._format_mentions(mentions)
        types_block = self._format_allowed_types()
        if previous_sentence is None and next_sentence is None:
            # Single-sentence path (Plan §3a PID-2 default).
            return (
                f"Extract relations from this sentence:\n"
                f'"{central_sentence.text.strip()}"\n\n'
                f"{mentions_block}\n\n"
                f"{types_block}\n\n"
                "Return JSON with a single key 'relations' holding a list. "
                "Each relation's evidence_span MUST be a substring of the "
                "sentence above. When no relation is supported by the text, "
                'return {"relations": []}.'
            )
        # Expanded-window path (Plan §3a PID-2 hybrid hook).
        prev_text = previous_sentence.text.strip() if previous_sentence else "(none)"
        next_text = next_sentence.text.strip() if next_sentence else "(none)"
        return (
            "You are extracting relations from one specific sentence. "
            "Two adjacent sentences are provided ONLY for resolving "
            "pronouns and references. You MUST NOT extract a relation "
            "whose evidence span lies outside the central sentence.\n\n"
            "PREVIOUS SENTENCE (context only — do not extract from this):\n"
            f'"{prev_text}"\n\n'
            "CENTRAL SENTENCE (extract relations FROM HERE):\n"
            f'"{central_sentence.text.strip()}"\n\n'
            "NEXT SENTENCE (context only — do not extract from this):\n"
            f'"{next_text}"\n\n'
            f"{mentions_block}\n\n"
            f"{types_block}\n\n"
            "Return JSON with a single key 'relations' holding a list. "
            "For each relation, evidence_span MUST be a substring of the "
            "CENTRAL SENTENCE (not previous or next). When no relation is "
            'supported by the central sentence, return {"relations": []}.'
        )

    @staticmethod
    def _format_mentions(mentions: Sequence[Mention]) -> str:
        """Render the per-sentence mention list as prompt text."""
        if not mentions:
            return "Mentioned entities: (none extracted by NER)"
        # Dedupe on (text, label) so repeated mentions in the same
        # sentence don't make the prompt verbose.
        seen: set[tuple[str, str]] = set()
        unique: list[Mention] = []
        for m in mentions:
            key = (m.text, m.label)
            if key in seen:
                continue
            seen.add(key)
            unique.append(m)
        lines = [f'  "{m.text}" ({m.label})' for m in unique]
        return "Mentioned entities (from NER):\n" + "\n".join(lines)

    @staticmethod
    def _format_allowed_types() -> str:
        return "Allowed relation types: " + ", ".join(RELATION_TYPES_LIST)

    # ---------------------------------------------------------------- parse

    def _parse_relations(
        self,
        text: str,
        *,
        central_sentence: Sentence,
    ) -> list[ExtractedRelation]:
        """Parse the LLM's JSON, normalise types, validate evidence_span."""
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "relation extraction JSON parse failed sentence_index=%d: %s; raw=%r",
                central_sentence.index,
                exc,
                text[:200],
            )
            return []
        if not isinstance(payload, dict):
            log.warning(
                "relation extraction returned non-object payload sentence_index=%d",
                central_sentence.index,
            )
            return []
        raw_relations = payload.get("relations", [])
        if not isinstance(raw_relations, list):
            log.warning(
                "relation extraction 'relations' is not a list sentence_index=%d",
                central_sentence.index,
            )
            return []

        normalised_central = fully_normalise(central_sentence.text)
        out: list[ExtractedRelation] = []
        for raw in raw_relations:
            relation = self._validate_one(raw, normalised_central=normalised_central)
            if relation is not None:
                out.append(relation)
        return out

    @staticmethod
    def _validate_one(
        raw: object,
        *,
        normalised_central: str,
    ) -> ExtractedRelation | None:
        """Validate one raw relation dict; return None on failure."""
        if not isinstance(raw, dict):
            return None
        subject = raw.get("subject")
        obj = raw.get("object")
        relation_type_raw = raw.get("relation_type")
        evidence_span = raw.get("evidence_span")
        confidence_raw = raw.get("confidence")
        reasoning = raw.get("reasoning", "")
        if not isinstance(subject, str) or not subject.strip():
            return None
        if not isinstance(obj, str) or not obj.strip():
            return None
        if not isinstance(relation_type_raw, str):
            return None
        if not isinstance(evidence_span, str) or not evidence_span.strip():
            return None
        if not isinstance(confidence_raw, (int, float)):  # noqa: UP038
            return None
        if not isinstance(reasoning, str):
            reasoning = ""

        # Plan §3a PID-2 Safeguard 3: evidence_span MUST be a substring
        # of central sentence after Unicode normalisation. Drop on miss.
        if fully_normalise(evidence_span) not in normalised_central:
            log.warning(
                "dropping relation: evidence_span outside central sentence; span=%r",
                evidence_span[:120],
            )
            return None

        normalised_type = normalise_relation_type(relation_type_raw)
        is_other = normalised_type == RelationType.OTHER.value and not is_known_relation_type(
            relation_type_raw
        )
        try:
            return ExtractedRelation(
                subject_text=subject.strip(),
                object_text=obj.strip(),
                relation_type=normalised_type,
                evidence_span=evidence_span,
                confidence=float(confidence_raw),
                reasoning=reasoning,
                is_other=is_other,
            )
        except (ValueError, TypeError) as exc:
            log.warning("dropping relation: validation failed: %s", exc)
            return None


__all__ = [
    "ExtractedRelation",
    "RelationExtractor",
]
