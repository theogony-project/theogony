"""Tests for theogony.reporting.models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from theogony.reporting.models import (
    CitationQuality,
    EmbeddingSummary,
    IngestRunReport,
    IngestStageReport,
    MultiHopBreakdown,
    NerSummary,
    OneirosTickReport,
    QualityFlags,
    QueryRunReport,
    RelationSummary,
    ResolutionSummary,
    StoreSummary,
    SynthesisBreakdown,
    VitalityShift,
    new_run_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_pair() -> tuple[datetime, datetime]:
    started = datetime.now(UTC)
    return started, started + timedelta(seconds=1)


def _minimal_ingest_report(**overrides: object) -> IngestRunReport:
    started, finished = _now_pair()
    base: dict[str, object] = {
        "started_at": started,
        "finished_at": finished,
        "duration_s": 1.0,
        "status": "completed",
        "verdict": "good",
        "source_type": "gutenberg",
        "source_identifier": "Gutenberg:944",
        "word_count": 110_000,
        "sentence_count": 5_000,
        "stages": [],
        "ner": NerSummary(total_mentions=0),
        "resolution": ResolutionSummary(),
        "relations": RelationSummary(),
        "embedding": EmbeddingSummary(nodes_embedded=0, embedding_model_id="x@v1", duration_s=0.0),
        "store": StoreSummary(nodes_upserted=0, edges_upserted=0),
        "quality_flags": QualityFlags(),
    }
    base.update(overrides)
    return IngestRunReport.model_validate(base)


# ---------------------------------------------------------------------------
# new_run_id
# ---------------------------------------------------------------------------


class TestNewRunId:
    def test_returns_26_char_string(self) -> None:
        rid = new_run_id()
        assert isinstance(rid, str)
        assert len(rid) == 26  # ULID Crockford-base32 length

    def test_each_call_unique(self) -> None:
        ids = {new_run_id() for _ in range(20)}
        assert len(ids) == 20

    def test_lexicographically_sortable(self) -> None:
        """Newer ULIDs sort after older ones — the property the storage layout relies on."""
        first = new_run_id()
        # a microsecond apart guarantees a fresh timestamp prefix
        import time

        time.sleep(0.002)
        second = new_run_id()
        assert second > first


# ---------------------------------------------------------------------------
# RunReportBase header
# ---------------------------------------------------------------------------


class TestHeader:
    def test_run_id_default_factory_used(self) -> None:
        rep = _minimal_ingest_report()
        assert len(rep.run_id) == 26

    def test_run_id_explicit_kept(self) -> None:
        rep = _minimal_ingest_report(run_id="01HXXXXXXXXXXXXXXXXXXXXXXX")
        assert rep.run_id == "01HXXXXXXXXXXXXXXXXXXXXXXX"

    def test_status_enum_enforced(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_ingest_report(status="weird")

    def test_verdict_enum_enforced(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_ingest_report(verdict="ok")

    def test_unknown_field_rejected(self) -> None:
        # Plan §2.11.4: typos in observation accumulators must fail loudly.
        with pytest.raises(ValidationError):
            _minimal_ingest_report(typo_field="oops")


# ---------------------------------------------------------------------------
# IngestRunReport
# ---------------------------------------------------------------------------


class TestIngestRunReport:
    def test_minimal_construction(self) -> None:
        rep = _minimal_ingest_report()
        assert rep.report_type == "ingest"
        assert rep.source_type == "gutenberg"

    def test_round_trip_json(self) -> None:
        rep = _minimal_ingest_report()
        dumped = rep.model_dump_json()
        restored = IngestRunReport.model_validate_json(dumped)
        assert restored.run_id == rep.run_id
        assert restored.source_identifier == rep.source_identifier

    def test_pretty_json_is_jq_friendly(self) -> None:
        """model_dump_json(indent=2) is what RunReportWriter uses."""
        rep = _minimal_ingest_report()
        pretty = rep.model_dump_json(indent=2)
        assert "\n  " in pretty  # indented

    def test_negative_word_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _minimal_ingest_report(word_count=-1)


class TestResolutionSummary:
    def test_low_tier_ratio_zero_when_no_resolutions(self) -> None:
        rs = ResolutionSummary()
        assert rs.low_tier_ratio == 0.0
        assert rs.total_resolved == 0

    def test_low_tier_ratio_basic(self) -> None:
        rs = ResolutionSummary(tier_counts={4: 50, 3: 30, 1: 15, 0: 5})
        # tier <= 1: 15 + 5 = 20 of 100 total → 0.20
        assert rs.low_tier_ratio == pytest.approx(0.20)

    def test_low_tier_ratio_all_low(self) -> None:
        rs = ResolutionSummary(tier_counts={0: 10, 1: 10})
        assert rs.low_tier_ratio == 1.0


class TestStageReport:
    def test_known_stage_names_accepted(self) -> None:
        for name in (
            "acquired",
            "cleaned",
            "sentencized",
            "mentions_extracted",
            "mentions_resolved",
            "relations_extracted",
            "embedded",
            "stored",
        ):
            stage = IngestStageReport(name=name, duration_s=1.0, status="ok")
            assert stage.name == name

    def test_unknown_stage_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IngestStageReport(name="hallucinated", duration_s=1.0, status="ok")


# ---------------------------------------------------------------------------
# QueryRunReport
# ---------------------------------------------------------------------------


class TestQueryRunReport:
    def _minimal(self, **overrides: object) -> QueryRunReport:
        started, finished = _now_pair()
        base: dict[str, object] = {
            "started_at": started,
            "finished_at": finished,
            "duration_s": 0.5,
            "status": "completed",
            "verdict": "good",
            "query": "Welche Ethnien?",
            "query_length_chars": 16,
            "embedding_duration_ms": 30,
            "multi_hop": MultiHopBreakdown(seed_count=10, duration_ms=200),
            "constellation_node_count": 35,
            "constellation_edge_count": 60,
            "suggested_source_count": 8,
            "gaps_identified": 1,
            "synthesis": SynthesisBreakdown(input_tokens=1500, output_tokens=400),
            "citation_quality": CitationQuality(
                cited_node_count=5,
                citations_with_high_confidence_source=4,
                citations_aka_only=1,
            ),
        }
        base.update(overrides)
        return QueryRunReport.model_validate(base)

    def test_round_trip(self) -> None:
        rep = self._minimal()
        restored = QueryRunReport.model_validate_json(rep.model_dump_json())
        assert restored.query == "Welche Ethnien?"
        assert restored.report_type == "query"

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._minimal(typo_field="oops")


# ---------------------------------------------------------------------------
# OneirosTickReport
# ---------------------------------------------------------------------------


class TestOneirosTickReport:
    def _minimal(self, **overrides: object) -> OneirosTickReport:
        started, finished = _now_pair()
        base: dict[str, object] = {
            "started_at": started,
            "finished_at": finished,
            "duration_s": 0.05,
            "status": "completed",
            "verdict": "good",
            "nodes_evaluated": 100,
            "nodes_promoted": 5,
            "nodes_degraded": 1,
            "vitality": VitalityShift(
                nodes_evaluated=100,
                mean_vitality_before=0.4,
                mean_vitality_after=0.45,
                median_shift=0.02,
            ),
        }
        base.update(overrides)
        return OneirosTickReport.model_validate(base)

    def test_round_trip(self) -> None:
        rep = self._minimal()
        restored = OneirosTickReport.model_validate_json(rep.model_dump_json())
        assert restored.report_type == "oneiros"
        assert restored.nodes_promoted == 5

    def test_negative_promoted_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._minimal(nodes_promoted=-1)
