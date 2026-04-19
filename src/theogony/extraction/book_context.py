"""
BookContextExtractor — distil a tiny, structured fingerprint of the book
that EntityResolver Stage 4 hands to the LLM during disambiguation
(Plan §3.4 v3).

Plan §3.4 verbatim:

    The book itself provides context: "Seven Years in Tibet" is set
    1939–1951, in Tibet/India/Nepal, with German-speaking Austrian
    protagonists. We extract this context once at ingest start (a
    small structured prompt against the book's metadata + opening
    pages: "What time period is this book set in? What places? What
    kinds of people are central?"). The result is a BookContext
    Pydantic model passed into every disambiguation.

This module owns that one-off LLM call. Output is a strictly-typed
:class:`BookContext`. The shape is small on purpose — Stage 4's
prompt template inlines it verbatim, so anything bigger would balloon
every per-mention disambiguation prompt by N candidates × the context
size.

Cost: one Gemini 2.5 Flash Lite call per ingest, roughly ~2 000 input
tokens (book title + authors + ~6 KB of opening text) + ~200 output
tokens. At Plan §3.3a pricing this is well below 0.001 EUR per book —
genuinely negligible against the rest of the pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from theogony.acquisition.base import RawContent
from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.sentence import Sentence

log = get_logger("extraction.book_context")


_AUDIT_STAGE = "book_context"


DEFAULT_MAX_OPENING_CHARS = 8_000
"""Roughly the first 6-8 pages of prose — enough for an LLM to infer
genre, era, and regional setting without paying for the whole book."""


_SYSTEM_PROMPT = (
    "You read the opening of a book and extract a tiny structured "
    "context: when it is set, where it takes place, what kinds of "
    "people are central. You answer ONLY with JSON matching the "
    "supplied schema. You do not invent facts. When the opening text "
    "does not establish a fact, the corresponding field is null or "
    "an empty list. Keep each list under 20 entries and the summary "
    "under 1000 characters."
)


_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "time_period": {
            "type": ["string", "null"],
            "description": (
                "Time the book is set in, as a short human-readable "
                "string (e.g. '1899-1908', 'early 20th century', "
                "'Han dynasty'). null when the opening does not "
                "establish it."
            ),
        },
        "places": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": (
                "Geographic places the book is set in or refers to "
                "centrally. Modern names where applicable. Empty when "
                "no place is explicitly established."
            ),
        },
        "people_descriptors": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "description": (
                "Short descriptors of the kinds of people central to "
                "the narrative — occupations, nationalities, ethnic "
                "groups, roles. Examples: 'Swedish geographer', "
                "'Tibetan monks', 'British colonial officials'."
            ),
        },
        "summary": {
            "type": "string",
            "maxLength": 1000,
            "description": (
                "Two-to-four-sentence summary of what the book appears "
                "to be about, useful as orienting context to a "
                "disambiguating LLM. Empty string when the opening is "
                "too thin to summarise."
            ),
        },
    },
    "required": ["time_period", "places", "people_descriptors", "summary"],
    "additionalProperties": False,
}


class BookContext(BaseModel):
    """Tiny structured fingerprint of the book under ingest.

    Carried by the ``EntityResolver`` and inlined into every Stage-4
    disambiguation prompt. The fields are intentionally cheap to
    serialise — Plan §3.4 wants this to add ~100 tokens to each
    candidate prompt, not 5 000.

    ``derived_from_book`` and ``derived_from_model_id`` make the
    context auditable: a future Reviewer agent looking at a Tier-2
    resolution can trace back through the run report to the LLM
    that produced the context this disambiguation was conditioned on.
    """

    model_config = ConfigDict(extra="forbid")

    time_period: str | None = Field(
        default=None,
        description=(
            "Time the book is set in, e.g. '1899-1908' or "
            "'early 20th century'. None when the opening doesn't "
            "establish it."
        ),
    )
    places: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Geographic places central to the narrative, in any "
            "stable order. Empty when the opening is silent."
        ),
    )
    people_descriptors: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Descriptors of the kinds of people central to the book "
            "(occupations, nationalities, ethnic groups, roles)."
        ),
    )
    summary: str = Field(
        default="",
        max_length=1000,
        description="Two-to-four-sentence orientation for downstream LLM prompts.",
    )
    derived_from_book: str | None = Field(
        default=None,
        description=(
            "Source identifier of the book this context was derived "
            "from (e.g. 'Gutenberg:43497'). Audit-only; the resolver "
            "does not consume this field."
        ),
    )
    derived_from_model_id: str = Field(
        default="",
        description=(
            "Model id of the LLM that produced this context "
            "(e.g. 'gemini-2.5-flash-lite' or 'stub-llm'). Recorded "
            "so a future Reviewer agent can correlate context "
            "quality with model identity."
        ),
    )

    def to_prompt_block(self) -> str:
        """Render the context as a compact, prompt-ready block.

        Used by EntityResolver Stage 4 to inline the book context
        into per-candidate disambiguation prompts. Keeps the format
        identical across the whole ingest so the LLM does not see
        different wrappers per call.
        """
        lines: list[str] = []
        if self.time_period:
            lines.append(f"Time period: {self.time_period}")
        if self.places:
            lines.append("Places: " + ", ".join(self.places))
        if self.people_descriptors:
            lines.append("Central people: " + ", ".join(self.people_descriptors))
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        if not lines:
            return "Book context: (none established by the opening pages.)"
        return "Book context:\n" + "\n".join(f"  {ln}" for ln in lines)


class BookContextExtractor:
    """Run one structured-output LLM call to derive a :class:`BookContext`.

    The constructor takes any :class:`~theogony.agents.llm.LLMProvider`
    — the production path uses
    :class:`~theogony.agents.llm_gemini.GeminiLLMProvider`, tests use
    :class:`~theogony.agents.llm.StubLLMProvider`. The component is
    stateless across calls (modulo the LLM client it holds).

    On LLM failure (timeout, schema-validation error, refusal, raw
    transport error) the extractor returns an *empty* BookContext
    rather than raising. The honest-failure principle: a missing
    book context downgrades Stage 4's signal but does not break
    ingest. Plan §3.4 anticipated this — Tier 1 ("LLM with sentence
    context only") exists exactly for the no-bio-facts / no-context
    case.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        max_opening_chars: int = DEFAULT_MAX_OPENING_CHARS,
        timeout_s: float = 30.0,
        audit_log: ExtractionAuditLog | None = None,
        audit_run_id: str | None = None,
    ) -> None:
        if max_opening_chars <= 0:
            raise ValueError(f"max_opening_chars must be positive; got {max_opening_chars}")
        self._llm = llm
        self._max_opening_chars = max_opening_chars
        self._timeout_s = timeout_s
        self._audit_log = audit_log
        self._audit_run_id = audit_run_id

    async def extract(
        self,
        *,
        raw_content: RawContent,
        opening_sentences: Sequence[Sentence],
        run_id: str | None = None,
    ) -> BookContext:
        """Produce a :class:`BookContext` for the given book.

        ``opening_sentences`` should be the first ~50-200 sentences
        from the cleaned content — enough text for an LLM to infer
        setting, not so much that the prompt blows past sensible
        sizes. The extractor truncates to ``max_opening_chars``
        regardless, so over-supplying is safe but wasteful.

        ``run_id`` overrides the constructor-supplied audit_run_id
        when both are provided. When neither is set and an audit_log
        is configured, the call is silently not audited (the audit
        log requires a run_id).

        Returns an empty BookContext (with ``derived_from_book``
        populated) when the LLM fails for any reason — the calling
        ingest pipeline must continue.
        """
        opening_text = self._render_opening(opening_sentences)
        prompt = self._build_prompt(raw_content=raw_content, opening_text=opening_text)
        identifier = f"{raw_content.source_type}:{raw_content.identifier}"

        try:
            result = await self._llm.complete(
                prompt,
                system=_SYSTEM_PROMPT,
                json_schema=_OUTPUT_SCHEMA,
                temperature=0.0,
                timeout_s=self._timeout_s,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "book context extraction failed for %s: %s — returning empty context",
                identifier,
                exc,
            )
            self._maybe_audit(
                run_id=run_id,
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                cost_eur=0.0,
                latency_ms=0,
                model_id=getattr(self._llm, "model_id", ""),
                parse_error=f"transport_error:{type(exc).__name__}",
            )
            return BookContext(
                derived_from_book=identifier,
                derived_from_model_id=getattr(self._llm, "model_id", ""),
            )

        ctx = self._parse_response(result.text, identifier=identifier)
        # parse_error tag is "json_decode" / "validation" / None depending
        # on whether the response was usable. The empty BookContext
        # returned by _parse_response on failure carries no time_period /
        # places etc., so we infer the failure mode from result.text.
        parse_error = self._infer_parse_error(result.text)
        self._maybe_audit(
            run_id=run_id,
            prompt=prompt,
            response=result.text,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_eur=result.cost_eur,
            latency_ms=result.latency_ms,
            model_id=result.model_id,
            parse_error=parse_error,
        )
        return ctx

    # ----------------------------------------------------------------- helpers

    def _render_opening(self, sentences: Sequence[Sentence]) -> str:
        """Concatenate sentences up to ``max_opening_chars``.

        Sentences are joined with their natural surrounding whitespace
        (each ``Sentence.text`` already includes trailing whitespace
        from spaCy). When the budget is hit mid-sentence we stop on
        the previous sentence boundary — partial sentences hurt LLM
        reasoning more than missing ones do.
        """
        if not sentences:
            return ""
        out_parts: list[str] = []
        running = 0
        for sent in sentences:
            text = sent.text
            if running + len(text) > self._max_opening_chars and running > 0:
                break
            out_parts.append(text)
            running += len(text)
        return "".join(out_parts).strip()

    def _build_prompt(self, *, raw_content: RawContent, opening_text: str) -> str:
        """Assemble the prompt body. Keep the wrapping minimal — the
        system prompt does the heavy lifting on instructions."""
        authors = ", ".join(raw_content.authors) if raw_content.authors else "(unknown)"
        language = raw_content.language or "(unknown)"
        return (
            f"Title: {raw_content.title}\n"
            f"Authors: {authors}\n"
            f"Language: {language}\n"
            f"Opening text (first ~{self._max_opening_chars} chars):\n"
            f"---\n"
            f"{opening_text}\n"
            f"---\n"
            "Return JSON for: when is the book set, where is it set, "
            "what kinds of people are central, and a brief summary."
        )

    def _maybe_audit(
        self,
        *,
        run_id: str | None,
        prompt: str,
        response: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
        latency_ms: int,
        model_id: str,
        parse_error: str | None,
    ) -> None:
        """Record one audit row when a log + run_id are both available."""
        if self._audit_log is None:
            return
        effective_run_id = run_id or self._audit_run_id
        if not effective_run_id:
            return
        self._audit_log.record(
            run_id=effective_run_id,
            stage=_AUDIT_STAGE,
            prompt=prompt,
            response=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=cost_eur,
            latency_ms=latency_ms,
            model_id=model_id,
            parse_error=parse_error,
        )

    @staticmethod
    def _infer_parse_error(text: str) -> str | None:
        """Best-effort tag for the audit log's parse_error column.

        We avoid double-parsing by mirroring _parse_response's failure
        modes here. Returns None when the response is at least valid
        JSON; the BookContext consumer (resolver/Stage 4) is the
        authority on whether the content was usable.
        """
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return "json_decode"
        return None

    def _parse_response(self, text: str, *, identifier: str) -> BookContext:
        """Parse the LLM's JSON response into a :class:`BookContext`.

        On JSON-decode or validation failure, log and return an empty
        context — never raise into the ingest pipeline.
        """
        model_id = getattr(self._llm, "model_id", "")
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "book context JSON parse failed for %s: %s; raw=%r",
                identifier,
                exc,
                text[:200],
            )
            return BookContext(
                derived_from_book=identifier,
                derived_from_model_id=model_id,
            )
        try:
            return BookContext(
                time_period=payload.get("time_period"),
                places=payload.get("places", []) or [],
                people_descriptors=payload.get("people_descriptors", []) or [],
                summary=payload.get("summary", "") or "",
                derived_from_book=identifier,
                derived_from_model_id=model_id,
            )
        except ValidationError as exc:
            log.warning(
                "book context validation failed for %s: %s; payload keys=%s",
                identifier,
                exc,
                list(payload.keys()) if isinstance(payload, dict) else "(non-dict)",
            )
            return BookContext(
                derived_from_book=identifier,
                derived_from_model_id=model_id,
            )


__all__ = [
    "DEFAULT_MAX_OPENING_CHARS",
    "BookContext",
    "BookContextExtractor",
]
