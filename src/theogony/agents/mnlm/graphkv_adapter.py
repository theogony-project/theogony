"""
Graph-KV adapter — injects graph-structured attention masks and edge-type
biases into a frozen LLM.

Architecture (mesh_native_lm_brief.md §3.2):
- Per-node KV prefilling: each node in the input subgraph is encoded into
  KV pairs prefilled into selected LLM layers
- Graph-structured block-mask attention: attention restricted by subgraph
  adjacency (message-passing inside self-attention)
- Edge-type as continuous attention bias: relation embeddings projected
  to per-head scalar biases added before softmax

For the PoC, this adapter produces the block mask and edge bias tensors
that would be injected into the LLM's forward pass.  The actual KV-cache
injection requires model-specific hooks and is stubbed here.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F


class GraphKVAdapter:
    """Produces structural attention masks and edge biases for a frozen LLM.

    This is not a torch.nn.Module — it produces the structural tensors
    that would be injected.  The actual KV-injection is implemented as
    a monkey-patch on the LLM's forward pass (not included in this stub).

    Parameters
    ----------
    num_heads:
        Number of attention heads in the frozen LLM
        (12 for Qwen2.5-1.5B-Instruct).
    llm_dim:
        Hidden dimension of the LLM (1536 for Qwen2.5-1.5B).
    edge_codebook_size:
        Number of relation types (512 for PoC).
    max_nodes:
        Maximum number of nodes in the graph (1024 for PoC).
    """

    def __init__(
        self,
        num_heads: int = 12,
        llm_dim: int = 1536,
        edge_codebook_size: int = 512,
        max_nodes: int = 1024,
    ) -> None:
        self._num_heads = num_heads
        self._llm_dim = llm_dim
        self._edge_codebook_size = edge_codebook_size
        self._max_nodes = max_nodes
        self._head_dim = llm_dim // num_heads

        self._edge_bias_net = torch.nn.Sequential(
            torch.nn.Linear(edge_codebook_size, edge_codebook_size),
            torch.nn.ReLU(),
            torch.nn.Linear(edge_codebook_size, num_heads),
        )

    def build_block_mask(
        self,
        num_nodes: int,
        edge_indices: torch.Tensor,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        """Build a graph-structured block mask for self-attention.

        The mask allows attention only between nodes that are connected
        by an edge (bidirectional). Shape: (N, N).

        Returns
        -------
        mask:
            Float tensor (N, N) with 0.0 for allowed positions
            and float('-inf') for blocked positions.
        """
        if device is None:
            device = torch.device("cpu")
        mask = torch.full((num_nodes, num_nodes), float("-inf"), device=device)
        mask.fill_diagonal_(0.0)

        if edge_indices.numel() > 0:
            mask[edge_indices[0], edge_indices[1]] = 0.0
            mask[edge_indices[1], edge_indices[0]] = 0.0

        return mask

    def build_edge_bias(
        self,
        num_nodes: int,
        edge_indices: torch.Tensor,
        edge_types: torch.Tensor,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        """Build per-head edge-type attention biases.

        Each edge type projects to a per-head scalar bias added to the
        attention logits before softmax.

        Returns
        -------
        bias:
            Float tensor (N, N, num_heads) with per-head biases.
        """
        if device is None:
            device = torch.device("cpu")
        bias = torch.zeros(num_nodes, num_nodes, self._num_heads, device=device)

        if edge_indices.numel() == 0:
            return bias

        one_hot = F.one_hot(edge_types, num_classes=self._edge_codebook_size).float()
        per_head = self._edge_bias_net(one_hot)
        bias[edge_indices[0], edge_indices[1]] = per_head
        bias[edge_indices[1], edge_indices[0]] = per_head

        return bias

    def kv_prefill(
        self,
        prefix_tokens: torch.Tensor,
        num_layers: int = 28,
    ) -> list[tuple[torch.Tensor, torch.Tensor]]:
        """Generate KV pairs for prefilling into selected LLM layers."""
        B, M = prefix_tokens.shape[0], prefix_tokens.shape[1]
        k = prefix_tokens.view(B, M, self._num_heads, self._head_dim).transpose(1, 2)
        v = k.clone()
        return [(k.clone(), v.clone()) for _ in range(num_layers)]
