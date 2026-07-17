"""PHX-1051: generic high-similarity hubs must not absorb entities.

Measured live on the founding mesh: deity references (Venus, Dione, Zeus)
eager-merged into the semantically generic work-node ("An ancient Greek epic
poem …") on description-vector cosine alone, leaving genealogy self-loops on
the hub and no entity nodes. The guard: a description-signal merge requires
lexical corroboration — a shared tag or a known label — otherwise identity
stays emergent (doctrine: eager only on *clear* evidence).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode


def _runtime(tmp_path: Path) -> MeshRuntime:
    return MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)


def _generic_hub(description: str, vec: list[float], tags: list[str]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        consolidation_tier=1,
        semantic_vector=vec,
        frame_vector=[0.0] * 4,
        description=description,
        description_vector=vec,
        tags=tags,
    )


def _linker(rt: MeshRuntime) -> EagerLinker:
    return EagerLinker(rt.nodes, rt.edges, semantic_dim=8, frame_dim=4)


def test_high_cosine_without_lexical_overlap_stays_emergent(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    hub_vec = [1.0, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    hub = _generic_hub("An ancient epic poem about the gods.", hub_vec, ["poem", "epic"])
    rt.nodes.append_consolidated(hub)
    linker = _linker(rt)
    linker._registry.remember(hub, aliases=["epic poem"], qids=[])

    # Near-identical description vector (cosine ~0.999) but zero shared tags
    # and an unknown label: before the guard this merged into the hub.
    decision = linker.link_reference(
        label="Venus",
        description="Goddess of love, wounded in battle before Troy.",
        tags=["goddess", "venus"],
        qids=[],
        semantic_vector=[0.99, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        frame_vector=[0.0] * 4,
        description_vector=[0.99, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    assert decision.is_new, "generic hub absorbed the entity again (PHX-1051)"
    assert decision.signal == "emergent"


def test_shared_tag_still_allows_description_merge(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    vec = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    aphrodite = _generic_hub("Greek goddess of love, born of sea foam.", vec, ["aphrodite"])
    rt.nodes.append_consolidated(aphrodite)
    linker = _linker(rt)
    linker._registry.remember(aphrodite, aliases=["Aphrodite"], qids=[])

    decision = linker.link_reference(
        label="Aphrodite of Cyprus",
        description="The goddess of love who came ashore at Cyprus.",
        tags=["aphrodite", "cyprus"],
        qids=[],
        semantic_vector=[0.98, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        frame_vector=[0.0] * 4,
        description_vector=[0.98, 0.15, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    assert not decision.is_new, "shared tag is clear evidence — merge should hold"
    assert decision.signal == "description"


def test_known_label_still_allows_description_merge(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    vec = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    zeus = _generic_hub("Ruler of the Olympian gods.", vec, ["zeus"])
    rt.nodes.append_consolidated(zeus)
    linker = _linker(rt)
    linker._registry.remember(zeus, aliases=["Zeus", "Jove"], qids=[])

    decision = linker.link_reference(
        label="Jove",
        description="The king of the gods in the Roman naming.",
        tags=["jove-king"],
        qids=[],
        semantic_vector=[0.05, 0.99, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        frame_vector=[0.0] * 4,
        description_vector=[0.05, 0.99, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    assert not decision.is_new, "known alias is clear evidence — merge should hold"
