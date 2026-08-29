"""Four load-bearing decisions that nothing asserted.

Found by mutation against a green baseline of 1,753 tests. Each of these
survived a change that should have been catastrophic:

    a backwards P-ID mapping (`child_of` -> P40)          1753 passed
    the saturation cap from 10,000 to 4                   1753 passed
    the linker's identity threshold 0.72 -> 0.20          1753 passed
    its corroboration threshold 0.55 -> 0.99              1753 passed

They are not tuning knobs. A wrong P-ID is a permanent false claim about a
Wikidata property; a wrong saturation cap silently deletes edges on the next
tick; a wrong linker threshold decides which entities are the same thing
(PHX-1092).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh.relation_pids import pid_for
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import DEFAULT_MAX_OUT_DEGREE, enforce_saturation

# Descriptor pairs that describe the same fact from opposite ends. Whatever they
# map to, they must not map to the *same* property: `father_of(Cronos, Zeus)` and
# `son_of(Zeus, Cronos)` are the same fact written both ways, and a table that
# gave them one property would assert one of them backwards on every edge that
# carries it.
_INVERSE_PAIRS = (
    ("father_of", "son_of"),
    ("mother_of", "daughter_of"),
    ("parent_of", "child_of"),
    ("bore", "born_of"),
    ("includes", "part_of"),
    ("has_part", "member_of"),
)


@pytest.mark.parametrize(("forward", "backward"), _INVERSE_PAIRS)
def test_inverse_descriptors_never_share_a_property(forward: str, backward: str) -> None:
    """The invariant the whole table exists to protect.

    A backwards mapping is not caught by anything downstream: no consumer reads
    the P-ID's identity (`typed_edges` and the store only check `is not None`),
    so recall does not move and the edge direction is untouched. What changes is
    that a false one-to-one claim about a Wikidata property lands permanently on
    `Edge.pids`, and the tick skips edges that already carry pids — no later pass
    corrects it.
    """
    a, b = pid_for(forward), pid_for(backward)
    assert not (a is not None and a == b), (
        f"{forward!r} and {backward!r} both map to {a} — one of them is backwards"
    )


def test_the_kinship_directions_hold_their_measured_values() -> None:
    """The families that carry the most edges, pinned by value.

    36% of typed edges on the founding mesh sit on descriptors no test named.
    These are the ones a mistake would cost most.
    """
    assert pid_for("father_of") == "P40", "P40 is 'child' — subject has object as child"
    assert pid_for("mother_of") == "P40"
    assert pid_for("bore") == "P40"
    assert pid_for("son_of") == "P8810", "P8810 is 'parent' — parent of the subject"
    assert pid_for("daughter_of") == "P8810"
    assert pid_for("child_of") == "P8810"
    assert pid_for("includes") == "P527", "P527 is 'has part(s)'"
    assert pid_for("part_of") == "P361", "P361 is 'part of' — the other direction"
    assert pid_for("killed_by") == "P157"
    assert pid_for("born_in") == "P19"


def _edge(source: str, target: str, weight: float, descriptor: str) -> Edge:
    now = datetime.now(UTC)
    return Edge(
        source_id=source,
        target_id=target,
        weight=weight,
        relation_descriptor=descriptor,
        born_at=now,
        last_fired_at=now,
    )


def test_saturation_keeps_the_strongest_edges_not_the_weakest() -> None:
    """Inverting this sort makes the tick destroy exactly what it should protect.

    The direction survived every test in the suite. It is the one property of
    saturation that cannot be recovered from: the tick rewrites the edge table
    and `_DEFAULT_VERSION_RETENTION` is zero, so the discarded edges are gone in
    the same pass that discarded them.
    """
    source = str(ULID())
    edges = [_edge(source, str(ULID()), weight=w, descriptor=f"r{w}") for w in (0.1, 0.5, 0.9)]
    kept = enforce_saturation(edges, max_out_degree=2, w_max=1.0)
    weights = sorted(e.weight for e in kept if str(e.source_id) == source)
    assert weights == [0.5, 0.9], f"strongest two must survive, got {weights}"


def test_the_saturation_default_is_the_doctrines_cap() -> None:
    """10,000 is MESH_SUBSTRATE §3's lowest tier. A mutation to 4 passed the suite.

    Currently inert on the founding mesh — the largest out-degree is 1,093 — which
    is exactly why nothing noticed.
    """
    assert DEFAULT_MAX_OUT_DEGREE == 10_000


def test_a_partially_written_dedup_index_is_repaired_on_reopen(
    mesh_runtime: MeshRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_ensure_dedup_index` read "not empty" as "complete".

    `append_edges` writes the edge rows and then the dedup rows. A crash between
    the two leaves an index that is neither empty nor complete — real on any long
    seed import — and the guard then refuses to repair it, because it only checks
    for emptiness. The exact check sits unused beside it: `_dedup_rows` emits one
    row per edge, so `count_rows()` equality is constructively the completeness
    test (94,490 == 94,490 on the founding mesh).
    """
    source = str(ULID())
    mesh_runtime.edges.append_edges([_edge(source, str(ULID()), 1.0, f"rel_{i}") for i in range(6)])
    assert mesh_runtime.edges.dedup_index.count_rows() == 6

    # Leave the index partial, the way a crash between the two adds would.
    mesh_runtime.edges.dedup_index.delete("true")
    mesh_runtime.edges.dedup_index.add(
        mesh_runtime.edges._dedup_rows([_edge(source, str(ULID()), 1.0, "rel_0")])
    )
    assert mesh_runtime.edges.dedup_index.count_rows() == 1

    mesh_runtime.edges._ensure_dedup_index()
    assert mesh_runtime.edges.dedup_index.count_rows() == mesh_runtime.edges.count_rows(), (
        "a partial index must be rebuilt, not accepted because it is non-empty"
    )


# --- identity thresholds ---------------------------------------------------
#
# `link_reference` resolves a reference through four tiers in order: Q-ID match,
# description match at cosine >= 0.72, tag match at >= 0.55, and otherwise a new
# candidate. Both numbers survived being moved to 0.20 and 0.99 respectively
# without a single test failing — and they decide which references are the same
# entity, which is the decision PHX-1063 and PHX-1051 were both about.


def _identity_runtime(tmp_path: object) -> MeshRuntime:
    return MeshRuntime(Path(str(tmp_path)) / "ws", semantic_dim=8, frame_dim=4)


def _unit(*values: float) -> list[float]:
    import math

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values] + [0.0] * (8 - len(values))


def _existing(description: str, vec: list[float], tags: list[str]) -> object:
    from theogony.mesh.schemas import ConsolidatedNode

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


def _link(runtime: MeshRuntime, existing: object, *, label: str, tags: list[str], vec: list[str]):  # type: ignore[no-untyped-def]
    from theogony.mesh.ingestion.linker import EagerLinker

    runtime.nodes.append_consolidated(existing)  # type: ignore[arg-type]
    linker = EagerLinker(runtime.nodes, runtime.edges, semantic_dim=8, frame_dim=4)
    linker._registry.remember(existing, aliases=[existing.description], qids=[])  # type: ignore[attr-defined]
    return linker.link_reference(
        label=label,
        description=label,
        tags=tags,
        qids=[],
        semantic_vector=vec,  # type: ignore[arg-type]
        frame_vector=[0.0] * 4,
        description_vector=vec,  # type: ignore[arg-type]
    )


def test_the_tag_tier_fires_below_the_description_one(tmp_path: object) -> None:
    """No test ever asserted `signal == "tag"`; moving its threshold to 0.99 was silent.

    Measured, because the tiers are not what their thresholds suggest. The
    description score is not a bare cosine — it composes cosine with context
    overlap, tag overlap and a label match — so which tier fires depends on both:

        label "Zeus the Thunderer", tag "zeus", against a node "Zeus"
            cosine 0.20, 0.50  ->  tag          (score 1.075)
            cosine 0.70, 0.90  ->  description  (score 0.780, 0.980)

    The tag tier is what catches a name variant whose *description* has drifted:
    same entity, differently worded. Nothing was checking it resolved at all.
    """
    runtime = _identity_runtime(tmp_path)
    existing = _existing("Zeus — king of the gods", _unit(1.0, 0.0), ["zeus"])
    decision = _link(
        runtime, existing, label="Zeus the Thunderer", tags=["zeus"], vec=_unit(0.5, 0.87)
    )
    assert decision.signal == "tag", f"expected the tag tier, got {decision.signal!r}"
    assert not decision.is_new


def test_a_referring_expression_never_merges_on_a_shared_tag_alone(tmp_path: object) -> None:
    """PHX-1051's guard, pinned across the whole cosine range.

    A shared tag corroborates identity only when it *names* the entity — its
    tokens appear in the label — or the label is already a known alias. Sharing
    the tag `zeus` while being called `Cloud-gatherer` is not enough, and stays
    not enough at cosine 1.0.

    That is deliberate and it is expensive: it is why deity references stopped
    being absorbed into a generic work-node (PHX-1051), and also why persisting
    merge-time aliases cost seven points of recall rather than gaining any
    (PHX-1071). The guard is doing exactly what it was built to do; this test
    exists so that a future loosening is a decision rather than a slip.
    """
    for n, (cosine, other) in enumerate(((0.5, 0.87), (0.9, 0.44), (1.0, 0.0))):
        # A fresh workspace per probe. Reusing one would merge the second
        # `Cloud-gatherer` into the candidate the first created — correctly, since
        # by then it is a known entity — and that is a different question.
        runtime = _identity_runtime(Path(str(tmp_path)) / f"probe{n}")
        existing = _existing("Zeus — king of the gods", _unit(1.0, 0.0), ["zeus"])
        decision = _link(
            runtime, existing, label="Cloud-gatherer", tags=["zeus"], vec=_unit(cosine, other)
        )
        assert decision.is_new, (
            f"a shared tag that does not name the entity merged at cosine {cosine}"
        )


def test_the_description_tier_needs_lexical_corroboration(tmp_path: object) -> None:
    """The other half of the same guard: high cosine alone must not merge.

    Deity references were being absorbed into a generic work-node on description
    cosine alone. A near-identical vector with no shared naming stays emergent.
    """
    runtime = _identity_runtime(tmp_path)
    existing = _existing("An ancient epic poem about the gods", _unit(1.0, 0.05), ["poem"])
    decision = _link(runtime, existing, label="Dione", tags=["dione"], vec=_unit(1.0, 0.06))
    assert decision.is_new, "cosine alone must not merge an entity into a generic hub"


def test_a_weak_match_creates_a_new_entity_rather_than_merging(tmp_path: object) -> None:
    """Below both thresholds identity must stay emergent.

    This is the direction that matters: merging on weak evidence is how 127 of
    130 Q-IDs came to name the wrong thing (PHX-1063) and how deity references
    were absorbed into a generic work-node (PHX-1051). A threshold moved down is
    silent — it produces fewer nodes, not an error.
    """
    runtime = _identity_runtime(tmp_path)
    existing = _existing("Zeus — king of the gods", _unit(1.0, 0.0), ["zeus"])
    orthogonal = _unit(0.0, 1.0)
    decision = _link(runtime, existing, label="Poseidon", tags=["poseidon"], vec=orthogonal)
    assert decision.is_new, "an unrelated reference must not merge into an existing entity"
    assert decision.signal not in {"description", "tag"}
