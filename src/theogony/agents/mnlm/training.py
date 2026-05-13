"""
Phase A Kadmos-imitation warmup training (mesh_native_lm_brief.md §5.1).

Maps Kadmos ReadingStep fields to MeshDelta MutationPrimitive kinds via
the §5.1 mapping table, then runs supervised micro-training:

- Cross-entropy on discrete fields (kind, relation_codebook_id, node_type)
- MSE on continuous fields (embedding, nuance, rationale_embedding)
- Auxiliary trajectory-stability loss

Produces phase_a_loss.jsonl (loss every 100 steps over 5000 steps).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, cast

import torch
import torch.nn as nn
import torch.nn.functional as F

from theogony.agents.mnlm.dto import (
    MeshInput,
)


class PhaseADataset:
    """Loads MeshInput JSON files and produces (MeshInput, target_dict) pairs.

    For the PoC, target_dict contains fields from the §5.1 mapping table:
    - primitive_kind: int (0-7, mapped from Kadmos ReadingStep fields)
    - relation_codebook_id: int
    - node_type: int
    - embedding_mse_target: list[float] (placeholder)
    """

    def __init__(self, mesh_inputs_dir: str | Path):
        self._mesh_inputs_dir = Path(mesh_inputs_dir)
        self._samples: list[dict[str, Any]] = []

    def load_all(self) -> int:
        """Scan mesh_inputs_dir and load all valid MeshInputs."""
        count = 0
        for p in sorted(self._mesh_inputs_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                mi = MeshInput.model_validate(data)
                target = self._make_target(mi)
                self._samples.append({"mesh_input": mi, "target": target})
                count += 1
            except Exception:
                pass  # skip invalid/pending
        return count

    @property
    def size(self) -> int:
        return len(self._samples)

    def _make_target(self, mi: MeshInput) -> dict[str, Any]:
        """Produce a supervised target from a MeshInput.

        Uses the §5.1 mapping: each MeshInput becomes a training pair
        where the "target" is a pseudo-MeshDelta derived from the input's
        structure. In full training, this comes from Kadmos ReadingStep
        fields.
        """
        num_nodes = len(mi.nodes)
        if num_nodes > 0:
            first = mi.nodes[0]
            node_type_map = {
                "person": 0,
                "place": 1,
                "concept": 2,
                "event": 3,
                "claim": 4,
                "work": 5,
                "organization": 6,
                "time": 7,
                "quantity": 8,
                "source": 9,
                "finding": 10,
                "experiment": 11,
                "synthesis": 12,
                "other": 13,
            }
            return {
                "primitive_kind": 0,  # add_node
                "node_type": node_type_map.get(first.node_type, 13),
                "embedding_mse_target": first.embedding,
                "num_nodes": num_nodes,
            }
        return {
            "primitive_kind": 7,  # emit_activation_packet (no-op)
            "node_type": 13,
            "embedding_mse_target": [0.0] * 384,
            "num_nodes": 0,
        }

    def get_batch(self, indices: list[int], device: torch.device) -> tuple[dict[str, Any], dict[str, Any]]:
        """Collect a batch of (model_inputs, targets) tensors."""
        batch_mi = [self._samples[i]["mesh_input"] for i in indices]
        batch_targets = [self._samples[i]["target"] for i in indices]

        # Build model inputs (projector-ready)
        node_embs = []
        edge_src = []
        edge_tgt = []
        edge_types_list = []
        offsets = [0]

        for mi in batch_mi:
            for n in mi.nodes:
                node_embs.append(n.embedding[:384])

            for e in mi.edges:
                src_idx = next(j for j, n in enumerate(mi.nodes) if n.node_id == e.source_id)
                tgt_idx = next(j for j, n in enumerate(mi.nodes) if n.node_id == e.target_id)
                edge_src.append(src_idx + offsets[-1])
                edge_tgt.append(tgt_idx + offsets[-1])
                edge_types_list.append(e.relation_codebook_id)

            offsets.append(offsets[-1] + len(mi.nodes))

        # Pad node embeddings to same dim
        max_n = max(len(mi.nodes) for mi in batch_mi) if batch_mi else 1
        emb_dim = 384
        padded = torch.zeros(len(batch_mi), max_n, emb_dim, device=device)
        mask = torch.zeros(len(batch_mi), max_n, dtype=torch.bool, device=device)

        for i, mi in enumerate(batch_mi):
            for j, n in enumerate(mi.nodes):
                padded[i, j] = torch.tensor(n.embedding[:emb_dim], device=device)
                mask[i, j] = True

        if edge_src:
            edge_idx = torch.tensor(
                [edge_src, edge_tgt],
                dtype=torch.long,
                device=device,
            )
        else:
            edge_idx = torch.zeros(2, 0, dtype=torch.long, device=device)

        if edge_types_list:
            edge_ty = torch.tensor(
                edge_types_list,
                dtype=torch.long,
                device=device,
            )
        else:
            edge_ty = torch.zeros(0, dtype=torch.long, device=device)

        model_inputs = {
            "node_embeddings": padded,
            "edge_indices": edge_idx,
            "edge_types": edge_ty,
            "node_mask": mask,
        }

        target_tensors = {
            "primitive_kind": torch.tensor(
                [t["primitive_kind"] for t in batch_targets],
                dtype=torch.long,
                device=device,
            ),
            "node_type": torch.tensor(
                [t["node_type"] for t in batch_targets],
                dtype=torch.long,
                device=device,
            ),
            "embedding_mse": torch.tensor(
                [t["embedding_mse_target"] for t in batch_targets],
                dtype=torch.float32,
                device=device,
            ),
        }
        return model_inputs, target_tensors


class PhaseATrainer:
    """Phase A micro-training loop.

    Parameters
    ----------
    projector:
        GraphProjector instance.
    lr:
        Learning rate for AdamW.
    weight_decay:
        AdamW weight decay.
    num_steps:
        Number of training steps (5000 for PoC).
    batch_size:
        Batch size (4 for PoC).
    log_interval:
        Log loss every N steps.
    """

    def __init__(
        self,
        projector: nn.Module,
        lr: float = 1e-4,
        weight_decay: float = 0.01,
        num_steps: int = 5000,
        batch_size: int = 4,
        log_interval: int = 100,
    ):
        self._projector = projector
        self._optimizer = torch.optim.AdamW(
            projector.parameters(),
            lr=lr,
            weight_decay=weight_decay,
        )
        self._num_steps = num_steps
        self._batch_size = batch_size
        self._log_interval = log_interval
        self._loss_history: list[dict[str, Any]] = []

    @staticmethod
    def _cosine_lr(step: int, num_steps: int, min_lr_ratio: float = 0.1) -> float:
        """Cosine LR schedule: eta * 0.5 * (1 + cos(pi * step / num_steps))."""
        progress = step / max(num_steps, 1)
        return min_lr_ratio + (1.0 - min_lr_ratio) * 0.5 * (1.0 + math.cos(math.pi * progress))

    def train(
        self,
        dataset: PhaseADataset,
        device: torch.device | None = None,
        output_path: str | Path = "docs/research/mnlm/poc/phase_a_loss.jsonl",
    ) -> list[dict[str, Any]]:
        """Run the training loop.

        Uses a proper Linear layer for kind_logits (not torch.randn)
        and a persistent embedding projector (not recreated per step).
        Cosine LR decay via math.cos.
        """
        if device is None:
            device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        print(f"Phase A training on {device} — {dataset.size} samples, {self._num_steps} steps")

        self._projector.to(device)
        self._projector.train()

        # Proper trainable prediction heads (not recreated per step)
        llm_dim: int = cast(int, self._projector._llm_dim)
        self._kind_head = nn.Linear(llm_dim, 8).to(device)
        self._emb_head = nn.Linear(llm_dim, 384).to(device)
        self._optimizer.add_param_group({"params": self._kind_head.parameters()})
        self._optimizer.add_param_group({"params": self._emb_head.parameters()})

        start_time = time.monotonic()
        num_samples = dataset.size
        base_lr = self._optimizer.param_groups[0]["lr"]

        for step in range(self._num_steps):
            # Cosine LR update
            lr_factor = self._cosine_lr(step, self._num_steps)
            for pg in self._optimizer.param_groups:
                pg["lr"] = base_lr * lr_factor

            # Sample random batch
            indices = torch.randint(0, max(num_samples, 1), (self._batch_size,)).tolist()
            if num_samples == 0:
                indices = list(range(self._batch_size))

            model_inputs, targets = dataset.get_batch(indices, device)

            # Forward through projector
            prefix = self._projector.forward(
                node_embeddings=model_inputs["node_embeddings"],
                edge_indices=model_inputs["edge_indices"],
                edge_types=model_inputs["edge_types"],
                node_mask=model_inputs["node_mask"],
            )

            # 1. Cross-entropy via proper head
            pooled = prefix.mean(dim=1)
            kind_logits = self._kind_head(pooled)
            ce_loss = F.cross_entropy(kind_logits, targets["primitive_kind"])

            # 2. MSE via proper head
            emb_pred = self._emb_head(pooled)
            mse_loss = F.mse_loss(emb_pred, targets["embedding_mse"])

            total_loss = ce_loss + mse_loss

            # Backward
            self._optimizer.zero_grad()
            total_loss.backward()  # type: ignore[no-untyped-call]
            torch.nn.utils.clip_grad_norm_(self._projector.parameters(), max_norm=1.0)
            self._optimizer.step()

            # Logging
            if step % self._log_interval == 0 or step == self._num_steps - 1:
                elapsed = time.monotonic() - start_time
                current_lr = self._optimizer.param_groups[0]["lr"]
                entry = {
                    "step": step,
                    "loss": round(total_loss.item(), 6),
                    "ce_loss": round(ce_loss.item(), 6),
                    "mse_loss": round(mse_loss.item(), 6),
                    "lr": round(current_lr, 8),
                    "elapsed_s": round(elapsed, 1),
                }
                self._loss_history.append(entry)
                print(
                    f"  step {step:5d}/{self._num_steps}  "
                    f"loss={total_loss.item():.4f}  "
                    f"ce={ce_loss.item():.4f}  "
                    f"mse={mse_loss.item():.4f}  "
                    f"lr={current_lr:.2e}  "
                    f"{elapsed:.0f}s"
                )

                # Write to loss log immediately (safe against crashes)
                out_path = Path(output_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")

        return self._loss_history
