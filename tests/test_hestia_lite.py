"""HestiaLite deterministic governance (W7-B, PHX-0037 slice 2)."""

from __future__ import annotations

from theogony.acquisition.base import SourceCandidate
from theogony.agents.hestia_lite import HestiaLiteApproval
from theogony.config.settings import HestiaLiteSettings
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor


def _trigger(search_query: str = "safe query") -> CuriosityTrigger:
    return CuriosityTrigger(
        origin_query="q",
        origin_query_run_id="r",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=1),
        stub_signal_strength=0.7,
        proposed_acquisition_spec=AcquisitionSpec(search_query=search_query),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.WEAK_ANSWER,
        answer_verdict="partial",
        cited_node_count=1,
    )


def _candidate(**kwargs: object) -> SourceCandidate:
    base = dict(
        source_type="gutenberg",
        identifier="1",
        title="Safe Title",
        authors=["Author, Test"],
        languages=["en"],
        download_url="https://example.org/pg1.txt",
        metadata={"copyright": False},
    )
    base.update(kwargs)
    return SourceCandidate.model_validate(base)


class TestBlocklist:
    def test_hestia_lite_blocklist_substring_case_insensitive(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings())
        c = _candidate(title="A minor study of botany")
        r = h.review(candidate=c, trigger=_trigger())
        assert r.status == "rejected"
        assert r.rule_fired == "title_or_search_in_blocklist"

    def test_blocklist_matches_trigger_search_query(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings())
        c = _candidate(title="Pure science")
        r = h.review(candidate=c, trigger=_trigger(search_query="weapons manufacturing guide"))
        assert r.status == "rejected"


class TestCopyright:
    def test_hestia_lite_copyright_true_rejected(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings())
        c = _candidate(metadata={"copyright": True})
        r = h.review(candidate=c, trigger=_trigger())
        assert r.status == "rejected"
        assert r.rule_fired == "license_unknown"


class TestDefaultApprove:
    def test_hestia_lite_default_approves_with_named_rule(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings())
        c = _candidate()
        r = h.review(candidate=c, trigger=_trigger())
        assert r.status == "approved"
        assert r.rule_fired == "default_approve"
        assert "public-domain" in r.reason


class TestAllowlist:
    def test_source_type_not_allowlisted(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings(allowlist=["gutenberg"]))
        c = _candidate(source_type="arxiv")
        r = h.review(candidate=c, trigger=_trigger())
        assert r.status == "rejected"
        assert r.rule_fired == "source_type_not_allowlisted"


class TestDownloadUrl:
    def test_download_url_missing_rejected(self) -> None:
        h = HestiaLiteApproval(HestiaLiteSettings())
        c = _candidate(download_url=None)
        r = h.review(candidate=c, trigger=_trigger())
        assert r.status == "rejected"
        assert r.rule_fired == "download_url_missing"
