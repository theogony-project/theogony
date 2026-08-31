"""What a consolidation merge must not silently do to the substrate.

The dangerous half of this operation is not the merge decision — a wrong merge is
visible in the audit and reversible from it. It is the bookkeeping: a merge
rewrites two main tables and four derived ones, and every way of getting that
wrong fails *quietly*. An edge left pointing at a deleted node hydrates to
``None`` and `assemble_constellation` renders it as a bare ULID in an answer slot
(constellation.py) without raising anything; a stale label-index row makes the
eager linker unable to find the node it just merged, so the next ingest mints a
fresh duplicate of the entity this pass consolidated.

So most of what is asserted here is not "did it merge", it is "is the substrate
still true afterwards".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh.runtime.consolidation import (
    CONSOLIDATION_ACTION,
    Adjudicator,
    ConsolidatedNode,
    MergeProposal,
    MergeVerdict,
    compose_description,
    description_head,
    fuse_nodes,
    normalise_name,
    propose_merges,
    resolve_clusters,
    rewire_edges,
    run_consolidation,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge, QIDTag

NOW = datetime(2026, 8, 31, tzinfo=UTC)


def _node(
    name: str,
    description: str,
    tags: list[str],
    *,
    born: datetime | None = None,
    qids: list[str] | None = None,
    source_anchor: bool = False,
    dim: int = 8,
) -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=born or NOW,
        last_fired_at=born or NOW,
        semantic_vector=[0.1] * dim,
        frame_vector=[0.1] * 4,
        description_vector=[0.1] * dim,
        description=f"{name} — {description}",
        tags=tags,
        is_candidate=True,
        is_source_anchor=source_anchor,
        qids=[QIDTag(qid=q, confidence=0.9, attached_at=NOW) for q in (qids or [])],
    )


def _edge(source: ULID, target: ULID, weight: float, descriptor: str | None = None) -> Edge:
    return Edge(
        source_id=source,
        target_id=target,
        weight=weight,
        born_at=NOW,
        last_fired_at=NOW,
        relation_descriptor=descriptor,
    )


class _ScriptedAdjudicator:
    """Answers from a table keyed by the member's displayed name."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, str]] = []

    async def judge(
        self, proposal: MergeProposal, anchor: ConsolidatedNode, member: ConsolidatedNode
    ) -> MergeVerdict:
        self.asked.append((description_head(anchor), description_head(member)))
        return MergeVerdict(
            proposal, self.answers.get(description_head(member), "uncertain"), "scripted"
        )


# ---------------------------------------------------------------- proposing


def test_a_name_the_substrate_uses_categorically_does_not_propose_merges() -> None:
    """Numbered things are not one thing, however alike their names read.

    `Fragment #3` and `Fragment #37` fold to the same string under the
    evaluator's name normalisation, which strips digits so that `Hestia 1618`
    matches `Hestia`. Identity cannot borrow that rule: it would propose every
    fragment in the corpus for merging into every other.
    """
    assert normalise_name("Fragment #3") != normalise_name("Fragment #37")
    assert normalise_name("Berlin Papyri 9739") != normalise_name("Berlin Papyri 10560")
    # The fold still does its job on everything that is not a number.
    assert normalise_name("Pallas Athene") == normalise_name("pallas  athene!")


def test_paragraph_concepts_are_never_proposed() -> None:
    """A summary of a passage is not the entity the passage is about.

    The first dry run proposed 23 of them for absorption into one node under the
    shared tag `Greek mythology`. No adjudicator wording fixes that — the node
    tagged `Demeter, journey, paragraph_concept` genuinely is about Demeter and
    genuinely is not Demeter.
    """
    demeter = _node("Demeter", "Goddess of agriculture.", ["Demeter", "concept"])
    passage = _node(
        "The passage",
        "describes the goddess being led to the house of the father.",
        ["Demeter", "journey", "paragraph_concept"],
    )
    proposals = propose_merges([demeter, passage], potentials={}, adjacency={})
    assert proposals == []


def test_source_anchors_are_never_proposed() -> None:
    """An anchor absorbed into an entity would put provenance back in the answer budget."""
    zeus = _node("Zeus", "King of the gods.", ["Zeus", "concept"])
    anchor = _node("Zeus", "text paragraph: Theogony batch_01", ["Zeus"], source_anchor=True)
    assert propose_merges([zeus, anchor], potentials={}, adjacency={}) == []


def test_an_anchor_is_never_proposed_as_someone_else_s_member() -> None:
    """The rule that stops merges chaining.

    `Daughter of Cronos` is tagged both Athena and Hestia. Under a transitive
    clustering it is the bridge that fuses two goddesses into one node — which
    then looks like the best-evidenced node in the mesh. A star forbids it by
    construction: Athena and Hestia both anchor a name, so neither can be
    absorbed, and the bridge can only be absorbed by one of them.
    """
    hestia = _node("Hestia", "Goddess of the hearth.", ["Hestia", "concept"])
    athena = _node("Athena", "Goddess of wisdom.", ["Athena", "concept"])
    bridge = _node(
        "Daughter of Cronos",
        "A goddess, likely Athena or Hestia.",
        ["Daughter of Cronos", "Athena", "Hestia", "concept"],
    )
    potentials = {str(hestia.id): 10.0, str(athena.id): 9.0, str(bridge.id): 1.0}
    proposals = propose_merges([hestia, athena, bridge], potentials=potentials, adjacency={})
    assert {p.member_id for p in proposals} == {str(bridge.id)}
    assert {p.anchor_id for p in proposals} == {str(hestia.id), str(athena.id)}


def test_the_node_that_is_named_for_the_entity_anchors_it() -> None:
    """Not the highest potential alone — the node that says what the entity is.

    `her father — Zeus, the father of Persephone` may well carry more edges than
    `Zeus — King of the gods`, because a referring expression appears in the
    passage where the action is. It is still not the node an answer should be
    read from.
    """
    canonical = _node("Zeus", "King of the gods.", ["Zeus", "concept"])
    referring = _node("her father", "Zeus, the father of Persephone.", ["her father", "Zeus"])
    potentials = {str(canonical.id): 1.0, str(referring.id): 99.0}
    proposals = propose_merges([canonical, referring], potentials=potentials, adjacency={})
    assert [p.anchor_id for p in proposals] == [str(canonical.id)]


def test_one_proposal_per_pair_however_many_names_they_share() -> None:
    """`her father` is tagged Zeus, Jupiter and Jove — one question, not three."""
    canonical = _node("Zeus", "King of the gods.", ["Zeus", "Jupiter", "Jove", "concept"])
    referring = _node("her father", "Zeus.", ["her father", "Zeus", "Jupiter", "Jove"])
    proposals = propose_merges(
        [canonical, referring],
        potentials={str(canonical.id): 5.0, str(referring.id): 1.0},
        adjacency={},
    )
    assert len(proposals) == 1
    assert set(proposals[0].shared_names) == {"zeus", "jupiter", "jove"}


# ------------------------------------------------------------- adjudicating


def test_only_same_merges() -> None:
    proposal = MergeProposal("a", "b", "zeus", "tag", ("zeus",), 0.9, 0.5)
    for decision in ("different", "uncertain"):
        remap, ambiguous = resolve_clusters([MergeVerdict(proposal, decision)])
        assert remap == {} and ambiguous == set()
    remap, _ = resolve_clusters([MergeVerdict(proposal, "same")])
    assert remap == {"b": "a"}


def test_a_member_that_fits_two_anchors_is_merged_into_neither() -> None:
    """It cannot be both entities, and the substrate cannot tell which verdict is wrong."""
    to_hestia = MergeProposal("hestia", "bridge", "hestia", "tag", ("hestia",), 0.8, 0.4)
    to_athena = MergeProposal("athena", "bridge", "athena", "tag", ("athena",), 0.8, 0.4)
    remap, ambiguous = resolve_clusters(
        [MergeVerdict(to_hestia, "same"), MergeVerdict(to_athena, "same")]
    )
    assert remap == {}
    assert ambiguous == {"bridge"}


# ------------------------------------------------------------------ fusing


def test_the_survivor_keeps_the_anchor_s_identifier() -> None:
    """Every edge and audit record that already names the anchor stays true."""
    anchor = _node("Zeus", "King of the gods.", ["Zeus"], qids=["Q34201"])
    member = _node("her father", "Zeus.", ["her father", "Jove"], born=NOW - timedelta(days=5))
    fused = fuse_nodes(anchor, [member])
    assert fused.id == anchor.id
    assert fused.born_at == member.born_at
    assert normalise_name("Jove") in {normalise_name(t) for t in fused.tags}
    assert [q.qid for q in fused.qids] == ["Q34201"]


def test_only_a_node_that_absorbed_something_stops_being_a_candidate() -> None:
    anchor = _node("Zeus", "King of the gods.", ["Zeus"])
    member = _node("her father", "Zeus.", ["her father", "Zeus"])
    assert fuse_nodes(anchor, [member]).is_candidate is False
    assert member.is_candidate is True


def test_a_merged_source_anchor_flag_is_never_invented() -> None:
    anchor = _node("Zeus", "King of the gods.", ["Zeus"])
    member = _node("her father", "Zeus.", ["her father", "Zeus"])
    assert fuse_nodes(anchor, [member]).is_source_anchor is False


# ---------------------------------------------------------------- rewiring


def test_rewiring_moves_the_ids_in_the_payload_too() -> None:
    """The payload is what `load_all_edges` reads, and it carries the endpoints.

    Updating only the Lance columns would look correct until the next tick, which
    loads from the payload and commits columns regenerated from it — restoring the
    entire pre-merge topology, pointing at nodes that no longer exist.
    """
    anchor, member, other = ULID(), ULID(), ULID()
    rewired, _, _ = rewire_edges([_edge(member, other, 0.4)], {str(member): str(anchor)})
    assert str(rewired[0].source_id) == str(anchor)
    assert str(anchor) in rewired[0].model_dump_json()
    assert str(member) not in rewired[0].model_dump_json()


def test_self_edges_the_merge_created_go_and_the_others_stay() -> None:
    """The founding mesh carries 38 self-edges that predate any merge.

    Dropping those too would make consolidation a second thing — a self-loop
    pruner — that nothing asked it to be, and the CSR builder already handles
    them at read time.
    """
    anchor, member, other = ULID(), ULID(), ULID()
    edges = [
        _edge(anchor, member, 0.5),  # internal to the cluster -> self-edge -> dropped
        _edge(other, other, 0.3),  # already a self-edge -> kept
        _edge(member, other, 0.4),  # rewired
    ]
    rewired, dropped, _ = rewire_edges(edges, {str(member): str(anchor)})
    assert dropped == 1
    assert any(str(e.source_id) == str(e.target_id) == str(other) for e in rewired)
    assert len(rewired) == 2


def test_parallel_typed_relations_survive_a_merge() -> None:
    """Keying on the node pair alone destroyed 2,520 typed relations once (PHX-1058)."""
    anchor, member, other = ULID(), ULID(), ULID()
    edges = [
        _edge(anchor, other, 0.4, "father_of"),
        _edge(member, other, 0.3, "co_mentions_in_paragraph"),
    ]
    rewired, _, coalesced = rewire_edges(edges, {str(member): str(anchor)})
    assert coalesced == 0
    assert {e.relation_descriptor for e in rewired} == {"father_of", "co_mentions_in_paragraph"}


def test_coalescing_never_exceeds_the_weight_cap() -> None:
    anchor, member, other = ULID(), ULID(), ULID()
    edges = [_edge(anchor, other, 0.8, "x"), _edge(member, other, 0.7, "x")]
    rewired, _, coalesced = rewire_edges(edges, {str(member): str(anchor)}, w_max=1.0)
    assert coalesced == 1
    assert rewired[0].weight == pytest.approx(1.0)


def test_rewiring_assigns_list_fields_and_never_mutates_them() -> None:
    """`model_copy` shares list fields with its source (`test_merge_copy_semantics`).

    A coalescing step that appended to `pids` would reach through into an edge
    outside the cluster, and nothing downstream corrects a wrong P-ID.
    """
    anchor, member, other = ULID(), ULID(), ULID()
    loser = _edge(member, other, 0.2, "x")
    winner = _edge(anchor, other, 0.9, "x")
    before = list(loser.pids)
    rewire_edges([winner, loser], {str(member): str(anchor)})
    assert loser.pids == before
    assert str(loser.source_id) == str(member), "the input edge must not be mutated"


# ------------------------------------------------------------- regenerating


def test_a_regenerated_name_the_substrate_does_not_hold_is_refused() -> None:
    """PHX-1065's guard, at the one moment it matters most.

    The label index and the eager linker both key on the head of the description.
    A regeneration that renamed the node to something the substrate has no record
    of would make it unreachable by every name it had — in the same pass that
    deletes the nodes which carried those names.
    """
    anchor = _node("Zeus", "King of the gods.", ["Zeus", "concept"])
    member = _node("her father", "Zeus.", ["her father", "Zeus"])
    good, fallback = compose_description(anchor, [member], "Zeus", "King of the gods, ...")
    assert good.startswith("Zeus —") and fallback is False

    invented, fallback = compose_description(anchor, [member], "Cloud-gatherer", "King of gods.")
    assert invented.startswith("Zeus —") and fallback is True


def test_an_empty_regeneration_leaves_the_anchor_s_description_alone() -> None:
    anchor = _node("Zeus", "King of the gods.", ["Zeus"])
    kept, fallback = compose_description(anchor, [], "", "")
    assert kept == anchor.description and fallback is True


def test_a_regenerated_description_stays_within_the_doctrine_s_bound() -> None:
    anchor = _node("Zeus", "King of the gods.", ["Zeus"])
    long_body = "a very long sentence " * 200
    composed, _ = compose_description(anchor, [], "Zeus", long_body)
    assert len(composed) <= 400


# -------------------------------------------------------------- whole pass


def _founding_shaped_mesh(tmp_path: Path) -> tuple[MeshRuntime, dict[str, ConsolidatedNode]]:
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    zeus = _node("Zeus", "King of the gods.", ["Zeus", "concept"])
    father = _node("her father", "Zeus, father of Persephone.", ["her father", "Zeus"])
    cronos = _node("Cronos", "Titan, father of Zeus.", ["Cronos", "concept"])
    runtime.nodes.append_consolidated_many([zeus, father, cronos])
    runtime.edges.append_edges(
        [
            _edge(zeus.id, cronos.id, 0.5, "son_of"),
            _edge(father.id, cronos.id, 0.4, "son_of"),
            _edge(father.id, zeus.id, 0.3, "co_mentions_in_paragraph"),
        ]
    )
    return runtime, {"zeus": zeus, "father": father, "cronos": cronos}


@pytest.mark.asyncio
async def test_without_an_adjudicator_the_pass_proposes_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """Honest failure: an unadjudicated merge is not a merge this module will make."""
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    before = runtime.nodes.consolidated_count(), runtime.edges.count_rows()
    result, proposals, verdicts = await run_consolidation(runtime)
    assert result.dry_run is True
    assert proposals and verdicts == []
    assert (runtime.nodes.consolidated_count(), runtime.edges.count_rows()) == before


@pytest.mark.asyncio
async def test_a_merge_leaves_no_edge_pointing_at_a_node_that_is_gone(
    tmp_path: Path,
) -> None:
    """The invariant every other bookkeeping failure ends at.

    An unresolvable endpoint does not raise: `assemble_constellation` renders the
    raw ULID as the node's name and spends an answer slot on it.
    """
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    adjudicator: Adjudicator = _ScriptedAdjudicator({"her father": "same"})
    result, _, _ = await run_consolidation(runtime, adjudicator=adjudicator)

    assert result.nodes_absorbed == 1
    live = {str(n.id) for n in runtime.nodes.iter_consolidated()}
    for edge in runtime.edges.load_all_edges():
        assert str(edge.source_id) in live
        assert str(edge.target_id) in live


@pytest.mark.asyncio
async def test_a_merge_leaves_the_survivor_findable_by_every_name_it_absorbed(
    tmp_path: Path,
) -> None:
    """A stale label index re-creates the duplication the merge just removed.

    `find_consolidated_by_labels` is the eager linker's identity path. If the
    survivor is not in it under the absorbed names, the next ingest mints a fresh
    candidate for the entity this pass consolidated.
    """
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    await run_consolidation(runtime, adjudicator=_ScriptedAdjudicator({"her father": "same"}))

    found = runtime.nodes.find_consolidated_by_labels(["her father"], limit=8)
    assert [str(n.id) for n in found] == [str(nodes["zeus"].id)]
    assert runtime.nodes.get_consolidated(str(nodes["father"].id)) is None


@pytest.mark.asyncio
async def test_a_merge_does_not_count_as_a_tick(tmp_path: Path) -> None:
    """`tick_count()` is the yardstick every recall figure in this repo is quoted against."""
    runtime, _ = _founding_shaped_mesh(tmp_path)
    before = runtime.tick_count()
    result, _, _ = await run_consolidation(
        runtime, adjudicator=_ScriptedAdjudicator({"her father": "same"})
    )
    assert runtime.tick_count() == before
    assert result.audit_id is not None
    actions = {row["action"] for row in runtime.audit.list_recent(limit=10)}
    assert CONSOLIDATION_ACTION in actions


@pytest.mark.asyncio
async def test_the_audit_names_every_absorbed_id_because_nothing_else_will(
    tmp_path: Path,
) -> None:
    """After the pass those ULIDs exist in no table and on no node field."""
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    await run_consolidation(runtime, adjudicator=_ScriptedAdjudicator({"her father": "same"}))
    record = next(
        row for row in runtime.audit.list_recent(limit=10) if row["action"] == CONSOLIDATION_ACTION
    )
    absorbed = json.loads(record["payload_json"])["absorbed"]
    assert absorbed[str(nodes["zeus"].id)] == [str(nodes["father"].id)]


@pytest.mark.asyncio
async def test_pending_reinforcement_follows_the_node_it_names(tmp_path: Path) -> None:
    """`merge_edge_deltas` *creates* an edge for a key it does not find.

    One delta naming an absorbed node would have the next tick mint an edge to a
    row that no longer exists — and the sidecar is the one piece of state Lance
    versioning cannot recover.
    """
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    runtime.edges.delta.append_hebbian_delta(
        source_id=str(nodes["father"].id),
        target_id=str(nodes["cronos"].id),
        weight_delta=0.1,
        relation_descriptor="son_of",
    )
    await run_consolidation(runtime, adjudicator=_ScriptedAdjudicator({"her father": "same"}))
    pending = runtime.edges.delta.drain()
    assert [row["source_id"] for row in pending] == [str(nodes["zeus"].id)]


@pytest.mark.asyncio
async def test_a_tick_after_a_merge_does_not_resurrect_the_absorbed_topology(
    tmp_path: Path,
) -> None:
    """The end-to-end form of the payload invariant, through the real tick."""
    runtime, nodes = _founding_shaped_mesh(tmp_path)
    await run_consolidation(runtime, adjudicator=_ScriptedAdjudicator({"her father": "same"}))
    runtime.run_minimal_tick()
    live = {str(n.id) for n in runtime.nodes.iter_consolidated()}
    for edge in runtime.edges.load_all_edges():
        assert str(edge.source_id) in live and str(edge.target_id) in live
