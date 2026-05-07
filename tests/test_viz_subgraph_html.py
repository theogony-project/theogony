"""Tests for standalone Chronik subgraph HTML export."""

from __future__ import annotations

from pathlib import Path

from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.viz.subgraph_html import chronik_subgraph_payload, write_chronik_subgraph_html


def _src() -> SourceRef:
    return SourceRef(source_type="test", identifier="doc:1")


def test_chronik_subgraph_payload_from_models() -> None:
    src = _src()
    n1 = KnowledgeNode(
        id="AKA-aaaaaaaaaaaa",
        label="Alpha",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
    )
    n2 = KnowledgeNode(
        id="AKA-bbbbbbbbbbbb",
        label="Beta",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
    )
    e = KnowledgeEdge(
        source_id=n1.id,
        target_id=n2.id,
        relation_type="BINDS_TO",
        weight=0.9,
        source_ref=src,
    )
    p = chronik_subgraph_payload([n1, n2], [e])
    assert p["nodes"] == [
        {"id": n1.id, "label": "Alpha"},
        {"id": n2.id, "label": "Beta"},
    ]
    assert len(p["edges"]) == 1
    assert p["edges"][0]["source"] == n1.id
    assert p["edges"][0]["target"] == n2.id
    assert p["edges"][0]["weight"] == 0.9
    assert p["edges"][0]["relation_type"] == "BINDS_TO"


def test_write_chronik_subgraph_html(tmp_path: Path) -> None:
    src = _src()
    n = KnowledgeNode(
        id="AKA-cccccccccccc",
        label="Lonely",
        node_type=NodeType.CONCEPT,
        layer=Layer.EPHEMERA,
        source_ref=src,
    )
    out = tmp_path / "sub.html"
    write_chronik_subgraph_html(out, nodes=[n], edges=[], title='Test <>&"')
    text = out.read_text(encoding="utf-8")
    assert "cytoscape" in text.lower()
    assert "AKA-cccccccccccc" in text
    assert "Lonely" in text
    assert "Test &lt;&gt;&amp;&quot;" in text or "&lt;" in text
