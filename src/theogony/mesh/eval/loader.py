"""Load a seeded MESH workspace into the arrays the eval harnesses consume.

This is the one place that touches the storage layer (LanceDB / MeshRuntime), so
the pure compute modules (:mod:`link_prediction`, :mod:`scaling`) stay free of
storage imports and remain unit-testable without a workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import torch

from theogony.mesh.eval.link_prediction import EdgeRow, l2_normalize_rows
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


@dataclass
class MeshEvalData:
    """Everything the link-prediction / scaling harnesses need from a workspace."""

    node_ids: list[str]
    id_to_index: dict[str, int]
    edge_rows: list[EdgeRow]
    sem_unit: torch.Tensor
    consolidated_count: int
    qid_to_node_id: dict[str, str] = field(default_factory=dict)
    node_id_to_qid: dict[str, str] = field(default_factory=dict)


def load_mesh_eval_data(root: Path) -> MeshEvalData:
    """Open a workspace and assemble node ids, edges, and aligned unit vectors."""
    rt = MeshRuntime.open(root.resolve())
    csr = rt.rebuild_csr()
    n = len(csr.node_ids)
    if n == 0:
        raise ValueError(f"empty CSR at {root} — seed the workspace first")

    semantic_dim = rt.semantic_dim
    qid_to_node_id: dict[str, str] = {}
    node_id_to_qid: dict[str, str] = {}
    sem = torch.zeros((n, semantic_dim), dtype=torch.float32)
    for node in rt.nodes.iter_consolidated():
        node_id = str(node.id)
        idx = csr.id_to_index.get(node_id)
        if idx is not None and node.semantic_vector:
            sem[idx] = torch.tensor(node.semantic_vector[:semantic_dim], dtype=torch.float32)
        if node.qids:
            qid = node.qids[0].qid
            qid_to_node_id.setdefault(qid, node_id)
            node_id_to_qid[node_id] = qid

    edge_rows: list[EdgeRow] = [
        (str(e.source_id), str(e.target_id), float(e.weight) * float(e.frame_consistency))
        for e in rt.edges.load_all_edges()
    ]

    return MeshEvalData(
        node_ids=list(csr.node_ids),
        id_to_index=dict(csr.id_to_index),
        edge_rows=edge_rows,
        sem_unit=l2_normalize_rows(sem),
        consolidated_count=rt.nodes.consolidated_count(),
        qid_to_node_id=qid_to_node_id,
        node_id_to_qid=node_id_to_qid,
    )
