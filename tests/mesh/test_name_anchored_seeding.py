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


def test_a_broad_category_word_does_not_starve_the_entity(mesh_runtime: MeshRuntime) -> None:
    """The subject of the question must survive a category prefix.

    Anchor spans were served in generation order — longest n-gram first — and the
    first one took the whole budget. On the founding mesh `greek mythology`
    matches 18 nodes, so "In Greek mythology, who is the father of Zeus?" spent
    all eight slots on paragraph summaries and never looked `Zeus` up at all.
    Two differently-worded questions returned the identical eight anchors, none
    of them the subject (PHX-1081).

    A fanout cut-off was measured and rejected: across the 47 gold questions the
    widest real name is `Hermes` at 11 nodes and the narrowest category word is
    `mythology` at 15. Ordering by fanout needs no such line.
    """
    # The filler is written FIRST on purpose. The label index returns rows in
    # insertion order, so writing Zeus first would put him inside the category's
    # own first page and the test would pass against the defect it exists for.
    filler = [
        _node(mesh_runtime, f"A paragraph about myth {i}", ["greek mythology"]) for i in range(20)
    ]
    zeus = _node(mesh_runtime, "Zeus — king of the gods", ["zeus", "greek mythology"])
    ids = [zeus, *filler]
    csr = _csr(mesh_runtime, ids)

    plain = _name_anchor_seeds(mesh_runtime, "Who is the father of Zeus?", csr)
    prefixed = _name_anchor_seeds(
        mesh_runtime, "In Greek mythology, who is the father of Zeus?", csr
    )

    zeus_index = csr.id_to_index[zeus]
    assert zeus_index in plain, "sanity: the plain question must find Zeus"
    assert zeus_index in prefixed, "the category prefix must not evict the subject"


def test_the_named_subject_is_seeded_before_the_category(mesh_runtime: MeshRuntime) -> None:
    """Narrow span first — that ordering IS the fix.

    Not "the two questions get different anchors": both subjects here carry the
    category tag themselves, so the category span legitimately pulls both in
    either question. What must hold is precedence. Under generation order the
    category ran first and the budget was gone before the subject was read.
    """
    filler = [
        _node(mesh_runtime, f"A paragraph about myth {i}", ["greek mythology"]) for i in range(20)
    ]
    zeus = _node(mesh_runtime, "Zeus — king of the gods", ["zeus", "greek mythology"])
    cronus = _node(mesh_runtime, "Cronus — the titan", ["cronus", "greek mythology"])
    csr = _csr(mesh_runtime, [*filler, zeus, cronus])

    for question, subject in (
        ("In Greek mythology, who fathered Zeus?", zeus),
        ("In Greek mythology, who was Cronus?", cronus),
    ):
        seeds = _name_anchor_seeds(mesh_runtime, question, csr)
        assert list(seeds)[0] == csr.id_to_index[subject], (
            f"{question!r}: the subject must be the first anchor, not the category"
        )


def test_a_narrow_name_still_gets_the_whole_budget_when_nothing_competes(
    mesh_runtime: MeshRuntime,
) -> None:
    """The fix must not cap the good case to rescue the bad one.

    A per-span quota was tried first and rejected for exactly this: it took "Who
    is the father of Zeus?" from six anchors to three, because Zeus legitimately
    answers to six nodes on the founding mesh.
    """
    ids = [_node(mesh_runtime, f"Zeus, aspect {i}", ["zeus"]) for i in range(6)]
    csr = _csr(mesh_runtime, ids)
    seeds = _name_anchor_seeds(mesh_runtime, "Who is the father of Zeus?", csr)
    assert len(seeds) == 6, "one name answering to six nodes must seed all six"
