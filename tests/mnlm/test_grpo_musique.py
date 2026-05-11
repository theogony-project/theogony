"""
Tests for Phase B micro-GRPO and Mini-MuSiQue evaluator.
"""

from __future__ import annotations

from pathlib import Path

import torch

from theogony.agents.mnlm.dto import MeshInput, MeshInputContext, MeshInputNode
from theogony.agents.mnlm.graph_projector import GraphProjector
from theogony.agents.mnlm.grpo import MicroGRPOTrainer, compute_start_vs_end_reward
from theogony.agents.mnlm.musique import MiniMuSiQue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_mesh_input() -> MeshInput:
    import uuid

    nid = f"AKA-{uuid.uuid4().hex[:12]}"
    return MeshInput(
        run_id="test",
        call_id="test",
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
        stamped_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc,
        ),
    )


def _dummy_probe_set(n: int = 10) -> list[tuple[MeshInput, list[float]]]:
    return [(_dummy_mesh_input(), [0.1] * 384) for _ in range(n)]


# ---------------------------------------------------------------------------
# Micro-GRPO
# ---------------------------------------------------------------------------


def test_grpo_initializes() -> None:
    proj = GraphProjector()
    trainer = MicroGRPOTrainer(proj, num_episodes=10, k_samples=4)
    assert trainer._num_episodes == 10
    assert trainer._k == 4


def test_grpo_training_runs(tmp_path: Path) -> None:
    proj = GraphProjector()
    trainer = MicroGRPOTrainer(proj, num_episodes=20, k_samples=4, log_interval=10)
    probe_set = _dummy_probe_set(5)
    log_path = tmp_path / "phase_b_reward.jsonl"
    history = trainer.train(probe_set, device=torch.device("cpu"), output_path=str(log_path))

    assert len(history) > 0
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) > 0


def test_grpo_compute_start_vs_end() -> None:
    history = [{"episode": i, "mean_reward": float(i) / 100} for i in range(50)]
    result = compute_start_vs_end_reward(history, window=10)
    assert result["rising"]


# ---------------------------------------------------------------------------
# Mini-MuSiQue
# ---------------------------------------------------------------------------


def test_musique_generates_50_questions() -> None:
    mq = MiniMuSiQue(num_questions=50)
    questions = mq.generate()
    assert len(questions) == 50


def test_musique_every_third_is_cross_domain() -> None:
    mq = MiniMuSiQue(num_questions=30)
    questions = mq.generate()
    cross = sum(1 for q in questions if q["is_cross_domain"])
    assert 5 <= cross <= 15  # ~1/3 cross-domain


def test_musique_baseline_accuracy() -> None:
    mq = MiniMuSiQue(num_questions=10)
    mq.generate()
    results = [
        {"question_id": i, "is_correct": i < 7, "is_direction_critical": i < 5} for i in range(10)
    ]
    overall = mq.compute_baseline_accuracy(results)
    assert overall["accuracy"] == 0.7  # 7/10
    directional = mq.compute_baseline_accuracy(results, direction_critical_only=True)
    assert directional["accuracy"] == 1.0  # all 5 direction-critical correct


def test_musique_evaluate_writes_output(tmp_path: Path) -> None:
    from theogony.agents.mnlm.graphkv_adapter import GraphKVAdapter
    from theogony.agents.mnlm.lfm_gae_decoder import LFMGAEDecoder
    from theogony.agents.mnlm.resonant_runner import SubstrateResonantRunner

    proj = GraphProjector()
    kv = GraphKVAdapter()
    decoder = LFMGAEDecoder()
    runner = SubstrateResonantRunner(proj, kv, decoder)

    mq = MiniMuSiQue(num_questions=5)
    mq.generate()
    out = tmp_path / "mini_musique_results.json"
    result = mq.evaluate_mnlm(runner, output_path=str(out))

    assert out.exists()
    assert "overall_accuracy" in result
    assert "direction_critical_accuracy" in result
