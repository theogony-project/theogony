"""
W7-A demo path smoke (Living Demo Plan, PHX-0037 slice 1).

The living-demo gate: enable the GrowthBridge explicitly via the same
settings surface the demo script will use, ask a thin question against
an intentionally empty in-memory chronicle, and assert that exactly
one CuriosityRunReport lands on disk with the expected ``gap_class``.

This is the truthful demo gate. Mock-only-green (a unit test that
mocks the bridge or the writer) is not green for the demo path; this
test wires the actual GrowthBridge, the actual RunReportWriter, the
actual InMemoryKnowledgeStore, and the actual StubLLMProvider so the
W7-A path is exercised end-to-end without touching real services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import GrowthBridgeSettings, Settings
from theogony.curiosity.growth_bridge import GrowthBridge
from theogony.curiosity.run_report import CuriosityRunReport
from theogony.curiosity.trigger import GapClass
from theogony.memory.relevance import RelevanceTracker
from theogony.reporting.writer import RunReportWriter
from theogony.retrieval.constellation import ConstellationAssembler
from theogony.retrieval.multi_hop import MultiHopRetriever
from theogony.retrieval.pipeline import QueryPipeline
from theogony.retrieval.synthesize import AnswerSynthesizer
from theogony.stores import InMemoryKnowledgeStore


class _ConstantEmbedder:
    @property
    def model_id(self) -> str:
        return "constant-embedder@v1"

    @property
    def dim(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


@pytest.mark.living_demo
async def test_growth_bridge_demo_path_smoke(tmp_path: Path) -> None:
    """W7-A demo path: a thin query enabled-bridge produces a curiosity report on disk."""
    store = InMemoryKnowledgeStore()
    writer = RunReportWriter(tmp_path)
    bridge = GrowthBridge(GrowthBridgeSettings(enabled=True))
    pipeline = QueryPipeline(
        embedder=_ConstantEmbedder(),
        retriever=MultiHopRetriever(store),
        assembler=ConstellationAssembler(store),
        synthesizer=AnswerSynthesizer(StubLLMProvider(default="")),
        relevance=RelevanceTracker(store),
        settings=Settings(),
        report_writer=writer,
        growth_bridge=bridge,
    )

    await pipeline.ask("Who was Sven Hedin and what did he investigate in Tibet?")

    curiosity_dir = tmp_path / "curiosity"
    files = [p for p in curiosity_dir.iterdir() if p.suffix == ".json"]
    assert len(files) == 1, f"expected exactly one curiosity report, got {len(files)}"

    report = CuriosityRunReport.model_validate_json(files[0].read_text(encoding="utf-8"))
    assert report.report_type == "curiosity"
    assert report.trigger.origin_query.startswith("Who was Sven Hedin")
    # Empty chronicle + empty synthesis ⇒ failed verdict, weak-answer gate;
    # gap_class REGION_THIN per W10 Knob 2 (cited=0, no entity-unknown pair).
    assert report.trigger.gap_class == GapClass.REGION_THIN
    # The W7-A trigger carries no acquisition decision yet — that is W7-B.
    assert report.decision.hestia_status == "not_evaluated"
    assert report.bytes_acquired == 0
