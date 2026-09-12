"""Finding the corpus's disagreements with itself (PHX-1107).

The expensive half of this pass is the adjudicator, and it is mocked. What is
pinned here is the cheap half, where the precision comes from: the provenance
filter that tells an enumeration ("Rhea bore Hestia, Demeter and Hera" — three
edges, one paragraph, no disagreement) from a contradiction ("Night bore the
Fates" / "Themis bore the Fates" — two paragraphs, one slot). Without that
filter every genealogy in Hesiod is a contradiction, which is the failure mode
this test file exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh import frames
from theogony.mesh.runtime.contradiction import (
    CONTRADICTION_ACTION,
    PARENTHOOD,
    ContradictionCandidate,
    ContradictionVerdict,
    LLMContradictionAdjudicator,
    ReplayAdjudicator,
    contradiction_edges,
    normalise_descriptor,
    propose_contradictions,
    run_contradiction_pass,
    witnesses,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance

NOW = datetime(2026, 9, 12, tzinfo=UTC)


def _entity(name: str) -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=frames.neutral_frame(4),
        description=f"{name} — a figure",
        tags=[name],
    )


def _chunk(stance: str = "current_claim") -> ChunkNode:
    return ChunkNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=frames.frame_vector(stance, dim=4),
        source=SourceProvenance(
            source_type="text", source_identifier="gutenberg_348", extracted_at=NOW
        ),
        raw_text_ref="gutenberg_348#p1",
    )


def _relation(src: ConsolidatedNode, tgt: ConsolidatedNode, descriptor: str) -> Edge:
    return Edge(
        source_id=src.id,
        target_id=tgt.id,
        weight=1.0,
        born_at=NOW,
        last_fired_at=NOW,
        relation_kind="semantic",
        relation_descriptor=descriptor,
        creation_context="kadmos_relation",
    )


def _mention(chunk: ChunkNode, entity: ConsolidatedNode) -> Edge:
    return Edge(
        source_id=chunk.id,
        target_id=entity.id,
        weight=1.0,
        born_at=NOW,
        last_fired_at=NOW,
        relation_kind="semantic",
        relation_descriptor="mentions",
        creation_context="kadmos_mentions",
    )


def test_two_accounts_of_one_birth_from_two_paragraphs_are_a_candidate() -> None:
    """The Fates: Night bore them in one passage of the Theogony and Themis in
    another. Same descriptor, same target, two sources, disjoint witnesses."""
    fates, night, themis = _entity("Fates"), _entity("Night"), _entity("Themis")
    p1, p2 = _chunk(), _chunk()
    edges = [
        _relation(night, fates, "bore"),
        _relation(themis, fates, "bore"),
        _mention(p1, night),
        _mention(p1, fates),
        _mention(p2, themis),
        _mention(p2, fates),
    ]
    nodes = {str(n.id): n for n in (fates, night, themis)}
    found = propose_contradictions(edges, nodes)
    assert len(found) == 1
    assert found[0].axis == "target"
    assert {found[0].left_name, found[0].right_name} == {"Night", "Themis"}
    assert found[0].shared_name == "Fates"
    assert set(found[0].left_chunks).isdisjoint(found[0].right_chunks)


def test_an_enumeration_in_one_paragraph_is_not_a_candidate() -> None:
    """'Rhea bore Hestia, Demeter and Hera' is three edges and no disagreement.
    The provenance filter is the whole reason this pass has any precision."""
    rhea = _entity("Rhea")
    children = [_entity(n) for n in ("Hestia", "Demeter", "Hera")]
    p1 = _chunk()
    edges = [_relation(rhea, c, "bore") for c in children]
    edges += [_mention(p1, rhea)] + [_mention(p1, c) for c in children]
    nodes = {str(n.id): n for n in [rhea, *children]}
    assert propose_contradictions(edges, nodes) == []


def test_the_mirror_grouping_finds_one_subject_with_two_origins() -> None:
    """Aphrodite born from the foam in the Theogony, daughter of Zeus in Hymn V."""
    aphrodite, foam, zeus = _entity("Aphrodite"), _entity("foam"), _entity("Zeus")
    p1, p2 = _chunk(), _chunk()
    edges = [
        _relation(aphrodite, foam, "born_from"),
        _relation(aphrodite, zeus, "born_from"),
        _mention(p1, aphrodite),
        _mention(p1, foam),
        _mention(p2, aphrodite),
        _mention(p2, zeus),
    ]
    nodes = {str(n.id): n for n in (aphrodite, foam, zeus)}
    found = propose_contradictions(edges, nodes)
    assert len(found) == 1
    # `born_from` points child to parent, so normalisation flips it into the
    # functional direction: the group is "who is Aphrodite's parent", not
    # "what did Aphrodite come from". That is the direction worth grouping on,
    # because a child has one parent and a parent has many children.
    assert found[0].axis == "target"
    assert found[0].shared_name == "Aphrodite"
    assert {found[0].left_name, found[0].right_name} == {"foam", "Zeus"}
    # the claim shown to the adjudicator keeps the words the text used
    assert "born_from" in found[0].claim("left")


def test_two_spellings_of_one_relation_meet_in_the_same_group() -> None:
    """Measured on the framed re-read: parenthood arrives under thirty-odd
    spellings, half of them pointing the other way. Without normalisation
    'Night bore the Fates' and 'the Fates son_of Themis' never meet, and the
    contradiction is invisible."""
    fates, night, themis = _entity("Fates"), _entity("Night"), _entity("Themis")
    p1, p2 = _chunk(), _chunk()
    edges = [
        _relation(night, fates, "bore"),
        _relation(fates, themis, "child_of"),  # the other direction, other word
        _mention(p1, night),
        _mention(p1, fates),
        _mention(p2, themis),
        _mention(p2, fates),
    ]
    nodes = {str(n.id): n for n in (fates, night, themis)}
    found = propose_contradictions(edges, nodes)
    assert len(found) == 1
    assert found[0].descriptor == PARENTHOOD
    assert {found[0].left_name, found[0].right_name} == {"Night", "Themis"}
    # each side is shown with the words its own passage used
    spellings = {found[0].left_descriptor, found[0].right_descriptor}
    assert spellings == {"bore", "child_of"}


def test_normalise_descriptor_folds_spelling_and_direction() -> None:
    assert normalise_descriptor("bore") == (PARENTHOOD, False)
    assert normalise_descriptor("son_of") == (PARENTHOOD, True)
    assert normalise_descriptor("mother of") == (PARENTHOOD, False)
    assert normalise_descriptor("Daughter-Of") == (PARENTHOOD, True)
    # anything uncurated keeps its own spelling, folded
    assert normalise_descriptor("located in") == ("located_in", False)
    assert normalise_descriptor(None) == ("", False)


def test_a_hub_is_not_a_disagreement() -> None:
    """Zeus fathers many children across many paragraphs. A group wider than
    `max_group` is an accumulation, and asking the model about each pair would
    cost more than the pass is worth."""
    zeus = _entity("Zeus")
    children = [_entity(f"child{i}") for i in range(6)]
    edges, nodes = [], {str(zeus.id): zeus}
    for child in children:
        p = _chunk()
        edges += [_relation(zeus, child, "father_of"), _mention(p, zeus), _mention(p, child)]
        nodes[str(child.id)] = child
    assert propose_contradictions(edges, nodes, max_group=4) == []
    assert propose_contradictions(edges, nodes, max_group=8)


def test_a_relation_with_no_witnessing_paragraph_is_skipped() -> None:
    """Without `mentions` edges there is no provenance, so there is no way to
    tell an enumeration from a disagreement. Skipping is the honest answer."""
    a, b, c = _entity("A"), _entity("B"), _entity("C")
    edges = [_relation(a, b, "bore"), _relation(a, c, "bore")]
    nodes = {str(n.id): n for n in (a, b, c)}
    assert propose_contradictions(edges, nodes) == []


def test_contradiction_edges_are_written_both_ways_and_carry_the_claims() -> None:
    left_chunk, right_chunk = str(ULID()), str(ULID())
    candidate = ContradictionCandidate(
        shared_id=str(ULID()),
        shared_name="Fates",
        descriptor="bore",
        left_id=str(ULID()),
        left_name="Night",
        right_id=str(ULID()),
        right_name="Themis",
        axis="target",
        left_chunks=(left_chunk,),
        right_chunks=(right_chunk,),
    )
    edges = contradiction_edges(
        ContradictionVerdict(candidate, "CONTRADICTION", "one mother only"), now=NOW
    )
    assert len(edges) == 2
    assert {(str(e.source_id), str(e.target_id)) for e in edges} == {
        (left_chunk, right_chunk),
        (right_chunk, left_chunk),
    }
    for edge in edges:
        assert edge.relation_kind == "contradicts"
        assert frames.is_contradiction_kind(edge.relation_kind)
        # The two claims do not share a frame, and the field says so.
        assert edge.frame_consistency == 0.0
        assert edge.valid_from == NOW
        assert "Night bore Fates" in edge.description
        assert "Themis bore Fates" in edge.description


def test_an_already_recorded_contradiction_is_not_reproposed() -> None:
    """The pass must be idempotent: a second run over a mesh it already marked
    should not rediscover its own edges as fresh candidates."""
    a, b, c = _entity("A"), _entity("B"), _entity("C")
    p1, p2 = _chunk(), _chunk()
    edges = [
        _relation(a, b, "bore"),
        _relation(a, c, "bore"),
        _mention(p1, a),
        _mention(p1, b),
        _mention(p2, a),
        _mention(p2, c),
    ]
    nodes = {str(n.id): n for n in (a, b, c)}
    assert len(propose_contradictions(edges, nodes)) == 1
    written = contradiction_edges(
        ContradictionVerdict(propose_contradictions(edges, nodes)[0], "CONTRADICTION"), now=NOW
    )
    # the `contradicts` edges themselves are never candidates
    assert len(propose_contradictions([*edges, *written], nodes)) == 1


def test_witnesses_maps_entities_to_the_paragraphs_that_mention_them() -> None:
    a, b = _entity("A"), _entity("B")
    p1, p2 = _chunk(), _chunk()
    table = witnesses([_mention(p1, a), _mention(p2, a), _mention(p1, b)])
    assert table[str(a.id)] == {str(p1.id), str(p2.id)}
    assert table[str(b.id)] == {str(p1.id)}


class _FixedAdjudicator:
    model_id = "fixed"

    def __init__(self, verdict: str) -> None:
        self._verdict = verdict
        self.seen: list[ContradictionCandidate] = []

    async def judge(self, candidate: ContradictionCandidate) -> ContradictionVerdict:
        self.seen.append(candidate)
        return ContradictionVerdict(candidate, self._verdict, "because")


@pytest.mark.asyncio
async def test_the_pass_writes_edges_and_moves_the_chunks_to_disputed(tmp_path: Path) -> None:
    """The end the whole ticket is for: after the pass the two witnessing
    paragraphs carry the `disputed` stance, so a contradiction query — which
    attenuates every settled claim to zero — can find them."""
    rt = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=4)
    fates, night, themis = _entity("Fates"), _entity("Night"), _entity("Themis")
    for node in (fates, night, themis):
        rt.nodes.append_consolidated(node)
    p1, p2 = _chunk(), _chunk()
    for chunk in (p1, p2):
        rt.nodes.append_chunk(chunk)
    rt.edges.append_edges(
        [
            _relation(night, fates, "bore"),
            _relation(themis, fates, "bore"),
            _mention(p1, night),
            _mention(p1, fates),
            _mention(p2, themis),
            _mention(p2, fates),
        ]
    )

    result = await run_contradiction_pass(rt, _FixedAdjudicator("CONTRADICTION"))
    assert result.candidates == 1 and result.confirmed == 1
    assert result.edges_written == 2
    assert result.chunks_marked == 2
    assert result.adjudicator_model == "fixed"

    written = [e for e in rt.edges.load_all_edges() if e.relation_kind == "contradicts"]
    assert len(written) == 2
    disputed = frames.frame_vector("disputed", dim=4)
    for chunk in rt.nodes.iter_chunks():
        assert chunk.frame_vector == pytest.approx(disputed)


@pytest.mark.asyncio
async def test_a_compatible_verdict_writes_nothing(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=4)
    zeus, athena, apollo = _entity("Zeus"), _entity("Athena"), _entity("Apollo")
    for node in (zeus, athena, apollo):
        rt.nodes.append_consolidated(node)
    p1, p2 = _chunk(), _chunk()
    for chunk in (p1, p2):
        rt.nodes.append_chunk(chunk)
    rt.edges.append_edges(
        [
            _relation(zeus, athena, "father_of"),
            _relation(zeus, apollo, "father_of"),
            _mention(p1, zeus),
            _mention(p1, athena),
            _mention(p2, zeus),
            _mention(p2, apollo),
        ]
    )
    result = await run_contradiction_pass(rt, _FixedAdjudicator("COMPATIBLE"))
    assert result.candidates == 1 and result.confirmed == 0 and result.compatible == 1
    assert result.edges_written == 0 and result.chunks_marked == 0
    assert not [e for e in rt.edges.load_all_edges() if e.relation_kind == "contradicts"]
    # the finding is still recorded, so a re-run can replay it without spending
    assert result.findings[0]["verdict"] == "COMPATIBLE"
    assert result.audit_id


@pytest.mark.asyncio
async def test_dry_run_judges_without_writing(tmp_path: Path) -> None:
    rt = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=4)
    a, b, c = _entity("A"), _entity("B"), _entity("C")
    for node in (a, b, c):
        rt.nodes.append_consolidated(node)
    p1, p2 = _chunk(), _chunk()
    for chunk in (p1, p2):
        rt.nodes.append_chunk(chunk)
    rt.edges.append_edges(
        [
            _relation(a, b, "bore"),
            _relation(a, c, "bore"),
            _mention(p1, a),
            _mention(p1, b),
            _mention(p2, a),
            _mention(p2, c),
        ]
    )
    result = await run_contradiction_pass(rt, _FixedAdjudicator("CONTRADICTION"), apply=False)
    assert result.confirmed == 1
    assert result.edges_written == 0
    assert not [e for e in rt.edges.load_all_edges() if e.relation_kind == "contradicts"]


@pytest.mark.asyncio
async def test_a_recorded_run_replays_without_the_model() -> None:
    candidate = ContradictionCandidate(
        shared_id="s",
        shared_name="Fates",
        descriptor="bore",
        left_id="l",
        left_name="Night",
        right_id="r",
        right_name="Themis",
        axis="target",
        left_chunks=("p1",),
        right_chunks=("p2",),
    )
    replay = ReplayAdjudicator.from_findings(
        [
            {
                "shared_id": "s",
                "descriptor": "bore",
                "left_id": "l",
                "right_id": "r",
                "verdict": "CONTRADICTION",
            }
        ]
    )
    assert (await replay.judge(candidate)).confirmed
    assert replay.model_id == "replay"


class _Reply:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubLLM:
    model_id = "stub-1"

    def __init__(self, text: str | Exception) -> None:
        self._text = text

    async def complete(self, prompt: str, **kwargs: object) -> _Reply:
        if isinstance(self._text, Exception):
            raise self._text
        return _Reply(self._text)


@pytest.mark.asyncio
async def test_the_adjudicator_reads_a_verdict_out_of_whatever_the_model_says() -> None:
    candidate = ContradictionCandidate(
        shared_id="s",
        shared_name="Fates",
        descriptor="bore",
        left_id="l",
        left_name="Night",
        right_id="r",
        right_name="Themis",
        axis="target",
        left_chunks=("p1",),
        right_chunks=("p2",),
    )
    for text, expected in (
        ("CONTRADICTION — one mother only", "CONTRADICTION"),
        ("compatible. Zeus has many children", "COMPATIBLE"),
        ("I think this is a CONTRADICTION, actually", "CONTRADICTION"),
        ("no idea", "UNCERTAIN"),
    ):
        verdict = await LLMContradictionAdjudicator(_StubLLM(text)).judge(candidate)
        assert verdict.verdict == expected, text

    # a failing model must not fail the pass; it records uncertainty
    failed = await LLMContradictionAdjudicator(_StubLLM(RuntimeError("429"))).judge(candidate)
    assert failed.verdict == "UNCERTAIN" and "429" in failed.reason


def test_the_action_name_is_stable() -> None:
    """Audit rows are read by ticket and by `mesh status`; renaming the action
    orphans every row already written."""
    assert CONTRADICTION_ACTION == "mesh_contradiction_pass"
