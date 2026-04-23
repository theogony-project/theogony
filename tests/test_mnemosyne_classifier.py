"""Unit tests for Mnemosyne heuristic classifier (PHX-0071 / W5)."""

from __future__ import annotations

import pytest

from theogony.agents.mnemosyne_classifier import MetaQueryClassifier, _heuristic_breakdown
from theogony.config.settings import MnemosyneSettings
from theogony.core.model import Constellation, ConstellationNode, Layer, NodeType, SourceRef
from theogony.reporting.models import MetaClassificationVerdict, SynthesisBreakdown
from theogony.retrieval.synthesize import Answer


def _classifier(**kwargs: object) -> MetaQueryClassifier:
    cfg = MnemosyneSettings(**kwargs) if kwargs else MnemosyneSettings()
    return MetaQueryClassifier(cfg=cfg, llm_fallback=None)


def test_heuristic_returns_self_referential_for_high_keyword_hit_in_query() -> None:
    c = _classifier()
    mc = c.classify_heuristic_query_only("How does the Pantheon store embeddings?")
    assert mc.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
    assert mc.high_keyword_hits >= 1


@pytest.mark.asyncio
async def test_heuristic_self_referential_high_keyword_in_cited_label() -> None:
    c = _classifier()
    nodes = [
        ConstellationNode(
            id="AKA-abc",
            label="Chronik overview",
            node_type=NodeType.CONCEPT,
            layer=Layer.MNEME,
            confidence=0.9,
            source_ref=SourceRef(source_type="book", identifier="x"),
        )
    ]
    const = Constellation(
        query="plain query",
        nodes=nodes,
        edges=[],
        gaps=[],
        suggested_sources=[],
    )
    answer = Answer(
        text="See [AKA-abc] for context.",
        cited_node_ids=["AKA-abc"],
        synthesis=SynthesisBreakdown(),
    )
    mc = await c.classify(
        query="plain query",
        answer=answer,
        cited_node_ids=answer.cited_node_ids,
        constellation=const,
    )
    assert mc.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
    assert mc.cited_label_meta_hits >= 1


def test_heuristic_returns_self_referential_for_two_mid_keyword_hits() -> None:
    c = _classifier()
    mc = c.classify_heuristic_query_only("Compare agent behaviour with store layout.")
    assert mc.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
    assert mc.mid_keyword_hits >= 2


def test_heuristic_returns_uncertain_for_one_mid_keyword_hit_long_query() -> None:
    q = (
        "This is a deliberately long filler sentence about cats and dogs "
        "and weather patterns in the mountains, ending with the word agent once."
    )
    v, _h, _m, _c = _heuristic_breakdown(
        query=q,
        answer=None,
        cited_node_ids=(),
        constellation=None,
    )
    assert v == MetaClassificationVerdict.UNCERTAIN


def test_heuristic_returns_not_self_referential_when_no_keywords() -> None:
    c = _classifier()
    mc = c.classify_heuristic_query_only("What is the weather in Tibet?")
    assert mc.verdict == MetaClassificationVerdict.NOT_SELF_REFERENTIAL


def test_classify_records_keyword_hit_breakdown() -> None:
    c = _classifier()
    mc = c.classify_heuristic_query_only("chronik schema tick phase")
    assert mc.high_keyword_hits + mc.mid_keyword_hits > 0
