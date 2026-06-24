#!/usr/bin/env python3
"""Probe Spreading Activation + semantic seeding on a MESH workspace (operator tool)."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import torch

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.runtime.spreading import spreading_activation
from theogony.mesh.seeds.wikidata5m.embedder import build_embedder


def _pick_device(name: str) -> torch.device:
    if name == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if name == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _merge_activation(accum: torch.Tensor, x: torch.Tensor) -> None:
    accum.copy_(torch.maximum(accum, x))


def _format_node(node_id: str, node) -> str:
    qid = node.qids[0].qid if node.qids else "—"
    label = node.description or (node.tags[0] if node.tags else str(node_id)[:12])
    return f"{qid:>10}  {label[:48]:48}"


async def _embed_query(embedder_name: str, query: str) -> tuple[list[float], float]:
    embedder = build_embedder(embedder_name)
    started = time.perf_counter()
    vectors = await embedder.embed_many([query], batch_size=1)
    return vectors[0], time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/mesh-smoke2-safe"))
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--embedder", type=str, default="bge-m3")
    parser.add_argument(
        "--seed-qid", type=str, default=None, help="Optional Q-ID seed (adds to vector seeds)."
    )
    parser.add_argument("--top-seeds", type=int, default=5)
    parser.add_argument("--top-results", type=int, default=20)
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    parser.add_argument(
        "--bidirectional", action="store_true", help="Treat edges as undirected for propagation."
    )
    args = parser.parse_args()

    device = _pick_device(args.device)
    rt = MeshRuntime.open(args.root.resolve())

    t0 = time.perf_counter()
    edges = rt.edges.load_all_edges()
    load_edges_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    csr = rt.rebuild_csr()
    build_csr_s = time.perf_counter() - t1

    id_to_node = {str(n.id): n for n in rt.nodes.iter_consolidated()}
    n = len(csr.node_ids)

    query_vec, embed_s = asyncio.run(_embed_query(args.embedder, args.query))

    t2 = time.perf_counter()
    seeds = rt.nodes.search_consolidated_by_vector(
        query_vec,
        vector_column_name="semantic_vector",
        limit=args.top_seeds,
    )
    vector_search_s = time.perf_counter() - t2

    seed_indices: list[int] = []
    seed_labels: list[str] = []
    for node in seeds:
        idx = csr.id_to_index.get(str(node.id))
        if idx is not None:
            seed_indices.append(idx)
            seed_labels.append(_format_node(str(node.id), node))

    if args.seed_qid:
        node = rt.nodes.get_consolidated_by_qid(args.seed_qid)
        if node is not None:
            idx = csr.id_to_index.get(str(node.id))
            if idx is not None and idx not in seed_indices:
                seed_indices.insert(0, idx)
                seed_labels.insert(0, _format_node(str(node.id), node))

    if not seed_indices:
        raise SystemExit("no seed nodes resolved in CSR — check workspace / query")

    t3 = time.perf_counter()
    accum = torch.zeros(n, dtype=torch.float32, device=device)
    if args.bidirectional:
        adj = torch.sparse_csr_tensor(
            csr.crow_indices.to(device),
            csr.col_indices.to(device),
            csr.values.to(device),
            size=(n, n),
            dtype=torch.float32,
            device=device,
        )
        for seed_index in seed_indices:
            x = torch.zeros(n, dtype=torch.float32, device=device)
            x[seed_index] = 1.0
            for _ in range(args.hops):
                fwd = torch.sparse.mm(adj, x.unsqueeze(1)).squeeze(1)
                bwd = torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1)
                x = args.damping * (fwd + bwd)
            _merge_activation(accum, x)
    else:
        for seed_index in seed_indices:
            x = spreading_activation(
                csr,
                seed_index=seed_index,
                hops=args.hops,
                damping=args.damping,
                device=device,
            )
            _merge_activation(accum, x.to(device))

    spread_s = time.perf_counter() - t3

    scores = accum.detach().cpu()
    topk = min(args.top_results, int(scores.numel()))
    values, indices = torch.topk(scores, topk)

    print("=== mesh spread probe ===")
    print(f"workspace: {args.root}")
    print(f"nodes: {rt.nodes.consolidated_count()}  edges: {len(edges)}  csr_n: {n}")
    print(f"query: {args.query!r}")
    print(
        f"hops={args.hops} damping={args.damping} "
        f"bidirectional={args.bidirectional} device={device}"
    )
    print()
    print("--- timing ---")
    print(f"load_edges:     {load_edges_s:.3f}s")
    print(f"build_csr:      {build_csr_s:.3f}s")
    print(f"embed_query:    {embed_s:.3f}s")
    print(f"vector_search:  {vector_search_s:.3f}s")
    print(f"spread ({len(seed_indices)} seeds): {spread_s:.3f}s")
    print(
        f"total:          {load_edges_s + build_csr_s + embed_s + vector_search_s + spread_s:.3f}s"
    )
    print()
    print("--- seeds (semantic + optional Q-ID) ---")
    for label in seed_labels:
        print(f"  {label}")
    print()
    print("--- top activated nodes ---")
    for rank, (score, idx) in enumerate(
        zip(values.tolist(), indices.tolist(), strict=False), start=1
    ):
        node_id = csr.node_ids[idx]
        node = id_to_node.get(node_id)
        if node is None:
            continue
        line = _format_node(node_id, node)
        print(f"{rank:2d}  {score:.6f}  {line}")

    out = {
        "query": args.query,
        "timings_s": {
            "load_edges": load_edges_s,
            "build_csr": build_csr_s,
            "embed_query": embed_s,
            "vector_search": vector_search_s,
            "spread": spread_s,
        },
        "seeds": seed_labels,
        "top": [
            {
                "rank": i + 1,
                "score": float(values[i]),
                "qid": id_to_node[csr.node_ids[int(indices[i])]].qids[0].qid
                if id_to_node.get(csr.node_ids[int(indices[i])])
                and id_to_node[csr.node_ids[int(indices[i])]].qids
                else None,
                "label": id_to_node[csr.node_ids[int(indices[i])]].description
                if id_to_node.get(csr.node_ids[int(indices[i])])
                else None,
            }
            for i in range(topk)
        ],
    }
    print()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
