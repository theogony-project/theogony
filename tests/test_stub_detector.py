"""Unit tests for :class:`~theogony.curiosity.stub_detector.StubDetector` (W3 / PHX-0058)."""

from __future__ import annotations

import pytest

from theogony.config.settings import StubThresholds
from theogony.core.model import Constellation, ConstellationNode, Layer, NodeType, SourceRef
from theogony.curiosity.stub_detector import StubDetector
from theogony.retrieval.synthesize import Answer


def _src(st: str) -> SourceRef:
    return SourceRef(source_type=st, identifier="1", location="loc", language="en")


def _node(
    i: int,
    *,
    confidence: float = 0.9,
    source_type: str = "wikidata",
) -> ConstellationNode:
    return ConstellationNode(
        id=f"n{i}",
        label=f"L{i}",
        node_type=NodeType.CONCEPT,
        layer=Layer.MNEME,
        confidence=confidence,
        source_ref=_src(source_type),
    )


def _cst(*nodes: ConstellationNode, edges: int = 0) -> Constellation:
    from theogony.core.model import ConstellationEdge

    e_list = []
    for j in range(edges):
        a, b = nodes[j % len(nodes)], nodes[(j + 1) % len(nodes)]
        e_list.append(
            ConstellationEdge(
                edge_id=f"e{j}",
                source_id=a.id,
                target_id=b.id,
                relation_type="R",
                weight=0.5,
                confidence=0.8,
            )
        )
    return Constellation(query="q", nodes=list(nodes), edges=e_list)


def test_detect_returns_no_stub_when_constellation_is_dense_and_diverse() -> None:
    t = StubThresholds()
    d = StubDetector(t)
    nodes = (_node(0, source_type="a"), _node(1, source_type="b"), _node(2, source_type="c"))
    c = _cst(*nodes, edges=4)
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert not v.is_stub
    assert v.stub_signal_strength == pytest.approx(0.0)


def test_detect_fires_low_node_count_below_threshold() -> None:
    t = StubThresholds(min_node_count=3)
    d = StubDetector(t)
    c = _cst(_node(0), _node(1))
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v.low_node_count
    assert v.is_stub


def test_detect_fires_low_edge_density_when_few_edges() -> None:
    t = StubThresholds(min_node_count=1, min_edge_density=0.9)
    d = StubDetector(t)
    c = _cst(_node(0), _node(1), _node(2), edges=0)
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v.low_edge_density
    assert v.edge_density == pytest.approx(0.0)


def test_detect_fires_narrow_source_diversity_when_one_source_type() -> None:
    t = StubThresholds(min_node_count=1, min_distinct_source_types=2)
    d = StubDetector(t)
    c = _cst(_node(0, source_type="onlyone"), _node(1, source_type="onlyone"))
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v.narrow_source_diversity


def test_detect_fires_low_mean_confidence_when_proxy_below_threshold() -> None:
    t = StubThresholds(min_node_count=1, min_mean_vitality=0.95, min_mean_confidence=0.95)
    d = StubDetector(t)
    c = _cst(_node(0, confidence=0.1))
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v.low_vitality
    assert v.low_confidence_aggregate
    assert v.mean_confidence == pytest.approx(0.1)


def test_detect_named_entity_coverage_records_one_when_input_is_none() -> None:
    t = StubThresholds(min_node_count=1)
    d = StubDetector(t)
    c = _cst(_node(0))
    v = d.detect(
        query="q",
        constellation=c,
        answer=Answer(text="x", cited_node_ids=[]),
        named_entities_in_query=None,
    )
    assert v.named_entities_resolved_ratio == pytest.approx(1.0)
    assert not v.poor_named_entity_coverage


def test_detect_named_entity_coverage_records_actual_ratio_when_input_supplied() -> None:
    t = StubThresholds(
        min_node_count=1,
        min_named_entities_resolved_ratio=0.9,
    )
    d = StubDetector(t)
    c = _cst(
        ConstellationNode(
            id="n0",
            label="Alpha",
            node_type=NodeType.CONCEPT,
            layer=Layer.MNEME,
            confidence=0.9,
            source_ref=_src("t"),
        )
    )
    v = d.detect(
        query="q",
        constellation=c,
        answer=Answer(text="x", cited_node_ids=["n0"]),
        named_entities_in_query=["Alpha", "Missing"],
    )
    assert v.named_entities_resolved_ratio == pytest.approx(0.5)
    assert v.poor_named_entity_coverage


def test_aggregate_strength_equals_fired_signal_count_over_six() -> None:
    t = StubThresholds(
        min_node_count=2,
        min_edge_density=1.0,
        min_mean_vitality=1.0,
        min_distinct_source_types=2,
        min_mean_confidence=1.0,
        min_named_entities_resolved_ratio=0.5,
    )
    d = StubDetector(t)
    c = _cst(_node(0, confidence=0.5, source_type="solo"), edges=0)
    v = d.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    fired = int(
        v.low_node_count
        + v.low_edge_density
        + v.low_vitality
        + v.narrow_source_diversity
        + v.low_confidence_aggregate
        + v.poor_named_entity_coverage
    )
    assert v.stub_signal_strength == pytest.approx(fired / 6.0)
    assert fired == 5
    assert not v.poor_named_entity_coverage


def test_is_stub_true_iff_strength_above_zero() -> None:
    t_loose = StubThresholds(
        min_node_count=0,
        min_edge_density=0.0,
        min_mean_vitality=0.0,
        min_distinct_source_types=1,
        min_mean_confidence=0.0,
    )
    d_loose = StubDetector(t_loose)
    c = _cst(_node(0))
    v0 = d_loose.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v0.stub_signal_strength == pytest.approx(0.0)
    assert not v0.is_stub

    t_tight = StubThresholds(min_node_count=99)
    d_tight = StubDetector(t_tight)
    v1 = d_tight.detect(query="q", constellation=c, answer=Answer(text="x", cited_node_ids=[]))
    assert v1.stub_signal_strength > 0.0
    assert v1.is_stub
