"""
Tests for Mini-Monkey-3 emergent-knowledge evaluator.
"""

from __future__ import annotations

from pathlib import Path

from theogony.agents.mnlm.monkey3 import MiniMonkey3


def test_monkey3_has_10_pairs() -> None:
    m3 = MiniMonkey3()
    assert len(m3.pairs()) == 10


def test_monkey3_rating_sheet_generated(tmp_path: Path) -> None:
    m3 = MiniMonkey3()
    path = tmp_path / "rating_sheet.md"
    m3.generate_rating_sheet(output_path=str(path))
    assert path.exists()
    content = path.read_text()
    assert "Bernoulli" in content
    assert "Ohm" in content
    assert "Rater 1" in content


def test_monkey3_record_ratings() -> None:
    m3 = MiniMonkey3()
    for pid in range(1, 11):
        m3.record_rating(pid, "rater_a", score=pid % 4, notes=f"Pair {pid}")
        m3.record_rating(pid, "rater_b", score=(pid + 1) % 4, notes="")
    summary = m3.compute_summary()
    assert summary["num_pairs"] == 10
    assert summary["num_raters"] == 2
    assert 0 <= summary["overall_mean_score"] <= 3


def test_monkey3_summary_output(tmp_path: Path) -> None:
    m3 = MiniMonkey3()
    for pid in range(1, 11):
        m3.record_rating(pid, "alice", score=2, notes="ok")
        m3.record_rating(pid, "bob", score=3, notes="good")
    path = tmp_path / "mini_monkey3_results.md"
    summary = m3.compute_summary(output_path=str(path))
    assert path.exists()
    assert summary["overall_mean_score"] == 2.5  # (2+3)/2
    assert summary["agreement_within_1"] == 1.0  # all within 1


def test_monkey3_likert_labels() -> None:
    from theogony.agents.mnlm.monkey3 import LIKERT_LABELS

    assert LIKERT_LABELS[0].startswith("No correspondence")
    assert LIKERT_LABELS[3].startswith("Strong correspondence")
