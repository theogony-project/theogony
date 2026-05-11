"""
PoC smoke test — Week 2: end-to-end forward pass.

Tests that:
- GraphProjector produces prefix tokens without NaN
- GraphKVAdapter produces valid masks and biases
- LFM-GAE decoder produces a MeshDelta-compatible dict
- SubstrateResonantRunner runs a full cycle
- No tensor dimension errors
- MeshDelta-valid output
"""

from __future__ import annotations

from pathlib import Path

import torch

from theogony.agents.mnlm.dto import (
    MeshDelta,
    MeshInput,
    MeshInputContext,
    MeshInputEdge,
    MeshInputNode,
)
from theogony.agents.mnlm.graph_projector import GraphProjector
from theogony.agents.mnlm.graphkv_adapter import GraphKVAdapter
from theogony.agents.mnlm.lfm_gae_decoder import LFMGAEDecoder
from theogony.agents.mnlm.resonant_runner import SubstrateResonantRunner

# ---------------------------------------------------------------------------
# Fixtures: toy MeshInput
# ---------------------------------------------------------------------------

SAMPLE_NODE = MeshInputNode(
    node_id="AKA-sampletest01",
    embedding=[0.1] * 384,
    activation_weight=0.8,
    node_type="concept",
    layer="ephemera",
    source_anchor="https://en.wikipedia.org/wiki/Test#s1",
)

SAMPLE_EDGE = MeshInputEdge(
    edge_id="EDGE-sampletest01",
    source_id="AKA-sampletest01",
    target_id="AKA-sampletest02",
    relation_codebook_id=42,
    nuance=[0.0] * 32,
    weight=0.9,
)


def _toy_mesh_input(nodes: int = 5, edges: int = 4) -> MeshInput:
    """Build a small toy MeshInput for smoke testing."""
    import uuid

    node_ids = [f"AKA-{uuid.uuid4().hex[:12]}" for _ in range(nodes)]

    nodes_list = [
        MeshInputNode(
            node_id=nid,
            embedding=[float(i + j) / 384 for j in range(384)],
            activation_weight=0.5 + (i / nodes) * 0.5,
            node_type="concept",
            source_anchor="https://test.org#s1",
        )
        for i, nid in enumerate(node_ids)
    ]

    edge_list: list[MeshInputEdge] = []
    for i in range(min(edges, nodes - 1)):
        edge_list.append(
            MeshInputEdge(
                edge_id=f"EDGE-{uuid.uuid4().hex[:12]}",
                source_id=node_ids[i],
                target_id=node_ids[(i + 1) % nodes],
                relation_codebook_id=i % 512,
                nuance=[0.0] * 32,
                weight=0.8,
            )
        )

    return MeshInput(
        schema_version="mnlm-input/1",
        run_id="poc-smoke-test-run",
        call_id="poc-smoke-test-call",
        nodes=nodes_list,
        edges=edge_list,
        active_node_ids=[node_ids[0]],
        context=MeshInputContext(
            role="generic",
            embedding_model_id="BAAI/bge-small-en-v1.5",
        ),
        stamped_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


# ---------------------------------------------------------------------------
# GraphProjector
# ---------------------------------------------------------------------------


def test_graph_projector_no_nan() -> None:
    """Forward pass produces prefix tokens without NaN."""
    proj = GraphProjector()
    mi = _toy_mesh_input(nodes=5, edges=4)
    inputs = proj.from_mesh_input(mi)
    prefix = proj.forward(**inputs)

    assert not torch.isnan(prefix).any(), "Projector output contains NaN"
    assert prefix.size(0) == 1  # batch
    assert prefix.size(-1) == 1536  # llm_dim
    print(f"Projector output shape: {prefix.shape}")


def test_graph_projector_empty_graph() -> None:
    """Empty graph (no edges) should still produce valid prefixes."""
    proj = GraphProjector()
    mi = _toy_mesh_input(nodes=3, edges=0)
    inputs = proj.from_mesh_input(mi)
    prefix = proj.forward(**inputs)
    assert not torch.isnan(prefix).any()


def test_graph_projector_single_node() -> None:
    """Single node graph produces valid prefix."""
    proj = GraphProjector()
    mi = _toy_mesh_input(nodes=1, edges=0)
    inputs = proj.from_mesh_input(mi)
    prefix = proj.forward(**inputs)
    assert not torch.isnan(prefix).any()
    assert prefix.shape == (1, 32, 1536)


# ---------------------------------------------------------------------------
# GraphKVAdapter
# ---------------------------------------------------------------------------


def test_graphkv_block_mask() -> None:
    """Block mask allows self-attention and connected nodes."""
    adapter = GraphKVAdapter()
    edge_indices = torch.tensor([[0, 1], [2, 3]], dtype=torch.long)
    mask = adapter.build_block_mask(num_nodes=5, edge_indices=edge_indices)

    assert mask.shape == (5, 5)
    # Self-loops should be allowed (0.0)
    assert mask[0, 0] == 0.0
    assert mask[3, 3] == 0.0
    # Connected nodes should be allowed
    assert mask[0, 2] == 0.0
    assert mask[2, 0] == 0.0  # bidirectional
    assert mask[1, 3] == 0.0  # Unconnected nodes should be blocked
    assert mask[0, 3] == float("-inf")


def test_graphkv_edge_bias() -> None:
    """Edge bias has correct shape (N, N, num_heads)."""
    adapter = GraphKVAdapter(num_heads=12)
    edge_indices = torch.tensor([[0, 1], [2, 3]], dtype=torch.long)
    edge_types = torch.tensor([7, 42], dtype=torch.long)

    bias = adapter.build_edge_bias(
        num_nodes=5,
        edge_indices=edge_indices,
        edge_types=edge_types,
    )
    assert bias.shape == (5, 5, 12)
    assert not torch.isnan(bias).any()


def test_graphkv_no_edges() -> None:
    """No edges → all-zero bias, all-blocked mask except self-loops."""
    adapter = GraphKVAdapter()
    empty_idx = torch.zeros(2, 0, dtype=torch.long)
    mask = adapter.build_block_mask(num_nodes=3, edge_indices=empty_idx)
    assert mask[0, 1] == float("-inf")
    assert mask[0, 0] == 0.0


# ---------------------------------------------------------------------------
# LFM-GAE Decoder
# ---------------------------------------------------------------------------


def test_lfm_gae_decodes_placeholder() -> None:
    """LFM-GAE decoder produces a placeholder dict."""
    decoder = LFMGAEDecoder(latent_dim=768, conditioning_dim=1536)
    dummy_llm_state = torch.randn(1, 1536)
    result = decoder.decode(dummy_llm_state)

    assert result["trajectory_converged"] is True
    assert isinstance(result["integration_steps"], int)
    assert result["integration_steps"] > 0


def test_lfm_gae_placeholder_mesh_delta() -> None:
    """Placeholder MeshDelta dict is valid."""
    decoder = LFMGAEDecoder()
    delta_dict = decoder.make_placeholder_mesh_delta()
    delta = MeshDelta.model_validate(delta_dict)
    assert delta.schema_version == "mnlm-output/1"
    assert delta.trajectory.converged


# ---------------------------------------------------------------------------
# SubstrateResonantRunner
# ---------------------------------------------------------------------------


def test_resonant_runner_end_to_end() -> None:
    """Full pass: MeshInput → projector → recurrence → decoder."""
    proj = GraphProjector()
    kv = GraphKVAdapter()
    decoder = LFMGAEDecoder()
    runner = SubstrateResonantRunner(
        projector=proj,
        graphkv=kv,
        decoder=decoder,
        sa_engine=None,
        sa_interleave_K=3,
        latent_step_cap=8,
    )

    mi = _toy_mesh_input(nodes=5, edges=4)
    result = runner.run(mi)

    # Validate against MeshDelta schema
    delta = MeshDelta.model_validate(result)
    assert delta.produced_at is not None
    assert delta.latent_steps_used <= 8
    assert delta.sa_cycles_used >= 0
    assert delta.halted_reason in (
        "stable",
        "lfm_converged",
        "step_cap",
        "budget_exhausted",
        "lfm_failed_convergence",
        "decoder_constraint_violation",
        "error",
    )


def test_resonant_runner_smoke_trace(tmp_path: Path) -> None:
    """End-to-end trace for pipeline validation.

    This test produces the poc_pipeline_trace.json that the PoC brief
    requires in its output artefacts.
    """
    import json

    proj = GraphProjector()
    kv = GraphKVAdapter()
    decoder = LFMGAEDecoder()
    runner = SubstrateResonantRunner(
        projector=proj,
        graphkv=kv,
        decoder=decoder,
        sa_engine=None,
    )

    mi = _toy_mesh_input(nodes=5, edges=4)
    result = runner.run(mi)

    # Assert all required fields are present
    assert "schema_version" in result
    assert "primitives" in result
    assert "trajectory" in result
    assert "halted_reason" in result

    # Validate against MeshDelta
    delta = MeshDelta.model_validate(result)
    assert len(delta.provenance_hash) >= 16

    # Write trace file
    trace_path = tmp_path / "poc_pipeline_trace.json"
    trace_path.write_text(json.dumps(result, indent=2, default=str))
    assert trace_path.exists()
    print(f"Trace written to {trace_path}")
