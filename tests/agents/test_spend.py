"""PHX-1124: a run that calls a paid model spends at most its limit, and asks first."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from theogony.agents import llm_deepseek
from theogony.agents.llm import LLMResult
from theogony.agents.spend import (
    AccountBalance,
    AccountCannotPay,
    RunMustStop,
    SpendLimitedLLM,
    SpendLimitReached,
    preflight,
    run_paid,
)


class _Paid:
    """A provider whose every call costs ``cost`` and whose worst case is ``worst``."""

    def __init__(
        self,
        cost: float = 0.1,
        *,
        worst: float | None = None,
        balance: AccountBalance | None = None,
        served: str = "",
    ) -> None:
        self.cost, self.calls, self.served = cost, 0, served
        self._balance = balance
        if worst is not None:
            self.worst_case_cost_usd = lambda _in, _out: worst
        if balance is not None:
            self.balance = self._read_balance

    async def _read_balance(self) -> AccountBalance:
        assert self._balance is not None
        return self._balance

    @property
    def model_id(self) -> str:
        return "paid-model"

    async def complete(self, prompt: str, **_: Any) -> LLMResult:
        self.calls += 1
        await asyncio.sleep(0)
        return LLMResult(
            text="OK", cost_usd=self.cost, model_id=self.model_id, served_model_id=self.served
        )

    async def complete_with_web_search_for_research_plan(self, **_: Any) -> Any:
        raise NotImplementedError


class _Refusing(_Paid):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def complete(self, prompt: str, **_: Any) -> LLMResult:
        self.calls += 1
        raise self.error


def _payment_required() -> Exception:
    error = RuntimeError("Error code: 402 - {'error': {'message': 'Insufficient Balance'}}")
    error.status_code = 402  # type: ignore[attr-defined]
    return error


def test_a_call_that_could_cross_the_limit_is_refused_before_it_is_made() -> None:
    inner = _Paid(cost=0.4, worst=0.4)
    llm = SpendLimitedLLM(inner, limit_usd=1.0)
    asyncio.run(llm.complete("a"))
    asyncio.run(llm.complete("b"))
    with pytest.raises(SpendLimitReached):
        asyncio.run(llm.complete("c"))
    assert inner.calls == 2 and llm.spent_usd == pytest.approx(0.8)
    # and the run stays stopped: no later call reaches the provider
    with pytest.raises(SpendLimitReached):
        asyncio.run(llm.complete("d"))
    assert inner.calls == 2


def test_concurrent_calls_never_reserve_past_the_limit() -> None:
    inner = _Paid(cost=0.3, worst=0.3)
    llm = SpendLimitedLLM(inner, limit_usd=1.0)

    async def many() -> list[Any]:
        return await asyncio.gather(
            *(llm.complete(str(i)) for i in range(10)), return_exceptions=True
        )

    outcomes = asyncio.run(many())
    assert inner.calls == 3
    assert llm.spent_usd <= llm.limit_usd
    assert sum(isinstance(o, SpendLimitReached) for o in outcomes) == 7


def test_the_first_refusal_to_pay_stops_the_run() -> None:
    inner = _Refusing(_payment_required())
    llm = SpendLimitedLLM(inner, limit_usd=1.0)
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("a"))
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("b"))
    assert inner.calls == 1, "the second call never reached the provider"


def test_another_provider_error_passes_through_and_frees_its_reservation() -> None:
    inner = _Refusing(TimeoutError("slow"))
    llm = SpendLimitedLLM(inner, limit_usd=1.0)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            asyncio.run(llm.complete("a"))
    assert llm.stopped is None and llm.spent_usd == 0.0


def test_an_unpriced_provider_reserves_twice_its_dearest_call_so_far() -> None:
    inner = _Paid(cost=0.3)  # no worst_case_cost_usd
    llm = SpendLimitedLLM(inner, limit_usd=1.0)
    asyncio.run(llm.complete("a"))  # reserved 0.01, paid 0.3
    asyncio.run(llm.complete("b"))  # reserved 0.6: 0.3 + 0.6 <= 1.0
    with pytest.raises(SpendLimitReached):  # 0.6 + 0.6 > 1.0
        asyncio.run(llm.complete("c"))
    assert inner.calls == 2


def test_the_running_count_reports_each_tenth_of_the_limit_once() -> None:
    seen: list[float] = []
    llm = SpendLimitedLLM(
        _Paid(cost=0.25, worst=0.25), limit_usd=1.0, on_spend=lambda w: seen.append(w.spent_usd)
    )
    for _ in range(4):
        asyncio.run(llm.complete("a"))
    assert seen == pytest.approx([0.25, 0.5, 0.75, 1.0])


def test_preflight_refuses_an_account_that_holds_less_than_the_limit() -> None:
    inner = _Paid(balance=AccountBalance(available=True, usd=3.0))
    llm = SpendLimitedLLM(inner, limit_usd=5.0)
    with pytest.raises(AccountCannotPay, match="3.00 USD, less than the run's limit of 5.00"):
        asyncio.run(preflight(llm))
    assert inner.calls == 0, "no probe once the balance has refused"
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("a"))


def test_preflight_refuses_an_account_the_provider_says_cannot_pay() -> None:
    inner = _Paid(balance=AccountBalance(available=False, usd=12.0))
    with pytest.raises(AccountCannotPay):
        asyncio.run(preflight(SpendLimitedLLM(inner, limit_usd=5.0)))


def test_preflight_probes_once_and_records_who_answered() -> None:
    inner = _Paid(cost=0.0001, balance=AccountBalance(available=True, usd=19.97), served="flash")
    llm = SpendLimitedLLM(inner, limit_usd=5.0)
    report = asyncio.run(preflight(llm))
    assert inner.calls == 1
    assert report.balance_usd == 19.97 and report.served_model_id == "flash"
    assert llm.preflight is report and llm.spent_usd == pytest.approx(0.0001)
    assert "served by flash" in report.line()


def test_a_failing_probe_stops_before_the_run() -> None:
    llm = SpendLimitedLLM(_Refusing(_payment_required()), limit_usd=1.0)
    with pytest.raises(AccountCannotPay):
        asyncio.run(preflight(llm))


def test_a_script_ends_with_the_reason_instead_of_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    llm = SpendLimitedLLM(_Paid(cost=0.4, worst=0.4), limit_usd=1.0)

    async def work() -> None:
        for _ in range(5):
            await llm.complete("a")

    with pytest.raises(SystemExit) as exit_:
        run_paid(llm, work)
    assert str(exit_.value).startswith("STOPPED: the next call could cost up to")
    assert "preflight:" in capsys.readouterr().out


def test_a_stop_is_not_a_failed_answer_in_either_answer_harness() -> None:
    """The harnesses retry a provider error and score it as an empty answer;
    a stop must end the run instead (it is re-raised, not retried)."""
    from theogony.mesh.eval import qa_answers, qa_mesh

    llm = SpendLimitedLLM(_Refusing(_payment_required()), limit_usd=1.0)
    semaphore = asyncio.Semaphore(1)
    with pytest.raises(RunMustStop):
        asyncio.run(qa_answers._ask(llm, "system", "prompt", semaphore))
    with pytest.raises(RunMustStop):
        asyncio.run(qa_mesh._ask(llm, "system", "prompt", semaphore, 8))
    assert llm.inner.calls == 1  # type: ignore[attr-defined]


def test_a_stop_ends_a_read_instead_of_failing_one_paragraph(tmp_path: Any) -> None:
    from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
    from theogony.mesh.runtime.oneiros_tick import MeshRuntime

    runtime = MeshRuntime(tmp_path / "mesh_ws", semantic_dim=8, frame_dim=4)
    llm = SpendLimitedLLM(_Refusing(_payment_required()), limit_usd=1.0)
    reader = MeshParagraphReader(runtime, llm=llm)
    with pytest.raises(AccountCannotPay):
        asyncio.run(reader._read_paragraph("Sven Hedin crossed the Tibetan Plateau."))


# --------------------------------------------------------------------------
# DeepSeek's prices, as billed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "peak"),
    [
        (datetime(2026, 11, 9, 0, 59, tzinfo=UTC), False),  # Monday
        (datetime(2026, 11, 9, 1, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 9, 3, 59, tzinfo=UTC), True),
        (datetime(2026, 11, 9, 4, 0, tzinfo=UTC), False),
        (datetime(2026, 11, 9, 6, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 13, 9, 59, tzinfo=UTC), True),  # Friday
        (datetime(2026, 11, 13, 10, 0, tzinfo=UTC), False),
        (datetime(2026, 11, 14, 2, 0, tzinfo=UTC), False),  # Saturday
        (datetime(2026, 11, 15, 7, 0, tzinfo=UTC), False),  # Sunday
    ],
)
def test_peak_hours_are_deepseeks(at: datetime, peak: bool) -> None:
    assert llm_deepseek.is_peak(at) is peak


def test_a_call_is_priced_by_cache_split_and_time_of_day() -> None:
    tuesday_peak = datetime(2026, 11, 10, 7, 0, tzinfo=UTC)
    tuesday_off = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    kwargs = {"cache_hit_tokens": 1_000_000, "cache_miss_tokens": 1_000_000, "output_tokens": 0}
    assert llm_deepseek.cost_usd("deepseek-flash", at=tuesday_peak, **kwargs) == pytest.approx(
        0.306
    )
    assert llm_deepseek.cost_usd("deepseek-flash", at=tuesday_off, **kwargs) == pytest.approx(0.153)
    output = {"cache_hit_tokens": 0, "cache_miss_tokens": 0, "output_tokens": 1_000_000}
    assert llm_deepseek.cost_usd("deepseek-v4-pro", at=tuesday_peak, **output) == pytest.approx(
        3.96
    )


def test_an_alias_is_priced_as_its_model_and_an_unknown_name_as_the_dearest() -> None:
    assert llm_deepseek.price_row("deepseek-chat") == llm_deepseek.PRICES_USD["deepseek-flash"]
    assert llm_deepseek.price_row("deepseek-v4-flash") == llm_deepseek.PRICES_USD["deepseek-flash"]
    assert llm_deepseek.price_row("deepseek-v9") == llm_deepseek.PRICES_USD["deepseek-v4-pro"]


def _provider(monkeypatch: pytest.MonkeyPatch, response: Any) -> llm_deepseek.DeepSeekLLMProvider:
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")

    async def create(**_: Any) -> Any:
        return response

    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    return provider


def test_the_provider_prices_what_the_response_says_and_names_who_served_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usage = SimpleNamespace(
        prompt_tokens=1_000, completion_tokens=10, prompt_cache_hit_tokens=600,
        prompt_cache_miss_tokens=400,
    )  # fmt: skip
    response = SimpleNamespace(
        model="deepseek-flash",
        usage=usage,
        choices=[SimpleNamespace(message=SimpleNamespace(content="Paris"))],
    )
    provider = _provider(monkeypatch, response)
    monkeypatch.setattr(llm_deepseek, "is_peak", lambda _at: True)
    result = asyncio.run(provider.complete("Q?", max_output_tokens=8))
    expected = (600 * 0.006 + 400 * 0.30 + 10 * 1.20) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)
    assert result.cost_eur == pytest.approx(expected * 0.93)
    assert result.model_id == "deepseek-chat" and result.served_model_id == "deepseek-flash"


def test_without_a_cache_split_every_input_token_is_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = SimpleNamespace(prompt_tokens=1_000, completion_tokens=0)
    response = SimpleNamespace(
        model="", usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
    )
    provider = _provider(monkeypatch, response)
    monkeypatch.setattr(llm_deepseek, "is_peak", lambda _at: False)
    result = asyncio.run(provider.complete("Q?"))
    assert result.cost_usd == pytest.approx(1_000 * 0.15 / 1_000_000)


def test_the_worst_case_is_every_token_a_peak_miss() -> None:
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")
    assert provider.worst_case_cost_usd(1_000_000, 1_000_000) == pytest.approx(0.30 + 1.20)


def test_the_balance_is_read_from_the_accounts_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "is_available": True,
                "balance_infos": [
                    {"currency": "USD", "total_balance": "19.97", "granted_balance": "0.00",
                     "topped_up_balance": "19.97"},
                ],
            },
        )  # fmt: skip

    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")
    balance = asyncio.run(provider.balance())
    assert seen == {"url": "https://api.deepseek.com/user/balance", "auth": "Bearer sk-test"}
    assert balance.available and balance.usd == pytest.approx(19.97)
