"""The stance a reading declares reaches the substrate (PHX-1107).

`test_frames.py` pins the basis and `test_contradiction.py` pins the pass that
reads it. What is left is the wiring in between, and it is the part that has
failed before: the frame field existed, was written on every node, and carried
a salted hash instead of a stance for the entire life of the project
(PHX-1095). A test that only checks *that* a frame is written would have passed
throughout. These check *what* is written.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.mesh import frames
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _reading(stance: str, *, relation_kind: str = "semantic") -> str:
    return json.dumps(
        {
            "stance": stance,
            "concepts": [
                {
                    "label": "Night",
                    "entity_type": "person",
                    "tags": ["goddess"],
                    "description": "Primordial goddess of night",
                },
                {
                    "label": "the Fates",
                    "entity_type": "concept",
                    "tags": ["Moerae"],
                    "description": "The three Fates",
                },
            ],
            "relations": [
                {
                    "source": "Night",
                    "target": "the Fates",
                    "relation_descriptor": "bore",
                    "relation_kind": relation_kind,
                    "stance": stance,
                    "rationale": "The paragraph says Night bore them.",
                }
            ],
            "paragraph_concept": {
                "label": "The children of Night",
                "description": "Night's parthenogenetic offspring.",
                "tags": ["genealogy"],
                "basis_concepts": ["Night", "the Fates"],
            },
        }
    )


def _paragraphs(readings: list[str]) -> tuple[str, dict[str, str]]:
    """One distinct paragraph per canned reading, keyed the way the stub matches."""
    texts = [f"Paragraph number {i} of the test corpus." for i in range(len(readings))]
    return "\n\n".join(texts), {
        f"PARAGRAPH:\n{text}": reading for text, reading in zip(texts, readings, strict=True)
    }


def _read(tmp_path: Path, readings: list[str]) -> MeshRuntime:
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=8)
    text, responses = _paragraphs(readings)
    reader = MeshParagraphReader(runtime, llm=StubLLMProvider(responses=responses))
    asyncio.run(
        reader.read_text(
            text=text,
            source_type="text",
            source_identifier="test",
            title="Test",
            anchor="test",
        )
    )
    return runtime


def _stance_of(vector: list[float], dim: int) -> str:
    """Which stance this frame is, by nearest reference point."""
    if all(v == 0.0 for v in vector):
        return "neutral"
    best, score = "?", -2.0
    for stance in frames.STANCES:
        if stance == "neutral":
            continue
        cos = frames.frame_cosine(vector, frames.frame_vector(stance, dim=dim))
        if cos > score:
            best, score = stance, cos
    return best if score > 0.999 else f"~{best}"


def test_the_chunk_carries_the_stance_the_reading_declared(tmp_path: Path) -> None:
    runtime = _read(tmp_path, [_reading("disputed")])
    chunks = list(runtime.nodes.iter_chunks())
    assert len(chunks) == 1
    assert _stance_of(chunks[0].frame_vector, runtime.frame_dim) == "disputed"


def test_different_paragraphs_get_different_frames(tmp_path: Path) -> None:
    """The failure this guards against is the one the first live probe found:
    every paragraph landing on the default because the prompt described the
    stance without showing that it is a top-level field."""
    runtime = _read(tmp_path, [_reading("historical_claim"), _reading("refuted_claim")])
    found = {_stance_of(c.frame_vector, runtime.frame_dim) for c in runtime.nodes.iter_chunks()}
    assert found == {"historical_claim", "refuted_claim"}


def test_entities_and_source_anchors_hold_no_stance(tmp_path: Path) -> None:
    """'Night' is neither asserted nor denied; the claims about her live on the
    chunks. A neutral frame is never attenuated by routing, which is what a
    thing that makes no claim should be."""
    runtime = _read(tmp_path, [_reading("refuted_claim")])
    for node in runtime.nodes.iter_consolidated():
        if node.is_source_anchor or "paragraph_concept" not in node.tags:
            assert all(v == 0.0 for v in node.frame_vector), node.description


def test_the_paragraph_concept_carries_the_paragraph_stance(tmp_path: Path) -> None:
    """It is the paragraph's claim in one node, so it holds the paragraph's
    stance — unlike the entities, which are things the claim is about."""
    runtime = _read(tmp_path, [_reading("hypothesis")])
    concepts = [
        n for n in runtime.nodes.iter_consolidated() if "paragraph_concept" in (n.tags or [])
    ]
    assert concepts
    assert _stance_of(concepts[0].frame_vector, runtime.frame_dim) == "hypothesis"


def test_an_unreadable_paragraph_falls_back_rather_than_failing(tmp_path: Path) -> None:
    """A failed reading has no stance to declare. The default claims least."""
    runtime = _read(tmp_path, ["not json at all"])
    chunks = list(runtime.nodes.iter_chunks())
    assert len(chunks) == 1
    assert _stance_of(chunks[0].frame_vector, runtime.frame_dim) == "current_claim"


def test_every_edge_records_when_it_came_to_hold(tmp_path: Path) -> None:
    """PANTHEON_VISION Non-Negotiable 3 asks that time be intrinsic. `valid_to`
    stays open until something supersedes the edge."""
    runtime = _read(tmp_path, [_reading("current_claim")])
    edges = runtime.edges.load_all_edges()
    assert edges
    for edge in edges:
        assert edge.valid_from is not None
        assert edge.valid_to is None


def test_frame_consistency_is_computed_where_both_endpoints_make_a_claim(
    tmp_path: Path,
) -> None:
    """PHX-1095 measured this field at exactly 1.0 on all 94,490 edges of the
    founding mesh and called it 'a missing pass, not missing data'. Two
    paragraphs in opposed stances must now produce an edge below 1.0."""
    runtime = _read(tmp_path, [_reading("current_claim"), _reading("refuted_claim")])
    values = {round(e.frame_consistency, 3) for e in runtime.edges.load_all_edges()}
    assert values != {1.0}, "no edge carried endpoint frame information"
    assert min(values) < 0.5


def test_the_reading_reports_which_stances_it_produced(tmp_path: Path) -> None:
    """A histogram with one key means the vocabulary reached the model and the
    model ignored it — which is exactly what the first live run showed."""
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=8)
    text, responses = _paragraphs(
        [_reading("disputed", relation_kind="contradicts"), _reading("definition")]
    )
    reader = MeshParagraphReader(runtime, llm=StubLLMProvider(responses=responses))
    result = asyncio.run(
        reader.read_text(
            text=text,
            source_type="text",
            source_identifier="test",
            title="Test",
            anchor="test",
        )
    )
    assert result["stances"] == {"definition": 1, "disputed": 1}
    assert result["contradiction_edges"] == 1


def test_a_contradicts_relation_survives_into_the_mesh(tmp_path: Path) -> None:
    """The relation kind the substrate could not express before."""
    runtime = _read(tmp_path, [_reading("disputed", relation_kind="contradicts")])
    kinds = {e.relation_kind for e in runtime.edges.load_all_edges()}
    assert "contradicts" in kinds
    assert any(frames.is_contradiction_kind(k) for k in kinds)


@pytest.mark.parametrize("stance", ["definition", "observation", "superseded", "direct_quote"])
def test_each_stance_the_prompt_offers_survives_the_round_trip(tmp_path: Path, stance: str) -> None:
    runtime = _read(tmp_path, [_reading(stance)])
    chunk = next(iter(runtime.nodes.iter_chunks()))
    assert _stance_of(chunk.frame_vector, runtime.frame_dim) == stance
