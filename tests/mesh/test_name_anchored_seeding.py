"""Retrieval seeds on the entities a question names, not only on what it resembles.

Vector search finds nodes that look like the *question*. The answer to a question
usually does not look like it: "What children did Themis bear to Zeus?" is
answered by Eunomia, Dike and Eirene, which rank 2345, 2578 and 2764 by cosine
because they share nothing with the words of the question — they are related to
something *in* it.

Measured on the founding gold set, every expected entity sits exactly one hop
from an entity the question names, against a 6.6% chance baseline. Looking those
up by name in the index the substrate already maintains took recall from 48% to
65%, and questions answered in full from 13 of 32 to 18 (PHX-1068).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.retrieval.retrieve import _name_anchor_seeds
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge


def _node(runtime: MeshRuntime, description: str, tags: list[str], *, anchor: bool = False) -> str:
    now = datetime.now(UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * runtime.semantic_dim,
        frame_vector=[0.0] * runtime.frame_dim,
        description=description,
        description_vector=[0.1] * runtime.semantic_dim,
        tags=tags,
        is_source_anchor=anchor,
    )
    runtime.nodes.append_consolidated(node)
    return str(node.id)


def _csr(runtime: MeshRuntime, ids: list[str]):
    now = datetime.now(UTC)
    runtime.edges.append_edges(
        [
            Edge(
                source_id=ids[i],
                target_id=ids[i + 1],
                weight=1.0,
                born_at=now,
                last_fired_at=now,
                relation_kind="semantic",
                relation_descriptor="next",
                creation_context="test",
            )
            for i in range(len(ids) - 1)
        ]
    )
    runtime.invalidate_csr_cache()
    return runtime.rebuild_csr()


def test_an_entity_named_in_the_question_becomes_a_seed(mesh_runtime: MeshRuntime) -> None:
    zeus = _node(mesh_runtime, "Zeus — King of the gods", ["Zeus"])
    other = _node(mesh_runtime, "Eunomia — Order", ["Eunomia"])
    csr = _csr(mesh_runtime, [zeus, other])

    seeds = _name_anchor_seeds(mesh_runtime, "What did Zeus decree?", csr)

    assert csr.id_to_index[zeus] in seeds
    assert seeds[csr.id_to_index[zeus]] == 1.0, "an exact name match beats any cosine"


def test_question_words_are_not_looked_up_as_names(mesh_runtime: MeshRuntime) -> None:
    """ "Who" and "What" are capitalised because they open a sentence."""
    who = _node(mesh_runtime, "Who — a node that should never be seeded this way", ["Who"])
    what = _node(mesh_runtime, "What — likewise", ["What"])
    csr = _csr(mesh_runtime, [who, what])

    seeds = _name_anchor_seeds(mesh_runtime, "Who did what?", csr)

    assert seeds == {}


def test_a_query_naming_nothing_seeds_nothing(mesh_runtime: MeshRuntime) -> None:
    a = _node(mesh_runtime, "Zeus — King of the gods", ["Zeus"])
    b = _node(mesh_runtime, "Hera — Queen of the gods", ["Hera"])
    csr = _csr(mesh_runtime, [a, b])

    assert _name_anchor_seeds(mesh_runtime, "what happened next", csr) == {}
    assert _name_anchor_seeds(mesh_runtime, "", csr) == {}


def test_multi_word_names_are_found(mesh_runtime: MeshRuntime) -> None:
    strait = _node(mesh_runtime, "The Straits of Messina — a narrow strait", ["Straits of Messina"])
    other = _node(mesh_runtime, "Zeus — King of the gods", ["Zeus"])
    csr = _csr(mesh_runtime, [strait, other])

    seeds = _name_anchor_seeds(mesh_runtime, "Where are the Straits of Messina?", csr)

    assert csr.id_to_index[strait] in seeds


def test_source_anchors_are_never_seeded_by_name(mesh_runtime: MeshRuntime) -> None:
    """Anchors are provenance. Seeding them would flood the answer with apparatus."""
    anchor = _node(mesh_runtime, "Theogony — text paragraph", ["Theogony"], anchor=True)
    entity = _node(mesh_runtime, "Zeus — King of the gods", ["Zeus"])
    csr = _csr(mesh_runtime, [anchor, entity])

    seeds = _name_anchor_seeds(mesh_runtime, "What does the Theogony say?", csr)

    assert csr.id_to_index[anchor] not in seeds


def test_the_anchor_count_is_capped(mesh_runtime: MeshRuntime) -> None:
    """A long question must not drown the ANN's contribution in name seeds."""
    ids = [_node(mesh_runtime, f"Name{i} — an entity", [f"Name{i}"]) for i in range(12)]
    csr = _csr(mesh_runtime, ids)

    question = "Tell me about " + " and ".join(f"Name{i}" for i in range(12))
    seeds = _name_anchor_seeds(mesh_runtime, question, csr, max_anchors=4)

    assert len(seeds) <= 4
