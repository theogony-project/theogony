"""Unit tests for :class:`~theogony.retrieval.synthesize.OfflineAnswerSynthesizer` (PHX-0070)."""

from __future__ import annotations

import pytest

from theogony.core.model import Constellation, ConstellationNode, Layer, NodeType, SourceRef
from theogony.retrieval.synthesize import AnswerSynthesizer, OfflineAnswerSynthesizer


def _slim(
    nid: str,
    label: str,
    *,
    confidence: float,
    description: str | None = None,
) -> ConstellationNode:
    ref = SourceRef(source_type="test", identifier="id-1", location="p1")
    return ConstellationNode(
        id=nid,
        label=label,
        node_type=NodeType.CONCEPT,
        layer=Layer.MNEME,
        confidence=confidence,
        source_ref=ref,
        description=description,
    )


@pytest.mark.asyncio
async def test_offline_synthesizer_picks_top_n_by_confidence() -> None:
    nodes = [
        _slim("AKA-aaaaaaaaaaaa", "low", confidence=0.1),
        _slim("AKA-bbbbbbbbbbbb", "mid", confidence=0.5),
        _slim("AKA-cccccccccccc", "high", confidence=0.99),
    ]
    c = Constellation(query="q", nodes=nodes, edges=[])
    synth = OfflineAnswerSynthesizer(top_n=2)
    ans = await synth.synthesize(c)
    assert ans.cited_node_ids == ["AKA-cccccccccccc", "AKA-bbbbbbbbbbbb"]


@pytest.mark.asyncio
async def test_offline_synthesizer_handles_empty_constellation_gracefully() -> None:
    c = Constellation(query="empty", nodes=[], edges=[])
    ans = await OfflineAnswerSynthesizer().synthesize(c)
    assert "no nodes" in ans.text.lower()
    assert ans.cited_node_ids == []


@pytest.mark.asyncio
async def test_offline_synthesizer_records_zero_cost_and_zero_tokens() -> None:
    c = Constellation(
        query="q",
        nodes=[_slim("AKA-dddddddddddd", "a", confidence=0.9)],
        edges=[],
    )
    ans = await OfflineAnswerSynthesizer(top_n=6).synthesize(c)
    assert ans.synthesis.input_tokens == 0
    assert ans.synthesis.output_tokens == 0
    assert ans.synthesis.cost_eur == 0.0
    assert ans.synthesis.latency_ms == 0


@pytest.mark.asyncio
async def test_offline_synthesizer_prints_the_node_text_under_its_citation() -> None:
    """PHX-1117: the citation list names the source and, when the node has one,
    its own stored text — verbatim, so the answer is still nothing generated."""
    noted = _slim(
        "AKA-111111111111",
        "The Permanent Dream (Oneiros)",
        confidence=0.9,
        description="Oneiros never sleeps. Status note: nothing schedules it.",
    )
    bare = _slim("AKA-222222222222", "Lethe", confidence=0.8)
    c = Constellation(query="q", nodes=[noted, bare], edges=[])
    ans = await OfflineAnswerSynthesizer(top_n=6).synthesize(c)
    lines = ans.text.splitlines()
    cited = lines.index(next(line for line in lines if "[AKA-111111111111]" in line))
    assert lines[cited + 1] == "  Oneiros never sleeps. Status note: nothing schedules it."
    bare_line = next(line for line in lines if "[AKA-222222222222]" in line)
    assert lines.index(bare_line) == len(lines) - 1, "a node without text adds no line"


@pytest.mark.asyncio
async def test_offline_synthesizer_text_contains_aka_brackets_for_each_cited_id() -> None:
    n1 = _slim("AKA-eeeeeeeeeeee", "one", confidence=0.8)
    n2 = _slim("AKA-ffffffffffff", "two", confidence=0.7)
    c = Constellation(query="topic", nodes=[n1, n2], edges=[])
    ans = await OfflineAnswerSynthesizer(top_n=6).synthesize(c)
    for cid in ans.cited_node_ids:
        assert f"[{cid}]" in ans.text
    extracted = AnswerSynthesizer._extract_citations(ans.text)
    for cid in ans.cited_node_ids:
        assert cid in extracted
