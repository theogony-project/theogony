"""PHX-1030: SeedConceptResolver keeps only QID → node_id (no vectors)."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.seeds.wikidata5m.seed_resolver import SeedConceptResolver


def _node(qid: str, *, dim: int = 8) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * dim,
        frame_vector=[0.0] * 4,
        description_vector=[0.2] * dim,
        description=qid,
        qids=[QIDTag(qid=qid, confidence=1.0, attached_at=now)],
    )


def test_seed_resolver_remember_and_lookup(mesh_runtime: MeshRuntime) -> None:
    node = _node("Q30")
    mesh_runtime.nodes.append_consolidated(node)
    resolver = SeedConceptResolver(mesh_runtime.nodes)

    assert resolver.has_qid("Q30") is True
    assert resolver.get_node_id("Q30") == str(node.id)
    assert resolver.get_ulid("Q30") == node.id
    assert resolver.known_qids() == {"Q30"}
    assert resolver.has_qid("Q999") is False


def test_seed_resolver_does_not_retain_vectors(mesh_runtime: MeshRuntime) -> None:
    node = _node("Q145")
    resolver = SeedConceptResolver(mesh_runtime.nodes)
    resolver.remember(node.qids[0].qid, node.id)

    assert resolver.cached_count() == 1
    # Only the string map is retained — no ConsolidatedNode in the resolver.
    assert not hasattr(resolver, "_nodes_by_id")
    assert "semantic_vector" not in vars(resolver)
    assert resolver.get_node_id("Q145") == str(node.id)
