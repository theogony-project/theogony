"""Read-only contract: Mnemosyne only appends self_referential_in_runs (PHX-0071 / W5)."""

from __future__ import annotations

import pytest

from theogony.config.settings import LLMSettings, Settings
from theogony.reporting.models import MetaClassificationVerdict
from theogony.core.model import KnowledgeEdge, KnowledgeNode, Layer
from theogony.docs_ingest import read_dump
from theogony.retrieval.pipeline import build_pipeline_from_settings
from theogony.seeds import pantheon_self_dump_path
from theogony.stores.memory import InMemoryKnowledgeStore


async def _all_nodes(store: InMemoryKnowledgeStore) -> list[KnowledgeNode]:
    out: list[KnowledgeNode] = []
    for layer in (Layer.EPHEMERA, Layer.MNEME):
        async for n in store.export_layer(layer):
            out.append(n)
    out.sort(key=lambda n: n.id)
    return out


def _node_core_dump(nodes: list[KnowledgeNode]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for n in nodes:
        d = n.model_dump(mode="python")
        props = dict(d.get("properties") or {})
        props.pop("self_referential_in_runs", None)
        d["properties"] = props
        rows.append(d)
    return rows


def _edge_dump(store: InMemoryKnowledgeStore) -> list[dict[str, object]]:
    edges = sorted(store._edges.values(), key=lambda e: e.id)
    return [e.model_dump(mode="python") for e in edges]


@pytest.mark.asyncio
async def test_mnemosyne_only_mutates_allowlisted_property() -> None:
    settings = Settings(llm=LLMSettings(provider="stub"))
    store = InMemoryKnowledgeStore()
    _, nodes, edges = read_dump(pantheon_self_dump_path())
    await store.batch_upsert_nodes([n for n in nodes if isinstance(n, KnowledgeNode)])
    await store.batch_upsert_edges([e for e in edges if isinstance(e, KnowledgeEdge)])

    before_nodes = await _all_nodes(store)
    before_sr: dict[str, tuple[str, ...]] = {
        n.id: tuple(n.properties.get("self_referential_in_runs") or ())
        for n in before_nodes
    }
    before_core = _node_core_dump(before_nodes)
    before_edges = _edge_dump(store)

    pipeline = await build_pipeline_from_settings(settings, store)
    sr = await pipeline.ask(
        "How does the OneirosWorker promote nodes between depth bands?",
        k=10,
        hops=2,
        pheromone_mode="ignore",
    )
    assert sr.report.meta_classification is not None
    assert sr.report.meta_classification.verdict == MetaClassificationVerdict.SELF_REFERENTIAL
    assert sr.answer.cited_node_ids

    after_nodes = await _all_nodes(store)
    after_core = _node_core_dump(after_nodes)
    after_edges = _edge_dump(store)

    assert len(after_nodes) == len(before_nodes)
    assert after_core == before_core
    assert after_edges == before_edges

    after_map = {n.id: n for n in after_nodes}
    assert set(before_sr.keys()) == after_map.keys()
    sr_delta = 0
    for nid, br in before_sr.items():
        ar = tuple(after_map[nid].properties.get("self_referential_in_runs") or ())
        sr_delta += len(ar) - len(br)
    assert sr_delta == len(set(sr.answer.cited_node_ids))
    run_id = sr.report.run_id
    for cid in sr.answer.cited_node_ids:
        node = next(n for n in after_nodes if n.id == cid)
        assert run_id in (node.properties.get("self_referential_in_runs") or ())
