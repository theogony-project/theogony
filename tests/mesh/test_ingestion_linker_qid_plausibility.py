"""A matching Q-ID must still bridge variant names, but not unrelated entities.

After the PHX-1051 naming guard closed the description and tag paths, the Q-ID
path was the strongest remaining identity-corruption vector: an LLM-asserted
identifier merged with score 1.0 and no corroboration at all, and
``merge_identity_evidence`` then wrote it back to the store, making the mistake
durable.

The fix must be dosed carefully. Requiring naming corroboration here — as the
other two signals do — would destroy the thing the Q-ID path exists for: bridging
entities whose *names* differ (Venus/Aphrodite, Jove/Zeus, cross-language
variants). So this is a plausibility floor, not a name check.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ulid import ULID

from theogony.mesh.ingestion.linker import EagerLinker
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, QIDTag

DIM = 8


def _vec(*values: float) -> list[float]:
    padded = list(values) + [0.0] * (DIM - len(values))
    return padded[:DIM]


def _linker(runtime: MeshRuntime) -> EagerLinker:
    return EagerLinker(runtime.nodes, runtime.edges, semantic_dim=DIM, frame_dim=4)


def _aphrodite(runtime: MeshRuntime, vector: list[float]) -> ConsolidatedNode:
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=vector,
        frame_vector=[0.0] * 4,
        description="Greek goddess of love, born from sea foam.",
        description_vector=vector,
        tags=["goddess", "olympian"],
        qids=[QIDTag(qid="Q35500", confidence=1.0, attached_at=now)],
    )
    runtime.nodes.append_consolidated(node)
    return node


@pytest.fixture
def runtime(mesh_runtime: MeshRuntime) -> MeshRuntime:
    return mesh_runtime


def test_qid_still_bridges_a_variant_name(runtime: MeshRuntime) -> None:
    """The Roman name must still merge into the Greek node — this is the point."""
    target = _aphrodite(runtime, _vec(1.0, 0.0, 0.0))
    linker = _linker(runtime)
    now = datetime.now(UTC)

    decision = linker.link_reference(
        label="Venus",  # different name, same deity
        description="Roman goddess of love, risen from the sea.",
        tags=["goddess"],
        qids=[QIDTag(qid="Q35500", confidence=1.0, attached_at=now)],
        semantic_vector=_vec(0.95, 0.1, 0.0),
        frame_vector=[0.0] * 4,
        description_vector=_vec(0.95, 0.1, 0.0),
    )

    assert decision.signal == "qid"
    assert decision.is_new is False
    assert str(decision.node.id) == str(target.id)


def test_hallucinated_qid_on_an_unrelated_entity_does_not_merge(runtime: MeshRuntime) -> None:
    """A Q-ID that lands somewhere semantically unrelated is not identity evidence."""
    target = _aphrodite(runtime, _vec(1.0, 0.0, 0.0))
    linker = _linker(runtime)
    now = datetime.now(UTC)

    decision = linker.link_reference(
        label="Bronze cauldron",  # nothing to do with the goddess
        description="A metal vessel used for boiling water at funeral games.",
        tags=["object"],
        qids=[QIDTag(qid="Q35500", confidence=1.0, attached_at=now)],  # hallucinated
        semantic_vector=_vec(0.0, 0.0, 1.0),  # orthogonal to the target
        frame_vector=[0.0] * 4,
        description_vector=_vec(0.0, 0.0, 1.0),
    )

    assert decision.signal == "emergent"
    assert decision.is_new is True
    assert str(decision.node.id) != str(target.id)


def test_a_rejected_qid_does_not_contaminate_the_target_node(runtime: MeshRuntime) -> None:
    """The rejected merge must leave no trace — the corruption was durable before."""
    target = _aphrodite(runtime, _vec(1.0, 0.0, 0.0))
    linker = _linker(runtime)
    now = datetime.now(UTC)

    linker.link_reference(
        label="Bronze cauldron",
        description="A metal vessel used for boiling water.",
        tags=["object"],
        qids=[
            QIDTag(qid="Q35500", confidence=1.0, attached_at=now),
            QIDTag(qid="Q999999", confidence=1.0, attached_at=now),  # would be written back
        ],
        semantic_vector=_vec(0.0, 0.0, 1.0),
        frame_vector=[0.0] * 4,
        description_vector=_vec(0.0, 0.0, 1.0),
    )

    reloaded = runtime.nodes.get_consolidated(str(target.id))
    assert reloaded is not None
    assert {q.qid for q in reloaded.qids} == {"Q35500"}  # the stray Q-ID was not attached


def test_missing_vectors_keep_the_qid_path_open(runtime: MeshRuntime) -> None:
    """Callers with nothing to compare must not lose the Q-ID signal."""
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.0] * DIM,  # bulk-seeded shape: no usable vectors
        frame_vector=[0.0] * 4,
        description="Seeded entity",
        qids=[QIDTag(qid="Q4242", confidence=1.0, attached_at=now)],
    )
    runtime.nodes.append_consolidated(node)

    decision = _linker(runtime).link_reference(
        label="Seeded entity",
        description="Seeded entity",
        tags=[],
        qids=[QIDTag(qid="Q4242", confidence=1.0, attached_at=now)],
        semantic_vector=[0.0] * DIM,
        frame_vector=[0.0] * 4,
        description_vector=None,
    )

    assert decision.signal == "qid"
    assert str(decision.node.id) == str(node.id)
