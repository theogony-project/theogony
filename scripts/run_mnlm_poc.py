#!/usr/bin/env python3
"""
MNLM PoC Run — chains all evaluators and training passes.

Usage::

    python scripts/run_mnlm_poc.py [--phase-a] [--phase-b] [--musique] [--monkey3] [--all]

Runs the entire PoC evaluation stack in order:

1. Phase A micro-training (5000 steps, AdamW, cosine LR)
2. Mini-DBB-20 evaluation
3. Phase B micro-GRPO (1000 episodes, K=4)
4. Reward curve plot
5. Mini-MuSiQue evaluation
6. Mini-Monkey-3 rating sheet generation

All results are written to docs/research/mnlm/poc/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="MNLM PoC evaluation runner")
    parser.add_argument("--phase-a", action="store_true", help="Run Phase A micro-training")
    parser.add_argument("--phase-b", action="store_true", help="Run Phase B micro-GRPO")
    parser.add_argument("--dbb20", action="store_true", help="Run Mini-DBB-20 evaluation")
    parser.add_argument("--musique", action="store_true", help="Run Mini-MuSiQue evaluation")
    parser.add_argument("--monkey3", action="store_true", help="Generate Mini-Monkey-3 rating sheet")
    parser.add_argument("--reward-plot", action="store_true", help="Generate reward curve plot")
    parser.add_argument("--all", action="store_true", help="Run all evaluations")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    run_all = args.all

    if run_all or args.phase_a:
        from theogony.agents.mnlm.graph_projector import GraphProjector
        from theogony.agents.mnlm.training import PhaseADataset, PhaseATrainer
        import torch

        print("\n=== Phase A: Micro-training ===")
        ds = PhaseADataset("docs/research/mnlm/poc/mesh_inputs")
        loaded = ds.load_all()
        if loaded == 0:
            print("WARNING: No MeshInputs found. Skipping Phase A.")
        else:
            proj = GraphProjector()
            trainer = PhaseATrainer(proj, num_steps=5000, batch_size=4)
            device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
            trainer.train(ds, device=device)

    if run_all or args.dbb20:
        from theogony.agents.mnlm.dbb20 import MiniDBB20
        from theogony.agents.mnlm.graph_projector import GraphProjector
        from theogony.agents.mnlm.graphkv_adapter import GraphKVAdapter
        from theogony.agents.mnlm.lfm_gae_decoder import LFMGAEDecoder
        from theogony.agents.mnlm.resonant_runner import SubstrateResonantRunner

        print("\n=== Mini-DBB-20: Directional binding ===")
        proj = GraphProjector()
        kv = GraphKVAdapter()
        decoder = LFMGAEDecoder()
        runner = SubstrateResonantRunner(proj, kv, decoder)

        dbb = MiniDBB20()
        dbb.generate()
        dbb.evaluate(runner)

    if run_all or args.phase_b:
        from theogony.agents.mnlm.graph_projector import GraphProjector
        from theogony.agents.mnlm.grpo import MicroGRPOTrainer
        from theogony.agents.mnlm.training import PhaseADataset
        import torch

        print("\n=== Phase B: Micro-GRPO ===")
        ds = PhaseADataset("docs/research/mnlm/poc/mesh_inputs")
        ds.load_all()

        # Build probe set from MeshInputs
        probe_set = [(s["mesh_input"], [0.1] * 384) for s in ds._samples[:50]]

        proj = GraphProjector()
        trainer = MicroGRPOTrainer(proj, num_episodes=1000, k_samples=4)
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        trainer.train(probe_set, device=device)

    if run_all or args.reward_plot:
        print("\n=== Reward curve plot ===")
        _generate_reward_plot()

    if run_all or args.musique:
        from theogony.agents.mnlm.musique import MiniMuSiQue

        print("\n=== Mini-MuSiQue: Multi-hop QA ===")
        mq = MiniMuSiQue(num_questions=50)
        mq.generate()
        # Without a real MNLM, this runs the evaluate_mnlm stub
        mq.evaluate_mnlm(None)

    if run_all or args.monkey3:
        from theogony.agents.mnlm.monkey3 import MiniMonkey3

        print("\n=== Mini-Monkey-3: Rating sheet ===")
        m3 = MiniMonkey3()
        m3.generate_rating_sheet()

    print("\nDone. All results in docs/research/mnlm/poc/")


def _generate_reward_plot() -> None:
    """Generate poc_reward_curve.png from phase_b_reward.jsonl."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    reward_path = Path("docs/research/mnlm/poc/phase_b_reward.jsonl")
    if not reward_path.exists():
        print(f"  SKIP: {reward_path} not found (run --phase-b first)")
        return

    episodes = []
    rewards = []
    with open(reward_path) as f:
        for line in f:
            import json
            entry = json.loads(line.strip())
            episodes.append(entry["episode"])
            rewards.append(entry["mean_reward"])

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(episodes, rewards, linewidth=1.5, label="Mean reward")
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)

    # Rolling average
    window = 50
    if len(rewards) >= window:
        import numpy as np
        rolling = np.convolve(rewards, np.ones(window) / window, mode="valid")
        ax.plot(
            episodes[window - 1:],
            rolling,
            linewidth=2,
            color="red",
            label=f"{window}-episode rolling avg",
        )

    ax.set_xlabel("Episode")
    ax.set_ylabel("Mean reward")
    ax.set_title("Phase B micro-GRPO reward curve")
    ax.legend()
    ax.grid(True, alpha=0.3)

    out_path = Path("docs/research/mnlm/poc/poc_reward_curve.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"  Reward curve saved to {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
