"""PHX-1127: a finished answer run, read by the dataset's question type.

The figures of `docs/etappes/question_types.md` come out of run files written
before their rows carried a type, joined to the dataset file by question id.
What a test can hold is that join, and that a run it cannot type is refused
rather than reported with a row missing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "mesh_qa_by_type.py"
_spec = importlib.util.spec_from_file_location("mesh_qa_by_type", _SCRIPT)
assert _spec is not None and _spec.loader is not None
by_type = importlib.util.module_from_spec(_spec)
sys.modules["mesh_qa_by_type"] = by_type
_spec.loader.exec_module(by_type)

_TYPES = {"c1": "compositional", "c2": "inference", "m1": "comparison", "m2": "bridge_comparison"}


def _run(rows: list[tuple[str, str, float]], *, typed: bool = False) -> dict:
    return {
        "model": "stub/stub-llm",
        "mesh": "data/mesh-test",
        "dataset": "2wikimultihopqa",
        "answers": [
            {
                "qid": qid,
                "arm": arm,
                "question": "?",
                "gold": "x",
                "answer": "x" if em else "",
                "em": em,
                "f1": em,
                "gold_in_context": bool(em),
                **({"question_type": _TYPES[qid]} if typed else {}),
            }
            for qid, arm, em in rows
        ],
    }


_ROWS = [
    ("c1", "constellation_typed", 1.0),
    ("c1", "passages", 0.0),
    ("c2", "constellation_typed", 1.0),
    ("c2", "passages", 0.0),
    ("m1", "constellation_typed", 0.0),
    ("m1", "passages", 1.0),
    ("m2", "constellation_typed", 1.0),
    ("m2", "passages", 1.0),
]


def _release(cache_dir: Path) -> None:
    rows = [{"_id": qid, "type": qtype, "question": "?"} for qid, qtype in _TYPES.items()]
    (cache_dir / "2wikimultihopqa.json").write_text(json.dumps(rows), encoding="utf-8")


def test_an_older_run_takes_its_types_from_the_dataset_file(tmp_path) -> None:
    _release(tmp_path)
    read = by_type.read_run(_run(_ROWS), tmp_path, by_type.QA_PAIRS)
    assert read["arms"] == ["constellation_typed", "passages"]
    table = read["by_type"]
    assert set(table) == set(_TYPES.values()) | {"answer_unnamed", "answer_named"}
    assert table["answer_unnamed"]["constellation_typed"]["exact_match"] == 1.0
    assert table["answer_unnamed"]["passages"]["exact_match"] == 0.0
    assert table["answer_named"]["passages"]["exact_match"] == 1.0
    # only the pairs both of whose arms the run has
    assert list(read["paired_by_type"]) == ["constellation_typed_vs_passages"]
    pair = read["paired_by_type"]["constellation_typed_vs_passages"]
    assert (pair["answer_unnamed"]["em_better"], pair["answer_unnamed"]["em_worse"]) == (2.0, 0.0)
    assert (pair["answer_named"]["em_better"], pair["answer_named"]["em_worse"]) == (0.0, 1.0)
    # each pool once more: by which arm found the answer, and by the gold's shape
    in_pool = read["paired_in_pool"]["constellation_typed_vs_passages"]
    assert in_pool["answer_unnamed"]["by_found"]["arm_only"]["em_better"] == 2.0
    assert in_pool["answer_named"]["by_found"]["both"]["questions"] == 1.0
    assert in_pool["answer_named"]["by_kind"]["entity"]["em_worse"] == 1.0


def test_a_run_whose_rows_carry_the_type_needs_no_dataset_file(tmp_path) -> None:
    read = by_type.read_run(_run(_ROWS, typed=True), tmp_path, by_type.QA_PAIRS)
    assert read["by_type"]["answer_unnamed"]["constellation_typed"]["questions"] == 2.0


def test_a_run_that_cannot_be_typed_is_refused(tmp_path) -> None:
    with pytest.raises(SystemExit, match="have no question type"):
        by_type.read_run(_run(_ROWS), tmp_path, by_type.QA_PAIRS)


def test_the_script_prints_the_tables_and_writes_them(tmp_path, monkeypatch, capsys) -> None:
    _release(tmp_path)
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(_run(_ROWS)), encoding="utf-8")
    out_path = tmp_path / "out" / "by_type.json"
    argv = [
        "mesh_qa_by_type.py",
        str(run_path),
        "--cache-dir",
        str(tmp_path),
        "--pairs",
        "constellation_typed:passages",
        "--json",
        str(out_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    by_type.main()
    printed = capsys.readouterr().out
    assert "constellation_typed_vs_passages" in printed
    assert "answer_unnamed, by where the answer stood: arm_only 2/0" in printed
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written[str(run_path)]["by_type"]["answer_named"]["passages"]["questions"] == 2.0

    monkeypatch.setattr(sys, "argv", [*argv[:4], "--pairs", "constellation_typed"])
    with pytest.raises(SystemExit, match="arm:baseline"):
        by_type.main()
