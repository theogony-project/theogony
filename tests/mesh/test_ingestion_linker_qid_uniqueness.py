"""Q-ID uniqueness — same Q-ID creates one Tier-1 node, second link attaches."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.ingestion.concept_resolver import ConceptResolver
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag


def test_same_label_resolves_to_same_id(mesh_runtime: MeshRuntime) -> None:
    """Label-based dedup: same label plus tag overlap → same node."""
    now = datetime.now(UTC)
    existing = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=[0.1] * mesh_runtime.semantic_dim,
        frame_vector=[0.1] * mesh_runtime.frame_dim,
        description="Thomas Addison",
        tags=["physician"],
        qids=[QIDTag(qid="Q336997", confidence=0.95, attached_at=now)],
    )
    mesh_runtime.nodes.append_consolidated(existing)

    resolver = ConceptResolver(
        mesh_runtime.nodes,
        semantic_dim=mesh_runtime.semantic_dim,
        frame_dim=mesh_runtime.frame_dim,
    )

    # Same label → hit directly
    nid1 = resolver.resolve("Thomas Addison", tags=["physician"])
    nid2 = resolver.resolve("Thomas Addison", tags=["physician"])
    assert nid1 == nid2

    # Variant label → token overlap match (Addison)
    nid3 = resolver.resolve("Addison", tags=["physician"])
    assert nid3 == nid1, "Addison should match Thomas Addison via token overlap"

    # Very different label → new node
    nid4 = resolver.resolve("Sven Hedin", tags=["explorer"])
    assert nid4 != nid1
