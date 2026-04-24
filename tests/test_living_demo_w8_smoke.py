"""
W8 living-demo gate: growth-stream SSE + CuriosityRunReport + IngestRunReport on disk.

Uses the same stub Gutenberg + Fake Wikidata wiring as W7-B; no Gutendex HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.cockpit.test_growth_stream import _stub_argus_session, _stub_gutenberg_cm
from theogony.config.settings import Settings
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.reporting.models import IngestRunReport


def _event_sequence(raw: str) -> list[str]:
    seq: list[str] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        ev: str | None = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data: "):
                obj = json.loads(line[6:])
                if ev:
                    seq.append(ev)
                elif obj.get("type") == "phase":
                    seq.append(f"legacy:{obj.get('phase')}")
                elif obj.get("type") == "complete":
                    seq.append("legacy:complete")
                ev = None
    return seq


@pytest.mark.living_demo
def test_w8_growth_stream_inline_smoke(
    api_client: TestClient,
    api_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end growth SSE with stub acquisition; reports land under run_reports_dir."""
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._gutenberg_adapter",
        _stub_gutenberg_cm,
    )
    monkeypatch.setattr(
        "theogony.cockpit.growth_stream._cockpit_argus_dispatch_session",
        _stub_argus_session,
    )
    reports_dir = Path(api_settings.run_reports_dir)
    with api_client.stream(
        "POST",
        "/cockpit/api/growth-stream",
        json={"q": "Who was Sven Hedin and what did he investigate in Tibet?", "growth": True},
    ) as r:
        assert r.status_code == 200
        raw = r.read().decode()

    seq = _event_sequence(raw)
    assert seq[:4] == [
        "legacy:chat_compact",
        "legacy:embed",
        "legacy:retrieve",
        "legacy:synthesize",
    ]
    assert "legacy:complete" in seq
    qp = [x for x in seq if x == "query_phase"]
    assert len(qp) == 3
    assert "query_complete" in seq
    assert "trigger_emitted" in seq
    assert "argus_phase" in seq
    assert "argus_complete" in seq
    assert seq.index("trigger_emitted") < seq.index("argus_complete")

    curiosity_files = list((reports_dir / "curiosity").glob("*.json"))
    assert len(curiosity_files) >= 1
    CuriosityRunReport.model_validate_json(curiosity_files[0].read_text(encoding="utf-8"))

    ingest_files = list((reports_dir / "ingest").glob("*.json"))
    assert len(ingest_files) >= 1
    IngestRunReport.model_validate_json(ingest_files[0].read_text(encoding="utf-8"))
