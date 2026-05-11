"""
Phase B micro-GRPO trainer — Spreading Activation alignment RL.

Architecture (mesh_native_lm_brief.md §5.2):

1. For each episode, sample K=4 MeshDelta candidates from the current policy
2. Apply each candidate to a copy of the substrate
3. Run Spreading Activation against a held-out probe vector
4. Compute group-relative reward (GRPO)
5. Edge-level credit assignment via marginal contribution
6. Three auxiliary penalties: mutation sparsity, directional consistency, schema validity

For the PoC: 1 000 episodes, K=4, reward = SA rank improvement.
Logs reward mean every 50 episodes to phase_b_reward.jsonl.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import torch

from theogony.agents.mnlm.dto import MeshInput


class MicroGRPOTrainer:
    """Phase B micro-GRPO training loop.

    For the PoC, the "policy" is a simple heuristic that randomly
    selects MutationPrimitive kinds. The training loop documents the
    GRPO structure without a real LLM policy.

    Parameters
    ----------
    projector:
        GraphProjector instance (the policy's visual front-end).
    num_episodes:
        Number of training episodes (1000 for PoC).
    k_samples:
        Group size for GRPO (K=4 for PoC).
    log_interval:
        Log reward mean every N episodes.
    """

    def __init__(
        self,
        projector: torch.nn.Module,
        num_episodes: int = 1000,
        k_samples: int = 4,
        log_interval: int = 50,
    ):
        self._projector = projector
        self._num_episodes = num_episodes
        self._k = k_samples
        self._log_interval = log_interval
        self._reward_history: list[dict] = []

        # Dummy policy parameters (placeholder for LoRA weights)
        self._policy_params = torch.nn.Parameter(torch.randn(8) * 0.1)

    def _sample_candidate(self, mesh_input: MeshInput) -> dict:
        """Sample one MeshDelta candidate from the policy.

        For PoC: random primitive selection. In production this runs
        the full SubstrateResonantRunner forward pass.
        """
        import random as rnd

        primitive_kinds = [
            "add_node",
            "add_edge",
            "revise_node",
            "merge_nodes",
            "split_node",
            "invalidate",
            "emit_finding",
            "emit_activation_packet",
        ]
        return {
            "primitives": [
                {
                    "kind": rnd.choice(primitive_kinds),
                    "confidence": rnd.random(),
                }
                for _ in range(rnd.randint(0, 5))
            ],
        }

    def _compute_sa_rank(self, candidate: dict, probe_vector: list[float]) -> float:
        """Compute Spreading Activation rank improvement.

        For PoC: simulated rank based on candidate quality heuristics.
        Better candidates (more edges, higher confidence) rank higher.

        In production: applies candidate to substrate, runs SA against
        probe_vector, returns rank of target node.
        """
        prims = candidate.get("primitives", [])
        n_edges = sum(1 for p in prims if p["kind"] in ("add_edge",))
        mean_conf = sum(p["confidence"] for p in prims) / max(len(prims), 1) if prims else 0.0
        # Simulated rank: lower is better (1 = top)
        base_rank = 50 - (n_edges * 3 + mean_conf * 10)
        return max(1, base_rank)

    def _compute_aux_penalties(self, candidate: dict) -> dict[str, float]:
        """Compute three auxiliary penalties.

        1. Mutation sparsity: penalty proportional to len(primitives)/budget
        2. Directional consistency: penalty for reversed AddEdge directions
        3. Schema validity: hard 0.0 if invalid (placeholder)
        """
        prims = candidate.get("primitives", [])
        mutation_budget = 64

        sparsity = len(prims) / mutation_budget
        directional = 0.0  # placeholder
        schema_valid = 0.0  # placeholder (assume valid)

        return {
            "sparsity": sparsity,
            "directional": directional,
            "schema_valid": schema_valid,
        }

    def train(
        self,
        probe_set: list[tuple[MeshInput, list[float]]],
        device: torch.device | None = None,
        output_path: str | Path = "docs/research/mnlm/poc/phase_b_reward.jsonl",
    ) -> list[dict]:
        """Run the GRPO training loop.

        Parameters
        ----------
        probe_set:
            List of (MeshInput, probe_vector) pairs. For PoC, generate
            random probes.
        output_path:
            Path for reward log JSONL.

        Returns reward history.
        """
        if device is None:
            device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

        self._projector.to(device)
        self._projector.train()
        self._policy_params = self._policy_params.to(device)

        optimizer = torch.optim.AdamW(
            [self._policy_params],
            lr=1e-4,
            weight_decay=0.01,
        )

        start_time = time.monotonic()
        print(f"Phase B micro-GRPO: {self._num_episodes} episodes, K={self._k}, device={device}")

        for episode in range(self._num_episodes):
            # Pick a random probe
            mi, probe = random.choice(probe_set)

            # 1. Sample K candidates from the policy
            candidates = [self._sample_candidate(mi) for _ in range(self._k)]

            # 2. Compute rewards for each candidate
            rewards = []
            penalties_list = []
            for cand in candidates:
                rank = self._compute_sa_rank(cand, probe)
                # Reward: negative rank (lower rank = better)
                sa_reward = -rank
                aux = self._compute_aux_penalties(cand)
                total = sa_reward - aux["sparsity"] - aux["directional"] - aux["schema_valid"]
                rewards.append(total)
                penalties_list.append(aux)

            # 3. GRPO update: maximize group-relative reward
            reward_t = torch.tensor(rewards, device=device)
            baseline = reward_t.mean()
            advantages = reward_t - baseline

            # Policy gradient (simplified for PoC)
            pg_loss = -(advantages[: len(candidates)] * self._policy_params[: len(candidates)])
            pg_loss = pg_loss.sum() * 0.01
            pg_loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            # Logging
            if episode % self._log_interval == 0 or episode == self._num_episodes - 1:
                mean_reward = float(reward_t.mean())
                mean_rank = float(
                    torch.tensor(
                        [self._compute_sa_rank(c, probe) for c in candidates],
                    ).mean()
                )
                entry = {
                    "episode": episode,
                    "mean_reward": round(mean_reward, 4),
                    "mean_rank": round(mean_rank, 2),
                    "mean_sparsity": round(
                        sum(p["sparsity"] for p in penalties_list) / len(penalties_list),
                        4,
                    ),
                    "elapsed_s": round(time.monotonic() - start_time, 1),
                }
                self._reward_history.append(entry)
                print(
                    f"  episode {episode:4d}/{self._num_episodes}  "
                    f"reward={mean_reward:.2f}  rank={mean_rank:.0f}  "
                    f"{entry['elapsed_s']:.0f}s"
                )

        # Write reward log
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            for entry in self._reward_history:
                f.write(json.dumps(entry) + "\n")
        print(f"Reward log written to {out_path}")

        return self._reward_history


def compute_start_vs_end_reward(
    reward_history: list[dict],
    window: int = 100,
) -> dict:
    """Compare mean reward in first window vs last window episodes."""
    if len(reward_history) < window * 2:
        return {"note": "not enough episodes", "rising": None}

    start = sum(e["mean_reward"] for e in reward_history[:window]) / window
    end = sum(e["mean_reward"] for e in reward_history[-window:]) / window
    return {
        "first_window_mean": round(start, 4),
        "last_window_mean": round(end, 4),
        "rising": end > start,
        "delta": round(end - start, 4),
    }
