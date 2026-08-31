#!/usr/bin/env python3
"""Render the founding-demo activation GIF from real propagate_frames (F6).

Every animation frame is one actual SpMV iteration of Spreading Activation on
the founding mesh — no staged animation. Output: demo asset GIF.
"""

import asyncio
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from theogony.mesh.cli import _query_embedder
from theogony.mesh.retrieval import retrieve
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

QUERY = "How was Aphrodite born and who are her parents?"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "founding_activation.gif")


async def main() -> None:
    rt = MeshRuntime.open(Path("data/mesh-founding"))
    emb = await _query_embedder(rt.semantic_dim, None)
    vec = (await emb.embed_many([QUERY], batch_size=1))[0]
    csr = rt.rebuild_csr()
    # Rendering a picture of the substrate is not using it (PHX-1101).
    result = retrieve(rt, vec, top_k=22, csr=csr, degree_beta=0.5, query=QUERY, record_firing=False)
    c = result.constellation
    prop = Propagator(csr)
    seed_idx = {csr.id_to_index[i]: 1.0 for i in result.seed_node_ids if i in csr.id_to_index}
    frames = prop.propagate_frames(seed_idx, operator=result.operator)
    peak = max(float(f.max()) for f in frames) or 1.0

    keep = [
        (n.node_id, csr.id_to_index[n.node_id], n.name, n.is_source_anchor)
        for n in c.nodes
        if n.node_id in csr.id_to_index
    ]
    g = nx.Graph()
    for nid, _, name, anchor in keep:
        g.add_node(nid, name=name, anchor=anchor)
    for e in c.edges:
        if e.source_id in g and e.target_id in g:
            g.add_edge(
                e.source_id,
                e.target_id,
                contradiction="contradict" in (e.relation_descriptor or "").lower(),
            )
    pos = nx.spring_layout(g, seed=7, k=0.9)

    fig, ax = plt.subplots(figsize=(8, 5.6), dpi=110)
    fig.patch.set_facecolor("#0f172a")

    def draw(frame_i: int) -> None:
        ax.clear()
        ax.set_facecolor("#0f172a")
        ax.set_axis_off()
        f = frames[frame_i]
        acts = {nid: float(f[idx]) / peak for nid, idx, _, _ in keep}
        edge_cols = ["#f87171" if g.edges[e].get("contradiction") else "#334155" for e in g.edges]
        nx.draw_networkx_edges(g, pos, ax=ax, edge_color=edge_cols, width=0.7, alpha=0.6)
        sizes = [60 + acts.get(n, 0.0) * 900 for n in g.nodes]
        colors = ["#fbbf24" if acts.get(n, 0) > 0.35 else "#38bdf8" for n in g.nodes]
        alphas = [0.25 + 0.75 * acts.get(n, 0.0) for n in g.nodes]
        nx.draw_networkx_nodes(g, pos, ax=ax, node_size=sizes, node_color=colors, alpha=alphas)
        top = sorted(g.nodes, key=lambda n: -acts.get(n, 0))[:6]
        labels = {
            n: (
                g.nodes[n]["name"][:26] + "…"
                if len(g.nodes[n]["name"]) > 27
                else g.nodes[n]["name"]
            )
            for n in top
        }
        nx.draw_networkx_labels(g, pos, labels=labels, ax=ax, font_size=6.5, font_color="#e2e8f0")
        ax.set_title(
            f"Spreading Activation — Iteration {frame_i + 1}/{len(frames)}\n“{QUERY}”",
            color="#94a3b8",
            fontsize=9,
        )

    from matplotlib.animation import FuncAnimation, PillowWriter

    anim = FuncAnimation(fig, draw, frames=len(frames), interval=380)
    anim.save(str(OUT), writer=PillowWriter(fps=2.6))
    print(
        f"GIF: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {len(frames)} Frames, "
        f"{len(g.nodes)} Knoten, {len(g.edges)} Kanten)"
    )


asyncio.run(main())
