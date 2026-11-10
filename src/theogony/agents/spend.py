"""A spend limit for a run that calls a paid model (PHX-1124).

On 2026-11-08 a detached chain, after waiting twenty hours for its replays,
started four answer runs of 5,000 calls each against a DeepSeek account whose
balance had run out. The default fallback handed the failed calls to another
model, 10,732 of them in 70 minutes, and the runs wrote nothing (PHX-1123).
PHX-1123 took the fallback out of measurements. What remained is that nothing
asked, before a run, whether the account could pay, and nothing stopped a run
whose spending ran away. This module does both:

- :class:`SpendLimitedLLM` wraps a provider and refuses any call that could take
  the run past its limit: before the call it reserves what the call can cost at
  most, and settles the reservation with what the call did cost. The first
  refusal to pay (HTTP 402) stops the run at once instead of failing every call
  after it.
- :func:`preflight` asks, before the first paid call, whether the account is
  able to pay at least the limit, and sends one call of one output token that
  must go through.

A stop raises :class:`RunMustStop`. The harnesses re-raise it where they would
otherwise record a failed call as an empty answer, so a run that cannot pay
ends with a reason instead of finishing on empty answers.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider, LLMResult, ResearchPlannerCost

# Before the first call a provider without a price table cannot say what a
# call costs; a reservation of this much stands in until one has been paid.
_UNPRICED_RESERVATION_USD = 0.01
# A call that names no output limit is reserved as if it used this many.
_DEFAULT_OUTPUT_TOKENS = 8192
# DeepSeek counts an English character as about 0.3 tokens and a Chinese one
# as about 0.6; reserving 0.6 per character overestimates English input twice.
_TOKENS_PER_CHAR_AT_MOST = 0.6
_EUR_PER_USD = 0.93


class RunMustStop(Exception):
    """A condition after which this run makes no further paid call."""


class SpendLimitReached(RunMustStop):
    """The next call could take the run past its spend limit."""


class AccountCannotPay(RunMustStop):
    """The provider refused to be paid: no balance, or not enough for the limit."""


class AccountBalance(BaseModel):
    """What a provider says its account holds."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    usd: float | None = None
    by_currency: dict[str, float] = Field(default_factory=dict)


class PreflightReport(BaseModel):
    """What a run knew before its first paid call."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    served_model_id: str = ""
    limit_usd: float
    balance_usd: float | None = None
    probe_cost_usd: float = 0.0

    def line(self) -> str:
        served = f" (served by {self.served_model_id})" if self.served_model_id else ""
        balance = (
            f"{self.balance_usd:.2f} USD on the account"
            if self.balance_usd is not None
            else "the provider reports no balance"
        )
        return (
            f"preflight: {self.model_id}{served} answers; {balance}; limit {self.limit_usd:.2f} USD"
        )


def is_payment_refusal(exc: BaseException) -> bool:
    """Whether a provider error says the account cannot pay (HTTP 402)."""
    if getattr(exc, "status_code", None) == 402:
        return True
    return "insufficient balance" in str(exc).lower()


def _call_cost_usd(result: LLMResult) -> float:
    if result.cost_usd > 0:
        return result.cost_usd
    return result.cost_eur / _EUR_PER_USD


class SpendLimitedLLM:
    """A provider that a run may spend at most ``limit_usd`` through.

    Safe under asyncio concurrency: the check and the reservation happen with
    no await between them, so the calls in flight never reserve more than the
    limit leaves. ``on_spend`` is called with the wrapper after each paid call
    that crosses another tenth of the limit, for a running count in the run's
    log.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        limit_usd: float,
        on_spend: Callable[[SpendLimitedLLM], None] | None = None,
    ) -> None:
        if limit_usd <= 0:
            raise ValueError(f"limit_usd must be positive, not {limit_usd}")
        self.inner = inner
        self.limit_usd = float(limit_usd)
        self.spent_usd = 0.0
        self.calls = 0
        self.preflight: PreflightReport | None = None
        self._reserved_usd = 0.0
        self._largest_call_usd = 0.0
        self._stopped: RunMustStop | None = None
        self._on_spend = on_spend
        self._tenths_reported = 0

    @property
    def model_id(self) -> str:
        return str(self.inner.model_id)

    @property
    def stopped(self) -> RunMustStop | None:
        return self._stopped

    def summary(self) -> str:
        return f"spent {self.spent_usd:.4f} USD of {self.limit_usd:.2f} in {self.calls} calls"

    def _reservation_usd(
        self, prompt: str, system: str | None, max_output_tokens: int | None
    ) -> float:
        worst = getattr(self.inner, "worst_case_cost_usd", None)
        if callable(worst):
            chars = len(prompt) + len(system or "")
            return float(
                worst(
                    int(chars * _TOKENS_PER_CHAR_AT_MOST) + 1,
                    max_output_tokens if max_output_tokens is not None else _DEFAULT_OUTPUT_TOKENS,
                )
            )
        return max(self._largest_call_usd * 2, _UNPRICED_RESERVATION_USD)

    def halt(self, stop: RunMustStop) -> RunMustStop:
        """Stop the run: this call and every later one raise ``stop``."""
        if self._stopped is None:
            self._stopped = stop
        return self._stopped

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
        if self._stopped is not None:
            raise self._stopped
        reservation = self._reservation_usd(prompt, system, max_output_tokens)
        if self.spent_usd + self._reserved_usd + reservation > self.limit_usd:
            raise self.halt(
                SpendLimitReached(
                    f"the next call could cost up to {reservation:.4f} USD and the run has "
                    f"{self.limit_usd - self.spent_usd - self._reserved_usd:.4f} of its "
                    f"{self.limit_usd:.2f} USD limit left ({self.summary()})"
                )
            )
        self._reserved_usd += reservation
        try:
            result: LLMResult = await self.inner.complete(
                prompt,
                system=system,
                json_schema=json_schema,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )
        except Exception as exc:
            if is_payment_refusal(exc):
                raise self.halt(
                    AccountCannotPay(f"the provider refused payment: {exc} ({self.summary()})")
                ) from exc
            raise
        finally:
            self._reserved_usd -= reservation
        paid = _call_cost_usd(result)
        self.spent_usd += paid
        self.calls += 1
        self._largest_call_usd = max(self._largest_call_usd, paid)
        tenths = int(10 * self.spent_usd / self.limit_usd)
        if self._on_spend is not None and tenths > self._tenths_reported:
            self._tenths_reported = tenths
            self._on_spend(self)
        return result

    async def complete_with_web_search_for_research_plan(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
        max_search_calls: int = 3,
        max_total_tokens: int = 4000,
    ) -> tuple[BaseModel, ResearchPlannerCost]:
        # Not a measurement path; refused rather than spent around the limit.
        raise NotImplementedError("a spend-limited provider makes plain completions only")


async def preflight(llm: SpendLimitedLLM) -> PreflightReport:
    """Before a run's first paid call: can the account pay, and does a call go through?

    Raises :class:`AccountCannotPay` when the provider says the account is not
    available or holds less than the run's limit, and lets the probe's own
    error through when the probe fails otherwise (a wrong key, an unknown
    model). The probe asks for one output token and counts against the limit.
    """
    balance_usd: float | None = None
    query = getattr(llm.inner, "balance", None)
    if callable(query):
        balance = await query()
        balance_usd = balance.usd
        if not balance.available:
            raise llm.halt(AccountCannotPay(f"the provider says the account cannot pay: {balance}"))
        if balance.usd is not None and balance.usd < llm.limit_usd:
            raise llm.halt(
                AccountCannotPay(
                    f"the account holds {balance.usd:.2f} USD, less than the run's limit of "
                    f"{llm.limit_usd:.2f}; top it up, or lower the limit to what the run needs"
                )
            )
    probe = await llm.complete("Reply with the word OK.", max_output_tokens=1)
    report = PreflightReport(
        model_id=llm.model_id,
        served_model_id=probe.served_model_id,
        limit_usd=llm.limit_usd,
        balance_usd=balance_usd,
        probe_cost_usd=_call_cost_usd(probe),
    )
    llm.preflight = report
    return report


async def after_preflight[T](llm: SpendLimitedLLM, work: Callable[[], Awaitable[T]]) -> T:
    """Run ``work`` in the same event loop, once :func:`preflight` has passed."""
    report = await preflight(llm)
    print(report.line(), flush=True)
    return await work()


def run_paid[T](llm: SpendLimitedLLM, work: Callable[[], Awaitable[T]]) -> T:
    """For a script: ``work`` in one event loop after :func:`preflight`, and a
    stop ends the process with its reason instead of a traceback."""
    try:
        result = asyncio.run(after_preflight(llm, work))
    except RunMustStop as stop:
        sys.exit(f"STOPPED: {stop}")
    print(f"spend: {llm.summary()}", flush=True)
    return result


def print_spend(llm: SpendLimitedLLM) -> None:
    """The running count a run prints as its spending crosses each tenth of the limit."""
    print(f"spend: {llm.summary()}", flush=True)


__all__ = [
    "AccountBalance",
    "AccountCannotPay",
    "PreflightReport",
    "RunMustStop",
    "SpendLimitReached",
    "SpendLimitedLLM",
    "after_preflight",
    "is_payment_refusal",
    "preflight",
    "print_spend",
    "run_paid",
]
