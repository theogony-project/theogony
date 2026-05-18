from __future__ import annotations

import asyncio
import json
from pathlib import Path

from theogony.agents.llm import StubLLMProvider
from theogony.mesh.ingestion.kadmos_v2 import MeshParagraphReader
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.importer import Wikidata5mSeedImporter
from theogony.reporting.models import IngestRunReport
from theogony.reporting.writer import RunReportWriter


def test_wikidata5m_smoke2_handoff_fixture_mentions_dense_slice_qids(
    wikidata_fixture_root: Path,
) -> None:
    handoff = (wikidata_fixture_root / "paragraph_smoke2_handoff.txt").read_text(encoding="utf-8")
    assert "Q30" in handoff
    assert "Q1860" in handoff


def test_wikidata5m_smoke2_seed_hands_off_qid_matches_to_eager_linker(
    mesh_runtime: MeshRuntime,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
    tmp_path: Path,
) -> None:
    handoff_fixture = wikidata_fixture_root / "paragraph_smoke2_handoff.txt"
    handoff_text = handoff_fixture.read_text(encoding="utf-8").strip()

    seed_root = tmp_path / "wikidata5m_smoke2_handoff"
    seed_root.mkdir()
    (seed_root / "wikidata5m_entity.txt").write_text(
        "\n".join(
            [
                "Q30\tUnited States of America\tUnited States\tUSA",
                "Q1860\tEnglish language\tEnglish",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (seed_root / "wikidata5m_text.txt").write_text(
        "\n".join(
            [
                "Q30\tCountry in North America comprising 50 states.",
                "Q1860\tWest Germanic language.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (seed_root / "wikidata5m_relation.txt").write_text("", encoding="utf-8")
    (seed_root / "wikidata5m_all_triplet.txt").write_text("Q30\tP31\tQ1860\n", encoding="utf-8")

    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=seed_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )
    asyncio.run(importer.run(max_entities=2, max_triplets=1))

    llm = StubLLMProvider(
        responses={
            f"PARAGRAPH:\n{handoff_text}": json.dumps(
                {
                    "concepts": [
                        {
                            "label": "United States",
                            "entity_type": "place",
                            "tags": ["country"],
                            "description": "Country in North America comprising 50 states",
                            "qids": [{"qid": "Q30", "confidence": 0.99}],
                        },
                        {
                            "label": "English",
                            "entity_type": "concept",
                            "tags": ["language"],
                            "description": "West Germanic language",
                            "qids": [{"qid": "Q1860", "confidence": 0.95}],
                        },
                    ],
                    "relations": [],
                    "paragraph_concept": None,
                }
            )
        }
    )
    reader = MeshParagraphReader(mesh_runtime, llm=llm, max_paragraphs=10)
    result = asyncio.run(
        reader.read_text(
            text=handoff_text,
            source_type="test",
            source_identifier=str(handoff_fixture),
            title="Smoke-2 handoff",
            anchor="fixture://paragraph-smoke2-handoff",
        )
    )

    report = IngestRunReport.model_validate_json(Path(result["report_path"]).read_text("utf-8"))
    q30_nodes = [
        node
        for node in mesh_runtime.nodes.load_all_consolidated()
        if any(qid.qid == "Q30" for qid in node.qids)
    ]

    assert report.resolution.tier_counts.get(4) == 2
    assert len(q30_nodes) == 1
