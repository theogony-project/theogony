#!/usr/bin/env python3
"""LLM-as-judge probe: are the substrate's high-activation NON-edges actually true?

This measures the project's central claim head-on — *can the vector-graph surface
relations that were never written?* (TARGET_ARCHITECTURE). Link prediction only
credits exact held-out hits; it *penalises* the substrate for ranking a
plausible-but-unrecorded relation highly. This probe inverts that: it takes pairs
the substrate strongly co-activates **but has no edge for**, and asks a frontier
model whether a real relationship plausibly exists.

Blind, controlled protocol (the control is what makes it honest):
  * EMERGENT pairs  — for sampled seeds, the top SA-activated target that is NOT a
                      neighbour (no edge in either direction). The substrate "thinks"
                      they are related but was never told so.
  * CONTROL pairs   — random non-edge pairs from the same node pool.
  * Both are shuffled together and judged by the SAME prompt, so the model never
    knows which group a pair belongs to. The headline is the LIFT
    (emergent yes-rate / control yes-rate): it cancels the model's absolute
    agreeableness bias. Mean target degree per group is reported so hub-inflation
    is visible rather than hidden.

Uses Claude via the Anthropic SDK (key from env). Model is auto-discovered so a
drifted model name does not break the run.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import torch
from ulid import ULID

from theogony.mesh.eval.link_prediction import build_adjacency, propagate
from theogony.mesh.runtime.oneiros_tick import MeshRuntime


def _pick_model(client, preferred: str | None) -> str:
    if preferred:
        return preferred
    models = [m.id for m in client.models.list(limit=100).data]
    for want in ("sonnet", "opus", "haiku"):
        for mid in models:
            if want in mid.lower():
                return mid
    if not models:
        raise SystemExit("no Anthropic models available to this key")
    return models[0]


def _judge_prompt(label_a: str, qid_a: str, label_b: str, qid_b: str) -> str:
    return (
        "You assess whether a direct, factual real-world relationship plausibly "
        "exists between two Wikidata entities. Be strict: answer true only if a "
        "specific relationship plausibly holds (e.g. part-of, member-of, "
        "located-in, created-by, parent/subsidiary, spouse, shares-border, "
        "same franchise/series), NOT mere topical similarity.\n\n"
        f"Entity A: {label_a} ({qid_a})\n"
        f"Entity B: {label_b} ({qid_b})\n\n"
        'Reply ONLY as JSON: {"related": true|false, "confidence": 0.0-1.0, '
        '"relation": "<short phrase or null>", "reason": "<one short sentence>"}'
    )


def _judge(client, model: str, label_a, qid_a, label_b, qid_b) -> dict:
    msg = client.messages.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": _judge_prompt(label_a, qid_a, label_b, qid_b)}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"related": None, "confidence": None, "relation": None, "reason": text[:200]}
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path("data/mesh-wiki-100k"))
    parser.add_argument("--n-emergent", type=int, default=100)
    parser.add_argument(
        "--n-seeds", type=int, default=600, help="Seeds fired to harvest emergent pairs."
    )
    parser.add_argument("--hops", type=int, default=3)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument(
        "--model", type=str, default=None, help="Override; else auto-discover a Claude model."
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=5, help="Concurrent judge API calls.")
    parser.add_argument("--report-dir", type=Path, default=Path("data/run_reports/mesh_eval"))
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set")

    rng = random.Random(args.seed)
    rt = MeshRuntime.open(args.root.resolve())
    csr = rt.rebuild_csr()
    n = len(csr.node_ids)
    index_to_id = csr.node_ids

    # node_id -> (label, qid) for the judge
    label: dict[str, str] = {}
    qid: dict[str, str] = {}
    for node in rt.nodes.iter_consolidated():
        nid = str(node.id)
        label[nid] = node.description or (node.tags[0] if node.tags else nid[:8])
        qid[nid] = node.qids[0].qid if node.qids else "?"

    # known directed edges as packed ints; in-degree for hub reporting
    known: set[int] = set()
    in_deg = torch.zeros(n, dtype=torch.int32)
    crow = csr.crow_indices.tolist()
    cols = csr.col_indices.tolist()
    for si in range(n):
        for p in range(crow[si], crow[si + 1]):
            ti = cols[p]
            known.add(si * n + ti)
            in_deg[ti] += 1

    def is_edge(a: int, b: int) -> bool:
        return (a * n + b) in known or (b * n + a) in known

    adj = build_adjacency(csr, torch.device("cpu"))

    # EMERGENT: per-seed top non-edge target by activation
    emergent: list[tuple[int, int, float]] = []
    seeds = rng.sample(range(n), min(args.n_seeds, n))
    for si in seeds:
        act = propagate(adj, si, n, hops=args.hops, damping=args.damping)
        act[si] = 0.0
        vals, idxs = torch.topk(act, 20)
        for val, ti in zip(vals.tolist(), idxs.tolist(), strict=False):
            ti = int(ti)
            if val <= 0.0 or ti == si or is_edge(si, ti):
                continue
            if index_to_id[si] not in label or index_to_id[ti] not in label:
                continue
            emergent.append((si, ti, val))
            break
        if len(emergent) >= args.n_emergent:
            break

    # CONTROL: target-matched. For each emergent (s, t), keep the SAME target t but
    # pair it with a RANDOM non-edge source s'. This matches the target-degree
    # distribution exactly, so the lift isolates SA's source-selection signal from
    # the trivial "hubs relate to everything" confound.
    control: list[tuple[int, int, float]] = []
    for s, t, _score in emergent:
        for _ in range(64):
            sp = rng.randrange(n)
            if sp in (t, s) or is_edge(sp, t):
                continue
            if index_to_id[sp] not in label:
                continue
            control.append((sp, t, 0.0))
            break

    tagged = [("emergent", p) for p in emergent] + [("control", p) for p in control]
    rng.shuffle(tagged)

    import anthropic

    client = anthropic.Anthropic()
    model = _pick_model(client, args.model)
    print(f"workspace: {args.root}  nodes: {n}  model: {model}")
    print(f"judging {len(emergent)} emergent + {len(control)} control pairs (blind)...")

    from concurrent.futures import ThreadPoolExecutor

    def _one(item: tuple[str, tuple[int, int, float]]) -> dict:
        group, (a, b, score) = item
        ida, idb = index_to_id[a], index_to_id[b]
        verdict = _judge(client, model, label[ida], qid[ida], label[idb], qid[idb])
        return {
            "group": group,
            "a": label[ida],
            "a_qid": qid[ida],
            "b": label[idb],
            "b_qid": qid[idb],
            "sa_score": score,
            "target_in_degree": int(in_deg[b].item()),
            "related": verdict.get("related"),
            "confidence": verdict.get("confidence"),
            "relation": verdict.get("relation"),
            "reason": verdict.get("reason"),
        }

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_one, tagged))
    print(f"  judged {len(results)} pairs in {time.perf_counter() - t0:.0f}s")

    def _rate(group: str) -> tuple[float, float, float]:
        rows = [r for r in results if r["group"] == group]
        yes = [r for r in rows if r["related"] is True]
        rate = len(yes) / max(len(rows), 1)
        mean_deg = sum(r["target_in_degree"] for r in rows) / max(len(rows), 1)
        mean_conf = sum((r["confidence"] or 0.0) for r in yes) / max(len(yes), 1)
        return rate, mean_deg, mean_conf

    e_rate, e_deg, e_conf = _rate("emergent")
    c_rate, c_deg, c_conf = _rate("control")
    lift = e_rate / c_rate if c_rate > 0 else float("inf")

    print()
    print("=== emergent-knowledge judge ===")
    print(f"{'group':<12}{'yes-rate':>10}{'mean tgt deg':>14}{'mean conf(yes)':>16}")
    print("-" * 52)
    print(f"{'emergent':<12}{e_rate:>10.2%}{e_deg:>14.1f}{e_conf:>16.2f}")
    print(f"{'control':<12}{c_rate:>10.2%}{c_deg:>14.1f}{c_conf:>16.2f}")
    print()
    print(f"LIFT (emergent / control yes-rate): {lift:.2f}x")
    print()
    print("--- sample emergent 'true' judgments ---")
    shown = 0
    for r in results:
        if r["group"] == "emergent" and r["related"] is True:
            print(f"  {r['a']} -- {r['relation']} --> {r['b']}  ({r['reason']})")
            shown += 1
            if shown >= 8:
                break

    report = {
        "run_id": str(ULID()),
        "workspace": str(args.root),
        "model": model,
        "n_emergent": len(emergent),
        "n_control": len(control),
        "emergent_yes_rate": e_rate,
        "control_yes_rate": c_rate,
        "lift": lift,
        "emergent_mean_target_degree": e_deg,
        "control_mean_target_degree": c_deg,
        "results": results,
        "elapsed_s": time.perf_counter() - t0,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out = args.report_dir / f"emergent_judge_{report['run_id']}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nreport: {out}")


if __name__ == "__main__":
    main()
