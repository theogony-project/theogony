"""
Tests for MNLM Pydantic DTOs (mesh_native_lm_brief.md §4.1–4.2).

Covers:
- Round-trip JSON serialisation for MeshInput, MeshDelta, all primitives
- extra="forbid" enforcement
- Discriminator-based sealed union for MutationPrimitive
- MeshInput graph-integrity model_validator
- TrajectoryMetadata field validation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.agents.mnlm.dto import (
    AddEdge,
    AddNode,
    EmitActivationPacket,
    EmitFinding,
    Invalidate,
    MergeNodes,
    MeshDelta,
    MeshInput,
    MeshInputContext,
    MeshInputEdge,
    MeshInputNode,
    MutationPrimitive,
    ReviseNode,
    SplitNode,
    TrajectoryMetadata,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc() -> datetime:
    return datetime.now(UTC)


def _sample_vector384() -> list[float]:
    return [0.1] * 384


def _sample_vector32() -> list[float]:
    return [0.1] * 32


def _sample_node(
    node_id: str = "AKA-testnode1234",
    embedding: list[float] | None = None,
    **kwargs: object,
) -> MeshInputNode:
    return MeshInputNode(
        node_id=node_id,
        embedding=embedding or _sample_vector384(),
        activation_weight=0.8,
        node_type="concept",
        layer="ephemera",
        source_anchor="https://en.wikipedia.org/wiki/Bernoulli%27s_principle#section-1",
        **kwargs,
    )


def _sample_edge(
    edge_id: str = "EDGE-testedge1234",
    source_id: str = "AKA-testnode1234",
    target_id: str = "AKA-testnode5678",
    **kwargs: object,
) -> MeshInputEdge:
    return MeshInputEdge(
        edge_id=edge_id,
        source_id=source_id,
        target_id=target_id,
        relation_codebook_id=42,
        nuance=_sample_vector32(),
        weight=0.9,
        **kwargs,
    )


def _minimal_mesh_input() -> MeshInput:
    return MeshInput(
        run_id="test-run-001",
        call_id="call-001",
        nodes=[_sample_node()],
        active_node_ids=["AKA-testnode1234"],
        context=MeshInputContext(
            role="generic",
            embedding_model_id="BAAI/bge-small-en-v1.5",
        ),
        stamped_at=_utc(),
    )


def _sample_trajectory() -> TrajectoryMetadata:
    return TrajectoryMetadata(
        trajectory_entropy=0.75,
        integration_steps=24,
        final_basin_id="basin-alpha",
        bifurcations_observed=1,
        max_curvature=2.3,
        converged=True,
    )


# ---------------------------------------------------------------------------
# MeshInputNode
# ---------------------------------------------------------------------------


def test_mesh_input_node_round_trip() -> None:
    n = _sample_node()
    loaded = MeshInputNode.model_validate_json(n.model_dump_json())
    assert loaded == n


def test_mesh_input_node_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        MeshInputNode(
            node_id="AKA-testnode1234",
            embedding=_sample_vector384(),
            activation_weight=0.5,
            source_anchor="test",
            bogus_field="bad",  # type: ignore[call-arg]
        )


def test_mesh_input_node_invalid_id_pattern() -> None:
    with pytest.raises(ValidationError):
        _sample_node(node_id="invalid-id-format")


def test_mesh_input_node_invalid_layer() -> None:
    with pytest.raises(ValidationError):
        MeshInputNode(
            node_id="AKA-testnode1234",
            embedding=_sample_vector384(),
            activation_weight=0.5,
            source_anchor="test",
            layer="hyperthymesia",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# MeshInputEdge
# ---------------------------------------------------------------------------


def test_mesh_input_edge_round_trip() -> None:
    e = _sample_edge()
    loaded = MeshInputEdge.model_validate_json(e.model_dump_json())
    assert loaded == e


def test_mesh_input_edge_codebook_range() -> None:
    with pytest.raises(ValidationError):
        MeshInputEdge(
            edge_id="EDGE-testedge1234",
            source_id="AKA-testnode1234",
            target_id="AKA-testnode5678",
            relation_codebook_id=999,  # >= 512
            nuance=_sample_vector32(),
            weight=0.9,
        )


def test_mesh_input_edge_invalid_id_pattern() -> None:
    with pytest.raises(ValidationError):
        _sample_edge(edge_id="bad-id-format")


# ---------------------------------------------------------------------------
# MeshInputContext
# ---------------------------------------------------------------------------


def test_mesh_input_context_defaults() -> None:
    ctx = MeshInputContext(role="generic", embedding_model_id="test-model")
    assert ctx.mutation_budget == 64
    assert ctx.latent_step_cap == 16
    assert ctx.sa_interleave_K == 3
    assert ctx.sa_recurrence_top_k == 8


def test_mesh_input_context_invalid_role() -> None:
    with pytest.raises(ValidationError):
        MeshInputContext(role="argus", embedding_model_id="test-model")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MeshInput — graph integrity validator
# ---------------------------------------------------------------------------


def test_mesh_input_minimal() -> None:
    mi = _minimal_mesh_input()
    assert mi.schema_version == "mnlm-input/1"
    assert len(mi.nodes) == 1


def test_mesh_input_with_edges() -> None:
    mi = MeshInput(
        run_id="test-run-002",
        call_id="call-002",
        nodes=[
            _sample_node(node_id="AKA-nodea1234"),
            _sample_node(node_id="AKA-nodeb5678"),
        ],
        active_node_ids=["AKA-nodea1234"],
        edges=[
            _sample_edge(
                source_id="AKA-nodea1234",
                target_id="AKA-nodeb5678",
            ),
        ],
        context=MeshInputContext(
            role="generic",
            embedding_model_id="test-model",
        ),
        stamped_at=_utc(),
    )
    loaded = MeshInput.model_validate_json(mi.model_dump_json())
    assert len(loaded.nodes) == 2
    assert len(loaded.edges) == 1


def test_mesh_input_duplicate_nodes_rejected() -> None:
    with pytest.raises(ValueError, match="unique node_id"):
        MeshInput(
            run_id="r",
            call_id="c",
            nodes=[
                _sample_node(node_id="AKA-duplicate1234"),
                _sample_node(node_id="AKA-duplicate1234"),
            ],
            active_node_ids=["AKA-duplicate1234"],
            context=MeshInputContext(role="generic", embedding_model_id="m"),
            stamped_at=_utc(),
        )


def test_mesh_input_active_not_in_nodes_rejected() -> None:
    with pytest.raises(ValueError, match="active_node_ids"):
        MeshInput(
            run_id="r",
            call_id="c",
            nodes=[_sample_node(node_id="AKA-onlynode1234")],
            active_node_ids=["AKA-missingnode5678"],
            context=MeshInputContext(role="generic", embedding_model_id="m"),
            stamped_at=_utc(),
        )


def test_mesh_input_edge_orphan_rejected() -> None:
    with pytest.raises(ValueError, match="edge endpoint"):
        MeshInput(
            run_id="r",
            call_id="c",
            nodes=[_sample_node(node_id="AKA-onlynode1234")],
            active_node_ids=["AKA-onlynode1234"],
            edges=[
                _sample_edge(
                    source_id="AKA-onlynode1234",
                    target_id="AKA-missingnode5678",
                ),
            ],
            context=MeshInputContext(role="generic", embedding_model_id="m"),
            stamped_at=_utc(),
        )


# ---------------------------------------------------------------------------
# MutationPrimitive sealed union
# ---------------------------------------------------------------------------


def test_mutation_primitive_add_node() -> None:
    mp: MutationPrimitive = AddNode(
        op_id="op-001",
        proposed_node_id="AKA-newguy123456",
        embedding=_sample_vector384(),
        node_type="concept",
        source_anchor="https://example.org/page#s1",
    )
    assert mp.kind == "add_node"
    serialized = mp.model_dump_json()
    loaded = AddNode.model_validate_json(serialized)
    assert loaded.proposed_node_id == mp.proposed_node_id


def test_mutation_primitive_add_edge() -> None:
    mp: MutationPrimitive = AddEdge(
        op_id="op-002",
        edge_id="EDGE-newedge1234",
        source_id="AKA-testnode1234",
        target_id="AKA-testnode5678",
        relation_codebook_id=7,
        nuance=_sample_vector32(),
        weight=0.8,
    )
    assert mp.kind == "add_edge"


def test_mutation_primitive_revise_node() -> None:
    mp: MutationPrimitive = ReviseNode(
        op_id="op-003",
        target_node_id="AKA-oldnode1234",
        supersedes_node_id="AKA-oldversion5678",
        new_embedding=_sample_vector384(),
        revision_kind="update",
    )
    assert mp.kind == "revise_node"


def test_mutation_primitive_merge_nodes() -> None:
    mp: MutationPrimitive = MergeNodes(
        op_id="op-004",
        surviving_id="AKA-svr12345678",
        absorbed_ids=["AKA-abs1abcdef", "AKA-abs2bcdefg"],
        merged_embedding=_sample_vector384(),
    )
    assert mp.kind == "merge_nodes"


def test_mutation_primitive_split_node() -> None:
    mp: MutationPrimitive = SplitNode(
        op_id="op-005",
        original_id="AKA-orig12345678",
        child_node_ids=["AKA-ch1abcdef", "AKA-ch2bcdefg"],
        child_embeddings=[_sample_vector384(), _sample_vector384()],
    )
    assert mp.kind == "split_node"


def test_mutation_primitive_invalidate() -> None:
    mp: MutationPrimitive = Invalidate(
        op_id="op-006",
        target_node_id="AKA-dead12345678",
        reason_embedding=_sample_vector384(),
        finding_code="contradiction",
    )
    assert mp.kind == "invalidate"


def test_mutation_primitive_emit_finding() -> None:
    mp: MutationPrimitive = EmitFinding(
        op_id="op-007",
        finding_node_id="FIND-test123456",
        finding_type="echo_chamber",
        severity="medium",
    )
    assert mp.kind == "emit_finding"


def test_mutation_primitive_emit_activation_packet() -> None:
    mp: MutationPrimitive = EmitActivationPacket(
        op_id="op-008",
        packet_id="PKT-test123456",
        node_energy_deltas=[("AKA-testnode1234", 0.5)],
    )
    assert mp.kind == "emit_activation_packet"


def test_mutation_primitive_sealed_union_discriminator() -> None:
    """Verify each MutationPrimitive variant round-trips through MeshDelta validation."""
    test_data: list[tuple[dict, str]] = [
        (
            {
                "op_id": "1",
                "kind": "add_node",
                "proposed_node_id": "AKA-newguy123456",
                "embedding": _sample_vector384(),
                "node_type": "concept",
                "source_anchor": "s",
            },
            "add_node",
        ),
        (
            {
                "op_id": "2",
                "kind": "add_edge",
                "edge_id": "EDGE-newedge1234",
                "source_id": "AKA-testnode1234",
                "target_id": "AKA-testnode5678",
                "relation_codebook_id": 0,
                "nuance": _sample_vector32(),
            },
            "add_edge",
        ),
        (
            {
                "op_id": "3",
                "kind": "revise_node",
                "target_node_id": "AKA-oldnode1234",
                "supersedes_node_id": "AKA-oldver123456",
                "new_embedding": _sample_vector384(),
                "revision_kind": "update",
            },
            "revise_node",
        ),
        (
            {
                "op_id": "4",
                "kind": "merge_nodes",
                "surviving_id": "AKA-svr12345678",
                "absorbed_ids": ["AKA-ab1abcdef", "AKA-ab2bcdefg"],
                "merged_embedding": _sample_vector384(),
            },
            "merge_nodes",
        ),
        (
            {
                "op_id": "5",
                "kind": "split_node",
                "original_id": "AKA-orig12345678",
                "child_node_ids": ["AKA-ch1abcdef", "AKA-ch2bcdefg"],
                "child_embeddings": [_sample_vector384(), _sample_vector384()],
            },
            "split_node",
        ),
        (
            {
                "op_id": "6",
                "kind": "invalidate",
                "target_node_id": "AKA-dead12345678",
                "reason_embedding": _sample_vector384(),
                "finding_code": "contradiction",
            },
            "invalidate",
        ),
        (
            {
                "op_id": "7",
                "kind": "emit_finding",
                "finding_node_id": "FIND-test123456",
                "finding_type": "other",
            },
            "emit_finding",
        ),
        (
            {
                "op_id": "8",
                "kind": "emit_activation_packet",
                "packet_id": "PKT-test123456",
                "node_energy_deltas": [],
            },
            "emit_activation_packet",
        ),
    ]
    t = TrajectoryMetadata(
        trajectory_entropy=0.5,
        integration_steps=10,
        final_basin_id="b",
        converged=True,
    )
    for primitive_data, expected_kind in test_data:
        delta = MeshDelta(
            run_id="test-r",
            call_id="test-c",
            model_id="test-model",
            produced_at=_utc(),
            primitives=[primitive_data],
            trajectory=t,
            latent_steps_used=0,
            sa_cycles_used=0,
            halted_reason="stable",
            provenance_hash="abcdef1234567890abcdef12",
        )
        assert len(delta.primitives) == 1
        assert delta.primitives[0].kind == expected_kind


# ---------------------------------------------------------------------------
# TrajectoryMetadata
# ---------------------------------------------------------------------------


def test_trajectory_metadata_round_trip() -> None:
    t = _sample_trajectory()
    loaded = TrajectoryMetadata.model_validate_json(t.model_dump_json())
    assert loaded == t


def test_trajectory_metadata_entropy_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        TrajectoryMetadata(
            trajectory_entropy=-1.0,
            integration_steps=10,
            final_basin_id="b",
            converged=True,
        )


# ---------------------------------------------------------------------------
# MeshDelta
# ---------------------------------------------------------------------------


def test_mesh_delta_round_trip() -> None:
    delta = MeshDelta(
        run_id="test-run-001",
        call_id="call-001",
        model_id="Qwen/Qwen2.5-1.5B-Instruct",
        produced_at=_utc(),
        primitives=[
            EmitActivationPacket(
                op_id="op-001",
                packet_id="PKT-test123456",
                node_energy_deltas=[],
            ),
        ],
        trajectory=_sample_trajectory(),
        latent_steps_used=3,
        sa_cycles_used=1,
        halted_reason="stable",
        provenance_hash="abcd1234efgh5678ijklmnopqr",
    )
    loaded = MeshDelta.model_validate_json(delta.model_dump_json())
    assert loaded.schema_version == "mnlm-output/1"
    assert len(loaded.primitives) == 1
    assert loaded.latent_steps_used == 3


def test_mesh_delta_empty_primitives() -> None:
    """A MeshDelta with zero primitives is valid (e.g. no-op decision)."""
    delta = MeshDelta(
        run_id="test-run-002",
        call_id="call-002",
        model_id="Qwen/Qwen2.5-1.5B-Instruct",
        produced_at=_utc(),
        trajectory=_sample_trajectory(),
        latent_steps_used=0,
        sa_cycles_used=0,
        halted_reason="stable",
        provenance_hash="abcd1234efgh5678ijklmnopqr",
    )
    assert len(delta.primitives) == 0


def test_mesh_delta_invalid_halted_reason() -> None:
    with pytest.raises(ValidationError):
        MeshDelta(
            run_id="r",
            call_id="c",
            model_id="m",
            produced_at=_utc(),
            trajectory=_sample_trajectory(),
            latent_steps_used=0,
            sa_cycles_used=0,
            halted_reason="crashed",  # type: ignore[arg-type]
            provenance_hash="abcd1234efgh5678ijklmnopqr",
        )


def test_mesh_delta_provenance_hash_min_length() -> None:
    with pytest.raises(ValidationError):
        MeshDelta(
            run_id="r",
            call_id="c",
            model_id="m",
            produced_at=_utc(),
            trajectory=_sample_trajectory(),
            latent_steps_used=0,
            sa_cycles_used=0,
            halted_reason="stable",
            provenance_hash="tooshort",
        )


def test_mesh_delta_extra_rejected() -> None:
    with pytest.raises(ValidationError):
        MeshDelta(
            run_id="r",
            call_id="c",
            model_id="m",
            produced_at=_utc(),
            trajectory=_sample_trajectory(),
            latent_steps_used=0,
            sa_cycles_used=0,
            halted_reason="stable",
            provenance_hash="abcd1234efgh5678ijklmnopqr",
            bogus=True,  # type: ignore[call-arg]
        )
