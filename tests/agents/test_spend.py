"""PHX-1124: a run that calls a paid model spends at most its limit, and asks first."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from theogony.agents import llm_deepseek, spend
from theogony.agents.llm import LLMResult
from theogony.agents.spend import (
    AccountBalance,
    AccountCannotPay,
    PreflightFailed,
    PreflightReport,
    RunMustStop,
    SpendLimitedLLM,
    SpendLimitReached,
    preflight,
    run_paid,
)

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend, "_RETRY_BACKOFF_S", 0.0)


class _Paid:
    """A provider whose every call costs ``cost`` and whose worst case is ``worst``."""

    def __init__(
        self,
        cost: float = 0.1,
        *,
        worst: float = 0.1,
        balance: AccountBalance | None = None,
        served: str = "",
        errors: list[Exception] | None = None,
    ) -> None:
        self.cost, self.worst, self.served = cost, worst, served
        self.calls: list[dict[str, Any]] = []
        self.loops: list[int] = []
        self.balance_reads = 0
        self._balance = balance
        self._errors = list(errors or [])

    def worst_case_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return self.worst

    async def balance(self) -> AccountBalance:
        self.balance_reads += 1
        return self._balance or AccountBalance(available=True, usd=100.0)

    @property
    def model_id(self) -> str:
        return "paid-model"

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResult:
        self.calls.append({"prompt": prompt, **kwargs})
        self.loops.append(id(asyncio.get_running_loop()))
        await asyncio.sleep(0)
        if self._errors:
            raise self._errors.pop(0)
        return LLMResult(
            text="OK", cost_usd=self.cost, model_id=self.model_id, served_model_id=self.served
        )

    async def complete_with_web_search_for_research_plan(self, **_: Any) -> Any:
        raise NotImplementedError


def _status_error(status: int, message: str = "") -> Exception:
    error = RuntimeError(f"Error code: {status} - {message}")
    error.status_code = status  # type: ignore[attr-defined]
    return error


def _limited(inner: _Paid, limit: float) -> SpendLimitedLLM:
    """A limiter whose preflight is done, for the tests of the limit itself."""
    llm = SpendLimitedLLM(inner, limit_usd=limit, on_preflight=None)
    llm.preflight = PreflightReport(model_id="paid-model", limit_usd=limit)
    return llm


# --------------------------------------------------------------------------
# The limit
# --------------------------------------------------------------------------


def test_a_call_that_could_cross_the_limit_is_refused_before_it_is_made() -> None:
    inner = _Paid(cost=0.4, worst=0.4)
    llm = _limited(inner, 1.0)
    asyncio.run(llm.complete("a"))
    asyncio.run(llm.complete("b"))
    with pytest.raises(SpendLimitReached):
        asyncio.run(llm.complete("c"))
    assert len(inner.calls) == 2 and llm.spent_usd == pytest.approx(0.8)
    # and the run stays stopped: no later call reaches the provider
    with pytest.raises(SpendLimitReached):
        asyncio.run(llm.complete("d"))
    assert len(inner.calls) == 2


def test_concurrent_calls_never_reserve_past_the_limit() -> None:
    inner = _Paid(cost=0.3, worst=0.3)
    llm = _limited(inner, 1.0)

    async def many() -> list[Any]:
        return await asyncio.gather(
            *(llm.complete(str(i)) for i in range(10)), return_exceptions=True
        )

    outcomes = asyncio.run(many())
    assert len(inner.calls) == 3
    assert llm.spent_usd <= llm.limit_usd
    assert sum(isinstance(o, SpendLimitReached) for o in outcomes) == 7


def test_the_cap_that_is_reserved_is_the_cap_that_is_sent() -> None:
    inner = _Paid()
    llm = _limited(inner, 1.0)
    asyncio.run(llm.complete("a"))
    asyncio.run(llm.complete("b", max_output_tokens=48, timeout_s=60))
    assert inner.calls[0]["max_output_tokens"] == spend.DEFAULT_OUTPUT_TOKENS
    assert "timeout_s" not in inner.calls[0], "the provider keeps its own default"
    assert inner.calls[1]["max_output_tokens"] == 48 and inner.calls[1]["timeout_s"] == 60


def test_the_first_refusal_to_pay_stops_the_run() -> None:
    inner = _Paid(errors=[_status_error(402, "Insufficient Balance")])
    llm = _limited(inner, 1.0)
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("a"))
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("b"))
    assert len(inner.calls) == 1, "the second call never reached the provider"


@pytest.mark.parametrize(
    "error",
    [
        _status_error(400, "Your credit balance is too low to access the Anthropic API"),
        _status_error(429, "You exceeded your current quota (insufficient_quota)"),
    ],
)
def test_other_providers_words_for_no_money_stop_the_run(error: Exception) -> None:
    llm = _limited(_Paid(errors=[error]), 1.0)
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("a"))


def test_an_attempt_that_may_have_been_billed_is_charged_and_retried() -> None:
    inner = _Paid(cost=0.1, worst=0.2, errors=[TimeoutError("slow"), TimeoutError("slow")])
    llm = _limited(inner, 5.0)
    result = asyncio.run(llm.complete("a"))
    assert result.text == "OK" and len(inner.calls) == 3
    assert llm.spent_usd == pytest.approx(0.2 + 0.2 + 0.1)
    assert llm.calls == 1 and llm.attempts == 3


def test_a_refusal_is_retried_but_not_charged() -> None:
    inner = _Paid(cost=0.1, worst=0.2, errors=[_status_error(429, "slow down")])
    llm = _limited(inner, 5.0)
    asyncio.run(llm.complete("a"))
    assert llm.spent_usd == pytest.approx(0.1) and len(inner.calls) == 2


def test_an_error_that_is_not_retried_passes_through() -> None:
    inner = _Paid(errors=[_status_error(400, "bad request")])
    llm = _limited(inner, 5.0)
    with pytest.raises(RuntimeError, match="bad request"):
        asyncio.run(llm.complete("a"))
    assert llm.stopped is None and llm.spent_usd == 0.0 and len(inner.calls) == 1


def test_a_provider_that_cannot_price_a_call_cannot_be_limited() -> None:
    class Unpriced:
        model_id = "unpriced"

    with pytest.raises(ValueError, match="cannot price"):
        SpendLimitedLLM(Unpriced(), limit_usd=1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        SpendLimitedLLM(_Paid(), limit_usd=float("nan"))


def test_the_running_count_reports_each_tenth_of_the_limit_once() -> None:
    seen: list[float] = []
    llm = SpendLimitedLLM(
        _Paid(cost=0.25, worst=0.25),
        limit_usd=1.0,
        on_spend=lambda w: seen.append(w.spent_usd),
        on_preflight=None,
    )
    llm.preflight = PreflightReport(model_id="paid-model", limit_usd=1.0)
    for _ in range(4):
        asyncio.run(llm.complete("a"))
    assert seen == pytest.approx([0.25, 0.5, 0.75, 1.0])


# --------------------------------------------------------------------------
# The preflight
# --------------------------------------------------------------------------


def test_the_first_paid_call_runs_the_preflight_once_and_only_then() -> None:
    inner = _Paid(cost=0.001, worst=0.01, served="flash")
    lines: list[str] = []
    llm = SpendLimitedLLM(inner, limit_usd=5.0, on_preflight=lines.append)

    async def three() -> None:
        await asyncio.gather(llm.complete("a"), llm.complete("b"), llm.complete("c"))

    asyncio.run(three())
    assert inner.balance_reads == 1
    assert [c["max_output_tokens"] for c in inner.calls].count(1) == 1, "one probe"
    assert len(inner.calls) == 4 and llm.preflight is not None
    assert lines and "served by flash" in lines[0] and "100.00 USD" in lines[0]


def test_a_run_with_nothing_to_pay_for_asks_nothing() -> None:
    inner = _Paid(balance=AccountBalance(available=False))

    async def nothing() -> str:
        return "from cache"

    assert run_paid(SpendLimitedLLM(inner, limit_usd=5.0), nothing) == "from cache"
    assert inner.balance_reads == 0 and inner.calls == []


def test_preflight_refuses_an_account_that_holds_less_than_the_limit() -> None:
    inner = _Paid(balance=AccountBalance(available=True, usd=3.0))
    llm = SpendLimitedLLM(inner, limit_usd=5.0, on_preflight=None)
    with pytest.raises(AccountCannotPay, match="3.00 USD, less than the run's limit of 5.00"):
        asyncio.run(llm.complete("a"))
    assert inner.calls == [], "no probe once the balance has refused"
    with pytest.raises(AccountCannotPay):
        asyncio.run(llm.complete("b"))


@pytest.mark.parametrize(
    "balance",
    [
        AccountBalance(available=False, usd=12.0),
        AccountBalance(available=True, usd=None, by_currency={"CNY": 50.0}),
    ],
)
def test_preflight_refuses_what_it_cannot_count_on(balance: AccountBalance) -> None:
    with pytest.raises(AccountCannotPay):
        asyncio.run(preflight(SpendLimitedLLM(_Paid(balance=balance), limit_usd=5.0)))


def test_a_failing_probe_stops_the_run_once() -> None:
    inner = _Paid(errors=[_status_error(401, "Authentication Fails")])
    llm = SpendLimitedLLM(inner, limit_usd=1.0, on_preflight=None)
    with pytest.raises(PreflightFailed):
        asyncio.run(llm.complete("a"))
    with pytest.raises(PreflightFailed):
        asyncio.run(llm.complete("b"))
    assert len(inner.calls) == 1


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


# --------------------------------------------------------------------------
# Where a stop must not turn into a result
# --------------------------------------------------------------------------


def _stopping() -> SpendLimitedLLM:
    return _limited(_Paid(errors=[_status_error(402, "Insufficient Balance")]), 1.0)


def _script(name: str) -> ModuleType:
    path = _ROOT / "scripts" / f"{name}.py"
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


def test_a_stop_is_not_a_failed_answer_in_either_answer_harness() -> None:
    """The harnesses retry a provider error and score it as an empty answer;
    a stop must end the run instead (it is re-raised, not retried)."""
    from theogony.mesh.eval import qa_answers, qa_mesh

    llm = _stopping()
    semaphore = asyncio.Semaphore(1)
    with pytest.raises(RunMustStop):
        asyncio.run(qa_answers._ask(llm, "system", "prompt", semaphore))
    with pytest.raises(RunMustStop):
        asyncio.run(qa_mesh._ask(llm, "system", "prompt", semaphore, 8))


def test_a_stop_ends_a_read_instead_of_failing_one_paragraph(tmp_path: Path) -> None:
    from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
    from theogony.mesh.runtime.oneiros_tick import MeshRuntime

    runtime = MeshRuntime(tmp_path / "mesh_ws", semantic_dim=8, frame_dim=4)
    reader = MeshParagraphReader(runtime, llm=_stopping())
    with pytest.raises(AccountCannotPay):
        asyncio.run(reader._read_paragraph("Sven Hedin crossed the Tibetan Plateau."))


def test_a_stop_leaves_nothing_in_the_readings_cache(tmp_path: Path) -> None:
    from theogony.mesh.eval.qa_retrieval import QAPassage

    kadmos = _script("mesh_qa_kadmos")
    cache = tmp_path / "readings.jsonl"
    passages = [QAPassage(idx=0, title="Hedin", text="Sven Hedin crossed the Tibetan Plateau.")]
    with pytest.raises(AccountCannotPay):
        asyncio.run(
            kadmos.extract_readings(
                passages, _stopping(), cache_path=cache, concurrency=1, timeout_s=5
            )
        )
    assert not cache.exists() or cache.read_text() == "", "a stop is no empty reading"


def test_a_stop_is_not_a_missed_recording() -> None:
    record = _script("record_demo_readings")
    with pytest.raises(AccountCannotPay):
        asyncio.run(record.read_one(_stopping(), "Sven Hedin crossed the Tibetan Plateau."))


def test_a_stopped_judge_writes_no_judgment_and_ends_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from theogony.agents import factory

    audit = _script("mesh_mention_audit")
    node = {"name": "Paris", "description": "Paris — capital of France", "signal": "tag"}
    item = {
        "id": "p1:0:Paris",
        "group": "moved",
        "title": "Paris",
        "text": "Paris is the capital of France.",
        "mention": {"label": "Paris", "description": "a city"},
        "a": node,
        "b": node,
    }
    items, out = tmp_path / "items.jsonl", tmp_path / "judgments.jsonl"
    items.write_text(json.dumps(item) + "\n")
    monkeypatch.setattr(factory, "build_named_llm", lambda *_a, **_k: _stopping())
    # One at a time: with two in flight, the second may be answered before the
    # first one's refusal arrives, and an answered judgment is written.
    args = SimpleNamespace(items=items, out=out, concurrency=1, spend_limit_usd=None)
    with pytest.raises(SystemExit, match="STOPPED"):
        audit.judge(args)
    assert not out.exists() or out.read_text() == "", "a stop is no 'error' row"


def test_the_corpus_answers_make_every_call_in_one_event_loop(tmp_path: Path) -> None:
    """Each call in its own asyncio.run once sent every answer twice: the
    provider's client carried its connection into the next loop."""
    from theogony.mesh.eval import corpus_answers
    from theogony.mesh.eval.corpus_qa import GoldQuestion
    from theogony.mesh.runtime.oneiros_tick import MeshRuntime

    inner = _Paid(cost=0.001, worst=0.01)
    llm = SpendLimitedLLM(inner, limit_usd=5.0, on_preflight=None)
    gold = [
        GoldQuestion(id=f"q{i}", question=f"Who is {i}?", expect=["x"], evidence="")
        for i in range(3)
    ]
    runtime = MeshRuntime(tmp_path / "mesh_ws", semantic_dim=8, frame_dim=4)
    with asyncio.Runner() as runner:
        corpus_answers.answer_gold_set(
            runtime,
            lambda _text: [0.0] * 8,
            llm,
            arms=("closed_book",),
            gold=gold,
            call_in_loop=runner.run,
        )
    assert len(inner.calls) == 4  # the probe and three answers
    assert len(set(inner.loops)) == 1


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


def _response(model: str, *, prompt: int, hit: int | None = None, out: int = 10) -> Any:
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=out)
    if hit is not None:
        usage.prompt_cache_hit_tokens = hit
        usage.prompt_cache_miss_tokens = prompt - hit
    return SimpleNamespace(
        model=model, usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="x"))]
    )


def _provider(
    monkeypatch: pytest.MonkeyPatch, response: Any, *, model_id: str = "deepseek-chat"
) -> llm_deepseek.DeepSeekLLMProvider:
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id=model_id)

    async def create(**_: Any) -> Any:
        return response

    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    monkeypatch.setattr(llm_deepseek, "is_peak", lambda _at: True)
    return provider


def test_the_provider_prices_the_model_that_served_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # requested as deepseek-chat (the Flash row), served by deepseek-v4-pro
    provider = _provider(monkeypatch, _response("deepseek-v4-pro", prompt=1_000, hit=600))
    result = asyncio.run(provider.complete("Q?", max_output_tokens=8))
    expected = (600 * 0.044 + 400 * 1.32 + 10 * 3.96) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)
    assert result.cost_eur == pytest.approx(expected * 0.93)
    assert result.model_id == "deepseek-chat" and result.served_model_id == "deepseek-v4-pro"


def test_a_served_name_the_table_does_not_know_is_priced_at_the_dearest_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(monkeypatch, _response("deepseek-v5", prompt=1_000, hit=0))
    result = asyncio.run(provider.complete("Q?"))
    assert result.cost_usd == pytest.approx((1_000 * 1.32 + 10 * 3.96) / 1_000_000)


def test_without_a_cache_split_every_input_token_is_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, _response("deepseek-flash", prompt=1_000, out=0))
    result = asyncio.run(provider.complete("Q?"))
    assert result.cost_usd == pytest.approx(1_000 * 0.30 / 1_000_000)


def test_the_worst_case_is_every_token_a_peak_miss() -> None:
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")
    assert provider.worst_case_cost_usd(1_000_000, 1_000_000) == pytest.approx(0.30 + 1.20)


def test_behind_the_limit_the_sdk_makes_no_retries_of_its_own() -> None:
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")
    assert provider._client.max_retries > 0
    assert provider.without_sdk_retries()._client.max_retries == 0


def test_the_balance_is_read_from_the_accounts_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        body = {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "USD",
                    "total_balance": "19.97",
                    "granted_balance": "0.00",
                    "topped_up_balance": "19.97",
                }
            ],
        }
        return httpx.Response(200, content=json.dumps(body).encode())

    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    provider = llm_deepseek.DeepSeekLLMProvider(api_key="sk-test", model_id="deepseek-chat")
    balance = asyncio.run(provider.balance())
    assert seen == {"url": "https://api.deepseek.com/user/balance", "auth": "Bearer sk-test"}
    assert balance.available and balance.usd == pytest.approx(19.97)
