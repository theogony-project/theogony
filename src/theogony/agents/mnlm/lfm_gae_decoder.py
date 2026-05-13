"""
LFM-GAE Decoder — Latent Flow Matching + Graph-Autoencoder reconstruction head.

Architecture (mesh_native_lm_brief.md §3.3, marked [RESEARCH]):

1. Takes the LLM's terminal hidden state after Substrate-Resonant Recurrence
2. Conditional Flow Matching module learns a time-dependent vector field
   v_θ(z; t, conditioning) that drives z_0 → z_1 in the latent space
3. A deterministic Graph-Autoencoder reconstructs a MeshDelta from z_1

The PoC stub implements the ODE-integration loop structurally without
a trained vector field — it produces a MeshDelta with a dummy LFM
trajectory for pipeline validation.

Fallback: discrete-mutation-token decoder (used if LFM fails to converge
during training).  Both decoders share the same output shape: MeshDelta.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import torch
import torch.nn as nn


class CFMVectorField(nn.Module):
    """Conditional Flow Matching vector field: v_θ(z; t, conditioning).

    For the PoC, this is an untrained MLP that structurally documents
    the expected forward pass shape.  Training begins in Week 3 (Phase A).
    """

    def __init__(self, latent_dim: int = 768, hidden_dim: int = 1024):
        super().__init__()
        self._latent_dim = latent_dim
        self.net = nn.Sequential(
            nn.Linear(latent_dim + latent_dim + 1, hidden_dim),  # z + conditioning + t
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, latent_dim),
        )

    def forward(
        self,
        z_t: torch.Tensor,
        t: torch.Tensor,
        conditioning: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Evaluate the vector field at state z_t and time t.

        Parameters
        ----------
        z_t:
            Float tensor (B, latent_dim). Current latent state.
        t:
            Float tensor (B, 1). Time in [0, 1].
        conditioning:
            Float tensor (B, latent_dim) or None. LLM terminal state.

        Returns
        -------
        v:
            Float tensor (B, latent_dim). Velocity at (z_t, t).
        """
        c = conditioning if conditioning is not None else torch.zeros_like(z_t)
        inp = torch.cat([z_t, c, t], dim=-1)
        return cast(torch.Tensor, self.net(inp))


class GAEDecoder(nn.Module):
    """Graph-Autoencoder reconstruction head.

    Decodes the final latent state z_1 into a MeshDelta-styled output.
    For the PoC, this maps z_1 to prototype vectors representing
    MutationPrimitive kinds.  Training begins in Week 3.
    """

    def __init__(self, latent_dim: int = 768, num_primitive_types: int = 8):
        super().__init__()
        self._latent_dim = latent_dim
        self._num_primitives = num_primitive_types
        self.proto = nn.Linear(latent_dim, num_primitive_types)

    def forward(self, z_1: torch.Tensor) -> dict[str, torch.Tensor]:
        """Decode final latent state into primitive logits.

        Returns dict with primitive logits for each MutationPrimitive kind.
        """
        primitive_logits = self.proto(z_1)  # (B, 8)
        return {"primitive_logits": primitive_logits}


class LFMGAEDecoder(nn.Module):
    """Combined Latent Flow Matching + Graph-Autoencoder decoder head.

    Parameters
    ----------
    latent_dim:
        Dimension of the LFM latent space.
    conditioning_dim:
        Dimension of the LLM's terminal hidden state.
    num_integration_steps:
        Number of ODE steps in the CFM trajectory (PoC default: 16).
    """

    def __init__(
        self,
        latent_dim: int = 768,
        conditioning_dim: int = 1536,
        num_integration_steps: int = 16,
    ):
        super().__init__()

        # Project conditioning (LLM hidden) to latent space
        self.conditioning_proj = nn.Linear(conditioning_dim, latent_dim)

        # CFM vector field
        self.vector_field = CFMVectorField(latent_dim=latent_dim)

        # GAE reconstruction head
        self.gae = GAEDecoder(latent_dim=latent_dim)

        self._num_steps = num_integration_steps
        self._latent_dim = latent_dim

    @torch.no_grad()
    def decode(
        self,
        llm_terminal_state: torch.Tensor,
    ) -> dict[str, Any]:
        """Run ODE integration + GAE reconstruction.

        Parameters
        ----------
        llm_terminal_state:
            Float tensor (B, conditioning_dim). Terminal hidden state
            after Substrate-Resonant Recurrence.

        Returns
        -------
        dict with keys:
            - trajectory_converged: bool
            - primitive_kind: int (index into MutationPrimitive types)
            - trajectory_entropy: float
            - integration_steps: int
            - latent_steps_used: int
        """
        device = llm_terminal_state.device
        B = llm_terminal_state.size(0)

        # Project conditioning
        c = self.conditioning_proj(llm_terminal_state)  # (B, latent_dim)

        # Euler integration of the probability flow ODE
        z_t = torch.randn(B, self._latent_dim, device=device)  # z_0 ~ N(0, I)
        dt = 1.0 / self._num_steps

        for step in range(self._num_steps):
            t = torch.full((B, 1), step * dt, device=device)
            v = self.vector_field(z_t, t, conditioning=c)
            z_t = z_t + v * dt

        z_1 = z_t

        # GAE reconstruction
        decoded = self.gae(z_1)
        logits = decoded["primitive_logits"]  # (B, 8)
        primitive_kind = logits.argmax(dim=-1).item() if B == 1 else 0

        return {
            "trajectory_converged": True,
            "primitive_kind": primitive_kind,
            "trajectory_entropy": 0.5,  # placeholder
            "integration_steps": self._num_steps,
            "latent_steps_used": self._num_steps,
        }

    def make_placeholder_mesh_delta(
        self,
        call_id: str = "poc-smoke-test",
        run_id: str = "poc-run-001",
    ) -> dict[str, Any]:
        """Produce a placeholder MeshDelta-compatible dict for smoke tests."""
        now = datetime.now(UTC).isoformat()
        return {
            "schema_version": "mnlm-output/1",
            "run_id": run_id,
            "call_id": call_id,
            "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
            "produced_at": now,
            "primitives": [],
            "trajectory": {
                "trajectory_entropy": 0.5,
                "integration_steps": self._num_steps,
                "final_basin_id": "cfm-basin-poc",
                "bifurcations_observed": 0,
                "max_curvature": 0.1,
                "converged": True,
            },
            "latent_steps_used": self._num_steps,
            "sa_cycles_used": 0,
            "halted_reason": "lfm_converged",
            "provenance_hash": "poc_smoke_test_provenance_hash_placeholder",
            "failure_reason_code": None,
        }
