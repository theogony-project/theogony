#!/usr/bin/env python
"""The latent last mile (PHX-1109): train the projector, then ask the gold set four ways.

    scripts/mesh_latent_mile.py train  --root data/mesh-founding --seed 0 \
        --projector data/latent_mile/projector_s0.pt [--epochs 5]
    scripts/mesh_latent_mile.py answer --root data/mesh-founding \
        --projector data/latent_mile/projector_s0.pt [--limit N] [--out detail.json]

Four arms, one frozen local reader, one Constellation per question:

    closed_book      no material
    constellation    the shipped text rendering
    soft             the same nodes as projected vectors, one soft token each
    soft_untrained   the same projector before training — the control

Costs no money; everything runs on the laptop. Costs time: a training epoch
over the founding mesh is minutes, the answer run over 47 questions and four
arms about a quarter of an hour. Greedy decoding is deterministic, so the
spread worth reporting is across projectors trained with different `--seed`s,
not across repeats of the same prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from theogony.mesh.eval.corpus_answers import summarise_answers
from theogony.mesh.eval.corpus_qa import load_gold
from theogony.mesh.eval.latent_mile import (
    ARMS,
    CONTROL_SEED,
    DEFAULT_READER,
    VECTOR_MODES,
    LocalReader,
    answer_gold_set_local,
    fresh_projector,
    load_projector,
    node_vector,
    paired_arms,
    report_dict,
    save_projector,
    split_holdout,
    token_loss_split,
    train_projector,
    training_nodes,
)
from theogony.mesh.retrieval.defaults import DEFAULT_K_SEEDS, DEFAULT_TOP_K
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.seeds.wikidata5m.embedder import BGESmallEnEmbedder


def _say(msg: str) -> None:
    # stdout in a pipe is block-buffered; a run that takes an hour must be
    # readable while it runs (lesson from the heartbeat scripts).
    print(msg, flush=True)


def cmd_train(args: argparse.Namespace) -> None:
    reader = LocalReader.load(args.reader, dtype=args.dtype)
    runtime = MeshRuntime.open(args.root)
    nodes = training_nodes(runtime.nodes.load_all_consolidated())
    if args.max_nodes:
        nodes = nodes[: args.max_nodes]
    node_dim = len(node_vector(nodes[0], args.vectors))
    projector = fresh_projector(reader, node_dim, seed=args.seed)
    resumed = None
    if args.resume:
        previous = load_projector(args.resume, reader.device)
        if previous.mode != args.vectors or previous.projector.node_dim != node_dim:
            raise SystemExit(
                f"{args.resume} was trained on {previous.mode!r} vectors, this run asks for "
                f"{args.vectors!r}"
            )
        projector.load_state_dict(previous.projector.state_dict())
        resumed = (
            f"{args.resume} after "
            f"{len(previous.report['epochs']) if previous.report else '?'} epochs"
        )
    _say(
        f"Leser {reader.name} auf {reader.device} ({args.dtype})   Knoten {len(nodes)}   "
        f"Vektoren {args.vectors}   Projektor {node_dim} -> {reader.llm_dim}   "
        f"Seed {args.seed}   Epochen {args.epochs}"
        + (f"   fortgesetzt von {resumed}" if resumed else "")
    )
    report = train_projector(
        reader,
        projector,
        nodes,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        holdout_fraction=args.holdout,
        mode=args.vectors,
        checkpoint=args.projector,
        resumed_from=resumed,
        log=_say,
    )
    save_projector(projector, args.projector, report)
    _say(f"Projektor geschrieben: {args.projector}")


def cmd_answer(args: argparse.Namespace) -> None:
    reader = LocalReader.load(args.reader, dtype=args.dtype)
    runtime = MeshRuntime.open(args.root)
    embedder = BGESmallEnEmbedder()

    def embed(text: str) -> list[float]:
        return asyncio.run(embedder.embed_many([text]))[0]

    loaded = load_projector(args.projector, reader.device) if args.projector else None
    projector = loaded.projector if loaded else None
    training = loaded.report if loaded else None
    # the soft arm reads the vectors its projector was trained on; the flag
    # only decides the width of the control when there is no projector at all
    mode = loaded.mode if loaded else (args.vectors or "semantic")
    gold = load_gold()
    if args.limit:
        gold = gold[: args.limit]
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    retrieve_kwargs = {"k_seeds": args.seeds} if args.seeds is not None else {}

    results = answer_gold_set_local(
        reader,
        runtime,
        embed,
        projector=projector,
        arms=arms,
        gold=gold,
        top_k=args.top_k,
        max_new_tokens=args.max_new_tokens,
        mode=mode,
        log=_say if args.verbose else None,
        **retrieve_kwargs,
    )
    summary = summarise_answers(results)

    _say(
        f"Leser {reader.name}   Ticks {runtime.tick_count()}   top_k {args.top_k}   "
        f"k_seeds {args.seeds if args.seeds is not None else DEFAULT_K_SEEDS}   "
        f"Fragen {len(gold)}   Vektoren {mode}   Projektor {args.projector or '-'}"
    )
    if training:
        last = training["epochs"][-1]
        _say(
            f"Projektor-Training: {training['nodes_train']} Knoten, "
            f"{len(training['epochs'])} Epochen, Verlust {last['train_loss']:.3f}, "
            f"Label wiedererkannt {last['label_recovery_train']:.0%} (Training) / "
            f"{last['label_recovery_holdout']:.0%} (zurückgehalten)"
        )
    _say("")
    _say(f"{'Arm':16s} {'Antwort-Recall':>15s} {'vollständig':>12s} {'verweigert':>11s}")
    for arm in arms:
        s = summary.get(arm)
        if s:
            _say(
                f"{arm:16s} {s['answer_recall']:14.0%} "
                f"{s['complete_answers']:7.0f}/{s['questions']:.0f} {s['declined']:10.0f}"
            )

    comparisons = [
        ("soft", "constellation", "Vektoren gegen Text, dieselbe Constellation"),
        ("soft", "soft_untrained", "trainiert gegen untrainiert"),
        ("soft", "closed_book", "Vektoren gegen Vorwissen"),
        ("constellation", "closed_book", "Text gegen Vorwissen"),
    ]
    for arm, against, label in comparisons:
        if arm in summary and against in summary:
            pair = paired_arms(results, arm=arm, against=against)
            _say(
                f"\n{label}: {pair['delta']:+.0%} Recall; Frage für Frage "
                f"{pair['better']} besser / {pair['worse']} schlechter / {pair['equal']} gleich"
            )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "reader": reader.name,
                    "projector": str(args.projector) if args.projector else None,
                    "vectors": mode,
                    "training": training,
                    "ticks": runtime.tick_count(),
                    "top_k": args.top_k,
                    "k_seeds": args.seeds if args.seeds is not None else DEFAULT_K_SEEDS,
                    "summary": summary,
                    "answers": [
                        {
                            "id": r.id,
                            "arm": r.arm,
                            "kind": r.kind,
                            "expected": r.expected,
                            "answer": r.answer,
                            "found": r.found,
                            "missed": r.missed,
                        }
                        for r in results
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _say(f"\nDetail geschrieben: {args.out}")


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Name or register: what the soft token pays for, on train and held-out nodes."""
    reader = LocalReader.load(args.reader, dtype=args.dtype)
    runtime = MeshRuntime.open(args.root)
    loaded = load_projector(args.projector, reader.device)
    nodes = training_nodes(runtime.nodes.load_all_consolidated())
    train, holdout = split_holdout(nodes, args.holdout, args.seed)
    control = fresh_projector(reader, loaded.projector.node_dim, seed=CONTROL_SEED)
    _say(
        f"Leser {reader.name}   Projektor {args.projector} "
        f"({len(loaded.report['epochs']) if loaded.report else '?'} Epochen, {loaded.mode})   "
        f"je {args.sample} Knoten"
    )
    _say(f"{'Knoten':8s} {'Vektor':10s} {'Name-Token':>11s} {'Beschreibung-Token':>19s}")
    for name, group in (("train", train[: args.sample]), ("holdout", holdout[: args.sample])):
        shifted = list(group[7:]) + list(group[:7])
        for label, projector, source in (
            ("richtig", loaded.projector, None),
            ("fremd", loaded.projector, shifted),
            ("Kontrolle", control, None),
        ):
            split = token_loss_split(reader, projector, group, mode=loaded.mode, vector_from=source)
            _say(
                f"{name:8s} {label:10s} {split['label_loss']:11.3f} "
                f"{split['description_loss']:19.3f}"
            )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", default=Path("data/mesh-founding"), type=Path)
        p.add_argument("--reader", default=DEFAULT_READER, help="HF id of the frozen chat model.")
        p.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])

    t = sub.add_parser("train", help="Train a projector by paraphrase on the mesh's own nodes.")
    common(t)
    t.add_argument("--projector", required=True, type=Path, help="Where to write the projector.")
    t.add_argument(
        "--vectors",
        default="both",
        choices=VECTOR_MODES,
        help="Which node vectors the projector reads: semantic | description | both.",
    )
    t.add_argument("--epochs", default=5, type=int)
    t.add_argument("--batch-size", default=8, type=int)
    t.add_argument("--lr", default=1e-3, type=float)
    t.add_argument("--seed", default=0, type=int)
    t.add_argument(
        "--holdout", default=0.05, type=float, help="Fraction of nodes kept for validation."
    )
    t.add_argument(
        "--max-nodes", default=0, type=int, help="Train on the first N nodes only (smoke)."
    )
    t.add_argument(
        "--resume", type=Path, default=None, help="Start from this projector's weights, not fresh."
    )
    t.set_defaults(func=cmd_train)

    a = sub.add_parser("answer", help="Ask the gold set through the local reader, four ways.")
    common(a)
    a.add_argument("--projector", type=Path, help="A trained projector; required for the soft arm.")
    a.add_argument(
        "--vectors",
        default=None,
        choices=VECTOR_MODES,
        help="Vector width for the control when no projector is given (else from the projector).",
    )
    a.add_argument("--top-k", default=DEFAULT_TOP_K, type=int)
    a.add_argument(
        "--seeds", default=None, type=int, help="k_seeds (default: the library default)."
    )
    a.add_argument("--limit", default=0, type=int, help="First N questions only (0 = all).")
    a.add_argument("--arms", default=",".join(ARMS))
    a.add_argument("--max-new-tokens", default=120, type=int)
    a.add_argument("--out", type=Path, help="Write per-answer detail as JSON here.")
    a.add_argument("--verbose", action="store_true")
    a.set_defaults(func=cmd_answer)

    d = sub.add_parser("diagnose", help="Per-token loss on the name against the description.")
    common(d)
    d.add_argument("--projector", required=True, type=Path)
    d.add_argument("--sample", default=60, type=int, help="Nodes per split.")
    d.add_argument("--holdout", default=0.05, type=float, help="Must match the training run.")
    d.add_argument("--seed", default=0, type=int, help="Must match the training run.")
    d.set_defaults(func=cmd_diagnose)

    args = ap.parse_args(argv)
    args.func(args)
    # every flag above is read by the command it belongs to; `report_dict` is
    # what the training report is serialised with when `--out` is given.
    assert report_dict is not None


if __name__ == "__main__":
    main(sys.argv[1:])
