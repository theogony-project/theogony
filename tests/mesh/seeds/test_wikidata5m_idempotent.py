from __future__ import annotations

import asyncio
from pathlib import Path

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.importer import Wikidata5mSeedImporter
from theogony.reporting.writer import RunReportWriter


def _build_importer(
    mesh_runtime: MeshRuntime,
    *,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
) -> Wikidata5mSeedImporter:
    return Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=wikidata_fixture_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )


def test_wikidata5m_seed_is_idempotent(
    mesh_runtime: MeshRuntime,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
) -> None:
    first = asyncio.run(
        _build_importer(
            mesh_runtime,
            wikidata_fixture_root=wikidata_fixture_root,
            seed_embedder=seed_embedder,
            seed_report_writer=seed_report_writer,
        ).run(max_entities=4, max_triplets=5)
    )
    second = asyncio.run(
        _build_importer(
            mesh_runtime,
            wikidata_fixture_root=wikidata_fixture_root,
            seed_embedder=seed_embedder,
            seed_report_writer=seed_report_writer,
        ).run(max_entities=4, max_triplets=5)
    )

    assert first["entities_upserted"] == 4
    assert second["entities_upserted"] == 0
    assert second["entities_skipped_duplicate_qid"] == 4
    assert second["edges_upserted"] == 0
    assert int(second["edges_skipped_duplicate"]) >= 3
