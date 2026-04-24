"""
GeminiLLMProvider — the Gen 1 default LLM (Plan §2.3, §3.3a).

Wraps ``google-genai`` behind the :class:`~theogony.agents.llm.LLMProvider`
protocol. Lazy SDK import keeps this module importable even when the
``gemini`` extra is not installed; the SDK is only required at
construction time, with a clear error message pointing at the right
``pip install`` command.

Pricing constants come from Plan §3.3a, verified against Google's
public pricing page on 2026-04-17:

    - input:  USD 0.10 / 1 M tokens
    - output: USD 0.40 / 1 M tokens
    - USD → EUR ≈ 0.93

Cost is computed from ``response.usage_metadata`` so :class:`LLMResult`
carries it onward to the Reporting layer (Plan §2.11). The class
attributes are overridable to absorb future price changes without
re-deploying provider code.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, SecretStr

from theogony.agents.llm import LLMResult, ResearchPlannerCost
from theogony.config.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("agents.llm_gemini")


class GeminiLLMProvider:
    """Production GeminiLLMProvider — default LLM for Gen 1.

    Parameters
    ----------
    api_key:
        Google AI Studio key. Accepts ``SecretStr`` (preferred — does
        not leak in repr) or raw ``str``. Required.
    model_id:
        Gemini model name. Default ``gemini-2.5-flash-lite``
        (Plan §3.3a recommendation).
    client:
        Optional pre-built ``google.genai.Client`` for dependency
        injection in tests. When omitted, the provider builds its own
        on first use.
    """

    USD_PER_M_INPUT_DEFAULT: float = 0.10
    USD_PER_M_OUTPUT_DEFAULT: float = 0.40
    USD_TO_EUR: float = 0.93

    def __init__(
        self,
        api_key: SecretStr | str | None,
        model_id: str = "gemini-2.5-flash-lite",
        *,
        client: Any | None = None,
        usd_per_m_input: float | None = None,
        usd_per_m_output: float | None = None,
    ) -> None:
        if api_key is None and client is None:
            raise ValueError("GeminiLLMProvider requires either api_key or a pre-built client")
        self._api_key_raw: str | None = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )
        self._model_id = model_id
        self._client: Any | None = client
        self._usd_per_m_input = (
            usd_per_m_input if usd_per_m_input is not None else self.USD_PER_M_INPUT_DEFAULT
        )
        self._usd_per_m_output = (
            usd_per_m_output if usd_per_m_output is not None else self.USD_PER_M_OUTPUT_DEFAULT
        )

    @property
    def model_id(self) -> str:
        return self._model_id

    def _ensure_client(self) -> Any:
        """Lazy SDK import + client construction.

        Importing ``google.genai`` at module load time would force every
        consumer of ``theogony.agents`` to install the ``gemini`` extra,
        even if they only use the StubLLMProvider. Deferring it to
        first call keeps the import surface clean.
        """
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - tested via separate path
            raise ImportError(
                "GeminiLLMProvider requires the `gemini` extra. "
                "Install with: pip install -e '.[gemini]'"
            ) from exc
        self._client = genai.Client(api_key=self._api_key_raw)
        return self._client

    def _cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        usd = (input_tokens / 1_000_000) * self._usd_per_m_input + (
            output_tokens / 1_000_000
        ) * self._usd_per_m_output
        return usd * self.USD_TO_EUR

    def _build_config(
        self,
        *,
        system: str | None,
        json_schema: dict[str, Any] | None,
        max_output_tokens: int | None,
        temperature: float,
    ) -> Any:
        """Translate protocol kwargs into google-genai's GenerateContentConfig."""
        from google.genai import types

        kwargs: dict[str, Any] = {"temperature": temperature}
        if system is not None:
            kwargs["system_instruction"] = system
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens
        if json_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = _to_gemini_schema(json_schema)
        return types.GenerateContentConfig(**kwargs)

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
        client = self._ensure_client()
        config = self._build_config(
            system=system,
            json_schema=json_schema,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                response = await client.aio.models.generate_content(
                    model=self._model_id,
                    contents=prompt,
                    config=config,
                )
        except TimeoutError:
            log.warning("gemini timeout model_id=%s timeout_s=%s", self._model_id, timeout_s)
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = getattr(response, "text", None) or ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=self._cost_eur(input_tokens, output_tokens),
            latency_ms=latency_ms,
            model_id=self._model_id,
        )

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type,
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        del system_prompt, user_prompt, output_schema, max_search_calls, max_total_tokens
        raise NotImplementedError("web_search planning requires Anthropic")


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a standard JSON Schema fragment into the form Gemini accepts.

    Gemini's ``response_schema`` is OpenAPI-3-flavoured and rejects two
    common JSON-Schema-2020-12 idioms:

    1. ``"type": ["string", "null"]`` — a type-array means
       "either string or null" in JSON Schema; Gemini wants a single
       type plus ``"nullable": true``.
    2. Top-level ``additionalProperties`` is fine but Gemini ignores
       most string-format hints — a soft no-op rather than an error,
       so we leave it intact.

    This converter walks the schema recursively and rewrites every
    ``type``-array into single-type-plus-``nullable``. Other shape
    differences are passed through untouched. Works for the small
    schemas the extraction pipeline uses (BookContext, Stage 4); a
    fully general JSON-Schema → OpenAPI converter is PHX-deferrable
    (PHX-0027 LLM provider re-evaluation will re-open it when we
    swap providers).
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        # Gemini's OpenAPI-3 schema does not understand a handful of
        # JSON-Schema-2020-12 keywords and rejects payloads that
        # include them. Strip them silently — they are advisory in
        # standard JSON Schema anyway, so the loss is the absence of
        # validator strictness, not semantic content.
        if key in _GEMINI_UNSUPPORTED_KEYS:
            continue
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            if len(non_null) == 1 and "null" in value:
                out["type"] = non_null[0]
                out["nullable"] = True
                continue
            # Multi-type without null, or all-null: leave untouched and
            # let Gemini decide whether to accept (it generally won't —
            # callers should narrow these themselves).
            out[key] = value
        elif key == "properties" and isinstance(value, dict):
            out[key] = {k: _to_gemini_schema(v) for k, v in value.items()}
        elif isinstance(value, dict):
            # Covers ``items`` (array element schema) and any other
            # nested-schema slot — recurse uniformly.
            out[key] = _to_gemini_schema(value)
        else:
            out[key] = value
    return out


# JSON-Schema keywords Gemini's response_schema rejects. ``pattern`` is
# fine; ``additionalProperties`` is the canonical strictness lever in
# JSON Schema but Gemini doesn't model it. ``$schema`` is meta and
# never relevant inside a Gemini config.
_GEMINI_UNSUPPORTED_KEYS: frozenset[str] = frozenset(
    {"additionalProperties", "$schema", "$id", "$ref"}
)
