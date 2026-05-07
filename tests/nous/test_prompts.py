"""
Unit tests for nous.prompts (nous_implementation_brief §5, E2).

All tests are deterministic (no LLM required) — given fixed inputs the
prompt must contain expected substrings and the schema must be valid.
"""

from __future__ import annotations

import json

from theogony.nous.model import ChronicleHint, WorkingMemoryState
from theogony.nous.prompts import (
    READING_STEP_OUTPUT_SCHEMA,
    READING_STEP_SYSTEM,
    build_reading_step_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wm(step: int = 1) -> WorkingMemoryState:
    return WorkingMemoryState(
        step_index=step,
        concepts={"AKA-abc": 0.9, "AKA-def": 0.4, "AKA-ghi": 0.2},
        pooled_embedding=[0.1, 0.2],
        open_tensions=[("AKA-abc", "Contradiction with earlier claim about Tibet")],
    )


def _hints() -> list[ChronicleHint]:
    return [
        ChronicleHint(id="AKA-abc", label="Sven Hedin", similarity=0.91, source="gutenberg:43497"),
        ChronicleHint(
            id="AKA-def",
            label="Trans-Himalaya",
            similarity=0.87,
            source="gutenberg:43497",
            tension=True,
        ),
    ]


_PARAGRAPH = "Hedin crossed the Trans-Himalaya range in 1906 with a small caravan."


# ---------------------------------------------------------------------------
# build_reading_step_prompt — structure
# ---------------------------------------------------------------------------


def test_prompt_is_valid_json() -> None:
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=_hints(),
        open_tensions=[("AKA-abc", "tension description")],
        synthesis_opportunity=True,
    )
    data = json.loads(prompt)
    assert isinstance(data, dict)


def test_prompt_contains_paragraph_text() -> None:
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=False,
    )
    assert "Hedin crossed" in prompt


def test_prompt_contains_synthesis_opportunity_true() -> None:
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=True,
    )
    data = json.loads(prompt)
    assert data["synthesis_opportunity"] is True


def test_prompt_contains_synthesis_opportunity_false() -> None:
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    assert data["synthesis_opportunity"] is False


def test_prompt_contains_chronicle_hints_block() -> None:
    hints = _hints()
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=hints,
        open_tensions=[],
        synthesis_opportunity=False,
    )
    assert "Sven Hedin" in prompt
    assert "Trans-Himalaya" in prompt
    assert "AKA-abc" in prompt


def test_prompt_hint_tension_flag_included() -> None:
    hints = _hints()
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=hints,
        open_tensions=[],
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    hints_block = data["chronicle_hints"]
    tension_hit = next(h for h in hints_block if h.get("id") == "AKA-def")
    assert tension_hit.get("tension") is True


def test_prompt_working_memory_summary_present() -> None:
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    wm = data["working_memory"]
    assert "step_index" in wm
    assert "top_concepts" in wm


def test_prompt_working_memory_top_concepts_capped_at_10() -> None:
    concepts = {f"AKA-{i:03d}": float(i) / 20.0 for i in range(20)}
    wm = WorkingMemoryState(step_index=5, concepts=concepts, pooled_embedding=[])
    prompt = build_reading_step_prompt(
        paragraph="x",
        working_memory=wm,
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    assert len(data["working_memory"]["top_concepts"]) == 10


def test_prompt_open_tensions_block() -> None:
    tensions = [("AKA-abc", "Contradicts prior route claim"), ("AKA-def", "Date mismatch")]
    prompt = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=_wm(),
        chronicle_hints=[],
        open_tensions=tensions,
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    assert len(data["open_tensions"]) == 2
    assert data["open_tensions"][0]["node_id"] == "AKA-abc"


def test_prompt_deterministic() -> None:
    """Same inputs must produce the same prompt string."""
    wm = _wm(step=2)
    hints = _hints()
    p1 = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=wm,
        chronicle_hints=hints,
        open_tensions=[("AKA-abc", "some tension")],
        synthesis_opportunity=True,
    )
    p2 = build_reading_step_prompt(
        paragraph=_PARAGRAPH,
        working_memory=wm,
        chronicle_hints=hints,
        open_tensions=[("AKA-abc", "some tension")],
        synthesis_opportunity=True,
    )
    assert p1 == p2


def test_prompt_empty_hints_and_tensions() -> None:
    prompt = build_reading_step_prompt(
        paragraph="Simple paragraph.",
        working_memory=WorkingMemoryState(step_index=0, concepts={}, pooled_embedding=[]),
        chronicle_hints=[],
        open_tensions=[],
        synthesis_opportunity=False,
    )
    data = json.loads(prompt)
    assert data["chronicle_hints"] == []
    assert data["open_tensions"] == []


# ---------------------------------------------------------------------------
# READING_STEP_OUTPUT_SCHEMA — validity
# ---------------------------------------------------------------------------


def test_output_schema_is_dict() -> None:
    assert isinstance(READING_STEP_OUTPUT_SCHEMA, dict)


def test_output_schema_has_required_top_level_keys() -> None:
    required = READING_STEP_OUTPUT_SCHEMA.get("required", [])
    for key in (
        "new_concepts",
        "new_edges",
        "chronicle_hits_used",
        "synthesis_event",
        "repair_events",
        "resolution_updates",
    ):
        assert key in required, f"'{key}' must be in schema required"


def test_output_schema_new_concepts_array() -> None:
    props = READING_STEP_OUTPUT_SCHEMA["properties"]
    assert props["new_concepts"]["type"] == "array"


def test_output_schema_synthesis_event_nullable() -> None:
    synthesis_type = READING_STEP_OUTPUT_SCHEMA["properties"]["synthesis_event"]["type"]
    assert "null" in synthesis_type


# ---------------------------------------------------------------------------
# READING_STEP_SYSTEM — content
# ---------------------------------------------------------------------------


def test_system_prompt_is_non_empty_string() -> None:
    assert isinstance(READING_STEP_SYSTEM, str)
    assert len(READING_STEP_SYSTEM) > 100


def test_system_prompt_mentions_codebook_relations() -> None:
    for rel in ("BINDS_TO", "REINFORCES", "CAUSED_BY", "CONTRADICTS"):
        assert rel in READING_STEP_SYSTEM, f"'{rel}' missing from system prompt"


def test_system_prompt_mentions_synthesis() -> None:
    assert "synthesis" in READING_STEP_SYSTEM.lower()
