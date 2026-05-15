from __future__ import annotations

import asyncio
from pathlib import Path

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.importer import Wikidata5mSeedImporter
from theogony.reporting.writer import RunReportWriter


def test_wikidata5m_seed_never_stores_paragraph_bodies(
    mesh_runtime: MeshRuntime,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
) -> None:
    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=wikidata_fixture_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )

    asyncio.run(importer.run(max_entities=4, max_triplets=5))

    descriptions = [node.description for node in mesh_runtime.nodes.load_all_consolidated()]
    assert all(description is None or len(description) <= 100 for description in descriptions)
    assert not any(
        description and "was an English physician and scientist known for describing" in description
        for description in descriptions
    )
