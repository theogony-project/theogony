"""PHX-1123: every measurement and recording builds the provider its settings name.

The project's default provider falls back to another model when a call fails.
In a measurement that answers under the wrong name: four answer runs handed
10,732 failed deepseek-chat calls to claude-sonnet-4-6 while their files named
deepseek-chat. These scripts must build their provider with `build_named_llm`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MEASUREMENTS = (
    "scripts/mesh_qa_constellation.py",
    "scripts/mesh_qa_answers.py",
    "scripts/mesh_corpus_answers.py",
    "scripts/mesh_mention_audit.py",
    "scripts/mesh_qa_kadmos.py",
    "scripts/record_demo_readings.py",
)


@pytest.mark.parametrize("path", MEASUREMENTS)
def test_a_measurement_builds_its_provider_without_the_fallback(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "build_named_llm(settings)" in text, path
    assert "build_llm_from_settings(" not in text, f"{path} would fall back to another model"


@pytest.mark.parametrize("path", ("scripts/mesh_qa_constellation.py", "scripts/mesh_qa_answers.py"))
def test_an_answer_harness_writes_who_answered(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert '"answered_by":' in text and '"model": r.model' in text, path
