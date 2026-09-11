"""The pure half of the latent mile (PHX-1109): prompts, splicing, pairing.

The reader and the training loop want a 1.5B model and are measured, not
unit-tested. What must be pinned is everything that could manufacture a
difference between the text arm and the soft arm other than the medium: the
soft prompt has to be the text prompt with names cut out, the soft tokens have
to land exactly where the names were, and the pairing has to count fairly.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import torch
from ulid import ULID

from theogony.mesh.eval.corpus_answers import AnswerResult, render_constellation
from theogony.mesh.eval.latent_mile import (
    PLACEHOLDER,
    NodeProjector,
    SoftPrompt,
    node_label,
    paired_arms,
    paraphrase_examples,
    soft_context,
    splice_soft_tokens,
    split_holdout,
    training_nodes,
)
from theogony.mesh.retrieval.constellation import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
)
from theogony.mesh.schemas import ConsolidatedNode


def _node(description: str | None, *, anchor: bool = False, dim: int = 4) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[random.random() for _ in range(dim)],
        frame_vector=[0.0] * 4,
        description=description,
        tags=[description.split(" — ")[0]] if description else [],
        is_source_anchor=anchor,
    )


def _constellation() -> tuple[Constellation, dict[str, list[float]]]:
    names = {
        "a": "Zeus — King of the gods",
        "b": "Rhea — Mother of Zeus",
        "c": "Cronos — Father of Zeus",
        "anchor": "text: Hesiod (batch 1)",
    }
    nodes = [
        ConstellationNode(node_id=k, name=v, is_source_anchor=(k == "anchor"), is_seed=(k == "a"))
        for k, v in names.items()
    ]
    edges = [
        ConstellationEdge(
            source_id="b",
            target_id="a",
            source_name=names["b"],
            target_name=names["a"],
            weight=0.9,
            relation_descriptor="mother_of",
        ),
        ConstellationEdge(  # touches no seed: the text arm hides it, so must the soft arm
            source_id="c",
            target_id="b",
            source_name=names["c"],
            target_name=names["b"],
            weight=0.8,
            relation_descriptor="husband_of",
        ),
        ConstellationEdge(  # touches a seed but has no descriptor: hidden too
            source_id="a",
            target_id="c",
            source_name=names["a"],
            target_name=names["c"],
            weight=0.7,
            relation_descriptor=None,
        ),
    ]
    c = Constellation(seed_node_ids=["a"], nodes=nodes, edges=edges)
    vectors = {k: [float(i)] * 4 for i, k in enumerate(names)}
    return c, vectors


def test_the_soft_prompt_is_the_text_rendering_with_the_names_cut_out() -> None:
    c, vectors = _constellation()
    soft = soft_context(c, vectors)
    # nodes shown (3, the anchor hidden) + 2 endpoints of the one visible edge
    assert soft.text.count(PLACEHOLDER) == 5 == len(soft.vectors)
    # the soft tokens stand for exactly these nodes, in this order
    assert soft.vectors == [vectors["a"], vectors["b"], vectors["c"], vectors["b"], vectors["a"]]
    # put the names back and the text arm's prompt reappears verbatim
    names = [
        "Zeus — King of the gods",
        "Rhea — Mother of Zeus",
        "Cronos — Father of Zeus",
        "Rhea",
        "Zeus",
    ]
    text = soft.text
    for name in names:
        text = text.replace(PLACEHOLDER, name, 1)
    assert text == render_constellation(c)


def test_a_soft_prompt_refuses_a_hole_count_that_does_not_match() -> None:
    try:
        SoftPrompt(text=f"- {PLACEHOLDER}\n- {PLACEHOLDER}", vectors=[[1.0]])
    except ValueError as err:
        assert "2 placeholders for 1 vectors" in str(err)
    else:
        raise AssertionError("mismatch accepted")


def test_soft_tokens_land_exactly_on_the_placeholders_and_carry_gradient() -> None:
    ph = 7
    ids = torch.tensor([1, ph, 2, 3, ph, 4])
    embeds = torch.zeros((6, 3))
    soft = torch.tensor([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]], requires_grad=True)
    out = splice_soft_tokens(embeds, ids, ph, soft)
    assert out[1].tolist() == [1.0, 1.0, 1.0]
    assert out[4].tolist() == [2.0, 2.0, 2.0]
    assert out[[0, 2, 3, 5]].abs().sum() == 0
    out.sum().backward()
    assert soft.grad is not None and soft.grad.abs().sum() > 0

    try:
        splice_soft_tokens(embeds, ids, ph, torch.ones((3, 3)))
    except ValueError as err:
        assert "2 placeholders for 3 soft tokens" in str(err)
    else:
        raise AssertionError("mismatch accepted")


def test_no_placeholders_means_the_embeddings_pass_through() -> None:
    embeds = torch.randn((4, 3))
    assert splice_soft_tokens(embeds, torch.tensor([1, 2, 3, 4]), 9, torch.zeros((0, 3))) is embeds


def test_paraphrase_examples_cover_every_node_once_in_small_groups() -> None:
    nodes = [_node(f"N{i} — entry {i}") for i in range(23)]
    examples = paraphrase_examples(nodes, random.Random(1), group_max=4)
    seen: list[list[float]] = []
    for prompt, target in examples:
        assert 1 <= len(prompt.vectors) <= 4
        assert prompt.text.count(PLACEHOLDER) == len(prompt.vectors)
        assert target.count("\n- ") + 1 == len(prompt.vectors)
        seen.extend(prompt.vectors)
    assert sorted(map(tuple, seen)) == sorted(tuple(n.semantic_vector) for n in nodes)
    # the target is what the text arm would show for the node
    prompt, target = examples[0]
    first = next(n for n in nodes if list(n.semantic_vector) == prompt.vectors[0])
    assert target.startswith(f"- {first.description}")


def test_training_nodes_drop_anchors_and_the_wordless() -> None:
    nodes = [_node("Zeus — king"), _node("text: Hesiod", anchor=True), _node(None)]
    kept = training_nodes(nodes)
    assert [n.description for n in kept] == ["Zeus — king"]


def test_the_holdout_is_disjoint_and_seeded() -> None:
    nodes = [_node(f"N{i} — e") for i in range(40)]
    train, hold = split_holdout(nodes, 0.25, seed=3)
    assert len(train) == 30 and len(hold) == 10
    assert {n.id for n in train}.isdisjoint({n.id for n in hold})
    again_train, _ = split_holdout(nodes, 0.25, seed=3)
    assert [n.id for n in again_train] == [n.id for n in train]


def test_node_label_is_the_head_of_the_description() -> None:
    assert node_label(_node("Zeus — King of the gods")) == "Zeus"
    bare = _node(None)
    bare.tags = ["Hera"]
    assert node_label(bare) == "Hera"


def test_calibrate_puts_a_fresh_projector_on_the_readers_scale() -> None:
    torch.manual_seed(0)
    projector = NodeProjector(node_dim=8, llm_dim=16, hidden_dim=32)
    sample = torch.randn((64, 8))
    sample = sample / sample.norm(dim=-1, keepdim=True)
    projector.calibrate(sample, target_norm=0.05)
    assert abs(float(projector(sample).norm(dim=-1).mean()) - 0.05) < 1e-4


def test_pairing_counts_wins_losses_and_ties_per_question() -> None:
    def row(qid: str, arm: str, found: list[str]) -> AnswerResult:
        return AnswerResult(
            id=qid,
            arm=arm,
            kind="g",
            question="?",
            expected=["A", "B"],
            answer="",
            found=found,
            missed=[x for x in ("A", "B") if x not in found],
        )

    rows = [
        row("q1", "soft", ["A", "B"]),
        row("q1", "constellation", ["A"]),
        row("q2", "soft", []),
        row("q2", "constellation", ["A"]),
        row("q3", "soft", ["A"]),
        row("q3", "constellation", ["A"]),
        row("q4", "constellation", ["A", "B"]),  # unpaired: ignored
    ]
    pair = paired_arms(rows, arm="soft", against="constellation")
    assert pair == {"questions": 3.0, "better": 1.0, "worse": 1.0, "equal": 1.0, "delta": 0.0}
