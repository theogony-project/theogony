"""
AnswerSynthesizer — turn a Constellation into a cited natural-language answer.

Plan §2.6 / §9.1; E8 brief.

The single LLM-using component in the retrieval stack. Takes a slim
``Constellation`` (Plan §9.1: no embeddings, no full KnowledgeNode
records), composes a prompt, calls ``LLMProvider.complete``, parses
the response, and returns an :class:`Answer` ready to drop into a
``QueryRunReport``.

Three discipline points (E8 brief):

1. **Plain-text completion.** No ``json_schema=`` constraint. Every
   provider supports text; structured citation parsing is owned here
   as a single regex. Forcing JSON would cap the answer at JSON-grammar
   tokens for marginal robustness gain.
2. **Citation grammar is exact.** ``\\[(AKA-[a-f0-9]+)\\]`` is the
   parser; the system prompt instructs the LLM to use exactly that
   bracket grammar. The regex tolerates ``**emphasis**`` markers
   (``[**AKA-abc123**]``) inside the brackets — Gemini occasionally
   wraps citations in markdown emphasis, and the cost of accepting
   that ($0) beats a Plan-deviation discussion every time it
   happens. Same kind of "real-LLM brittleness" deviation the brief
   anticipates.
3. **Citation invariant.** Every id in ``Answer.cited_node_ids`` MUST
   appear in ``constellation.nodes``. If the LLM cites an id that is
   not in the constellation, the synthesizer drops it and emits a
   WARNING. Tests assert this; the docstring on ``synthesize`` makes
   the invariant explicit so downstream consumers (the Hover-Lupe,
   the report's CitationQuality) can rely on it.

The system prompt is shipped inside the package as
``theogony.retrieval.prompts.answer_synthesizer.md`` and loaded via
:func:`importlib.resources.files` (PHX-0049, Hesiod Option A). Wheel
installs from PyPI and editable installs both find it; tests can
override by passing an explicit ``prompt_path`` to the constructor.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.core.model import Constellation
from theogony.reporting.models import SynthesisBreakdown

if TYPE_CHECKING:
    from theogony.extraction.audit import ExtractionAuditLog

log = get_logger("retrieval.synthesize")

#: Audit-log stage tag — matches the convention established in
#: BookContextExtractor / EntityResolver Stage 4 / RelationExtractor
#: (Plan §8 / PHX-0038 audit-log tracking).
_AUDIT_STAGE = "answer_synthesis"

#: Resource anchor for the packaged system prompt. Lives inside the
#: distribution as ``theogony/retrieval/prompts/answer_synthesizer.md``;
#: ``importlib.resources.files`` resolves it identically for editable
#: installs and wheel installs (PHX-0049 Option A). Tests that need a
#: specific on-disk file pass ``prompt_path=Path(...)`` directly.
_PROMPT_PACKAGE = "theogony.retrieval.prompts"
_PROMPT_RESOURCE = "answer_synthesizer.md"


def _load_default_prompt() -> str:
    """Read the packaged system prompt via ``importlib.resources``.

    Raises ``FileNotFoundError`` when the prompt is missing from the
    install — possible if a packager strips the package's
    ``prompts/`` subdirectory or drops the ``__init__.py`` that turns
    it into a sub-package.
    """
    try:
        return (
            resources.files(_PROMPT_PACKAGE).joinpath(_PROMPT_RESOURCE).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:  # pragma: no cover - defensive
        raise FileNotFoundError(
            f"AnswerSynthesizer system prompt not found in package "
            f"{_PROMPT_PACKAGE!r}; check the install includes "
            f"src/theogony/retrieval/prompts/{_PROMPT_RESOURCE}."
        ) from exc


#: Citation regex (see module docstring point 2). Tolerates
#: ``[**…**]`` and ``[*…*]`` so Gemini's occasional emphasis wrapping
#: does not silently drop valid citations.
_CITATION_RE = re.compile(r"\[\*{0,2}(AKA-[a-f0-9]+)\*{0,2}\]")


class Answer(BaseModel):
    """Synthesised, citation-anchored answer to a single user query."""

    model_config = ConfigDict(extra="forbid")

    text: str
    cited_node_ids: list[str] = Field(default_factory=list)
    raw_llm_response: str = ""
    synthesis: SynthesisBreakdown = Field(default_factory=SynthesisBreakdown)


class AnswerSynthesizer:
    """LLM-driven synthesis of a Constellation into a cited prose answer."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        prompt_path: Path | None = None,
        audit_log: ExtractionAuditLog | None = None,
        audit_run_id: str | None = None,
    ) -> None:
        self._llm = llm
        # When prompt_path is given, read it directly (test surface).
        # Otherwise resolve via importlib.resources from the packaged
        # location — works for editable installs AND wheel installs
        # (PHX-0049 Hesiod Option A).
        self._prompt_path = prompt_path
        if prompt_path is not None:
            if not prompt_path.exists():
                raise FileNotFoundError(
                    f"AnswerSynthesizer system prompt not found at {prompt_path}; "
                    "pass an existing path or omit prompt_path to use the packaged default."
                )
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        else:
            self._system_prompt = _load_default_prompt()
        self._audit_log = audit_log
        self._audit_run_id = audit_run_id

    async def synthesize(
        self,
        constellation: Constellation,
        *,
        max_output_tokens: int | None = 600,
        temperature: float = 0.0,
        run_id: str | None = None,
    ) -> Answer:
        """Synthesise a cited answer for the given Constellation.

        Invariant: every id in the returned ``Answer.cited_node_ids``
        is present in ``constellation.nodes``. Hallucinated ids are
        dropped + a WARNING is logged with the dropped id and the
        query that produced it (so the Reviewer agent can audit
        prompt-vs-output drift over time).

        ``run_id`` overrides the constructor-supplied audit_run_id
        when both are provided. When neither is set and an audit_log
        is configured, the call is silently not audited (the audit
        log requires a run_id).
        """
        prompt = self._build_user_prompt(constellation)
        identifier = constellation.query

        try:
            result = await self._llm.complete(
                prompt,
                system=self._system_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            # Audit the failure with a transport_error parse_error tag so
            # the Reviewer agent can bucket failure modes — same contract
            # as BookContextExtractor / RelationExtractor.
            log.warning(
                "answer synthesis LLM call failed for query=%r: %s — returning empty answer",
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
            return Answer(
                text="",
                cited_node_ids=[],
                raw_llm_response="",
                synthesis=SynthesisBreakdown(),
            )

        all_cited = self._extract_citations(result.text)
        valid_ids = {n.id for n in constellation.nodes}
        kept: list[str] = []
        dropped: list[str] = []
        for cid in all_cited:
            if cid in valid_ids:
                kept.append(cid)
            else:
                dropped.append(cid)
        if dropped:
            log.warning(
                "synthesizer dropped %d hallucinated citation(s) %s for query=%r",
                len(dropped),
                dropped,
                identifier,
            )
        parse_error = "hallucinated_citations" if dropped else None
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
        return Answer(
            text=result.text,
            cited_node_ids=kept,
            raw_llm_response=result.text,
            synthesis=SynthesisBreakdown(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_eur=result.cost_eur,
                latency_ms=result.latency_ms,
            ),
        )

    @staticmethod
    def _extract_citations(text: str) -> list[str]:
        """Extract deduplicated, source-order-preserving AKA-… ids from ``text``.

        Exposed (rather than ``_private``) for direct test coverage of
        the citation grammar. The regex tolerates markdown emphasis
        markers around the id (see module docstring).
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for match in _CITATION_RE.finditer(text):
            cid = match.group(1)
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        return ordered

    def _build_user_prompt(self, constellation: Constellation) -> str:
        """Compose the user-facing prompt body.

        The slim Constellation is dumped as JSON (Pydantic's
        ``model_dump_json`` excludes the embeddings the slim DTOs
        already strip). When the constellation is insufficient
        (``Constellation.is_sufficient`` is False), an explicit
        prefix is prepended so the LLM gives the honest "not enough
        in the Chronik" answer the system prompt asks for.
        """
        body = constellation.model_dump_json(indent=2, exclude_none=False)
        sufficiency_note = (
            ""
            if constellation.is_sufficient
            else (
                "NOTE: This Constellation is below the sufficiency threshold "
                "(<3 nodes or <1 edge). Answer honestly that the Chronik does "
                "not yet have enough on this topic.\n\n"
            )
        )
        return (
            f"{sufficiency_note}"
            f"User query: {constellation.query}\n\n"
            f"Constellation (slim DTOs — every node id is citable):\n"
            f"{body}\n\n"
            "Answer the query using only the supplied Constellation. "
            "Cite every claim with [AKA-…] per the system-prompt grammar."
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


__all__ = ["Answer", "AnswerSynthesizer"]
