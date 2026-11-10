"""Were the mentions that moved between two builds of a mesh better or worse placed?

PHX-1118 found that with description accrual on, 961 of the 43,118 mentions of
the 2Wiki mesh landed on a different node than without it, and that none of
its identity controls — the entity count, the top-20 in-degree, the gold-name
control — can say whether such a move was right. This is the instrument that
can (PHX-1120).

Three steps, each writing a file the next one reads:

``collect``
    Joins the two meshes' ``mesh_ingest_link_decision`` audit rows on
    (paragraph, the concept label the reader extracted, its occurrence in the
    paragraph) — one row per mention, so the join is exact, unlike a join on
    labels — and keeps every mention whose node's label differs between the
    builds, plus a seeded sample of mentions that did not move, as the base
    rate. Each item carries the paragraph, the mention as the reader extracted
    it, and the node each build linked it to (name, description, the linker's
    signal and score). With ``--same-name`` it also keeps the mentions that
    moved to another node of the same name — matched across the builds by the
    mention that minted each node, since a name cannot tell *Paris* the prince
    from *Paris* the city — as a group of their own, judged like the others and
    left out of the control sample (PHX-1121).

``judge``
    Shows a judge model the paragraph, the mention and **one candidate node at
    a time**, never both and never which build it came from, and asks whether
    the node is the entity the mention refers to: ``same``, ``different`` or
    ``unclear``. Resumable; every judgment records the model that actually
    answered, so a silent provider fallback is visible.

``export-blind`` / ``import-blind``
    The same judgments for a second judge — another model, an agent fleet or
    a person — who answers in batches: every batch holds only old or only new
    candidates, shuffled with a seed, so no batch shows both nodes of one
    mention; a list of ``{unit_id, verdict}`` comes back in as a judgments
    file. PHX-1120's second judge, Claude Opus 5.5 in batches of forty run as a
    Claude Code workflow (sixty in the first pass, twenty-five for the second
    pass's new nodes, under opaque ids), was fed and read back this way.

``summarise``
    For a moved mention, the two verdicts say whether the move was an
    improvement (old node different, new node same), a loss (the reverse), a
    move between two nodes of one entity (both same — a duplicate), or between
    two wrong ones; better against worse with an exact sign test, by the
    linker signal that placed it. With ``--second``, the agreement of two
    judges (Cohen's kappa) over the judgments they share.

    .venv/bin/python scripts/mesh_mention_audit.py collect --a data/mesh-2wiki-off \\
        --b data/mesh-2wiki-on --out data/run_reports/phx1120/items.jsonl
    THEOGONY_LLM__PROVIDER=deepseek THEOGONY_LLM__MODEL_ID=deepseek-chat \\
        .venv/bin/python scripts/mesh_mention_audit.py judge \\
        --items data/run_reports/phx1120/items.jsonl \\
        --out data/run_reports/phx1120/judgments_deepseek.jsonl
    .venv/bin/python scripts/mesh_mention_audit.py summarise \\
        --items data/run_reports/phx1120/items.jsonl \\
        --judgments data/run_reports/phx1120/judgments_deepseek.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from theogony.mesh.eval.qa_datasets import load_dataset
from theogony.mesh.eval.qa_mesh import load_readings, reading_key, sign_test_p
from theogony.mesh.runtime.oneiros_tick import MeshRuntime

VERDICTS = ("same", "different", "unclear")

JUDGE_SYSTEM = (
    "You check one link in a knowledge graph. A reader extracted a mention from a "
    "Wikipedia paragraph and linked it to a node. Decide whether the node denotes the "
    "same real-world entity the mention refers to in this paragraph. Answer with one "
    "word: same, different or unclear."
)

JUDGE_RULES = """\
Answer with exactly one word.
- same: the node is the entity the mention refers to here. Another name, spelling,
  translation or form of the same name counts as the same entity.
- different: the node is another entity: a different person, place, work,
  organisation, event or thing, or a broader, narrower or related one (a country for
  its empire, a city for its region, a film for its sequel, an award for one of its
  ceremonies, a person for a relative).
- unclear: the paragraph and the node's description do not let you tell."""


def judge_prompt(item: dict[str, Any], side: str) -> str:
    """The user prompt for one candidate node; the build it came from is not named."""
    node = item[side]
    mention = item["mention"]
    note = f" — {mention['description']}" if mention.get("description") else ""
    return (
        f"PARAGRAPH (from the Wikipedia article {item['title']!r}):\n{item['text']}\n\n"
        f"MENTION: {mention['label']!r}{note}\n\n"
        f"NODE: {node['name']} — {node['description']}\n\n"
        f"{JUDGE_RULES}"
    )


def parse_verdict(text: str) -> str:
    """The first of the three words the reply starts with; 'unparsed' otherwise."""
    head = text.strip().lower().lstrip("*\"'`").split()
    if not head:
        return "unparsed"
    word = head[0].strip(".,:;!*\"'`")
    return word if word in VERDICTS else "unparsed"


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


def _audit(
    runtime: MeshRuntime,
) -> tuple[dict[tuple[int, str, int], dict[str, Any]], dict[str, int]]:
    """The build's link decisions, one per mention — (paragraph, label, occurrence)
    -> the row — and, per revised node, the length of its description before
    the first revision."""
    runtime.audit.flush()
    table = runtime.audit._table.search().select(["action", "payload_json"]).to_arrow()
    decisions: dict[tuple[int, str, int], dict[str, Any]] = {}
    created_chars: dict[str, int] = {}
    seen: Counter[tuple[int, str]] = Counter()
    for action, payload in zip(
        table.column("action").to_pylist(), table.column("payload_json").to_pylist(), strict=True
    ):
        if action == "mesh_ingest_description_revised":
            row = json.loads(payload)
            node_id = str(row["node_id"])
            before = int(row["chars_before"])
            created_chars[node_id] = min(before, created_chars.get(node_id, before))
            continue
        if action != "mesh_ingest_link_decision":
            continue
        row = json.loads(payload)
        base = (int(row["paragraph"]), str(row["label"]))
        decisions[(*base, seen[base])] = row
        seen[base] += 1
    return decisions, created_chars


def _decisions(runtime: MeshRuntime) -> dict[tuple[int, str, int], dict[str, Any]]:
    """One row per mention: (paragraph, label, occurrence) -> the link decision."""
    return _audit(runtime)[0]


def _node_view(node: Any, created_chars: int | None = None) -> dict[str, Any]:
    """A node as the judge sees it: its name and the description it was created
    with. Accrual keeps that text as a byte-identical prefix, so it is the stored
    description cut where the first revision began. Judging a node on its accrued
    text would show the judge the mention's own words, which accrual folded in
    when the mention linked (PHX-1120, found by its claim check)."""
    tags = list(node.tags or [])
    description = (node.description or "").strip()
    created = description if created_chars is None else description[:created_chars].strip()
    name = tags[0] if tags else description.split(" — ", 1)[0]
    return {
        "name": name,
        "description": created,
        "accrued_description": description if created != description else None,
        "revised": bool(node.description_source_chunks),
    }


# A mention moved by name (its node's name differs between the builds), or to
# another node of the same name (``collect --same-name``); both are judged on
# both sides. A control mention is judged on its one node.
MOVED_GROUPS = ("moved", "moved_same_name")


def judged_sides(item: dict[str, Any]) -> tuple[str, ...]:
    return ("a", "b") if item["group"] in MOVED_GROUPS else ("a",)


def minted_by(
    decisions: dict[tuple[int, str, int], dict[str, Any]],
) -> dict[str, tuple[int, str, int]]:
    """Each node's minting mention: the link decision that created it.

    Node ids differ between two builds, so a node is matched across them by the
    mention that minted it: two nodes minted by the same mention are the same
    node, whatever their names; two nodes of one name minted by different
    mentions are not (*Paris* the prince and *Paris* the city, PHX-1120).
    """
    minted: dict[str, tuple[int, str, int]] = {}
    for key in sorted(decisions):
        row = decisions[key]
        if row.get("signal") == "emergent":
            minted.setdefault(str(row["node_id"]), key)
    return minted


def split_same_name(
    stayed: list[tuple[int, str, int]],
    dec_a: dict[tuple[int, str, int], dict[str, Any]],
    dec_b: dict[tuple[int, str, int], dict[str, Any]],
) -> tuple[list[tuple[int, str, int]], list[tuple[int, str, int]], int]:
    """Of the mentions whose node kept its name, those that moved to another node
    of that name, those that did not, and how many could not be told: a node
    no link decision minted (a paragraph concept's, or a seed's) has no mention
    to be matched by, and its mentions count as not moved."""
    minted_a, minted_b = minted_by(dec_a), minted_by(dec_b)
    moved: list[tuple[int, str, int]] = []
    still: list[tuple[int, str, int]] = []
    unknown = 0
    for key in stayed:
        origin_a = minted_a.get(str(dec_a[key]["node_id"]))
        origin_b = minted_b.get(str(dec_b[key]["node_id"]))
        if origin_a is None or origin_b is None:
            unknown += 1
            still.append(key)
        elif origin_a != origin_b:
            moved.append(key)
        else:
            still.append(key)
    return moved, still, unknown


def split_moves(
    dec_a: dict[tuple[int, str, int], dict[str, Any]],
    dec_b: dict[tuple[int, str, int], dict[str, Any]],
    nodes_a: dict[str, Any],
    nodes_b: dict[str, Any],
) -> tuple[list[tuple[int, str, int]], list[tuple[int, str, int]]]:
    """The mentions both builds hold, split by whether their node's name differs.

    Node ids are not shared between two builds, so "the same node" is the same
    name — the label the reader created it with, which accrual never changes. A
    mention whose node is missing from its build (it cannot be judged) is in
    neither list.
    """
    moved: list[tuple[int, str, int]] = []
    stayed: list[tuple[int, str, int]] = []
    for key in sorted(set(dec_a) & set(dec_b)):
        node_a = nodes_a.get(str(dec_a[key]["node_id"]))
        node_b = nodes_b.get(str(dec_b[key]["node_id"]))
        if node_a is None or node_b is None:
            continue
        if _node_view(node_a)["name"] != _node_view(node_b)["name"]:
            moved.append(key)
        else:
            stayed.append(key)
    return moved, stayed


def select_mentions(
    dec_a: dict[tuple[int, str, int], dict[str, Any]],
    dec_b: dict[tuple[int, str, int], dict[str, Any]],
    nodes_a: dict[str, Any],
    nodes_b: dict[str, Any],
    *,
    same_name: bool,
    control: int,
    seed: int,
) -> tuple[
    list[tuple[int, str, int]], list[tuple[int, str, int]], list[tuple[int, str, int]], int, int
]:
    """The mentions to judge: moved by name; moved to another node of the same
    name (with ``same_name``); and a seeded sample of those that did not move,
    drawn after the same-name moves are taken out. Also the size of that
    population, and how many mentions sat on a node no link decision minted."""
    moved, stayed = split_moves(dec_a, dec_b, nodes_a, nodes_b)
    same: list[tuple[int, str, int]] = []
    unknown = 0
    if same_name:
        same, stayed, unknown = split_same_name(stayed, dec_a, dec_b)
    rng = random.Random(seed)
    sample = sorted(rng.sample(stayed, min(control, len(stayed))))
    return moved, same, sample, len(stayed), unknown


def collect(args: argparse.Namespace) -> None:
    data = load_dataset(args.dataset, args.cache_dir, max_questions=1000, seed=0)
    readings_path = args.readings or (args.cache_dir / f"kadmos_readings_{args.dataset}.jsonl")
    readings = load_readings(readings_path)
    passages = list(data.passages)

    meshes = {}
    for side, root in (("a", args.a), ("b", args.b)):
        runtime = MeshRuntime.open(root)
        nodes = {str(n.id): n for n in runtime.nodes.load_all_consolidated()}
        decisions, created_chars = _audit(runtime)
        meshes[side] = (nodes, decisions, created_chars)
        print(
            f"{side}: {root} — {len(nodes)} consolidated nodes, {len(decisions)} mentions, "
            f"{len(created_chars)} revised nodes"
        )

    nodes_a, dec_a, created_a = meshes["a"]
    nodes_b, dec_b, created_b = meshes["b"]
    shared = sorted(set(dec_a) & set(dec_b))
    only = len(set(dec_a) ^ set(dec_b))
    print(f"mentions in both builds: {len(shared)}; in one only: {only}")

    def concept_of(passage_idx: int, label: str) -> dict[str, Any]:
        reading = readings.get(reading_key(passages[passage_idx].text)) or {}
        for concept in reading.get("concepts", []):
            if concept.get("label") == label:
                return {
                    "label": label,
                    "entity_type": concept.get("entity_type"),
                    "description": concept.get("description") or "",
                }
        return {"label": label, "entity_type": None, "description": ""}

    moved, same_name, control, stayed, unknown = select_mentions(
        dec_a,
        dec_b,
        nodes_a,
        nodes_b,
        same_name=args.same_name,
        control=args.control,
        seed=args.seed,
    )
    if args.same_name:
        print(
            f"moved to another node of the same name: {len(same_name)} "
            f"({unknown} on a node no link decision minted, counted as not moved)"
        )
    print(f"moved: {len(moved)}; did not move: {stayed}; control sample: {len(control)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for group, keys in (
            ("moved", moved),
            ("moved_same_name", same_name),
            ("control", control),
        ):
            for paragraph, label, occurrence in keys:
                passage = passages[paragraph - 1]
                row_a, row_b = (
                    dec_a[(paragraph, label, occurrence)],
                    dec_b[(paragraph, label, occurrence)],
                )
                item = {
                    "id": f"p{paragraph}:{occurrence}:{label}",
                    "group": group,
                    "paragraph": paragraph,
                    "passage_idx": passage.idx,
                    "title": passage.title,
                    "text": passage.text,
                    "mention": concept_of(paragraph - 1, label),
                    "a": {
                        **_node_view(
                            nodes_a[str(row_a["node_id"])],
                            created_a.get(str(row_a["node_id"])),
                        ),
                        "signal": row_a.get("signal"),
                        "score": row_a.get("score"),
                    },
                    "b": {
                        **_node_view(
                            nodes_b[str(row_b["node_id"])],
                            created_b.get(str(row_b["node_id"])),
                        ),
                        "signal": row_b.get("signal"),
                        "score": row_b.get("score"),
                    },
                }
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"written: {args.out}")


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def judge(args: argparse.Namespace) -> None:
    from theogony.agents.factory import build_named_llm
    from theogony.agents.spend import RunMustStop, run_paid
    from theogony.config.settings import Settings

    settings = Settings()
    # The judge is the model this run names, or none: a fallback provider would
    # put a second judge's verdicts under the first one's file (PHX-1123).
    llm = build_named_llm(settings, spend_limit_usd=args.spend_limit_usd)
    items = _read_jsonl(args.items)
    done = {(j["item_id"], j["side"]) for j in _read_jsonl(args.out)}
    todo = [
        (item, side)
        for item in items
        for side in judged_sides(item)
        if (item["id"], side) not in done
    ]
    print(
        f"model={settings.llm.provider}/{settings.llm.model_id or '<default>'} "
        f"items={len(items)} judgments to make={len(todo)} already={len(done)}",
        flush=True,
    )
    semaphore = asyncio.Semaphore(args.concurrency)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    async def one(item: dict[str, Any], side: str, fh: Any) -> str:
        async with semaphore:
            try:
                result = await llm.complete(
                    prompt=judge_prompt(item, side),
                    system=JUDGE_SYSTEM,
                    max_output_tokens=8,
                    temperature=0.0,
                    timeout_s=60,
                )
                text, model, cost = result.text, result.model_id, result.cost_eur
            except RunMustStop:
                raise  # the run cannot pay for the next judgment (PHX-1124)
            except Exception as exc:  # noqa: BLE001 - recorded, the next run retries it
                print(f"failed {item['id']} {side}: {exc}", flush=True)
                return "error"
        verdict = parse_verdict(text)
        fh.write(
            json.dumps(
                {
                    "item_id": item["id"],
                    "side": side,
                    "verdict": verdict,
                    "raw": text[:80],
                    "model": model,
                    "cost_eur": cost,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        fh.flush()
        return verdict

    async def run() -> Counter[str]:
        with args.out.open("a", encoding="utf-8") as fh:
            verdicts = await asyncio.gather(*(one(item, side, fh) for item, side in todo))
        return Counter(verdicts)

    # A stop ends the run with its reason; what was judged stays written, and a
    # rerun resumes from it (PHX-1124).
    counts = run_paid(llm, run)
    print(f"{dict(counts)} in {(time.monotonic() - started) / 60:.1f} min; written: {args.out}")


# ---------------------------------------------------------------------------
# export-blind / import-blind: the same judgments for a second judge
# ---------------------------------------------------------------------------


def blind_batches(
    items: list[dict[str, Any]], *, size: int, seed: int, sides: tuple[str, ...] = ("a", "b")
) -> list[list[dict[str, Any]]]:
    """Judgment units in batches that never hold both candidates of one mention.

    The ``unit_id`` names the mention and the side; :func:`export_blind` replaces
    it with an opaque id before a judge sees it.
    """
    units: dict[str, list[dict[str, Any]]] = {"a": [], "b": []}
    for item in items:
        for side in judged_sides(item):
            if side not in sides:
                continue
            node, mention = item[side], item["mention"]
            units[side].append(
                {
                    "unit_id": f"{item['id']}|{side}",
                    "article": item["title"],
                    "paragraph": item["text"],
                    "mention": mention["label"],
                    "reader_note": mention.get("description", ""),
                    "node": f"{node['name']} — {node['description']}",
                }
            )
    rng = random.Random(seed)
    batches: list[list[dict[str, Any]]] = []
    for side in ("a", "b"):
        shuffled = units[side][:]
        rng.shuffle(shuffled)
        batches.extend(shuffled[k : k + size] for k in range(0, len(shuffled), size))
    rng.shuffle(batches)
    return batches


def export_blind(args: argparse.Namespace) -> None:
    """Write the batches with opaque unit ids, and the key that maps them back.

    The judge sees ``u0001``, not the mention and side: an id ending in the side
    letter would tell a batch which build its nodes came from (found by the
    PHX-1120 claim check). The key stays with whoever imports the answers.
    """
    sides = tuple(args.sides.split(","))
    batches = blind_batches(_read_jsonl(args.items), size=args.size, seed=args.seed, sides=sides)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "RULES.txt").write_text(f"{JUDGE_SYSTEM}\n\n{JUDGE_RULES}\n", encoding="utf-8")
    key: dict[str, str] = {}
    for n, batch in enumerate(batches):
        for unit in batch:
            opaque = f"u{len(key) + 1:05d}"
            key[opaque] = unit["unit_id"]
            unit["unit_id"] = opaque
        path = args.out_dir / f"batch_{n:03d}.json"
        path.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
    args.key.parent.mkdir(parents=True, exist_ok=True)
    args.key.write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(batches)} batches, {len(key)} units, rules: RULES.txt, key: {args.key}")


def import_blind(args: argparse.Namespace) -> None:
    """Read ``{unit_id, verdict, reason?}`` lists (JSON files) into a judgments file."""
    key: dict[str, str] = json.loads(args.key.read_text(encoding="utf-8")) if args.key else {}
    seen: set[str] = set()
    rows = []
    for path in args.answers:
        payload = json.loads(path.read_text(encoding="utf-8"))
        answers = payload.get("judgments", payload) if isinstance(payload, dict) else payload
        for answer in answers:
            unit_id = key.get(str(answer["unit_id"]), str(answer["unit_id"]))
            if unit_id in seen:
                continue
            seen.add(unit_id)
            item_id, side = unit_id.rsplit("|", 1)
            verdict = str(answer.get("verdict", "")).lower()
            rows.append(
                {
                    "item_id": item_id,
                    "side": side,
                    "verdict": verdict if verdict in VERDICTS else "unparsed",
                    "raw": str(answer.get("reason", ""))[:200],
                    "model": args.judge,
                    "cost_eur": 0.0,
                }
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} judgments by {args.judge!r}: {args.out}")


# ---------------------------------------------------------------------------
# summarise
# ---------------------------------------------------------------------------


def _verdicts(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    return {(j["item_id"], j["side"]): j for j in _read_jsonl(path)}


def outcome(verdict_a: str, verdict_b: str) -> str:
    if verdict_a == "different" and verdict_b == "same":
        return "better"
    if verdict_a == "same" and verdict_b == "different":
        return "worse"
    if verdict_a == "same" and verdict_b == "same":
        return "both_same"
    if verdict_a == "different" and verdict_b == "different":
        return "both_different"
    return "unclear"


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa of two raters over the same judgments."""
    if not pairs:
        return float("nan")
    labels = sorted({x for pair in pairs for x in pair})
    n = len(pairs)
    observed = sum(1 for x, y in pairs if x == y) / n
    left, right = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    expected = sum(left[label] * right[label] for label in labels) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def _move_outcomes(moves: list[dict[str, Any]], verdicts: dict) -> Counter[str]:
    outcomes: Counter[str] = Counter()
    for item in moves:
        va, vb = verdicts.get((item["id"], "a")), verdicts.get((item["id"], "b"))
        if va is not None and vb is not None:
            outcomes[outcome(va["verdict"], vb["verdict"])] += 1
    return outcomes


def summarise_one(items: list[dict[str, Any]], verdicts: dict) -> dict[str, Any]:
    moved = [i for i in items if i["group"] == "moved"]
    same_name = [i for i in items if i["group"] == "moved_same_name"]
    control = [i for i in items if i["group"] == "control"]
    outcomes: Counter[str] = Counter()
    by_signal: dict[str, Counter[str]] = defaultdict(Counter)
    by_revision: dict[str, Counter[str]] = defaultdict(Counter)
    judged = 0
    for item in moved:
        va, vb = verdicts.get((item["id"], "a")), verdicts.get((item["id"], "b"))
        if va is None or vb is None:
            continue
        judged += 1
        result = outcome(va["verdict"], vb["verdict"])
        outcomes[result] += 1
        by_signal[str(item["b"]["signal"])][result] += 1
        revised = f"new node revised={item['b']['revised']}"
        by_revision[revised][result] += 1
    base: Counter[str] = Counter()
    for item in control:
        v = verdicts.get((item["id"], "a"))
        if v is not None:
            base[v["verdict"]] += 1
    models = Counter(v.get("model") for v in verdicts.values())
    by_name_and_same: dict[str, Any] = {}
    if same_name:
        same = _move_outcomes(same_name, verdicts)
        every = outcomes + same
        by_name_and_same = {
            "same_name_total": len(same_name),
            "same_name_outcomes": dict(same),
            "same_name_better_vs_worse_p": sign_test_p(same["better"], same["worse"]),
            "all_moves_outcomes": dict(every),
            "all_moves_better_vs_worse_p": sign_test_p(every["better"], every["worse"]),
        }
    return {
        **by_name_and_same,
        "moved_judged": judged,
        "moved_total": len(moved),
        "outcomes": dict(outcomes),
        "better_vs_worse_p": sign_test_p(outcomes["better"], outcomes["worse"]),
        "by_new_signal": {k: dict(v) for k, v in sorted(by_signal.items())},
        "by_new_node_revised": {k: dict(v) for k, v in sorted(by_revision.items())},
        "control_judged": sum(base.values()),
        "control_verdicts": dict(base),
        "old_node_verdicts": dict(
            Counter(
                verdicts[(i["id"], "a")]["verdict"] for i in moved if (i["id"], "a") in verdicts
            )
        ),
        "new_node_verdicts": dict(
            Counter(
                verdicts[(i["id"], "b")]["verdict"] for i in moved if (i["id"], "b") in verdicts
            )
        ),
        "models": dict(models),
        "cost_eur": round(sum(float(v.get("cost_eur") or 0) for v in verdicts.values()), 4),
    }


def summarise(args: argparse.Namespace) -> None:
    items = _read_jsonl(args.items)
    out: dict[str, Any] = {"first": summarise_one(items, _verdicts(args.judgments))}
    if args.second:
        first, second = _verdicts(args.judgments), _verdicts(args.second)
        out["second"] = summarise_one(items, second)
        shared = sorted(set(first) & set(second))
        pairs = [(first[k]["verdict"], second[k]["verdict"]) for k in shared]
        confusion = Counter(f"{x}->{y}" for x, y in pairs)
        out["agreement"] = {
            "shared_judgments": len(shared),
            "observed": round(sum(1 for x, y in pairs if x == y) / max(1, len(pairs)), 4),
            "kappa": round(kappa(pairs), 4),
            "confusion_first_to_second": dict(sorted(confusion.items())),
        }
        # Outcomes both judges agree on, item by item, per kind of move.
        agreed: dict[str, Counter[str]] = {group: Counter() for group in MOVED_GROUPS}
        for item in items:
            if item["group"] not in MOVED_GROUPS:
                continue
            keys = [(item["id"], "a"), (item["id"], "b")]
            if not all(k in first and k in second for k in keys):
                continue
            o1 = outcome(first[keys[0]]["verdict"], first[keys[1]]["verdict"])
            o2 = outcome(second[keys[0]]["verdict"], second[keys[1]]["verdict"])
            if o1 == o2:
                agreed[item["group"]][o1] += 1
        by_name = agreed["moved"]
        out["agreed_outcomes"] = dict(by_name)
        out["agreed_better_vs_worse_p"] = sign_test_p(by_name["better"], by_name["worse"])
        if any(i["group"] == "moved_same_name" for i in items):
            same = agreed["moved_same_name"]
            every = by_name + same
            out["agreed_outcomes_same_name"] = dict(same)
            out["agreed_outcomes_all_moves"] = dict(every)
            out["agreed_all_moves_better_vs_worse_p"] = sign_test_p(every["better"], every["worse"])
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("collect", help="join two builds' link decisions; write the items")
    c.add_argument("--a", type=Path, required=True, help="the first build (the baseline)")
    c.add_argument("--b", type=Path, required=True, help="the second build")
    c.add_argument("--dataset", default="2wikimultihopqa")
    c.add_argument("--cache-dir", default=Path("data/raw/qa_bench"), type=Path)
    c.add_argument(
        "--readings", type=Path, help="default: <cache-dir>/kadmos_readings_<dataset>.jsonl"
    )
    c.add_argument(
        "--same-name",
        action="store_true",
        help="also collect mentions that moved to another node of the same name, matched "
        "by the mention that minted each node; they are left out of the control sample",
    )
    c.add_argument("--control", type=int, default=400, help="mentions that did not move, sampled")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--out", type=Path, required=True)
    c.set_defaults(func=collect)

    j = sub.add_parser("judge", help="ask the configured model about each candidate node")
    j.add_argument("--items", type=Path, required=True)
    j.add_argument("--out", type=Path, required=True, help="judgments, appended and resumable")
    j.add_argument("--concurrency", type=int, default=16)
    j.add_argument(
        "--spend-limit-usd",
        type=float,
        default=None,
        help="the most this run may spend; default THEOGONY_LLM__SPEND_LIMIT_USD or 5 (PHX-1124)",
    )
    j.set_defaults(func=judge)

    e = sub.add_parser("export-blind", help="write blind batches for a second judge")
    e.add_argument("--items", type=Path, required=True)
    e.add_argument("--out-dir", type=Path, required=True)
    e.add_argument("--size", type=int, default=40, help="units per batch")
    e.add_argument("--seed", type=int, default=1120)
    e.add_argument("--sides", default="a,b", help="which candidates to export: a, b or a,b")
    e.add_argument("--key", type=Path, required=True, help="where to write the opaque-id key")
    e.set_defaults(func=export_blind)

    i = sub.add_parser("import-blind", help="read a second judge's answers as judgments")
    i.add_argument("answers", type=Path, nargs="+", help="JSON files of {unit_id, verdict}")
    i.add_argument("--judge", required=True, help="who judged, recorded on every row")
    i.add_argument("--key", type=Path, help="the key export-blind wrote, to map opaque ids back")
    i.add_argument("--out", type=Path, required=True)
    i.set_defaults(func=import_blind)

    s = sub.add_parser("summarise", help="outcomes of the moves, and agreement of two judges")
    s.add_argument("--items", type=Path, required=True)
    s.add_argument("--judgments", type=Path, required=True)
    s.add_argument("--second", type=Path, help="a second judge's judgments of the same items")
    s.add_argument("--json", type=Path)
    s.set_defaults(func=summarise)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
