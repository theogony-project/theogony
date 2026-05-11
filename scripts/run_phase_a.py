#!/usr/bin/env python3
"""
Phase A micro-training runner — standalone for MPS execution.

Runs 5000-step training on all available MeshInputs, logs loss every
100 steps to docs/research/mnlm/poc/phase_a_loss.jsonl.

Usage::

    python scripts/run_phase_a.py [--steps 5000] [--batch-size 4]

On M4 Pro MPS: ~2-4 hours for 5000 steps.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase A micro-training")
    parser.add_argument("--steps", type=int, default=5000, help="Training steps (default: 5000)")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size (default: 4)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (default: 1e-4)")
    parser.add_argument("--device", type=str, default="mps", help="Device: mps, cpu, cuda")
    args = parser.parse_args()

    from theogony.agents.mnlm.graph_projector import GraphProjector
    from theogony.agents.mnlm.training import PhaseADataset, PhaseATrainer

    # Determine device
    device_name = args.device
    if device_name == "mps" and not torch.backends.mps.is_available():
        print("WARNING: MPS not available, falling back to CPU")
        device_name = "cpu"
    device = torch.device(device_name)

    # Load dataset
    mesh_dir = Path("docs/research/mnlm/poc/mesh_inputs")
    if not mesh_dir.exists() or not any(mesh_dir.iterdir()):
        print(f"ERROR: No MeshInputs found in {mesh_dir}")
        print("Run the Kadmos crawl first — MeshInputs are produced automatically.")
        sys.exit(1)

    ds = PhaseADataset(str(mesh_dir))
    count = ds.load_all()
    print(f"Loaded {count} MeshInput samples from {mesh_dir}")

    if count == 0:
        print("ERROR: No valid samples loaded. Ensure MeshInputs exist.")
        sys.exit(1)

    # Train
    projector = GraphProjector()
    trainer = PhaseATrainer(
        projector=projector,
        lr=args.lr,
        num_steps=args.steps,
        batch_size=args.batch_size,
    )
    history = trainer.train(ds, device=device)

    # Summary
    if len(history) >= 2:
        start_loss = history[0]["loss"]
        end_loss = history[-1]["loss"]
        print(f"\nSummary:")
        print(f"  Start loss: {start_loss:.4f}")
        print(f"  End loss:   {end_loss:.4f}")
        print(f"  Delta:      {end_loss - start_loss:.4f}")
        print(f"  Monotonic:  {'YES' if history[-1]['loss'] < history[0]['loss'] else 'NO'}")


if __name__ == "__main__":
    main()
