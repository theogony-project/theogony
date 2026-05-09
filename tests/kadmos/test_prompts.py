"""
Unit tests for Kadmos v2 prompt builders (E2).

All tests are deterministic (no LLM required).
"""

from __future__ import annotations

import json

from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    HypothesisCandidate,
    ReadingHypotheses,
    ReadingState,
    SynthesisNode,
)
from theogony.kadmos.prompts import (
    READING_STEP_OUTPUT_SCHEMA,
    READING_STEP_SYSTEM,
    build_reading_step_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _state_with_concepts() -> ReadingState:
    state = ReadingState(session_id="sess-001", current_step=3)
    state.active_concepts["c1"] = ActiveConcept(
        id="c1",
        label="Tibet",
        description="A region in Central Asia",
        activation=0.9,
        step_created=0,
    )
    state.active_concepts["c2"] = ActiveConcept(
        id="c2", label="Sven Hedin", description="Swedish explorer", activation=0.7, step_created=1
    )
    state.active_edges["e1"] = ActiveEdge(
        id="e1",
        source_id="c2",
        target_id="c1",
        relation_description="Hedin explored Tibet extensively",
        weight=0.85,
        step_created=1,
    )
    state.open_tensions = ["unclear date of first crossing"]
    return state


def _hypotheses() -> ReadingHypotheses:
    return ReadingHypotheses(
        similarity_candidates=[
            HypothesisCandidate(
                concept_id="c1", label="Tibet", score=0.92, hypothesis_type="similarity"
            ),
        ],
        traversal_candidates=[
            HypothesisCandidate(
                concept_id="c2", label="Sven Hedin", score=0.7, hypothesis_type="traversal"
            ),
        ],
    )


_TEXT = "Hedin crossed the Trans-Himalaya range in 1906 with a small caravan."


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_prompt_is_valid_json() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT,
        state=_state_with_concepts(),
        hypotheses=_hypotheses(),
    )
    data = json.loads(prompt)
    assert isinstance(data, dict)


def test_prompt_contains_passage_text() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT, state=_state_with_concepts(), hypotheses=_hypotheses()
    )
    assert "Hedin crossed" in prompt


def test_prompt_contains_active_concepts() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT, state=_state_with_concepts(), hypotheses=_hypotheses()
    )
    assert "Tibet" in prompt
    assert "Sven Hedin" in prompt


def test_prompt_contains_hypotheses() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT, state=_state_with_concepts(), hypotheses=_hypotheses()
    )
    data = json.loads(prompt)
    assert len(data["hypotheses"]["similarity_candidates"]) == 1
    assert len(data["hypotheses"]["traversal_candidates"]) == 1


def test_prompt_contains_open_tensions() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT, state=_state_with_concepts(), hypotheses=_hypotheses()
    )
    data = json.loads(prompt)
    assert "unclear date" in str(data["current_understanding"]["open_tensions"])


def test_prompt_section_title_included_when_provided() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT,
        state=_state_with_concepts(),
        hypotheses=_hypotheses(),
        section_title="Early Expeditions",
    )
    data = json.loads(prompt)
    assert data.get("section_title") == "Early Expeditions"


def test_prompt_section_title_absent_when_none() -> None:
    prompt = build_reading_step_prompt(
        text=_TEXT, state=_state_with_concepts(), hypotheses=_hypotheses()
    )
    data = json.loads(prompt)
    assert "section_title" not in data


def test_prompt_deterministic() -> None:
    state = _state_with_concepts()
    h = _hypotheses()
    p1 = build_reading_step_prompt(text=_TEXT, state=state, hypotheses=h)
    p2 = build_reading_step_prompt(text=_TEXT, state=state, hypotheses=h)
    assert p1 == p2


def test_prompt_empty_state() -> None:
    empty_state = ReadingState(session_id="s")
    prompt = build_reading_step_prompt(
        text="Simple passage.", state=empty_state, hypotheses=ReadingHypotheses()
    )
    data = json.loads(prompt)
    assert data["current_understanding"]["active_concepts"] == []
    assert data["hypotheses"]["similarity_candidates"] == []


def test_prompt_top20_concepts_cap() -> None:
    state = ReadingState(session_id="s")
    for i in range(30):
        cid = f"c{i}"
        state.active_concepts[cid] = ActiveConcept(
            id=cid, label=f"Concept {i}", activation=float(i) / 30, step_created=0
        )
    prompt = build_reading_step_prompt(text="x", state=state, hypotheses=ReadingHypotheses())
    data = json.loads(prompt)
    assert len(data["current_understanding"]["active_concepts"]) == 20


def test_prompt_with_synthesis_in_state() -> None:
    state = _state_with_concepts()
    state.syntheses["s1"] = SynthesisNode(
        id="s1",
        label="Tibetan Exploration",
        description="Synthesis of exploration themes",
        basis_concept_ids=["c1", "c2"],
        synthesis_level="paragraph",
        step_created=3,
    )
    prompt = build_reading_step_prompt(text=_TEXT, state=state, hypotheses=_hypotheses())
    data = json.loads(prompt)
    assert len(data["current_understanding"]["recent_syntheses"]) == 1
    assert data["current_understanding"]["recent_syntheses"][0]["label"] == "Tibetan Exploration"


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


def test_output_schema_is_dict() -> None:
    assert isinstance(READING_STEP_OUTPUT_SCHEMA, dict)


def test_output_schema_required_fields() -> None:
    required = READING_STEP_OUTPUT_SCHEMA.get("required", [])
    for field in (
        "new_concepts",
        "new_connections",
        "confirmed_hypotheses",
        "rejected_hypotheses",
        "revisions",
        "synthesis",
        "open_tensions",
        "next_granularity",
    ):
        assert field in required, f"'{field}' must be in required"


def test_output_schema_synthesis_nullable() -> None:
    synthesis_type = READING_STEP_OUTPUT_SCHEMA["properties"]["synthesis"]["type"]
    assert "null" in synthesis_type


def test_output_schema_next_granularity_enum() -> None:
    enum = READING_STEP_OUTPUT_SCHEMA["properties"]["next_granularity"]["enum"]
    assert set(enum) == {"sentence", "paragraph", "section", "skim"}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_is_non_empty_string() -> None:
    assert isinstance(READING_STEP_SYSTEM, str)
    assert len(READING_STEP_SYSTEM) > 200


def test_system_prompt_mentions_revision() -> None:
    assert "revision" in READING_STEP_SYSTEM.lower()


def test_system_prompt_mentions_working_memory() -> None:
    assert "working memory" in READING_STEP_SYSTEM.lower()


def test_system_prompt_mentions_synthesis() -> None:
    assert "synthesis" in READING_STEP_SYSTEM.lower()
