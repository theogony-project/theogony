"""
LLMProvider protocol and the deterministic stub used by tests.

Plan §2.3 specifies three first-class providers behind a single
Protocol — Gemini (default, §3.3a), OpenAI, Anthropic — plus a Stub
that ships scripted responses for offline development.

The Protocol shape is intentionally small: one async method,
``complete``, with optional structured-output enforcement via JSON
Schema. The downstream consumers (RelationExtractor, EntityResolver
LLM disambiguation, AnswerSynthesizer) all reduce to "send a prompt,
get text back, optionally validated against a schema".

JSON-Schema enforcement is plumbed through as a dict so each
provider's native API can do the work — Gemini's
``response_schema``, OpenAI's ``response_format={"type":"json_schema"}``,
Anthropic's tool-as-output. The protocol does not commit to a single
back-end's vocabulary.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMResult(BaseModel):
    """Structured response from any :class:`LLMProvider`.

    Token counts and cost are recorded on the result so the future
    Reporting layer (Plan §2.11) can populate
    :class:`~theogony.reporting.models.SynthesisBreakdown` and the
    `cost_eur` aggregate without having to reach back into the
    provider client.

    Cost in EUR (not USD) so it lines up with the Plan §3.3a budget
    table without per-call conversion.
    """

    text: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_eur: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    model_id: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """Strategy interface for hosted (or stubbed) LLMs.

    Implementations MUST:
        - be safe to call concurrently from asyncio tasks (the
          extraction pipeline runs at concurrency 8 per Plan §4.1).
        - respect ``timeout_s`` — the FastAPI ``serve`` lifespan
          relies on cancellation propagating cleanly (Plan §4.4).
        - return an :class:`LLMResult` with at least ``text`` populated.

    Implementations MAY:
        - support ``json_schema`` to enforce structured output;
          providers that don't (or that fail to honour the schema)
          must raise so the caller's Pydantic validator catches it
          rather than parsing junk.
    """

    @property
    def model_id(self) -> str: ...

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float = 30.0,
    ) -> LLMResult:
        """Send `prompt` to the model and return its response."""
        ...


class StubLLMProvider:
    """Deterministic, offline LLM for tests and CI.

    The provider holds a ``responses`` dict keyed by *prompt prefix* —
    when ``complete`` is called, the longest matching prefix wins, and
    the corresponding canned response is returned. A ``default``
    response is used when nothing matches.

    Why prefix-match (not exact match): real test scenarios assemble
    prompts from templates with variable parts (e.g. ``"Extract
    relations from:\\n<sentence>"``). Pinning canned responses to the
    template prefix lets a single fixture cover many sentence
    variations.

    The stub records every call in ``calls`` so tests can assert
    "the synthesizer asked once with the constellation prompt" without
    any HTTP mocking.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str = "",
        model_id: str = "stub-llm",
        latency_ms: int = 0,
    ) -> None:
        self._responses: dict[str, str] = dict(responses or {})
        self._default = default
        self._model_id = model_id
        self._latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    def add_response(self, prompt_prefix: str, response: str) -> None:
        """Register a canned response. Tests can build the script up incrementally."""
        self._responses[prompt_prefix] = response

    def _match(self, prompt: str) -> str:
        """Longest-matching-prefix lookup, falling back to default."""
        best = ""
        for prefix in self._responses:
            if prompt.startswith(prefix) and len(prefix) > len(best):
                best = prefix
        if best:
            return self._responses[best]
        return self._default

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float = 30.0,
    ) -> LLMResult:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "json_schema": json_schema,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
                "timeout_s": timeout_s,
            }
        )
        text = self._match(prompt)
        # Token counts: simple word-count proxy. Good enough for tests
        # asserting "the report records non-zero tokens".
        input_tokens = len(prompt.split()) + (len(system.split()) if system else 0)
        output_tokens = len(text.split())
        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=0.0,
            latency_ms=self._latency_ms,
            model_id=self._model_id,
        )
