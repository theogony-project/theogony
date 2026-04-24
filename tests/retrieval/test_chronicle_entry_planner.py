"""Unit tests for chronicle entry planning + merged multi-hop results."""

from __future__ import annotations

import pytest

from theogony.agents.llm import StubLLMProvider
from theogony.config.settings import ChronicleEntryPlannerSettings
from theogony.core.model import KnowledgeNode, NodeType, SourceRef
from theogony.core.store import ScoredNode
from theogony.retrieval.chronicle_entry_planner import (
    anchor_turn_for_subqueries,
    merge_multi_hop_results,
    normalize_sub_queries,
    plan_chronicle_entry_queries,
)
from theogony.retrieval.multi_hop import MultiHopResult


def _node(label: str, nid: str) -> KnowledgeNode:
    return KnowledgeNode(
        label=label,
        node_type=NodeType.CONCEPT,
        source_ref=SourceRef(source_type="test", identifier=nid, language="en"),
        embedding=[1.0, 0.0, 0.0, 0.0],
        embedding_dim=4,
        embedding_model_id="t@v1",
    )


def test_merge_multi_hop_results_keeps_best_score_per_node() -> None:
    a = _node("A", "AKA-a")
    b = _node("B", "AKA-b")
    r1 = MultiHopResult(
        scored_nodes=[
            ScoredNode(node=a, score=0.5),
            ScoredNode(node=b, score=0.4),
        ],
        seed_count=2,
        final_node_count=2,
        duration_ms=3,
    )
    r2 = MultiHopResult(
        scored_nodes=[
            ScoredNode(node=a, score=0.9),
        ],
        seed_count=1,
        final_node_count=1,
        duration_ms=5,
    )
    merged = merge_multi_hop_results([r1, r2], cap=10)
    assert merged.final_node_count == 2
    by_id = {s.node.id: s.score for s in merged.scored_nodes}
    assert by_id[a.id] == 0.9
    assert by_id[b.id] == 0.4
    assert merged.duration_ms == 8


def test_normalize_sub_queries_inserts_user_query_and_caps() -> None:
    limits = ChronicleEntryPlannerSettings(max_sub_queries=2, max_chars_per_sub_query=100)
    out = normalize_sub_queries(
        ["alpha", "beta", "gamma"],
        user_query="user q",
        limits=limits,
    )
    assert len(out) == 2
    assert out[0] == "user q"


def test_anchor_turn_extracts_current_question_from_blend() -> None:
    blend = (
        "User: Who is Daedalus?\n\nAssistant: A craftsman.\n\n"
        "---\nCurrent question:\nHow does he relate to Athene?"
    )
    assert anchor_turn_for_subqueries(blend, max_chars=240) == "How does he relate to Athene?"


def test_normalize_never_inserts_full_multi_turn_blend() -> None:
    blend = (
        "Rolling summary:\nDaedalus labyrinth wings\n\n"
        "---\nCurrent question:\nHow does he relate to Athene?"
    )
    limits = ChronicleEntryPlannerSettings(max_sub_queries=4, max_chars_per_sub_query=120)
    out = normalize_sub_queries(
        ["Daedalus Athena myth", "labyrinth craftsman"],
        user_query=blend,
        limits=limits,
    )
    assert all(len(s) <= 120 for s in out)
    assert "Rolling summary" not in "\n".join(out)
    assert "How does he relate to Athene?" in out
    assert "Daedalus Athena myth" in out


@pytest.mark.asyncio
async def test_plan_chronicle_entry_queries_skips_stub_llm() -> None:
    llm = StubLLMProvider(default="{}")
    limits = ChronicleEntryPlannerSettings(enabled=True)
    plan = await plan_chronicle_entry_queries(llm=llm, user_query="hello", limits=limits)
    assert plan.used_llm is False
    assert plan.search_queries == ["hello"]
