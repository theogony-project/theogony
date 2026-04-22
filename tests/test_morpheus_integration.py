"""Integration gates for Morpheus + depth bands (PHX-0059 / W4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.config.settings import MorpheusSettings, Settings
from theogony.core.model import EdgeType, Layer
from theogony.docs_ingest import read_dump
from theogony.memory.depth_band_phase import DepthBandPhase
from theogony.memory.morpheus_phase import MorpheusPhase
from theogony.memory.tick_phase import TickContext
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


def _ctx(store: InMemoryKnowledgeStore, *, rid: str) -> TickContext:
    settings = Settings().model_copy(
        update={
            "morpheus": MorpheusSettings(
                candidate_isolation_max_edges=40,
            )
        }
    )
    return TickContext(
        started_at=datetime.now(UTC),
        perf_started=0.0,
        run_id=rid,
        cfg=settings.oneiros,
        store=store,
        app_settings=settings,
        writer=None,
    )


@pytest.mark.asyncio
async def test_pantheon_self_morpheus_run_proposes_plausible_edges() -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    store = InMemoryKnowledgeStore()
    for n in nodes:
        await store.upsert_node(n)
    for e in edges:
        await store.upsert_edge(e)

    # Bundled self-chronicle is entirely MNEME today; Morpheus only targets EPHEMERA.
    for n in nodes[:140]:
        await store.upsert_node(n.model_copy(update={"layer": Layer.EPHEMERA}))

    await MorpheusPhase().run(_ctx(store, rid="integration-morpheus"))

    node_ids = [n.id for n in nodes]
    all_edges = await store.get_edges_among(node_ids, min_weight=0.0)
    morpheus_edges = [
        e
        for e in all_edges
        if e.properties.get("proposed_by") == "morpheus" and e.epistemic_type == EdgeType.INFERENCE
    ]
    assert len(morpheus_edges) >= 5
    for e in morpheus_edges:
        assert e.confidence == pytest.approx(0.4)

    cross_identifier = False
    for e in morpheus_edges:
        src = await store.get_node(e.source_id)
        tgt = await store.get_node(e.target_id)
        if not src or not tgt:
            continue
        sid = src.source_ref.identifier or ""
        tid = tgt.source_ref.identifier or ""
        if sid and tid and sid != tid:
            cross_identifier = True
            break
    assert cross_identifier

    assert any(e.properties.get("signal") == "embedding" for e in morpheus_edges)
    assert any(e.properties.get("signal") == "cooccurrence" for e in morpheus_edges)


@pytest.mark.asyncio
async def test_depth_band_phase_stratifies_pantheon_self_seed() -> None:
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    store = InMemoryKnowledgeStore()
    for n in nodes:
        await store.upsert_node(n)
    for e in edges:
        await store.upsert_edge(e)

    node_ids = [n.id for n in nodes]

    for i, nid in enumerate(node_ids):
        n = await store.get_node(nid)
        assert n is not None
        conn = ((i * 3) % 7) / 12.0
        fresh = 0.25 + ((i * 5) % 6) * 0.12
        await store.upsert_node(
            n.model_copy(
                update={
                    "scores": n.scores.model_copy(
                        update={"connectivity": conn, "freshness": min(fresh, 1.0)}
                    )
                }
            )
        )

    for nid in node_ids[::17]:
        n = await store.get_node(nid)
        assert n is not None
        await store.upsert_node(
            n.model_copy(
                update={
                    "scores": n.scores.model_copy(
                        update={
                            "connectivity": 1.0,
                            "confidence": 0.95,
                            "relevance": 0.95,
                            "freshness": 1.0,
                        }
                    )
                }
            )
        )
    for nid in node_ids[7::29]:
        n = await store.get_node(nid)
        assert n is not None
        await store.upsert_node(
            n.model_copy(
                update={
                    "scores": n.scores.model_copy(
                        update={
                            "connectivity": 0.02,
                            "confidence": 0.12,
                            "relevance": 0.12,
                            "freshness": 0.15,
                        }
                    ),
                    "last_accessed": datetime.now(UTC) - timedelta(days=120),
                }
            )
        )

    await DepthBandPhase().run(_ctx(store, rid="integration-depth-bootstrap"))

    async def bands_map() -> dict[str, int]:
        out: dict[str, int] = {}
        for nid in node_ids:
            got = await store.get_node(nid)
            assert got is not None
            out[nid] = got.depth_band
        return out

    prev = await bands_map()
    for t in range(12):
        await DepthBandPhase().run(_ctx(store, rid=f"integration-depth-{t}"))
        nxt = await bands_map()
        for nid in node_ids:
            assert abs(nxt[nid] - prev[nid]) <= 1
        prev = nxt

    dist: dict[int, int] = {}
    for nid in node_ids:
        got = await store.get_node(nid)
        assert got is not None
        dist[got.depth_band] = dist.get(got.depth_band, 0) + 1
    assert len(dist) >= 3
