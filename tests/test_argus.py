"""ArgusAgent acquisition loop (W7-B, PHX-0037 slice 2)."""

from __future__ import annotations

from theogony.acquisition.base import RawContent, SourceCandidate
from theogony.agents.argus import ArgusAgent, ArgusOutcome, ArgusSettings
from theogony.agents.argus_ingest_runner import IngestRunner
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.curiosity.verification_pool import PoolEntry
from theogony.reporting.models import RegionDescriptor


def _region() -> RegionDescriptor:
    return RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1)


def _trigger(search_query: str = "Sven Hedin Tibet") -> CuriosityTrigger:
    return CuriosityTrigger(
        origin_query="Who was Hedin?",
        origin_query_run_id="run1",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=_region(),
        stub_signal_strength=0.8,
        proposed_acquisition_spec=AcquisitionSpec(search_query=search_query),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=0,
    )


class _StubAdapter:
    def __init__(
        self,
        *,
        candidates: list[SourceCandidate] | None = None,
        raw: RawContent | None = None,
    ) -> None:
        self._candidates = candidates or []
        self._raw = raw
        self.search_calls = 0
        self.acquire_calls = 0

    @property
    def source_type(self) -> str:
        return "gutenberg"

    def supports(self, source_type: str) -> bool:
        return source_type == "gutenberg"

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        self.search_calls += 1
        return list(self._candidates[:limit])

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        self.acquire_calls += 1
        assert self._raw is not None
        return self._raw

    async def aclose(self) -> None:
        return None


class _StubIngestRunner:
    def __init__(self) -> None:
        self.raws: list[RawContent] = []

    async def run_from_raw_content(self, raw: RawContent) -> str:
        self.raws.append(raw)
        return "01ARZ3NDEKTSV4RRFFQ69G5FAV"


class _StubVerificationPool:
    def __init__(self) -> None:
        self.entries: list[PoolEntry] = []

    def register(
        self,
        candidate_label: str,
        ingest_run_id: str | None = None,
        *,
        source_type: str | None = None,
        source_identifier: str | None = None,
        target_node_ids: list[str] | None = None,
    ) -> PoolEntry:
        entry = PoolEntry(
            candidate_label=candidate_label,
            ingest_run_id=ingest_run_id,
            source_type=source_type,
            source_identifier=source_identifier,
            target_node_ids=list(target_node_ids or ()),
        )
        self.entries.append(entry)
        return entry


def _good_candidate() -> SourceCandidate:
    return SourceCandidate(
        source_type="gutenberg",
        identifier="43497",
        title="Trans-Himalaya exploration",
        authors=["Hedin, Sven"],
        languages=["en"],
        download_url="https://example.org/pg43497.txt",
        metadata={"copyright": False, "download_count": 100},
    )


def _raw_small() -> RawContent:
    text = "Sven Hedin explored Tibet in the early twentieth century.\n" * 20
    return RawContent(
        source_type="gutenberg",
        identifier="43497",
        title="Test",
        language="en",
        content=text,
        content_format="text/plain; charset=utf-8",
        bytes_acquired=len(text.encode("utf-8")),
        metadata={"copyright": False},
    )


def _agent(
    adapter: _StubAdapter,
    runner: IngestRunner | None = None,
    *,
    min_score: float = 0.0,
) -> ArgusAgent:
    return ArgusAgent(
        adapter=adapter,
        ingest_runner=runner or _StubIngestRunner(),
        verification_pool=_StubVerificationPool(),  # type: ignore[arg-type]
        settings=ArgusSettings(enabled=True, min_candidate_score=min_score, search_limit=5),
    )


class TestArgusOutcomes:
    async def test_argus_unsupported_source_type_outcome(self) -> None:
        bad_spec = AcquisitionSpec.model_construct(
            source_type="arxiv",  # type: ignore[arg-type]
            search_query="anything",
        )
        trig = CuriosityTrigger.model_construct(
            origin_query="q",
            origin_query_run_id="r",
            gap_class=GapClass.REGION_THIN,
            region_descriptor=_region(),
            stub_signal_strength=0.5,
            proposed_acquisition_spec=bad_spec,
            budget=TriggerBudget(),
        )
        adapter = _StubAdapter(candidates=[_good_candidate()], raw=_raw_small())
        r = await _agent(adapter).process(trig)
        assert r.outcome == ArgusOutcome.UNSUPPORTED_SOURCE_TYPE
        assert adapter.acquire_calls == 0

    async def test_argus_no_candidates_outcome(self) -> None:
        adapter = _StubAdapter(candidates=[], raw=_raw_small())
        r = await _agent(adapter).process(_trigger())
        assert r.outcome == ArgusOutcome.NO_CANDIDATES
        assert adapter.acquire_calls == 0

    async def test_argus_score_threshold_gate(self) -> None:
        weak = SourceCandidate(
            source_type="gutenberg",
            identifier="9",
            title="ZZZZ unrelated zzz",
            authors=["Nobody"],
            languages=["de"],
            download_url="https://example.org/x.txt",
            metadata={"copyright": False},
        )
        adapter = _StubAdapter(candidates=[weak], raw=_raw_small())
        r = await _agent(adapter, min_score=1.0).process(_trigger())
        assert r.outcome == ArgusOutcome.NO_CANDIDATE_ABOVE_THRESHOLD
        assert adapter.acquire_calls == 0

    async def test_argus_no_longer_content_gates_before_acquire(self) -> None:
        bad = _good_candidate().model_copy(
            update={"title": "A minor study of geography"},
        )
        adapter = _StubAdapter(candidates=[bad], raw=_raw_small())
        r = await _agent(adapter).process(_trigger())
        assert r.outcome == ArgusOutcome.APPROVED_AND_INGESTED
        assert adapter.acquire_calls == 1

    async def test_argus_budget_exceeded_does_not_acquire(self) -> None:
        huge_meta = SourceCandidate(
            source_type="gutenberg",
            identifier="1",
            title="Trans-Himalaya exploration",
            authors=["Hedin, Sven"],
            languages=["en"],
            download_url="https://example.org/x.txt",
            metadata={"copyright": False, "estimated_bytes": 10_000_000},
        )
        adapter = _StubAdapter(candidates=[huge_meta], raw=_raw_small())
        r = await _agent(adapter).process(_trigger())
        assert r.outcome == ArgusOutcome.BUDGET_EXCEEDED
        assert adapter.acquire_calls == 0

    async def test_argus_happy_path_calls_ingest_runner_once(self) -> None:
        adapter = _StubAdapter(candidates=[_good_candidate()], raw=_raw_small())
        runner = _StubIngestRunner()
        r = await _agent(adapter, runner).process(_trigger())
        assert r.outcome == ArgusOutcome.APPROVED_AND_INGESTED
        assert adapter.acquire_calls == 1
        assert len(runner.raws) == 1
        assert r.decision.ingest_run_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert r.decision.status == "processed"
        assert r.decision.pool_entry_id is not None
        assert r.bytes_acquired > 0

    async def test_argus_dry_run_skips_acquire(self) -> None:
        adapter = _StubAdapter(candidates=[_good_candidate()], raw=_raw_small())
        runner = _StubIngestRunner()
        r = await _agent(adapter, runner).process(_trigger(), dry_run=True)
        assert r.outcome == ArgusOutcome.DRY_RUN
        assert adapter.acquire_calls == 0
        assert runner.raws == []


class TestScoreCandidate:
    def test_score_increases_with_title_overlap(self) -> None:
        from theogony.agents.argus import score_candidate

        trig = _trigger()
        low = SourceCandidate(
            source_type="gutenberg",
            identifier="1",
            title="Cookbook",
            authors=["Chef"],
            languages=["en"],
            download_url="http://x",
            metadata={"copyright": False},
        )
        high = _good_candidate()
        assert score_candidate(high, trig) > score_candidate(low, trig)
