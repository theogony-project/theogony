"""Cockpit operator worker tick (Wave 3 sequence in-process)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theogony.cockpit.operator_tick import run_wave3_worker_pass
from theogony.cockpit.standalone_app import app
from theogony.config.settings import LLMSettings, Settings
from theogony.reporting.writer import RunReportWriter
from theogony.stores.memory import InMemoryKnowledgeStore


@pytest.mark.asyncio
async def test_run_wave3_worker_pass_returns_five_steps(tmp_path: Path) -> None:
    data = tmp_path / "op"
    data.mkdir()
    settings = Settings(llm=LLMSettings(provider="stub"), data_dir=data)
    store = InMemoryKnowledgeStore()
    writer = RunReportWriter(settings.run_reports_dir)
    steps = await run_wave3_worker_pass(store=store, settings=settings, report_writer=writer)
    assert [s.step for s in steps] == ["athene", "chronos", "nemesis", "eris", "mnemosyne"]
    assert all(s.ok for s in steps)


def test_post_operator_worker_tick_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEOGONY_COCKPIT__KNOWLEDGE_STORE", "memory")
    monkeypatch.setenv("THEOGONY_COCKPIT__OPERATOR_WORKER_FROM_UI", "true")
    with TestClient(app) as client:
        r = client.post("/cockpit/operator/worker-tick")
    assert r.status_code == 200
    body = r.json()
    assert "steps" in body
    assert len(body["steps"]) == 5


def test_post_operator_worker_tick_disabled_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THEOGONY_COCKPIT__KNOWLEDGE_STORE", "memory")
    monkeypatch.setenv("THEOGONY_COCKPIT__OPERATOR_WORKER_FROM_UI", "false")
    with TestClient(app) as client:
        r = client.post("/cockpit/operator/worker-tick")
    assert r.status_code == 404
