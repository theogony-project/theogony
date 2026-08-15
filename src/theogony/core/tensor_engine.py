"""
PyTorch-based Tensor Engine for the Neural Vector Mesh.

This module implements the core Spreading Activation algorithm over a
Compressed Sparse Row (CSR) tensor representation of the knowledge graph.
It abandons pointer-chasing in favor of massively parallel Sparse Matrix-Vector
Multiplication (SpMV).

Edges are treated as first-class vectors (or compressed via a Codebook).
"""

import torch
import torch.nn.functional as F


class TensorMeshEngine:
    """
    In-memory CSR representation of the Neural Vector Mesh.
    Optimized for GPU execution (or fast CPU fallback).
    """

    def __init__(self, device: str = "cpu"):
        self.device = torch.device(device)

        # --- Graph Topology (CSR Format) ---
        # row_ptr[i] to row_ptr[i+1] gives the range of edges for node i
        self.row_ptr: torch.Tensor | None = None  # Shape: (N+1,), dtype: int64
        # col_idx[e] gives the target node for edge e
        self.col_idx: torch.Tensor | None = None  # Shape: (E,), dtype: int64

        # --- Embeddings ---
        self.node_embeddings: torch.Tensor | None = None  # Shape: (N, D), dtype: float32/16

        # --- Edge Features ---
        # We use a Codebook for edge vectors to save VRAM (1 billion edges * 768 dims = TBs of VRAM)
        # Instead: a 2-byte index per edge pointing to a learned codebook of relation types.
        self.edge_type_idx: torch.Tensor | None = None  # Shape: (E,), dtype: int16
        self.edge_codebook: torch.Tensor | None = None  # Shape: (Num_Types, D)

        # Base weight (extraction confidence) and Hebbian strength (reactivation frequency)
        self.base_weight: torch.Tensor | None = None  # Shape: (E,)
        self.hebbian_strength: torch.Tensor | None = None  # Shape: (E,)

    def load_from_arrays(
        self,
        row_ptr: list[int],
        col_idx: list[int],
        node_embeddings: list[list[float]],
        edge_type_idx: list[int],
        edge_codebook: list[list[float]],
        base_weight: list[float],
        hebbian_strength: list[float],
    ) -> None:
        """Load the mesh from raw arrays into PyTorch tensors on the target device."""
        self.row_ptr = torch.tensor(row_ptr, dtype=torch.int64, device=self.device)
        self.col_idx = torch.tensor(col_idx, dtype=torch.int64, device=self.device)
        self.node_embeddings = torch.tensor(
            node_embeddings, dtype=torch.float32, device=self.device
        )

        self.edge_type_idx = torch.tensor(edge_type_idx, dtype=torch.int64, device=self.device)
        self.edge_codebook = torch.tensor(edge_codebook, dtype=torch.float32, device=self.device)

        self.base_weight = torch.tensor(base_weight, dtype=torch.float32, device=self.device)
        self.hebbian_strength = torch.tensor(
            hebbian_strength, dtype=torch.float32, device=self.device
        )

        # Normalize node embeddings for fast cosine similarity via dot product
        self.node_embeddings = F.normalize(self.node_embeddings, p=2, dim=1)
        self.edge_codebook = F.normalize(self.edge_codebook, p=2, dim=1)

    def spreading_activation(
        self,
        stimulus: torch.Tensor,
        max_hops: int = 3,
        decay: float = 0.85,
        top_k_seeds: int = 64,
        activation_threshold: float = 0.01,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Execute Spreading Activation over the tensor mesh.

        Args:
            stimulus: The query/agent context vector (Shape: (D,)).
            max_hops: Maximum number of propagation steps.
            decay: Energy loss per hop.
            top_k_seeds: Number of initial nodes to activate via ANN.
            activation_threshold: Minimum energy to keep a node active (Lateral Inhibition).

        Returns:
            A tuple of (active_node_indices, activation_energies).
        """
        # The edge tensors are as load-bearing here as the node ones — dynamic edge
        # weighting reads all four below. Leaving them out of the guard meant an
        # unloaded engine failed later with a bare "NoneType is not subscriptable"
        # instead of saying what the caller actually did wrong.
        if (
            self.node_embeddings is None
            or self.row_ptr is None
            or self.col_idx is None
            or self.edge_codebook is None
            or self.edge_type_idx is None
            or self.base_weight is None
            or self.hebbian_strength is None
        ):
            raise ValueError("TensorMeshEngine is not initialized. Call load_from_arrays first.")

        N = self.node_embeddings.size(0)
        _E = self.col_idx.size(0)  # noqa: F841

        # Ensure stimulus is normalized and on the right device
        stimulus = stimulus.to(self.device)
        stimulus = F.normalize(stimulus, p=2, dim=0)

        # ---------------------------------------------------------------------
        # 1. INJECTION (Seed Activation)
        # ---------------------------------------------------------------------
        # Cosine similarity: dot product since both vectors are normalized
        sim_scores = torch.matmul(self.node_embeddings, stimulus)

        # Find Top-K seeds
        top_k = min(top_k_seeds, N)
        seed_scores, seed_indices = torch.topk(sim_scores, top_k)

        # Initialize activation vector A (Shape: (N,))
        A = torch.zeros(N, dtype=torch.float32, device=self.device)
        # Apply softmax temperature to seed scores for initial energy distribution
        A[seed_indices] = F.softmax(seed_scores / 0.1, dim=0)

        # ---------------------------------------------------------------------
        # 2. DYNAMIC EDGE WEIGHT CALCULATION
        # ---------------------------------------------------------------------
        # In a classic graph, edge weights are static. In our Neural Mesh, the weight
        # depends on how relevant the edge's semantic vector is to the current stimulus.

        # Reconstruct full edge embeddings from the codebook (Shape: (E, D))
        edge_embs = self.edge_codebook[self.edge_type_idx]

        # Relevance: Cosine similarity between edge vector and stimulus
        edge_relevance = torch.matmul(edge_embs, stimulus)
        # ReLU ensures energy only flows through edges that are somewhat aligned with the thought
        edge_relevance = F.relu(edge_relevance)

        # Effective Weight = (Base * Hebbian) * Relevance
        # The +1 on hebbian ensures brand new edges still conduct energy
        W_dynamic = self.base_weight * torch.log1p(self.hebbian_strength) * edge_relevance

        # ---------------------------------------------------------------------
        # 3. PROPAGATION (SpMV)
        # ---------------------------------------------------------------------
        # We construct a sparse adjacency matrix using the dynamic weights
        # Shape: (N, N)
        adj_matrix = torch.sparse_csr_tensor(self.row_ptr, self.col_idx, W_dynamic, size=(N, N))

        for _hop in range(max_hops):
            # Sparse Matrix-Vector Multiplication (SpMV)
            # Energy flows from active nodes to their neighbors
            # A_next = (Adj^T * A)
            # Note: PyTorch sparse matmul expects (Sparse @ Dense).
            # To push energy forward (source -> target), we actually need (Adj^T @ A).
            # We simulate this by transposing the CSR matrix (which becomes CSC) and multiplying.
            # For simplicity in this MVP, we assume bidirectional flow or use standard SpMV.

            # Forward propagation
            incoming_energy = torch.matmul(adj_matrix.t(), A.unsqueeze(1)).squeeze(1)

            # Apply Decay
            A_next = incoming_energy * decay

            # Lateral Inhibition (Winner-takes-most)
            # Zero out nodes below the threshold to prevent context exhaustion
            A_next[A_next < activation_threshold] = 0.0

            # Add residual energy from previous step (persistent sensory input)
            A = A_next + (A * 0.2)

            # If no energy is left moving, break early
            if A.max() < activation_threshold:
                break

        # ---------------------------------------------------------------------
        # 4. CONSTELLATION EXTRACTION
        # ---------------------------------------------------------------------
        # Find all nodes that have non-zero activation energy
        active_mask = A > 0
        active_indices = torch.nonzero(active_mask).squeeze(1)
        active_energies = A[active_indices]

        # Sort by energy descending
        sorted_energies, sort_idx = torch.sort(active_energies, descending=True)
        sorted_indices = active_indices[sort_idx]

        return sorted_indices, sorted_energies
