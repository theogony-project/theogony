"""
SubstrateResonantRunner — wraps the MNLM forward pass with Substrate-Resonant
Recurrence (mesh_native_lm_brief.md §3.4).

Every K-th latent reasoning step interleaves a one-hop Spreading Activation
call against the TensorMeshEngine.  The resulting top-k constellation is
projected back into the next forward pass as additional context.

Architecture:
1. GraphProjector encodes MeshInput → prefix tokens
2. Graph-KV adapter produces masks + biases
3. LLM forward pass runs with the graph-structured prefix
4. Every K-th step: pool hidden state → one-hop SA on TensorMeshEngine →
   re-project constellation → feed back
5. After recurrence: LFM-GAE decoder produces MeshDelta

For the PoC, this module is a stateless runner that orchestrates the
other components.  No LLM loading — it works on tensors only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torch

from theogony.agents.mnlm.lfm_gae_decoder import LFMGAEDecoder

if TYPE_CHECKING:
    from theogony.agents.mnlm.dto import MeshInput
    from theogony.agents.mnlm.graph_projector import GraphProjector
    from theogony.agents.mnlm.graphkv_adapter import GraphKVAdapter
    from theogony.core.tensor_engine import TensorMeshEngine


class SubstrateResonantRunner:
    """Orchestrates the full MNLM forward pass with SA recurrence.

    This is the top-level runner for the PoC smoke test.  It wires
    GraphProjector → GraphKV → recurrence loop → LFM-GAE decoder.

    Parameters
    ----------
    projector:
        GraphProjector instance.
    graphkv:
        GraphKVAdapter instance.
    decoder:
        LFMGAEDecoder instance.
    sa_engine:
        TensorMeshEngine instance (from theogony.core.tensor_engine).
    sa_interleave_K:
        Substrate-Resonant interleave frequency (K=3 default).
    latent_step_cap:
        Maximum number of latent reasoning steps (default 16).
    sa_top_k:
        Top-K nodes to return from Spreading Activation (default 8).
    """

    def __init__(
        self,
        projector: GraphProjector,
        graphkv: GraphKVAdapter,
        decoder: LFMGAEDecoder,
        sa_engine: TensorMeshEngine | None = None,
        sa_interleave_K: int = 3,
        latent_step_cap: int = 16,
        sa_top_k: int = 8,
    ):
        self._projector = projector
        self._graphkv = graphkv
        self._decoder = decoder
        self._sa_engine = sa_engine
        self._K = sa_interleave_K
        self._step_cap = latent_step_cap
        self._sa_top_k = sa_top_k

    @torch.no_grad()
    def run(
        self,
        mesh_input: MeshInput,
    ) -> dict[str, Any]:
        """Run one full MeshInput → MeshDelta cycle.

        Parameters
        ----------
        mesh_input:
            A validated MeshInput instance.

        Returns
        -------
        dict with MeshDelta-relevant fields plus telemetry.
        """
        # 1. Project MeshInput to prefix tokens
        inputs = self._projector.from_mesh_input(mesh_input)
        prefix = self._projector.forward(
            node_embeddings=inputs["node_embeddings"],
            edge_indices=inputs["edge_indices"],
            edge_types=inputs["edge_types"],
            node_mask=inputs["node_mask"],
        )  # (1, M, llm_dim)

        N = inputs["node_embeddings"].size(1)

        # 2. Build structural masks
        self._graphkv.build_block_mask(
            N,
            inputs["edge_indices"],
            device=prefix.device,
        )
        self._graphkv.build_edge_bias(
            N,
            inputs["edge_indices"],
            inputs["edge_types"],
            device=prefix.device,
        )

        # 3. Substrate-Resonant Recurrence (simulated)
        # For the PoC, we run a dummy loop that doesn't call a real LLM.
        # The recurrence structures the API: every K-th step would call SA.
        latent_state = prefix
        sa_cycles_used = 0
        latent_steps_used = 0
        prev_state = latent_state.clone()

        for step in range(self._step_cap):
            if step > 0 and step % self._K == 0 and self._sa_engine is not None:
                # Pool latent state to a stimulus vector
                stimulus = latent_state.mean(dim=1)  # (B, llm_dim)
                # One-hop SA (structurally documented, actual call succeeds
                # if TensorMeshEngine has data loaded)
                try:
                    node_energies = self._sa_engine.forward(  # type: ignore[attr-defined]
                        stimulus.cpu().numpy().tolist(),
                        max_hops=1,
                    )
                    _ = node_energies  # telemetry only for PoC
                except Exception:
                    pass
                sa_cycles_used += 1

            # Simulate LLM forward — in production this runs the LLM layers
            latent_state = prefix + torch.randn_like(prefix) * 0.01

            # Stability gate: stop if mean change < threshold
            if step > 0:
                change = (latent_state - prev_state).abs().mean().item()
                if change < 0.001:
                    latent_steps_used = step + 1
                    break
            latent_steps_used = step + 1

        # 4. LFM-GAE decoder
        terminal = latent_state.mean(dim=1)  # pool prefix tokens → (B, llm_dim)
        lfm_result = self._decoder.decode(terminal)

        # 5. Build MeshDelta-compatible result
        delta = self._decoder.make_placeholder_mesh_delta(
            call_id=mesh_input.call_id,
            run_id=mesh_input.run_id,
        )
        delta["latent_steps_used"] = latent_steps_used
        delta["sa_cycles_used"] = sa_cycles_used
        delta["trajectory"]["converged"] = lfm_result["trajectory_converged"]
        delta["trajectory"]["integration_steps"] = lfm_result["integration_steps"]
        delta["halted_reason"] = (
            "lfm_converged" if lfm_result["trajectory_converged"] else "step_cap"
        )

        return delta

    @property
    def sa_interleave_K(self) -> int:
        return self._K

    @sa_interleave_K.setter
    def sa_interleave_K(self, value: int) -> None:
        self._K = value
