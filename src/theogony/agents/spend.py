"""A spend limit for a run that calls a paid model (PHX-1124).

On 2026-11-08 a detached chain, after waiting twenty hours for its replays,
started four answer runs of 5,000 calls each against a DeepSeek account whose
balance had run out. The default fallback handed the failed calls to another
model, 10,732 of them in 70 minutes, and the runs wrote nothing (PHX-1123).
PHX-1123 took the fallback out of measurements. What remained is that nothing
asked, before a run, whether the account could pay, and nothing stopped a run
whose spending ran away. :class:`SpendLimitedLLM` does both:

- Before each attempt it reserves what the attempt can cost at most — every
  input token a cache miss, the output at the cap it sends with the request,
  at the peak rate — and refuses the attempt when that could take the run past
  its limit. So the calls in flight never reserve more than the limit leaves.
  The reservation is settled with what the attempt did cost; an attempt that
  failed in a way the provider may still bill (a timeout, a dropped
  connection, a server error) is charged at its reservation, one the provider
  refused (a 4xx) is not. It makes the retries itself, so each is counted,
  rather than leaving them to the SDK.
- Before its first paid attempt it runs :func:`preflight`: the account must
  say it can pay at least the limit, and a probe of one output token must go
  through. A run that has nothing to pay for — a rerun from a full cache —
  asks nothing.
- The first refusal to pay (HTTP 402, or the provider's words for it) stops
  the run; every later attempt raises the same stop without being made.

A stop raises :class:`RunMustStop`. The harnesses re-raise it where they would
otherwise record a failed call as an empty answer, so a run that cannot pay
ends with a reason instead of finishing on empty answers.

Only a provider that can price its worst case (``worst_case_cost_usd``) can be
limited this way; :func:`theogony.agents.factory.build_named_llm` refuses the
others.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider, LLMResult, ResearchPlannerCost

# A call that names no output limit is sent with this one, and reserved at it.
DEFAULT_OUTPUT_TOKENS = 8192
# DeepSeek counts an English character as about 0.3 tokens and a Chinese one
# as about 0.6; reserving 0.6 per character overestimates English input twice.
_TOKENS_PER_CHAR_AT_MOST = 0.6
_EUR_PER_USD = 0.93
# The retries the SDK would make (408, 409, 429, 5xx, timeouts, dropped
# connections), made here so that each is reserved and counted.
_RETRIES = 2
_RETRY_BACKOFF_S = 1.0
# The words providers use for "no money": DeepSeek's 402 "Insufficient
# Balance", Anthropic's 400 "Your credit balance is too low", OpenAI's 429
# "insufficient_quota".
_REFUSAL_WORDS = ("insufficient balance", "credit balance is too low", "insufficient_quota")


class RunMustStop(Exception):
    """A condition after which this run makes no further paid call."""


class SpendLimitReached(RunMustStop):
    """The next call could take the run past its spend limit."""


class AccountCannotPay(RunMustStop):
    """The provider refused to be paid: no balance, or not enough for the limit."""


class PreflightFailed(RunMustStop):
    """The probe before the run's first paid call failed: a wrong key, an unknown model."""


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
    """Whether a provider error says the account cannot pay."""
    if getattr(exc, "status_code", None) == 402:
        return True
    text = f"{exc} {getattr(exc, 'code', '') or ''}".lower()
    return any(words in text for words in _REFUSAL_WORDS)


def _status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def _is_refusal(exc: BaseException) -> bool:
    """A 4xx: the provider answered and declined; DeepSeek bills none of these."""
    status = _status(exc)
    return status is not None and 400 <= status < 500


def _is_retryable(exc: BaseException) -> bool:
    """What the OpenAI SDK retries by default: 408, 409, 429, 5xx, no answer at all."""
    status = _status(exc)
    if status is None:
        return isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__name__ in (
            "APITimeoutError",
            "APIConnectionError",
        )
    return status in (408, 409, 429) or status >= 500


def _call_cost_usd(result: LLMResult) -> float:
    if result.cost_usd > 0:
        return result.cost_usd
    return result.cost_eur / _EUR_PER_USD


def _print_line(text: str) -> None:
    print(text, flush=True)


class SpendLimitedLLM:
    """A provider that a run may spend at most ``limit_usd`` through.

    Safe under asyncio concurrency: the check and the reservation happen with
    no await between them. ``on_spend`` is called with the wrapper after a paid
    attempt that crosses another tenth of the limit, and ``on_preflight`` with
    the preflight's one-line report, for a running count in the run's log.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        limit_usd: float,
        on_spend: Callable[[SpendLimitedLLM], None] | None = None,
        on_preflight: Callable[[str], None] | None = _print_line,
    ) -> None:
        if not limit_usd > 0:  # also refuses NaN
            raise ValueError(f"limit_usd must be a positive number, not {limit_usd}")
        if not callable(getattr(inner, "worst_case_cost_usd", None)):
            raise ValueError(
                f"{type(inner).__name__} cannot price the most a call may cost "
                "(worst_case_cost_usd), so a spend limit cannot bound it (PHX-1124)"
            )
        self.inner = inner
        self.limit_usd = float(limit_usd)
        self.spent_usd = 0.0
        self.calls = 0
        self.attempts = 0
        self.preflight: PreflightReport | None = None
        self._reserved_usd = 0.0
        self._stopped: RunMustStop | None = None
        self._on_spend = on_spend
        self._on_preflight = on_preflight
        self._tenths_reported = 0
        self._lock: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None

    @property
    def model_id(self) -> str:
        return str(self.inner.model_id)

    @property
    def stopped(self) -> RunMustStop | None:
        return self._stopped

    def summary(self) -> str:
        return (
            f"spent {self.spent_usd:.4f} USD of {self.limit_usd:.2f} in {self.calls} calls"
            f" ({self.attempts} attempts)"
        )

    def halt(self, stop: RunMustStop) -> RunMustStop:
        """Stop the run: this call and every later one raise ``stop``."""
        if self._stopped is None:
            self._stopped = stop
        return self._stopped

    def _preflight_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock[0] is not loop:
            self._lock = (loop, asyncio.Lock())
        return self._lock[1]

    async def _ensure_preflight(self) -> None:
        if self.preflight is not None:
            return
        async with self._preflight_lock():
            if self._stopped is not None:
                raise self._stopped
            if self.preflight is None:
                try:
                    report = await preflight(self)
                except RunMustStop:
                    raise
                except Exception as exc:
                    # A run whose probe fails would fail every call after it, and
                    # each would retry the probe: it stops once, with the reason.
                    raise self.halt(PreflightFailed(f"the probe call failed: {exc}")) from exc
                if self._on_preflight is not None:
                    self._on_preflight(report.line())

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        timeout_s: float | None = None,
    ) -> LLMResult:
        if self._stopped is not None:
            raise self._stopped
        await self._ensure_preflight()
        return await self._paid(
            prompt,
            system=system,
            json_schema=json_schema,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    async def _paid(
        self,
        prompt: str,
        *,
        system: str | None,
        json_schema: dict[str, Any] | None,
        max_output_tokens: int | None,
        temperature: float,
        timeout_s: float | None,
    ) -> LLMResult:
        """One call, its retries each reserved and counted."""
        # The cap that is reserved is the cap that is sent.
        cap = max_output_tokens if max_output_tokens is not None else DEFAULT_OUTPUT_TOKENS
        chars = len(prompt) + len(system or "")
        worst = self.inner.worst_case_cost_usd  # type: ignore[attr-defined]
        reservation = float(worst(int(chars * _TOKENS_PER_CHAR_AT_MOST) + 1, cap))
        kwargs: dict[str, Any] = {
            "system": system,
            "json_schema": json_schema,
            "max_output_tokens": cap,
            "temperature": temperature,
        }
        if timeout_s is not None:
            kwargs["timeout_s"] = timeout_s
        for attempt in range(_RETRIES + 1):
            if self._stopped is not None:
                raise self._stopped
            if self.spent_usd + self._reserved_usd + reservation > self.limit_usd:
                raise self.halt(
                    SpendLimitReached(
                        f"the next call could cost up to {reservation:.4f} USD and the run has "
                        f"{self.limit_usd - self.spent_usd - self._reserved_usd:.4f} of its "
                        f"{self.limit_usd:.2f} USD limit left ({self.summary()})"
                    )
                )
            self._reserved_usd += reservation
            self.attempts += 1
            result: LLMResult | None = None
            failure: Exception | None = None
            try:
                result = await self.inner.complete(prompt, **kwargs)
            except Exception as exc:
                failure = exc
            finally:
                # Released on every way out, a cancellation included.
                self._reserved_usd -= reservation
            if result is not None:
                self._settle(_call_cost_usd(result))
                self.calls += 1
                return result
            assert failure is not None
            if is_payment_refusal(failure):
                raise self.halt(
                    AccountCannotPay(f"the provider refused payment: {failure} ({self.summary()})")
                ) from failure
            if not _is_refusal(failure):
                # It may have been answered and billed after the client gave up.
                self._settle(reservation)
            if attempt < _RETRIES and _is_retryable(failure):
                await asyncio.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise failure
        raise AssertionError("unreachable: the last attempt returns or raises")

    def _settle(self, paid_usd: float) -> None:
        self.spent_usd += paid_usd
        tenths = int(10 * self.spent_usd / self.limit_usd)
        if self._on_spend is not None and tenths > self._tenths_reported:
            self._tenths_reported = tenths
            self._on_spend(self)

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
    available or holds less than the run's limit — or holds money only in
    currencies a USD limit cannot be compared with — and lets the probe's own
    error through when the probe fails otherwise (a wrong key, an unknown
    model). The probe asks for one output token and counts against the limit.
    :class:`SpendLimitedLLM` runs this itself before its first paid attempt.
    """
    balance_usd: float | None = None
    query = getattr(llm.inner, "balance", None)
    if callable(query):
        balance = await query()
        balance_usd = balance.usd
        if not balance.available:
            raise llm.halt(AccountCannotPay(f"the provider says the account cannot pay: {balance}"))
        if balance.usd is None and balance.by_currency:
            raise llm.halt(
                AccountCannotPay(
                    f"the account holds {balance.by_currency} and no USD; the run's limit is "
                    f"{llm.limit_usd:.2f} USD and cannot be compared with it"
                )
            )
        if balance.usd is not None and balance.usd < llm.limit_usd:
            raise llm.halt(
                AccountCannotPay(
                    f"the account holds {balance.usd:.2f} USD, less than the run's limit of "
                    f"{llm.limit_usd:.2f}; top it up, or lower the limit to what the run needs"
                )
            )
    probe = await llm._paid(
        "Reply with the word OK.",
        system=None,
        json_schema=None,
        max_output_tokens=1,
        temperature=0.0,
        timeout_s=None,
    )
    report = PreflightReport(
        model_id=llm.model_id,
        served_model_id=probe.served_model_id,
        limit_usd=llm.limit_usd,
        balance_usd=balance_usd,
        probe_cost_usd=_call_cost_usd(probe),
    )
    llm.preflight = report
    return report


def run_paid[T](llm: SpendLimitedLLM, work: Callable[[], Awaitable[T]]) -> T:
    """For a script: ``work`` in one event loop, and a stop ends the process
    with its reason instead of a traceback. The spend is printed at the end."""
    try:
        result = asyncio.run(_awaited(work))
    except RunMustStop as stop:
        sys.exit(f"STOPPED: {stop}")
    print(f"spend: {llm.summary()}", flush=True)
    return result


async def _awaited[T](work: Callable[[], Awaitable[T]]) -> T:
    return await work()


def print_spend(llm: SpendLimitedLLM) -> None:
    """The running count a run prints as its spending crosses each tenth of the limit."""
    print(f"spend: {llm.summary()}", flush=True)


__all__ = [
    "DEFAULT_OUTPUT_TOKENS",
    "AccountBalance",
    "AccountCannotPay",
    "PreflightFailed",
    "PreflightReport",
    "RunMustStop",
    "SpendLimitReached",
    "SpendLimitedLLM",
    "is_payment_refusal",
    "preflight",
    "print_spend",
    "run_paid",
]
