"""
Tests for Phase A micro-training loop and Mini-DBB-20 synthesizer.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC
from pathlib import Path

import torch

from theogony.agents.mnlm.dbb20 import MiniDBB20
from theogony.agents.mnlm.graph_projector import GraphProjector
from theogony.agents.mnlm.training import PhaseADataset, PhaseATrainer

# ---------------------------------------------------------------------------
# Mini-DBB-20
# ---------------------------------------------------------------------------


def test_dbb20_generates_20_pairs() -> None:
    dbb = MiniDBB20()
    pairs = dbb.generate()
    assert len(pairs) == 20


def test_dbb20_each_pair_has_two_mesh_inputs() -> None:
    dbb = MiniDBB20()
    pairs = dbb.generate()
    for p in pairs:
        assert hasattr(p["mesh_input_a_to_b"], "nodes")
        assert hasattr(p["mesh_input_b_to_a"], "nodes")
        assert len(p["mesh_input_a_to_b"].nodes) == 2
        assert len(p["mesh_input_b_to_a"].nodes) == 2


def test_dbb20_random_baseline_is_around_50() -> None:
    dbb = MiniDBB20()
    acc = dbb.compute_random_baseline()
    assert 0.3 <= acc <= 0.7


def test_dbb20_results_serialization(tmp_path: Path) -> None:
    dbb = MiniDBB20()
    dbb.generate()
    from theogony.agents.mnlm.lfm_gae_decoder import LFMGAEDecoder
    from theogony.agents.mnlm.resonant_runner import SubstrateResonantRunner

    proj = GraphProjector()
    kv = __import__("importlib").import_module("theogony.agents.mnlm.graphkv_adapter")
    decoder = LFMGAEDecoder()
    runner = SubstrateResonantRunner(proj, kv.GraphKVAdapter(), decoder)

    out = tmp_path / "mini_dbb20_results.json"
    dbb.evaluate(runner, output_path=str(out))
    assert out.exists()
    data = json.loads(out.read_text())
    assert "accuracy" in data
    assert "results" in data
    assert len(data["results"]) == 40  # 20 pairs × 2 directions


# ---------------------------------------------------------------------------
# Phase A dataset
# ---------------------------------------------------------------------------


def test_phase_a_dataset_empty_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ds = PhaseADataset(tmp)
        count = ds.load_all()
        assert count == 0


def test_phase_a_dataset_single_sample(tmp_path: Path) -> None:
    import uuid
    from datetime import datetime

    from theogony.agents.mnlm.dto import (
        MeshInput,
        MeshInputContext,
        MeshInputNode,
    )

    nid = f"AKA-{uuid.uuid4().hex[:12]}"
    mi = MeshInput(
        schema_version="mnlm-input/1",
        run_id="test-run",
        call_id="test-call",
        nodes=[
            MeshInputNode(
                node_id=nid,
                embedding=[0.1] * 384,
                activation_weight=0.8,
                node_type="concept",
                source_anchor="test",
            ),
        ],
        edges=[],
        active_node_ids=[nid],
        context=MeshInputContext(role="generic", embedding_model_id="m"),
        stamped_at=datetime.now(UTC),
    )
    p = tmp_path / "test_mesh_input.json"
    p.write_text(mi.model_dump_json(indent=2))

    ds = PhaseADataset(tmp_path)
    count = ds.load_all()
    assert count == 1
    assert ds.size == 1


# ---------------------------------------------------------------------------
# Phase A training
# ---------------------------------------------------------------------------


def test_phase_a_trainer_forward_pass(tmp_path: Path) -> None:
    """Trainer can run a minimal forward+backward pass without error."""
    import uuid
    from datetime import datetime

    from theogony.agents.mnlm.dto import (
        MeshInput,
        MeshInputContext,
        MeshInputNode,
    )

    nid = f"AKA-{uuid.uuid4().hex[:12]}"
    mi = MeshInput(
        schema_version="mnlm-input/1",
        run_id="train-test",
        call_id="train-test-call",
        nodes=[
            MeshInputNode(
                node_id=nid,
                embedding=[float(i) / 384 for i in range(384)],
                activation_weight=0.8,
                node_type="concept",
                source_anchor="train-test",
            ),
        ],
        edges=[],
        active_node_ids=[nid],
        context=MeshInputContext(role="generic", embedding_model_id="m"),
        stamped_at=datetime.now(UTC),
    )
    p = tmp_path / "train_mesh.json"
    p.write_text(mi.model_dump_json(indent=2))

    ds = PhaseADataset(tmp_path)
    ds.load_all()

    proj = GraphProjector()
    trainer = PhaseATrainer(
        projector=proj,
        num_steps=10,
        batch_size=2,
        log_interval=5,
    )
    device = torch.device("cpu")
    loss_path = tmp_path / "phase_a_loss.jsonl"
    history = trainer.train(ds, device=device, output_path=str(loss_path))

    assert len(history) > 0
    assert loss_path.exists()
    lines = loss_path.read_text().strip().split("\n")
    assert len(lines) > 0
    last = json.loads(lines[-1])
    assert "loss" in last
    assert "step" in last


def test_phase_a_dataset_get_batch(tmp_path: Path) -> None:
    """get_batch produces correctly shaped tensors."""
    import uuid
    from datetime import datetime

    from theogony.agents.mnlm.dto import (
        MeshInput,
        MeshInputContext,
        MeshInputNode,
    )

    for i in range(3):
        nid = f"AKA-{uuid.uuid4().hex[:12]}"
        mi = MeshInput(
            schema_version="mnlm-input/1",
            run_id=f"batch-test-{i}",
            call_id="batch-call",
            nodes=[
                MeshInputNode(
                    node_id=nid,
                    embedding=[float(i + j) / 384 for j in range(384)],
                    activation_weight=0.8,
                    node_type="concept",
                    source_anchor=f"batch-{i}",
                ),
            ],
            edges=[],
            active_node_ids=[nid],
            context=MeshInputContext(role="generic", embedding_model_id="m"),
            stamped_at=datetime.now(UTC),
        )
        p = tmp_path / f"batch_{i}.json"
        p.write_text(mi.model_dump_json(indent=2))

    ds = PhaseADataset(tmp_path)
    ds.load_all()
    assert ds.size == 3

    inputs, targets = ds.get_batch([0, 1, 2], torch.device("cpu"))
    assert inputs["node_embeddings"].shape[0] == 3
    assert targets["primitive_kind"].shape[0] == 3
