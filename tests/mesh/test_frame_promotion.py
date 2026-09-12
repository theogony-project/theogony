"""Entities inherit the stance of the paragraphs about them (PHX-1107)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh import frames
from theogony.mesh.runtime.frame_promotion import (
    FRAME_PROMOTION_ACTION,
    mean_frame,
    run_frame_promotion,
    witnesses_by_entity,
)
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ChunkNode, ConsolidatedNode, Edge, SourceProvenance

NOW = datetime(2026, 9, 12, tzinfo=UTC)
DIM = 8


def _entity(name: str, *, anchor: bool = False) -> ConsolidatedNode:
    return ConsolidatedNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=frames.neutral_frame(DIM),
        description=f"{name} — a figure",
        tags=[name],
        is_source_anchor=anchor,
    )


def _chunk(stance: str) -> ChunkNode:
    return ChunkNode(
        id=ULID(),
        born_at=NOW,
        last_fired_at=NOW,
        semantic_vector=[0.1] * 8,
        frame_vector=frames.frame_vector(stance, dim=DIM),
        source=SourceProvenance(
            source_type="text", source_identifier="gutenberg_348", extracted_at=NOW
        ),
        raw_text_ref="gutenberg_348#p1",
    )


def _mention(chunk: ChunkNode, entity: ConsolidatedNode) -> Edge:
    return Edge(
        source_id=chunk.id,
        target_id=entity.id,
        weight=1.0,
        born_at=NOW,
        last_fired_at=NOW,
        relation_descriptor="mentions",
        creation_context="kadmos_mentions",
    )


def _build(tmp_path: Path, plan: dict[str, list[str]], *, anchor: bool = False) -> MeshRuntime:
    """`plan` maps an entity name to the stances of the chunks mentioning it."""
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=DIM)
    edges: list[Edge] = []
    for name, stances in plan.items():
        entity = _entity(name, anchor=anchor)
        runtime.nodes.append_consolidated(entity)
        for stance in stances:
            chunk = _chunk(stance)
            runtime.nodes.append_chunk(chunk)
            edges.append(_mention(chunk, entity))
    if edges:
        runtime.edges.append_edges(edges)
    return runtime


def _stance_of(vector: list[float]) -> str:
    if all(v == 0.0 for v in vector):
        return "neutral"
    best, score = "?", -2.0
    for stance in frames.STANCES:
        if stance == "neutral":
            continue
        cos = frames.frame_cosine(vector, frames.frame_vector(stance, dim=DIM))
        if cos > score:
            best, score = stance, cos
    return best


def test_an_entity_named_only_in_disputed_paragraphs_reads_as_disputed(
    tmp_path: Path,
) -> None:
    runtime = _build(tmp_path, {"Aphrodite": ["disputed", "disputed"]})
    result = run_frame_promotion(runtime)
    assert result.promoted == 1
    node = next(iter(runtime.nodes.iter_consolidated()))
    assert _stance_of(node.frame_vector) == "disputed"


def test_a_mixture_keeps_the_minority_in_it(tmp_path: Path) -> None:
    """The doctrine says 'dominant frame'; a centroid is the dominant direction
    with the minority still in it. A mode would erase the two disputed
    paragraphs among forty settled ones, which is exactly the signal a
    contradiction query is looking for."""
    runtime = _build(tmp_path, {"Zeus": ["current_claim"] * 6 + ["disputed"] * 2})
    run_frame_promotion(runtime)
    node = next(iter(runtime.nodes.iter_consolidated()))
    # reads as a current claim, but the disputed axis is not zero
    assert _stance_of(node.frame_vector) == "current_claim"
    assert node.frame_vector[frames.AXIS_INDEX["standing"]] < 0.0
    # and a contradiction query no longer attenuates it to exactly zero
    assert frames.frame_cosine(node.frame_vector, frames.query_frame("contradiction", dim=DIM)) > 0


def test_a_source_anchor_stays_neutral(tmp_path: Path) -> None:
    """A container asserts nothing, so nothing should ever attenuate it."""
    runtime = _build(tmp_path, {"gutenberg_348": ["disputed"]}, anchor=True)
    result = run_frame_promotion(runtime)
    assert result.promoted == 0
    assert result.anchors_skipped == 1
    node = next(iter(runtime.nodes.iter_consolidated()))
    assert all(v == 0.0 for v in node.frame_vector)


def test_an_entity_no_paragraph_mentions_is_left_alone(tmp_path: Path) -> None:
    runtime = MeshRuntime(tmp_path / "mesh", semantic_dim=8, frame_dim=DIM)
    runtime.nodes.append_consolidated(_entity("Orphan"))
    result = run_frame_promotion(runtime)
    assert result.promoted == 0 and result.without_witness == 1
    assert all(v == 0.0 for v in next(iter(runtime.nodes.iter_consolidated())).frame_vector)


def test_opposed_paragraphs_cancel_to_neutral_rather_than_to_nonsense(
    tmp_path: Path,
) -> None:
    """An entity spoken of in exactly opposed stances has no dominant frame.
    Zero is the honest answer, and zero means neutral everywhere downstream —
    never 'opposed to everything'."""
    runtime = _build(tmp_path, {"Contested": ["current_claim", "refuted_claim"]})
    run_frame_promotion(runtime)
    node = next(iter(runtime.nodes.iter_consolidated()))
    # veridicality cancels; what is left must still be a legal frame
    assert len(node.frame_vector) == DIM
    norm = sum(v * v for v in node.frame_vector) ** 0.5
    assert norm == pytest.approx(1.0) or norm == pytest.approx(0.0)


def test_mean_frame_is_a_unit_vector_or_zero() -> None:
    a = frames.frame_vector("definition", dim=DIM)
    b = frames.frame_vector("current_claim", dim=DIM)
    mixed = mean_frame([a, b], DIM)
    assert sum(v * v for v in mixed) ** 0.5 == pytest.approx(1.0)
    assert frames.frame_cosine(mixed, a) > 0.9
    assert mean_frame([], DIM) == [0.0] * DIM


def test_witnesses_are_read_from_the_mention_edges() -> None:
    entity = _entity("Zeus")
    c1, c2 = _chunk("current_claim"), _chunk("disputed")
    table = witnesses_by_entity([_mention(c1, entity), _mention(c2, entity)])
    assert sorted(table[str(entity.id)]) == sorted([str(c1.id), str(c2.id)])


def test_a_dry_run_changes_nothing(tmp_path: Path) -> None:
    runtime = _build(tmp_path, {"Aphrodite": ["disputed"]})
    result = run_frame_promotion(runtime, apply=False)
    assert result.promoted == 1
    assert all(v == 0.0 for v in next(iter(runtime.nodes.iter_consolidated())).frame_vector)
    assert result.audit_id


def test_running_twice_promotes_nothing_the_second_time(tmp_path: Path) -> None:
    runtime = _build(tmp_path, {"Aphrodite": ["disputed"], "Zeus": ["current_claim"]})
    first = run_frame_promotion(runtime)
    second = run_frame_promotion(runtime)
    assert first.promoted == 2
    assert second.promoted == 0 and second.unchanged == 2


def test_the_action_name_is_stable() -> None:
    assert FRAME_PROMOTION_ACTION == "mesh_frame_promotion"
