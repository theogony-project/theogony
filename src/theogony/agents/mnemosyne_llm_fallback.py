"""Rate-limited LLM escalation for Mnemosyne uncertain band (PHX-0071 / W5)."""

from __future__ import annotations

import json
import time
from collections import deque
from importlib import resources

from pydantic import BaseModel, ConfigDict

from theogony.agents.llm import LLMProvider
from theogony.reporting.models import MetaClassification, MetaClassificationVerdict
from theogony.retrieval.synthesize import Answer


def mnemosyne_classifier_system_prompt() -> str:
    return (
        resources.files("theogony.agents.prompts")
        .joinpath("mnemosyne_classifier.md")
        .read_text(encoding="utf-8")
    )


class _LLMVerdictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: str
    rationale: str = ""


class MnemosyneLLMFallback:
    """Rate-limited LLM classifier for Mnemosyne's uncertain band."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        max_calls_per_hour: int,
        max_cost_eur_per_call: float,
    ) -> None:
        self._llm = llm
        self._max_calls = max_calls_per_hour
        self._max_cost = max_cost_eur_per_call
        self._calls: deque[float] = deque()

    def _prune(self, now: float) -> None:
        horizon = now - 3600.0
        while self._calls and self._calls[0] < horizon:
            self._calls.popleft()

    async def classify(self, *, query: str, answer: Answer) -> MetaClassification | None:
        now = time.monotonic()
        self._prune(now)
        if self._max_calls == 0 or len(self._calls) >= self._max_calls:
            return None

        system = mnemosyne_classifier_system_prompt()
        user = f"Query:\n{query}\n\nAnswer excerpt:\n{answer.text[:4000]}\n"
        result = await self._llm.complete(
            user,
            system=system,
            max_output_tokens=256,
            temperature=0.0,
        )
        if result.cost_eur > self._max_cost:
            return None

        line = result.text.strip().splitlines()[0] if result.text.strip() else ""
        try:
            raw = json.loads(line)
            payload = _LLMVerdictPayload.model_validate(raw)
        except (json.JSONDecodeError, ValueError):
            return None

        if payload.verdict == MetaClassificationVerdict.SELF_REFERENTIAL.value:
            verdict = MetaClassificationVerdict.SELF_REFERENTIAL
        elif payload.verdict == MetaClassificationVerdict.NOT_SELF_REFERENTIAL.value:
            verdict = MetaClassificationVerdict.NOT_SELF_REFERENTIAL
        else:
            return None

        self._calls.append(now)
        return MetaClassification(
            verdict=verdict,
            classifier_mode_used="llm_fallback",
            llm_cost_eur=result.cost_eur,
        )


__all__ = ["MnemosyneLLMFallback", "mnemosyne_classifier_system_prompt"]
