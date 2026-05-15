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


def test_wikidata5m_seed_hands_off_qid_matches_to_eager_linker(
    mesh_runtime: MeshRuntime,
    wikidata_fixture_root: Path,
    seed_embedder: object,
    seed_report_writer: RunReportWriter,
    tmp_path: Path,
) -> None:
    """Fixture QID must lie in the Smoke-1 slice; regenerate via _build_handoff_fixture.py."""
    handoff_fixture = wikidata_fixture_root / "paragraph_smoke1_handoff.txt"
    handoff_text = handoff_fixture.read_text(encoding="utf-8").strip()
    seeded_description = handoff_text.removeprefix("Renan Barao (Q947890) ").strip()

    seed_root = tmp_path / "wikidata5m_handoff"
    seed_root.mkdir()
    (seed_root / "wikidata5m_entity.txt").write_text(
        "Q947890\tRenan Barao\trenan barão\tRenan Pegado\n",
        encoding="utf-8",
    )
    (seed_root / "wikidata5m_text.txt").write_text(
        f"Q947890\t{seeded_description}\n",
        encoding="utf-8",
    )
    (seed_root / "wikidata5m_relation.txt").write_text("", encoding="utf-8")
    (seed_root / "wikidata5m_all_triplet.txt").write_text("", encoding="utf-8")

    importer = Wikidata5mSeedImporter(
        mesh_runtime,
        data_root=seed_root,
        embedder=seed_embedder,  # type: ignore[arg-type]
        embedder_requested="dummy",
        batch_size=2,
        report_writer=seed_report_writer,
    )
    asyncio.run(importer.run(max_entities=1, max_triplets=0))

    llm = StubLLMProvider(
        responses={
            f"PARAGRAPH:\n{handoff_text}": json.dumps(
                {
                    "concepts": [
                        {
                            "label": "Renan Barao",
                            "entity_type": "person",
                            "tags": ["fighter", "martial artist"],
                            "description": (
                                "Brazilian professional mixed martial artist and former UFC "
                                "Bantamweight Champion"
                            ),
                            "qids": [{"qid": "Q947890", "confidence": 0.99}],
                        }
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
            title="Smoke-1 handoff",
            anchor="fixture://paragraph-smoke1-handoff",
        )
    )

    report = IngestRunReport.model_validate_json(Path(result["report_path"]).read_text("utf-8"))
    qid_nodes = [
        node
        for node in mesh_runtime.nodes.load_all_consolidated()
        if any(qid.qid == "Q947890" for qid in node.qids)
    ]

    assert report.resolution.tier_counts.get(4) == 1
    assert len(qid_nodes) == 1
