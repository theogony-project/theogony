"""W16 ErisRedTeam."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.eris import ErisProbe, ErisRedTeam, ProbeAnswer, ProbeAnswerer
from theogony.config.settings import ErisSettings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.stores.memory import InMemoryKnowledgeStore


@pytest.mark.asyncio
async def test_eris_disabled_returns_skipped_summary() -> None:
    store = InMemoryKnowledgeStore()
    team = ErisRedTeam(store=store, settings=ErisSettings(enabled=False), answerer=None)
    s = await team.run_once()
    assert s.skipped_reason == "eris disabled"


@pytest.mark.asyncio
async def test_eris_fixture_mode_without_answerer_marks_adversarial_queries_not_run() -> None:
    store = InMemoryKnowledgeStore()
    team = ErisRedTeam(store=store, settings=ErisSettings(enabled=True), answerer=None)
    s = await team.run_once()
    assert s.not_run == 2
    assert s.passed == 1
    assert s.failed == 0
    assert all(
        r.outcome == "not_run" for r in s.probe_results if r.probe_kind == "adversarial_query"
    )


@pytest.mark.asyncio
async def test_eris_fixture_mode_writes_info_finding_for_source_poisoning_fixture() -> None:
    store = InMemoryKnowledgeStore()
    team = ErisRedTeam(store=store, settings=ErisSettings(enabled=True), answerer=None)
    s = await team.run_once()
    assert s.findings_written >= 1
    finding_nodes = [n for n in store._nodes.values() if n.node_type == NodeType.FINDING]
    assert any(
        (n.properties or {}).get("severity") == "info"
        and (n.properties or {}).get("cell") == "eris"
        for n in finding_nodes
    )


class _FailingAnswerer:
    async def answer_probe(self, probe: ErisProbe) -> ProbeAnswer:
        return ProbeAnswer(observed_verdict="good", evidence=["stub"])


@pytest.mark.asyncio
async def test_eris_with_fake_answerer_writes_finding_for_failed_probe() -> None:
    store = InMemoryKnowledgeStore()
    answerer: ProbeAnswerer = _FailingAnswerer()
    team = ErisRedTeam(store=store, settings=ErisSettings(enabled=True), answerer=answerer)
    s = await team.run_once()
    assert s.failed >= 1
    assert s.findings_written >= 1


@pytest.mark.asyncio
async def test_eris_never_ingests_adversarial_content() -> None:
    store = InMemoryKnowledgeStore()
    await store.batch_upsert_nodes(
        [
            KnowledgeNode(
                id="KEEP",
                label="keeper",
                node_type=NodeType.PERSON,
                source_ref=SourceRef(source_type="test", identifier="k"),
            )
        ]
    )
    before = {nid: n for nid, n in store._nodes.items() if n.node_type != NodeType.FINDING}
    team = ErisRedTeam(store=store, settings=ErisSettings(enabled=True), answerer=None)
    await team.run_once()
    after_non_finding = {
        nid: n for nid, n in store._nodes.items() if n.node_type != NodeType.FINDING
    }
    assert set(before.keys()) == set(after_non_finding.keys())
    for nid, n0 in before.items():
        assert after_non_finding[nid].label == n0.label


def test_eris_module_has_no_query_pipeline() -> None:
    eris_path = Path(__file__).resolve().parents[2] / "src" / "theogony" / "agents" / "eris.py"
    text = eris_path.read_text(encoding="utf-8")
    assert "QueryPipeline(" not in text
    assert "delete_node" not in text
    assert "batch_update_scores" not in text
