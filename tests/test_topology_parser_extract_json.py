"""Tests for topology JSON extraction helpers."""

from __future__ import annotations

import pytest

from theogony.extraction.topology_parser import extract_topology_blueprint_dict_from_llm_text


def test_extract_strips_markdown_fence() -> None:
    raw = """```json
{"cognitive_analysis": "x", "concepts": [], "synapses": []}
```
"""
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert d["cognitive_analysis"] == "x"
    assert d["concepts"] == []


def test_extract_first_object_with_trailing_noise() -> None:
    raw = """Here you go:
{"cognitive_analysis": "ok", "concepts": [{"local_id": "c1", "text": "A"}], "synapses": []}
(trailing commentary must not break parse)"""
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert d["concepts"][0]["text"] == "A"


def test_truncates_long_cognitive_analysis() -> None:
    long_ca = "z" * 800
    raw = '{"cognitive_analysis": "' + long_ca + '", "concepts": [], "synapses": []}'
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert len(d["cognitive_analysis"]) == 250


def test_coerces_null_cognitive_analysis_to_empty_string() -> None:
    raw = '{"cognitive_analysis": null, "concepts": [], "synapses": []}'
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert d["cognitive_analysis"] == ""


def test_coerces_concept_name_alias_to_text() -> None:
    raw = (
        '{"cognitive_analysis": "", "concepts": [{"local_id": "c1", "name": "Tibet passage"}], '
        '"synapses": []}'
    )
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert d["concepts"][0]["text"] == "Tibet passage"


def test_coerces_synapse_source_target_to_from_to() -> None:
    raw = (
        '{"cognitive_analysis": "", "concepts": [], '
        '"synapses": [{"source": "c1", "target": "c2", "type": "BINDS_TO", "weight": 0.9}]}'
    )
    d = extract_topology_blueprint_dict_from_llm_text(raw)
    assert d["synapses"][0]["from"] == "c1"
    assert d["synapses"][0]["to"] == "c2"


def test_no_json_raises() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        extract_topology_blueprint_dict_from_llm_text("just prose")
