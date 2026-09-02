#!/usr/bin/env python3
"""The heartbeat on a corpus with headroom — 2WikiMultihopQA, 50 rounds (PHX-1104).

    scripts/mesh_heartbeat_qa.py --dataset 2wikimultihopqa --rounds 50

On the founding mesh the heartbeat test could not move: retrieval sits at 85%
with the gold membership pinned by name anchors, so no weight dynamics show.
This runs the same protocol where Spreading Activation has room and where its
one demonstrated result lives (+0.102 recall@5 held-out on 2Wiki at hybrid
seeding, S=2):

    split the questions in two halves, used and held-out
    measure passage recall@5 on both
    R rounds of: every used question fires -> the substrate's tick
    measure both again, with kNN as the control that must not move

If used rises and held-out does not fall, the substrate learned from use. If
held-out falls, use is crowding out the rest.

**In memory, on the substrate's real tick functions.** The graph is the
benchmark's (`build_qa_graph`, Kadmos-grade edges from the cache), the
propagation kernel is the benchmark's (row-normalised adjacency, 3 hops,
damping 0.5 — the operating point the published number was measured at), and
the dynamics are the substrate's own: `merge_edge_deltas`,
`decay_edges_inplace(fired=)`, `enforce_saturation`, `fired_pairs`. A pass is
the top-`top_k` nodes by activation, as in a Constellation. Nothing is written
to any workspace. No LLM, no network, no money.

Weights enter the substrate's regime first: `w_max = 1.0`, which the tick would
impose on its first run anyway. Containment edges arrive *at* the cap and
relation-count bridges above it, so round 0 is reported both raw (comparable to
the published number) and clamped (the substrate's baseline).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.qa_datasets import DATASETS, load_dataset, subsample_corpus
from theogony.mesh.eval.qa_features import BGE_QUERY_INSTRUCTION, embed_texts
from theogony.mesh.eval.qa_retrieval import (
    _adjacencies,
    _l2_unit,
    build_qa_graph,
    build_seed_vector,
    graph_inputs_from_extractions,
    rank_desc,
    recall_at_k,
)
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import (
    decay_edges_inplace,
    enforce_saturation,
    fired_pairs,
    merge_edge_deltas,
)

W_MAX = 1.0
LAMBDA = 0.05
TOP_K = 50  # the working set, as DEFAULT_TOP_K
MAX_DELTAS = 64  # as append_hebbian_deltas


def _cache_key(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _load_readings(cache_path: Path, texts: list[str]) -> list[dict]:
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key")
            if isinstance(key, str):
                cache[key] = row.get("reading") or {}
    return [cache.get(_cache_key(t), {}) for t in texts]


def _edges(rows: list[tuple[str, str, float]]) -> list[Edge]:
    now = datetime.now(UTC)
    return [
        Edge(
            source_id=ULID.from_str(s),
            target_id=ULID.from_str(t),
            weight=w,
            born_at=now,
            last_fired_at=now,
        )
        for s, t, w in rows
    ]


def _propagate(
    adj: torch.Tensor, seed_x: torch.Tensor, *, hops: int, damping: float
) -> torch.Tensor:
    x = seed_x.clone()
    for _ in range(hops):
        x = damping * torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1) + seed_x
    return x


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dataset", choices=sorted(DATASETS), default="2wikimultihopqa")
    ap.add_argument("--max-questions", type=int, default=300)
    ap.add_argument("--corpus-size", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--checkpoints", default="1,2,3,5,10,20,30,50")
    ap.add_argument(
        "--mode", default="hybrid", help="seeding scheme; hybrid S=2 is the published point"
    )
    ap.add_argument("--top-s", type=int, default=2)
    ap.add_argument("--hops", type=int, default=3)
    ap.add_argument("--damping", type=float, default=0.5)
    ap.add_argument("--knn-k", type=int, default=10)
    ap.add_argument("--policies", default="shipped,gate,grow01,grow10")
    ap.add_argument("--embedder", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache-dir", type=Path, default=Path("data/raw/qa_bench"))
    ap.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    t0 = time.perf_counter()
    data = load_dataset(
        args.dataset, args.cache_dir, max_questions=args.max_questions, seed=args.seed
    )
    data = subsample_corpus(data, corpus_size=args.corpus_size, seed=args.seed)
    model = SentenceTransformer(args.embedder)
    passage_texts = [f"{p.title}. {p.text}" for p in data.passages]
    passage_emb = embed_texts(model, passage_texts, batch_size=64)
    question_emb = embed_texts(
        model,
        [q.question for q in data.questions],
        batch_size=64,
        instruction=BGE_QUERY_INSTRUCTION,
    )
    readings = _load_readings(
        args.cache_dir / f"kadmos_readings_{args.dataset}.jsonl", [p.text for p in data.passages]
    )
    if not any(readings):
        raise SystemExit("no cached Kadmos readings — run scripts/mesh_qa_kadmos.py first")
    names, per_passage, relation_pairs = graph_inputs_from_extractions(readings)
    entity_emb = embed_texts(model, names, batch_size=64)
    graph = build_qa_graph(
        passage_emb,
        entity_emb,
        per_passage,
        knn_k=args.knn_k,
        seed=args.seed,
        relation_pairs=relation_pairs,
    )
    # `Edge` carries ULIDs by schema and the benchmark names nodes p0/e0: one
    # synthetic ULID per node, in graph order, so passage indices stay 0..P-1.
    ulid_of = {nid: str(ULID()) for nid in graph.node_ids}
    node_ids = [ulid_of[nid] for nid in graph.node_ids]
    rows0 = [
        (ulid_of[s], ulid_of[t], w)
        for s, t, w in graph.containment_edges + graph.knn_edges + graph.entity_edges
    ]
    print(
        f"dataset={args.dataset} passages={len(data.passages)} entities={len(names)} "
        f"questions={len(data.questions)} edges={len(rows0)}  "
        f"({time.perf_counter() - t0:.0f}s to build)"
    )

    passage_unit = _l2_unit(passage_emb)
    question_unit = _l2_unit(question_emb)
    n_passages = passage_emb.shape[0]
    entity_unit = graph.sem_unit[n_passages:]
    n_nodes = len(graph.node_ids)

    order = list(range(len(data.questions)))
    random.Random(args.seed).shuffle(order)
    half = len(order) // 2
    used, held = sorted(order[:half]), sorted(order[half:])
    checkpoints = {int(c) for c in args.checkpoints.split(",") if c.strip()} | {args.rounds}

    def seed_vec(qi: int) -> torch.Tensor:
        return build_seed_vector(
            question_unit[qi], passage_unit, entity_unit, n_nodes, mode=args.mode, top_s=args.top_s
        )

    knn_recall = {
        "used": statistics.mean(
            recall_at_k(
                rank_desc(passage_unit @ question_unit[qi]), data.questions[qi].gold_idxs, 5
            )
            for qi in used
        ),
        "held": statistics.mean(
            recall_at_k(
                rank_desc(passage_unit @ question_unit[qi]), data.questions[qi].gold_idxs, 5
            )
            for qi in held
        ),
    }

    def measure(adj: torch.Tensor, idxs: list[int]) -> tuple[float, float]:
        """(recall@5, mean gold rank) for SA on these questions, current adjacency."""
        rec, ranks = 0.0, []
        for qi in idxs:
            x = _propagate(adj, seed_vec(qi), hops=args.hops, damping=args.damping)
            ranked = rank_desc(x[:n_passages])
            rec += recall_at_k(ranked, data.questions[qi].gold_idxs, 5)
            pos = {p: r + 1 for r, p in enumerate(ranked)}
            ranks.extend(min(pos.get(g, 201), 201) for g in data.questions[qi].gold_idxs)
        return rec / max(1, len(idxs)), statistics.mean(ranks) if ranks else 0.0

    # Round 0, raw graph: comparable to the published seeding-study number.
    _, adj_raw0 = _adjacencies(node_ids, rows0)
    u_raw, _ = measure(adj_raw0, used)
    h_raw, _ = measure(adj_raw0, held)
    print(
        f"kNN@5 control: used {knn_recall['used']:.3f} held {knn_recall['held']:.3f}   "
        f"SA@5 on the raw graph ({args.mode} S={args.top_s}): used {u_raw:.3f} held {h_raw:.3f}"
    )

    policies = {
        "shipped": dict(gate=False, alpha=0.0),
        "gate": dict(gate=True, alpha=0.0),
        "grow01": dict(gate=True, alpha=0.01),
        "grow10": dict(gate=True, alpha=0.1),
    }
    report: dict[str, object] = {
        "run_id": str(ULID()),
        "dataset": args.dataset,
        "passages": len(data.passages),
        "entities": len(names),
        "questions": len(data.questions),
        "used": len(used),
        "held": len(held),
        "mode": args.mode,
        "top_s": args.top_s,
        "hops": args.hops,
        "damping": args.damping,
        "top_k_working_set": TOP_K,
        "w_max": W_MAX,
        "lambda": LAMBDA,
        "knn_recall": knn_recall,
        "raw_round0": {"used": u_raw, "held": h_raw},
        "policies": {},
    }

    history: list[dict[str, float | int]] = []
    for name in [p.strip() for p in args.policies.split(",") if p.strip()]:
        pol = policies[name]
        edges = _edges(rows0)
        # Enter the substrate's regime: the tick's cap, before any decay.
        edges = enforce_saturation(edges, max_out_degree=10_000, w_max=W_MAX)
        history.clear()

        def snapshot(r: int, edges_: list[Edge], spared: int, deltas: int) -> None:
            rows = [(str(e.source_id), str(e.target_id), float(e.weight)) for e in edges_]
            _, adj = _adjacencies(node_ids, rows)
            u, ru = measure(adj, used)
            h, rh = measure(adj, held)
            ws = [e.weight for e in edges_]
            row: dict[str, float | int] = {
                "round": r,
                "used": u,
                "used_rank": ru,
                "held": h,
                "held_rank": rh,
                "w_median": statistics.median(ws),
                "w_max": max(ws),
                "at_cap": sum(1 for w in ws if w >= 0.999) / len(ws),
                "spared": spared,
                "deltas": deltas,
            }
            history.append(row)
            print(
                f"{r:5d} {u:7.3f} {ru:7.1f} {h:7.3f} {rh:7.1f} "
                f"{row['w_median']:7.4f} {row['w_max']:7.4f} {row['at_cap']:6.1%} "
                f"{spared:8d} {deltas:7d}"
            )

        print(
            f"\n== {name}  (decay_gate={pol['gate']}, hebbian alpha={pol['alpha']}, normalised) =="
        )
        print(
            f"{'round':>5s} {'used@5':>7s} {'rank':>7s} {'held@5':>7s} {'rank':>7s} "
            f"{'w med':>7s} {'w max':>7s} {'cap':>6s} {'spared':>8s} {'deltas':>7s}"
        )
        snapshot(0, edges, 0, 0)

        for r in range(1, args.rounds + 1):
            rows = [(str(e.source_id), str(e.target_id), float(e.weight)) for e in edges]
            _, adj = _adjacencies(node_ids, rows)
            # Neighbour index for the Hebbian credit: the working set is ~50 nodes,
            # so credit is found by walking their out-lists (~2k checks), not by
            # scanning all 283k edges per question — that scan cost hours.
            out_of: dict[str, list[str]] = {}
            if pol["alpha"] > 0.0:
                for e in edges:
                    out_of.setdefault(str(e.source_id), []).append(str(e.target_id))
            passes: list[dict[str, object]] = []
            deltas: list[dict[str, object]] = []
            for qi in used:
                x = _propagate(adj, seed_vec(qi), hops=args.hops, damping=args.damping)
                k = min(TOP_K, n_nodes)
                # Stable order, because 56.8% of this graph's weights sit at the
                # cap and produce exactly tied activations: `torch.topk` broke
                # those ties differently between two policies started from the
                # same state (spared 36,858 against 30,214 in round 1). The
                # top-5 passage ranking was unaffected; the working set's tail
                # was not. The first measured run predates this line.
                idx = torch.argsort(-x, stable=True)[:k]
                vals = x[idx]
                working = [
                    node_ids[i] for i, v in zip(idx.tolist(), vals.tolist(), strict=True) if v > 0
                ]
                passes.append({"at": datetime.now(UTC).isoformat(), "node_ids": working})
                if pol["alpha"] > 0.0 and working:
                    act = {
                        node_ids[i]: float(v)
                        for i, v in zip(idx.tolist(), vals.tolist(), strict=True)
                        if v > 0
                    }
                    peak = max(act.values()) or 1.0
                    scored = []
                    for s in act:
                        for t in out_of.get(s, ()):
                            if t in act:
                                scored.append(((act[s] / peak) * (act[t] / peak), s, t))
                    scored.sort(reverse=True)
                    for prod, s, t in scored[:MAX_DELTAS]:
                        deltas.append(
                            {"source_id": s, "target_id": t, "weight_delta": pol["alpha"] * prod}
                        )
            if deltas:
                edges = merge_edge_deltas(edges, deltas, w_max=W_MAX)
            fired = fired_pairs(passes, deltas) if pol["gate"] else None
            spared = decay_edges_inplace(edges, lam=LAMBDA, dt=1.0, fired=fired)
            edges = enforce_saturation(edges, max_out_degree=10_000, w_max=W_MAX)
            if r in checkpoints:
                snapshot(r, edges, spared, len(deltas))

        report["policies"][name] = {
            "gate": pol["gate"],
            "alpha": pol["alpha"],
            "history": list(history),
        }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"heartbeat_{args.dataset}_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport: {out}   ({time.perf_counter() - t0:.0f}s total)")


if __name__ == "__main__":
    main()
