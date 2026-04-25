"""W13 research-request SSE endpoint tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.cockpit.test_growth_stream import (
    _parse_sse_blocks,
    _stub_argus_session,
    _stub_gutenberg_cm,
)
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import (
    AcquisitionSpec,
    CuriosityTrigger,
    GapClass,
    TriggerBudget,
    TriggerReason,
)
from theogony.reporting.models import RegionDescriptor
from theogony.reporting.writer import RunReportWriter


def test_research_request_stream_endpoint_returns_sse_with_trigger_replay(
    cockpit_client: TestClient,
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer: RunReportWriter = api_app.state.report_writer
    trig = CuriosityTrigger(
        origin_query="Who was Sven Hedin?",
        origin_query_run_id="query-run-1",
        gap_class=GapClass.REGION_THIN,
        region_descriptor=RegionDescriptor(query_embedding=[0.1, 0.2], seed_node_count=0),
        stub_signal_strength=0.9,
        proposed_acquisition_spec=AcquisitionSpec(search_query="Sven Hedin Tibet"),
        budget=TriggerBudget(),
        trigger_reason=TriggerReason.USER_REQUEST,
        answer_verdict="partial",
        cited_node_count=0,
    )
    writer.write(
        CuriosityRunReport(
            started_at=datetime(2026, 4, 25, tzinfo=UTC),
            finished_at=datetime(2026, 4, 25, 0, 0, 1, tzinfo=UTC),
            duration_s=1.0,
            status="completed",
            verdict="good",
            verdict_reasoning="research initiated by user request",
            trigger=trig,
        )
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._gutenberg_adapter",
        _stub_gutenberg_cm,
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._cockpit_argus_dispatch_session",
        _stub_argus_session,
    )

    with cockpit_client.stream(
        "GET",
        f"/cockpit/api/research-request-stream/{trig.trigger_id}",
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()

    names = [e for e, _ in _parse_sse_blocks(raw) if e]
    assert names[0] == "trigger_emitted"
    assert "acquired_into_pool" in names
    assert names[-1] == "research_complete"
