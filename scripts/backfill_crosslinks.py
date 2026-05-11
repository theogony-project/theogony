#!/usr/bin/env python3
"""Backfill crosslinks for articles that were crawled before the crosslinker fix."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure theogony is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main() -> None:
    from theogony.extraction.embedding import LocalSentenceTransformerEmbedder
    from theogony.kadmos.crosslink import ChronikCrosslinker

    readings_dir = Path("data/kadmos/readings")
    chronicle_dir = Path("data/kadmos/chronicle")

    embedder = LocalSentenceTransformerEmbedder()
    crosslinker = ChronikCrosslinker(db_path=str(chronicle_dir))

    session_ids = [
        "01KRAJX247P1WBGXQTG180CRXV",  # Bernoulli
        "01KRAN9EK2846NXJ3NKXN5B911",  # Ohm
        "01KRAP1DJWQTNW4N2CNBGWZZJZ",  # Entropy
        "01KRAQAZAZMFY1RQM5W0CTXTQ8",  # Thermodynamics
        "01KRAQZKP9ZBG6GHPH2TFFX23W",  # Fluid dynamics
    ]

    for sid in session_ids:
        ar_path = readings_dir / f"{sid}.json"
        if not ar_path.exists():
            print(f"[SKIP] {sid} — no reading found")
            continue

        print(f"[READ] {sid}")
        from theogony.kadmos.model import AnnotatedReading
        annotated = AnnotatedReading.model_validate_json(ar_path.read_text(encoding="utf-8"))

        crosslink_nodes = []
        for synth in annotated.final_syntheses:
            emb = await embedder.embed(synth.label + ": " + synth.description)
            emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))
            crosslink_nodes.append({
                "id": f"SYNTH-{synth.id[:20]}",
                "label": synth.label,
                "embedding": emb_vec,
                "node_type": "synthesis",
                "source_anchor": f"{annotated.source_url}#synthesis-{synth.synthesis_level}",
            })
        for concept in annotated.final_active_concepts:
            text = concept.label
            if concept.description:
                text += " " + concept.description
            emb = await embedder.embed(text)
            emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))
            crosslink_nodes.append({
                "id": f"CONC-{concept.id[:20]}",
                "label": concept.label,
                "embedding": emb_vec,
                "node_type": "concept",
                "source_anchor": f"{annotated.source_url}#step-{concept.step_created}",
            })

        result = crosslinker.ingest_and_link(
            embedder=embedder,
            new_nodes=crosslink_nodes,
            new_edges=[],
            source_domain="physics",
        )
        print(
            f"  nodes_written={result['nodes_written']} "
            f"crosslinks={result['crosslinks_created']} "
            f"chronicle now: nodes={crosslinker.node_count} edges={crosslinker.edge_count}"
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
