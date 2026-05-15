from __future__ import annotations

from pathlib import Path

from theogony.mesh.seeds.wikidata5m.loader import (
    iter_entity_records,
    iter_entity_text_pairs,
    iter_relation_records,
    iter_text_records,
    iter_triplet_records,
    iter_triplet_records_for_qids,
)


def test_wikidata5m_loader_parses_fixture_rows(wikidata_fixture_root: Path) -> None:
    entities = list(iter_entity_records(wikidata_fixture_root / "entities_50.txt"))
    texts = list(iter_text_records(wikidata_fixture_root / "text_50.txt"))
    relations = list(iter_relation_records(wikidata_fixture_root / "relations_5.txt"))
    triplets = list(iter_triplet_records(wikidata_fixture_root / "triplets_10.txt"))
    pairs = list(
        iter_entity_text_pairs(
            wikidata_fixture_root / "entities_50.txt",
            wikidata_fixture_root / "text_50.txt",
        )
    )

    assert len(entities) == 6
    assert entities[0].qid == "Q336997"
    assert entities[0].aliases[0] == "Thomas Addison"
    assert texts[0].qid == "Q336997"
    assert "English physician" in texts[0].description_text
    assert relations[0].pid == "P31"
    assert relations[0].aliases[0] == "instance of"
    assert triplets[0].subject_qid == "Q336997"
    assert triplets[0].predicate_pid == "P31"
    assert triplets[0].object_qid == "Q1289672"
    assert len(pairs) == 6
    assert pairs[0][0].qid == pairs[0][1].qid == "Q336997"


def test_wikidata5m_loader_reports_malformed_lines(tmp_path: Path) -> None:
    malformed = tmp_path / "entities_bad.txt"
    malformed.write_text("Q336997\tThomas Addison\nbad-line\nQ1289672\t\n", encoding="utf-8")

    seen: list[tuple[str, int, str, str]] = []
    rows = list(
        iter_entity_records(
            malformed,
            on_malformed=lambda file_name, line_number, reason, raw_line: seen.append(
                (file_name, line_number, reason, raw_line)
            ),
        )
    )

    assert [row.qid for row in rows] == ["Q336997"]
    assert len(seen) == 2
    assert any("missing Q-ID" in item[2] for item in seen)
    assert any("missing aliases" in item[2] for item in seen)


def test_wikidata5m_loader_filters_triplets_to_seeded_qids(tmp_path: Path) -> None:
    triplets = tmp_path / "triplets.txt"
    triplets.write_text(
        "\n".join(
            [
                "Q1\tP31\tQ2",
                "Q9\tP31\tQ2",
                "Q2\tP31\tQ3",
                "Q4\tP31\tQ5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = list(
        iter_triplet_records_for_qids(
            triplets,
            {"Q1", "Q2", "Q3"},
            max_triplets=2,
        )
    )

    assert [(row.subject_qid, row.object_qid) for row in rows] == [
        ("Q1", "Q2"),
        ("Q2", "Q3"),
    ]
