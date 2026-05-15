from __future__ import annotations

from pathlib import Path

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.importer import Wikidata5mSeedImporter
from theogony.reporting.models import MeshSeedRunReport
from theogony.reporting.writer import RunReportWriter


async def _run_import(
    mesh_runtime: MeshRuntime,
    *,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
    max_entities: int = 4,
    max_triplets: int = 5,
) -> dict[str, object]:
    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=wikidata_fixture_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )
    return await importer.run(max_entities=max_entities, max_triplets=max_triplets)


def test_wikidata5m_importer_writes_nodes_edges_audit_and_report(
    mesh_runtime: MeshRuntime,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
) -> None:
    import asyncio

    result = asyncio.run(
        _run_import(
            mesh_runtime,
            wikidata_fixture_root=wikidata_fixture_root,
            seed_embedder=seed_embedder,
            seed_report_writer=seed_report_writer,
        )
    )

    nodes = mesh_runtime.nodes.load_all_consolidated()
    qid_sets = [tuple(qid.qid for qid in node.qids) for node in nodes]
    report = MeshSeedRunReport.model_validate_json(
        Path(result["report_path"]).read_text(encoding="utf-8")
    )

    assert result["entities_streamed"] == 4
    assert result["entities_upserted"] == 4
    assert result["entities_missing_text"] == 0
    assert result["edges_streamed"] == 4
    assert result["edges_upserted"] == 4
    assert result["edges_skipped_missing_endpoint"] == 0
    assert len(nodes) == 4
    assert len({qid for qids in qid_sets for qid in qids}) == 4
    assert mesh_runtime.audit.count() >= report.entities_upserted + report.edges_upserted + 1
    assert report.embedding_model_id == "dummy-seed-embedder"
    assert report.entities_missing_text == 0


def test_wikidata5m_importer_bounded_lookup_reaches_requested_matches(
    mesh_runtime: MeshRuntime,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
    tmp_path: Path,
) -> None:
    import asyncio

    fixture_root = tmp_path / "wikidata5m_sparse"
    fixture_root.mkdir()
    (fixture_root / "wikidata5m_entity.txt").write_text(
        "\n".join(
            [
                "Q1\tAlpha",
                "Q2\tBeta",
                "Q3\tGamma",
                "Q4\tDelta",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (fixture_root / "wikidata5m_text.txt").write_text(
        "\n".join(
            [
                "Q3\tGamma description",
                "Q1\tAlpha description",
                "Q4\tDelta description",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (fixture_root / "wikidata5m_relation.txt").write_text("", encoding="utf-8")
    (fixture_root / "wikidata5m_all_triplet.txt").write_text("", encoding="utf-8")

    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=fixture_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )
    result = asyncio.run(importer.run(max_entities=3, max_triplets=1))
    report = MeshSeedRunReport.model_validate_json(
        Path(result["report_path"]).read_text(encoding="utf-8")
    )

    imported_qids = sorted(
        qid.qid for node in mesh_runtime.nodes.load_all_consolidated() for qid in node.qids
    )

    assert result["entities_streamed"] == 3
    assert result["entities_upserted"] == 3
    assert result["entities_missing_text"] == 1
    assert result["loader_malformed_lines"] == 0
    assert imported_qids == ["Q1", "Q3", "Q4"]
    assert report.entities_streamed == 3
    assert report.entities_upserted == 3
    assert report.entities_missing_text == 1
    assert report.loader_malformed_lines == 0
    assert "entities_missing_text" in report.anomalies


def test_wikidata5m_importer_collects_relevant_triplets_not_first_rows(
    mesh_runtime: MeshRuntime,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
    tmp_path: Path,
) -> None:
    import asyncio

    fixture_root = tmp_path / "wikidata5m_triplets"
    fixture_root.mkdir()
    (fixture_root / "wikidata5m_entity.txt").write_text(
        "\n".join(
            [
                "Q1\tAlpha",
                "Q2\tBeta",
                "Q3\tGamma",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (fixture_root / "wikidata5m_text.txt").write_text(
        "\n".join(
            [
                "Q1\tAlpha description",
                "Q2\tBeta description",
                "Q3\tGamma description",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (fixture_root / "wikidata5m_relation.txt").write_text(
        "P31\tinstance of\n",
        encoding="utf-8",
    )
    (fixture_root / "wikidata5m_all_triplet.txt").write_text(
        "\n".join(
            [
                "Q9\tP31\tQ10",
                "Q1\tP31\tQ2",
                "Q8\tP31\tQ7",
                "Q2\tP31\tQ3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=fixture_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )
    result = asyncio.run(importer.run(max_entities=3, max_triplets=2))

    assert result["entities_upserted"] == 3
    assert result["edges_streamed"] == 2
    assert result["edges_upserted"] == 2
    assert result["edges_skipped_missing_endpoint"] == 0
