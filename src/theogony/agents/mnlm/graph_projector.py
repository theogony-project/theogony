"""
GraphProjector — encodes a MeshInput subgraph into continuous prefix tokens
for injection into a frozen LLM.

Architecture (mesh_native_lm_brief.md §3.2):
- Takes MeshInput (nodes + edges + context)
- Runs a lightweight GraphGPS-class encoder over node features
  with Laplacian positional encoding and HGT-style edge-type embeddings
- Projects the N node representations into M continuous prefix tokens
  that are prepended to the LLM's input embedding sequence
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import torch
import torch.nn as nn
import torch.nn.functional as F

if TYPE_CHECKING:
    from theogony.agents.mnlm.dto import MeshInput


class GraphProjector(nn.Module):
    """Projects a MeshInput subgraph into continuous prefix tokens.

    For the PoC, this is a simplified GraphGPS encoder followed by a
    linear projection to the LLM's hidden dimension. No training in
    this commit — just structural scaffolding.

    Parameters
    ----------
    node_dim:
        Input node embedding dimension (384 for BGE-small).
    hidden_dim:
        Hidden dimension of the GraphGPS encoder.
    llm_dim:
        Target dimension of the frozen LLM (1536 for Qwen2.5-1.5B).
    num_prefix_tokens:
        Number of output prefix tokens per graph.
        The PoC uses 32 per node; total = min(N, 64) × 32.
    max_nodes:
        Maximum number of nodes the projector can handle.
    """

    def __init__(
        self,
        node_dim: int = 384,
        hidden_dim: int = 512,
        llm_dim: int = 1536,
        num_prefix_tokens: int = 32,
        max_nodes: int = 1024,
    ) -> None:
        super().__init__()
        self._node_dim = node_dim
        self._llm_dim = llm_dim
        self._num_prefix_tokens = num_prefix_tokens
        self._max_nodes = max_nodes

        # Laplacian positional encoding: projects node degree into PE
        self.pe_proj = nn.Linear(1, hidden_dim)

        # MLP for node features
        self.node_mlp = nn.Sequential(
            nn.Linear(node_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

        # Edge-type embedding lookup (512-entry codebook → hidden_dim)
        self.edge_type_embed = nn.Embedding(512, hidden_dim)

        # Simple graph convolution layer (message passing, no training)
        self.conv = nn.Linear(hidden_dim, hidden_dim)

        # Cross-attention: node states → prefix tokens
        self.query_proj = nn.Parameter(
            torch.randn(1, num_prefix_tokens, hidden_dim) * 0.02,
        )
        self.key_proj = nn.Linear(hidden_dim, hidden_dim)
        self.value_proj = nn.Linear(hidden_dim, hidden_dim)
        self.attn_out = nn.Linear(hidden_dim, hidden_dim)

        # Final projection: hidden_dim → llm_dim
        self.to_llm = nn.Linear(hidden_dim, llm_dim)

        # Register buffers
        self.register_buffer(
            "_dummy",
            torch.zeros(1),
            persistent=False,
        )

    def forward(
        self,
        node_embeddings: torch.Tensor,
        edge_indices: torch.Tensor,
        edge_types: torch.Tensor,
        node_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Encode a subgraph and produce prefix tokens.

        Parameters
        ----------
        node_embeddings:
            Float tensor (B, N, node_dim). Node embeddings from MeshInput.
        edge_indices:
            Long tensor (2, E). COO-format edges (source, target).
        edge_types:
            Long tensor (E,). Codebook IDs for each edge.
        node_mask:
            Bool tensor (B, N). True for valid nodes.

        Returns
        -------
        prefix_tokens:
            Float tensor (B, M, llm_dim) where M = num_prefix_tokens.
        """
        B, N, D = node_embeddings.shape
        device = node_embeddings.device

        # Node degree for Laplacian PE
        if edge_indices.numel() > 0:
            degrees = torch.zeros(N, device=device)
            src = edge_indices[0]
            degrees.scatter_add_(0, src, torch.ones_like(src, dtype=torch.float))
        else:
            degrees = torch.zeros(N, device=device)
        pe = self.pe_proj(degrees.unsqueeze(-1))  # (N, hidden_dim)

        # Node state
        h = self.node_mlp(node_embeddings)  # (B, N, hidden_dim)
        h = h + pe.unsqueeze(0)  # broadcast PE

        # Edge-type embeddings aggregated per node (simple message passing)
        if edge_indices.numel() > 0:
            edge_emb = self.edge_type_embed(edge_types)  # (E, hidden_dim)
            src_emb = torch.zeros(N, edge_emb.size(-1), device=device)
            src_emb.scatter_add_(
                0,
                edge_indices[0].unsqueeze(-1).expand(-1, edge_emb.size(-1)),
                edge_emb,
            )
            # Mean aggregation
            edge_counts = torch.zeros(N, device=device)
            edge_counts.scatter_add_(
                0,
                edge_indices[0],
                torch.ones_like(edge_indices[0], dtype=torch.float),
            )
            edge_counts = edge_counts.clamp(min=1)
            src_emb = src_emb / edge_counts.unsqueeze(-1)
            h = h + self.conv(src_emb.unsqueeze(0))  # (1, N, hidden_dim)

        # Cross-attention: fixed query tokens attend to all nodes
        # Q: (B, M, D),  K,V: (B, N, D)
        q = self.query_proj.expand(B, -1, -1)  # (B, M, hidden_dim)
        k = self.key_proj(h)  # (B, N, hidden_dim)
        v = self.value_proj(h)  # (B, N, hidden_dim)

        attn_mask = None
        if node_mask is not None:
            # Mask invalid nodes: -inf where node_mask is False
            attn_mask = torch.zeros(B, 1, 1, N, device=device)
            attn_mask = attn_mask.masked_fill(~node_mask.unsqueeze(1).unsqueeze(2), float("-inf"))

        attn_weights = torch.matmul(q, k.transpose(-2, -1)) / (h.size(-1) ** 0.5)
        if attn_mask is not None:
            attn_weights = attn_weights + attn_mask.squeeze(1)
        attn_weights = F.softmax(attn_weights, dim=-1)  # (B, M, N)

        prefix = torch.matmul(attn_weights, v)  # (B, M, hidden_dim)
        prefix = self.attn_out(prefix)

        # Final projection to LLM dimension
        prefix = self.to_llm(prefix)  # (B, M, llm_dim)
        return cast(torch.Tensor, prefix)

    @torch.no_grad()
    def from_mesh_input(self, mesh_input: MeshInput) -> dict[str, Any]:
        """Convert a MeshInput pydantic model to projector inputs.

        Returns dict with tensors for forward(). Useful for smoke tests.
        """
        import numpy as np

        device: torch.device = cast(torch.device, self._dummy.device)

        node_arr = np.array([n.embedding for n in mesh_input.nodes], dtype=np.float32)
        node_emb = torch.from_numpy(node_arr).unsqueeze(0).to(device)

        N = node_emb.size(1)
        edge_src = []
        edge_tgt = []
        edge_types = []
        for edge in mesh_input.edges:
            src_idx = next(i for i, n in enumerate(mesh_input.nodes) if n.node_id == edge.source_id)
            tgt_idx = next(i for i, n in enumerate(mesh_input.nodes) if n.node_id == edge.target_id)
            edge_src.append(src_idx)
            edge_tgt.append(tgt_idx)
            edge_types.append(edge.relation_codebook_id)

        if edge_src:
            edge_indices = torch.tensor([edge_src, edge_tgt], dtype=torch.long, device=device)
            edge_types_t = torch.tensor(edge_types, dtype=torch.long, device=device)
        else:
            edge_indices = torch.zeros(2, 0, dtype=torch.long, device=device)
            edge_types_t = torch.zeros(0, dtype=torch.long, device=device)

        node_mask = torch.ones(1, N, dtype=torch.bool, device=device)

        return {
            "node_embeddings": node_emb,
            "edge_indices": edge_indices,
            "edge_types": edge_types_t,
            "node_mask": node_mask,
        }
