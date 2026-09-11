"""The latent last mile: hand a Constellation to a reader as vectors, not text.

VISION.md §"Latent Space Communication" says the Constellation is returned "in
vector form, directly injectable into the agent's latent space — no text
translation required". Nothing in the repo has ever tried it: Kadmos reads
text, the Constellation is rendered as text (`render_constellation`), the
answer is text. This module makes the sentence measurable (PHX-1109).

The design is xRAG's (Cheng et al. 2024): retriever frozen, language model
frozen, one small trained projector in between. Here the retriever is the
substrate itself — a node's `semantic_vector` (384-d, bge-small-en) — and the
projector maps it to one *soft token* in the reader's input-embedding space.
A Constellation of fifty nodes becomes fifty soft tokens plus the relation
triples among them, spelled with the same soft tokens in place of the names.

Four arms, same frozen reader, same Constellation, same scoring as
`corpus_answers`:

    closed_book       no material — what the reader already knows
    constellation     the shipped text rendering (label — description, triples)
    soft              the same nodes as projected vectors
    soft_untrained    the same projector before training — the control that
                      says whether the reader read the vectors or the layout

The projector is trained the way xRAG pre-trains its bridge: paraphrase. Given
a soft token, produce the entry it stands for. Training data are the
substrate's own consolidated nodes, never the gold questions; a held-out
fraction of nodes says whether the mapping generalises to vectors the projector
has not seen, which is what a live substrate would hand it every day.

What a null result means: not that the vision is wrong, but that at this
scale — a 1.5B reader, a few thousand training vectors, a laptop — the medium
does not carry what the reader needs. That is a measurement the plan can use.

The reader's `generate()` cannot be used: on MPS with transformers 5.5 it
returns garbage for `inputs_embeds` while a plain forward pass is exact, so
decoding is a hand-rolled greedy loop over the KV cache (`LocalReader.greedy`).
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import torch
from torch import nn

from theogony.mesh.eval.corpus_answers import (
    _SYSTEM,
    _SYSTEM_CLOSED,
    AnswerResult,
    _score,
    render_constellation,
)
from theogony.mesh.eval.corpus_qa import GoldQuestion, _normalise, load_gold
from theogony.mesh.retrieval.constellation import Constellation
from theogony.mesh.retrieval.defaults import DEFAULT_TOP_K
from theogony.mesh.retrieval.retrieve import retrieve
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode

DEFAULT_READER = "Qwen/Qwen2.5-1.5B-Instruct"

# An existing special token the reader never produces in text. Every occurrence
# in a prompt is replaced, in order, by one projected node vector.
PLACEHOLDER = "<|vision_pad|>"

ARMS = ("closed_book", "constellation", "soft", "soft_untrained")

_SYSTEM_PARAPHRASE = (
    "You are given entries from a knowledge mesh. Each entry is shown as a single "
    "token. Write every entry out in words, one per line, in the same order."
)
_PARAPHRASE_ASK = "Write out each entry as it appears in the material."

# The label of a node is the head of its description ("Zeus — King of the gods")
# or its first tag when there is no description.
_LABEL_SPLIT = " — "


# --------------------------------------------------------------------------- #
# Pure pieces — no model, testable                                             #
# --------------------------------------------------------------------------- #


@dataclass
class SoftPrompt:
    """A prompt with holes: `text` carries PLACEHOLDER once per vector."""

    text: str
    vectors: list[list[float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        holes = self.text.count(PLACEHOLDER)
        if holes != len(self.vectors):
            raise ValueError(f"{holes} placeholders for {len(self.vectors)} vectors")


def node_label(node: ConsolidatedNode) -> str:
    if node.description and _LABEL_SPLIT in node.description:
        return node.description.split(_LABEL_SPLIT, 1)[0].strip()
    if node.tags:
        return node.tags[0]
    return node.description or str(node.id)


def node_entry(node: ConsolidatedNode) -> str:
    """What the text arm shows for the node — the paraphrase target."""
    return node.description or node_label(node)


VECTOR_MODES = ("semantic", "description", "both")


def node_vector(node: ConsolidatedNode, mode: str = "semantic") -> list[float]:
    """The vector(s) the projector reads for a node.

    `semantic` is the vector Spreading Activation propagates over. `description`
    is the embedding of the regenerated description — the closest thing the
    substrate has to xRAG's document embedding, since the paraphrase target *is*
    that description. `both` concatenates the two. A node without a description
    vector falls back to its semantic vector, so every node yields one width.
    """
    if mode == "semantic":
        return list(node.semantic_vector)
    described = (
        list(node.description_vector) if node.description_vector else list(node.semantic_vector)
    )
    if mode == "description":
        return described
    if mode == "both":
        return list(node.semantic_vector) + described
    raise ValueError(f"unknown vector mode {mode!r}; choose from {VECTOR_MODES}")


def training_nodes(nodes: Iterable[ConsolidatedNode]) -> list[ConsolidatedNode]:
    """Entity nodes with something to say. Source anchors are excluded: their
    descriptions are file names, and they are hidden from the text arm too."""
    return [n for n in nodes if n.description and not n.is_source_anchor]


def split_holdout(
    nodes: Sequence[ConsolidatedNode], fraction: float, seed: int
) -> tuple[list[ConsolidatedNode], list[ConsolidatedNode]]:
    order = list(nodes)
    random.Random(seed).shuffle(order)
    cut = int(round(len(order) * (1.0 - fraction)))
    return order[:cut], order[cut:]


def paraphrase_examples(
    nodes: Sequence[ConsolidatedNode],
    rng: random.Random,
    *,
    group_max: int = 4,
    mode: str = "semantic",
) -> list[tuple[SoftPrompt, str]]:
    """One epoch of paraphrase examples: nodes in random groups of 1..group_max.

    Groups matter. The answer prompt shows fifty soft tokens in a list and
    triples over them; a projector trained only on single tokens has never seen
    a soft token *after* another one, and the reader has never had to keep two
    apart. Mixed group sizes teach position-independence cheaply.
    """
    order = list(nodes)
    rng.shuffle(order)
    out: list[tuple[SoftPrompt, str]] = []
    i = 0
    while i < len(order):
        size = rng.randint(1, group_max)
        group = order[i : i + size]
        i += size
        lines = "\n".join(f"- {PLACEHOLDER}" for _ in group)
        prompt = SoftPrompt(
            text=f"Entities:\n{lines}\n\n{_PARAPHRASE_ASK}",
            vectors=[node_vector(n, mode) for n in group],
        )
        target = "\n".join(f"- {node_entry(n)}" for n in group)
        out.append((prompt, target))
    return out


def soft_context(
    constellation: Constellation, vectors_by_id: Mapping[str, Sequence[float]]
) -> SoftPrompt:
    """The soft twin of `render_constellation`: same nodes, same edge selection,
    same headers and wording, one soft token wherever the text shows a name."""
    shown = [n for n in constellation.nodes if not n.is_source_anchor]
    vectors: list[list[float]] = []
    lines = ["Entities:"]
    for n in shown:
        lines.append(f"- {PLACEHOLDER}")
        vectors.append(list(vectors_by_id[n.node_id]))

    seeds = set(constellation.seed_node_ids)
    described = [
        e
        for e in constellation.edges
        if e.relation_descriptor and (e.source_id in seeds or e.target_id in seeds)
    ]
    if described:
        lines.append("")
        lines.append("Relations between them:")
        for e in described[:120]:
            lines.append(f"- {PLACEHOLDER} {e.relation_descriptor} {PLACEHOLDER}")
            vectors.append(list(vectors_by_id[e.source_id]))
            vectors.append(list(vectors_by_id[e.target_id]))
    return SoftPrompt(text="\n".join(lines), vectors=vectors)


def splice_soft_tokens(
    token_embeds: torch.Tensor,
    ids: torch.Tensor,
    placeholder_id: int,
    soft: torch.Tensor,
) -> torch.Tensor:
    """Replace every placeholder position in one sequence by the next soft token.

    `token_embeds` is (T, D), `ids` is (T,), `soft` is (k, D) with k equal to the
    number of placeholders. Returns a new (T, D) tensor; gradients flow into
    `soft` only, which is all the projector needs.
    """
    positions = (ids == placeholder_id).nonzero(as_tuple=False).flatten()
    if positions.numel() != soft.shape[0]:
        raise ValueError(f"{positions.numel()} placeholders for {soft.shape[0]} soft tokens")
    if positions.numel() == 0:
        return token_embeds
    out = token_embeds.clone()
    out[positions] = soft.to(out.dtype)
    return out


class NodeProjector(nn.Module):
    """One node vector in, one reader-space token out. Two layers, as in xRAG."""

    def __init__(self, node_dim: int, llm_dim: int, hidden_dim: int = 2048) -> None:
        super().__init__()
        self.node_dim = node_dim
        self.llm_dim = llm_dim
        self.net = nn.Sequential(
            nn.Linear(node_dim, hidden_dim), nn.GELU(), nn.Linear(hidden_dim, llm_dim)
        )

    def forward(self, vectors: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self.net(vectors))

    @torch.no_grad()
    def calibrate(self, sample: torch.Tensor, target_norm: float) -> float:
        """Scale the output layer so a projected vector has the norm of a real
        token embedding. Without this an untrained projector emits vectors an
        order of magnitude off the reader's scale, and the control arm would
        measure that instead of the absence of training."""
        current = float(self.forward(sample).norm(dim=-1).mean())
        if current > 0:
            factor = target_norm / current
            last = self.net[-1]
            assert isinstance(last, nn.Linear)
            last.weight.mul_(factor)
            last.bias.mul_(factor)
        return current


# --------------------------------------------------------------------------- #
# The reader                                                                   #
# --------------------------------------------------------------------------- #


class LocalReader:
    """A frozen open-weight chat model with an embedding-level front door."""

    def __init__(self, tokenizer: Any, model: Any, device: str) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.device = device
        self.placeholder_id = int(tokenizer.convert_tokens_to_ids(PLACEHOLDER))
        self.im_end_id = int(tokenizer.convert_tokens_to_ids("<|im_end|>"))
        self.pad_id = int(tokenizer.pad_token_id)
        self._embeddings = model.get_input_embeddings()
        for p in model.parameters():
            p.requires_grad_(False)
        model.eval()

    @classmethod
    def load(
        cls, name: str = DEFAULT_READER, *, device: str | None = None, dtype: str = "float16"
    ) -> LocalReader:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        tokenizer = AutoTokenizer.from_pretrained(name)
        model: Any = AutoModelForCausalLM.from_pretrained(name, dtype=getattr(torch, dtype))
        return cls(tokenizer, model.to(device), device)

    @property
    def llm_dim(self) -> int:
        return int(self.model.config.hidden_size)

    def training_mode(self, on: bool) -> None:
        """Backward passes through a frozen 3B model keep every layer's
        activations unless they are recomputed; without checkpointing a batch of
        eight paraphrases pushed the laptop 23 GB into swap. Checkpointing is
        only honoured while the model is in train mode, and no parameter has a
        gradient, so train mode changes nothing but that."""
        if on:
            self.model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
            self.model.train()
        else:
            self.model.gradient_checkpointing_disable()
            self.model.eval()

    @property
    def name(self) -> str:
        return str(self.model.config._name_or_path)

    def chat_ids(self, system: str | None, user: str, assistant: str | None = None) -> torch.Tensor:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        if assistant is not None:
            messages.append({"role": "assistant", "content": assistant})
        ids = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=assistant is None,
            return_tensors="pt",
            return_dict=True,
        )["input_ids"]
        return cast(torch.Tensor, ids[0].to(self.device))

    def embed(self, ids: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return cast(torch.Tensor, self._embeddings(ids))

    @torch.no_grad()
    def mean_token_norm(self, sample: int = 4096) -> float:
        weight = self._embeddings.weight
        idx = torch.randperm(weight.shape[0], device=weight.device)[:sample]
        return float(weight[idx].float().norm(dim=-1).mean())

    def inputs_for(
        self, system: str | None, prompt: SoftPrompt, soft: torch.Tensor | None
    ) -> torch.Tensor:
        ids = self.chat_ids(system, prompt.text)
        embeds = self.embed(ids)
        if soft is None:
            return embeds
        return splice_soft_tokens(embeds, ids, self.placeholder_id, soft)

    @torch.no_grad()
    def greedy(self, inputs_embeds: torch.Tensor, max_new_tokens: int) -> str:
        """Greedy decoding from a (T, D) embedding sequence, via the KV cache."""
        out = self.model(inputs_embeds=inputs_embeds.unsqueeze(0), use_cache=True)
        cache = out.past_key_values
        nxt = out.logits[0, -1].argmax()
        tokens: list[int] = []
        for _ in range(max_new_tokens):
            tid = int(nxt)
            if tid in (self.im_end_id, self.tokenizer.eos_token_id):
                break
            tokens.append(tid)
            out = self.model(
                inputs_embeds=self._embeddings(nxt.view(1, 1)),
                past_key_values=cache,
                use_cache=True,
            )
            cache = out.past_key_values
            nxt = out.logits[0, -1].argmax()
        return str(self.tokenizer.decode(tokens, skip_special_tokens=True)).strip()


# --------------------------------------------------------------------------- #
# Training                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class EpochReport:
    epoch: int
    steps: int
    train_loss: float
    holdout_loss: float | None
    label_recovery_train: float | None
    label_recovery_holdout: float | None
    seconds: float
    nan_steps: int = 0


@dataclass
class TrainingReport:
    reader: str
    node_dim: int
    llm_dim: int
    nodes_train: int
    nodes_holdout: int
    seed: int
    mode: str = "semantic"
    epochs: list[EpochReport] = field(default_factory=list)


def _batch_paraphrase(
    reader: LocalReader,
    projector: NodeProjector,
    batch: Sequence[tuple[SoftPrompt, str]],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Embeddings, attention mask and labels for one right-padded batch.

    Labels cover the assistant turn only: the prompt (system, user, template)
    is -100, and so is the padding.
    """
    sequences: list[torch.Tensor] = []
    labels: list[torch.Tensor] = []
    for prompt, target in batch:
        prompt_ids = reader.chat_ids(_SYSTEM_PARAPHRASE, prompt.text)
        full_ids = reader.chat_ids(_SYSTEM_PARAPHRASE, prompt.text, assistant=target)
        vectors = torch.tensor(prompt.vectors, dtype=torch.float32, device=reader.device)
        soft = projector(vectors)
        embeds = splice_soft_tokens(reader.embed(full_ids), full_ids, reader.placeholder_id, soft)
        lab = full_ids.clone()
        lab[: prompt_ids.shape[0]] = -100
        sequences.append(embeds)
        labels.append(lab)

    length = max(s.shape[0] for s in sequences)
    dim = sequences[0].shape[1]
    dtype = sequences[0].dtype
    x = torch.zeros((len(batch), length, dim), dtype=dtype, device=reader.device)
    mask = torch.zeros((len(batch), length), dtype=torch.long, device=reader.device)
    y = torch.full((len(batch), length), -100, dtype=torch.long, device=reader.device)
    for i, (s, lab) in enumerate(zip(sequences, labels, strict=True)):
        x[i, : s.shape[0]] = s
        mask[i, : s.shape[0]] = 1
        y[i, : lab.shape[0]] = lab
    return x, mask, y


def _loss_on(
    reader: LocalReader, projector: NodeProjector, batch: Sequence[tuple[SoftPrompt, str]]
) -> torch.Tensor:
    x, mask, y = _batch_paraphrase(reader, projector, batch)
    return cast(torch.Tensor, reader.model(inputs_embeds=x, attention_mask=mask, labels=y).loss)


@torch.no_grad()
def label_recovery(
    reader: LocalReader,
    projector: NodeProjector,
    nodes: Sequence[ConsolidatedNode],
    *,
    mode: str = "semantic",
) -> float:
    """Of these nodes, shown one at a time as a single soft token, how many does
    the reader name back? The bluntest possible check that a vector carries its
    label through the projector."""
    if not nodes:
        return 0.0
    hit = 0
    for n in nodes:
        prompt = SoftPrompt(
            text=f"Entities:\n- {PLACEHOLDER}\n\n{_PARAPHRASE_ASK}",
            vectors=[node_vector(n, mode)],
        )
        vectors = torch.tensor(prompt.vectors, dtype=torch.float32, device=reader.device)
        answer = reader.greedy(
            reader.inputs_for(_SYSTEM_PARAPHRASE, prompt, projector(vectors)), 40
        )
        if f" {_normalise(node_label(n))} " in f" {_normalise(answer)} ":
            hit += 1
    return hit / len(nodes)


def train_projector(
    reader: LocalReader,
    projector: NodeProjector,
    nodes: Sequence[ConsolidatedNode],
    *,
    epochs: int = 5,
    batch_size: int = 8,
    lr: float = 1e-3,
    seed: int = 0,
    holdout_fraction: float = 0.05,
    group_max: int = 4,
    recovery_sample: int = 30,
    mode: str = "semantic",
    checkpoint: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> TrainingReport:
    say = log or (lambda _msg: None)
    train, holdout = split_holdout(nodes, holdout_fraction, seed)
    report = TrainingReport(
        reader=reader.name,
        node_dim=projector.node_dim,
        llm_dim=projector.llm_dim,
        nodes_train=len(train),
        nodes_holdout=len(holdout),
        seed=seed,
        mode=mode,
    )
    rng = random.Random(seed)
    optimiser = torch.optim.AdamW(projector.parameters(), lr=lr, weight_decay=0.01)
    projector.to(reader.device)
    recovery_train = train[:recovery_sample]
    recovery_holdout = holdout[:recovery_sample]

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        examples = paraphrase_examples(train, rng, group_max=group_max, mode=mode)
        projector.train()
        reader.training_mode(True)
        losses: list[float] = []
        nan_steps = 0
        for start in range(0, len(examples), batch_size):
            batch = examples[start : start + batch_size]
            optimiser.zero_grad(set_to_none=True)
            loss = _loss_on(reader, projector, batch)
            if not torch.isfinite(loss):
                nan_steps += 1
                continue
            loss.backward()  # type: ignore[no-untyped-call]
            torch.nn.utils.clip_grad_norm_(projector.parameters(), 1.0)
            optimiser.step()
            losses.append(loss.detach().item())
            if len(losses) % 25 == 0:
                say(
                    f"epoch {epoch} step {len(losses)}/{-(-len(examples) // batch_size)} "
                    f"loss {sum(losses[-25:]) / 25:.3f}"
                )
                if reader.device == "mps":
                    # the MPS allocator holds on to every batch shape it has
                    # seen; a run over variable-length batches slows down by
                    # the epoch without this
                    torch.mps.empty_cache()
        projector.eval()
        reader.training_mode(False)
        holdout_loss: float | None = None
        if holdout:
            hold_examples = paraphrase_examples(
                holdout, random.Random(seed + 1), group_max=1, mode=mode
            )
            with torch.no_grad():
                vals = [
                    _loss_on(reader, projector, hold_examples[s : s + batch_size]).item()
                    for s in range(0, len(hold_examples), batch_size)
                ]
            holdout_loss = sum(vals) / len(vals)
        rec_train = label_recovery(reader, projector, recovery_train, mode=mode)
        rec_hold = (
            label_recovery(reader, projector, recovery_holdout, mode=mode)
            if recovery_holdout
            else None
        )
        ep = EpochReport(
            epoch=epoch,
            steps=len(losses),
            train_loss=sum(losses) / max(1, len(losses)),
            holdout_loss=holdout_loss,
            label_recovery_train=rec_train,
            label_recovery_holdout=rec_hold,
            seconds=time.time() - t0,
            nan_steps=nan_steps,
        )
        report.epochs.append(ep)
        say(
            f"epoch {epoch}: train loss {ep.train_loss:.3f}, holdout loss "
            f"{holdout_loss if holdout_loss is None else round(holdout_loss, 3)}, "
            f"label recovery train {rec_train:.2f} / holdout "
            f"{'-' if rec_hold is None else f'{rec_hold:.2f}'}, {ep.seconds:.0f} s, "
            f"{nan_steps} non-finite steps skipped"
        )
        if checkpoint is not None:
            save_projector(projector, checkpoint, report)
    return report


def save_projector(projector: NodeProjector, path: Path, report: TrainingReport | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": projector.state_dict(),
            "node_dim": projector.node_dim,
            "llm_dim": projector.llm_dim,
            "hidden_dim": projector.net[0].out_features,
            "mode": report.mode if report is not None else "semantic",
            "report": None if report is None else _report_dict(report),
        },
        path,
    )


@dataclass
class LoadedProjector:
    projector: NodeProjector
    mode: str
    report: dict[str, Any] | None


def load_projector(path: Path, device: str) -> LoadedProjector:
    blob = torch.load(path, map_location=device)
    projector = NodeProjector(blob["node_dim"], blob["llm_dim"], blob["hidden_dim"])
    projector.load_state_dict(blob["state_dict"])
    projector.to(device).eval()
    return LoadedProjector(projector, str(blob.get("mode", "semantic")), blob.get("report"))


def paired_arms(results: Sequence[AnswerResult], *, arm: str, against: str) -> dict[str, float]:
    """Question by question: where does `arm` beat `against`, lose, or tie?

    The totals are the wrong comparison when the arms share a reader and a
    Constellation: the pairing is where the medium shows, the totals are where
    the questions the reader knows by heart drown it.
    """
    mine = {r.id: r for r in results if r.arm == arm}
    theirs = {r.id: r for r in results if r.arm == against}
    ids = sorted(set(mine) & set(theirs))
    better = sum(1 for i in ids if mine[i].recall > theirs[i].recall)
    worse = sum(1 for i in ids if mine[i].recall < theirs[i].recall)
    delta = sum(mine[i].recall - theirs[i].recall for i in ids) / len(ids) if ids else 0.0
    return {
        "questions": float(len(ids)),
        "better": float(better),
        "worse": float(worse),
        "equal": float(len(ids) - better - worse),
        "delta": delta,
    }


def report_dict(report: TrainingReport) -> dict[str, Any]:
    return _report_dict(report)


def _report_dict(report: TrainingReport) -> dict[str, Any]:
    return {
        "reader": report.reader,
        "node_dim": report.node_dim,
        "llm_dim": report.llm_dim,
        "nodes_train": report.nodes_train,
        "nodes_holdout": report.nodes_holdout,
        "seed": report.seed,
        "mode": report.mode,
        "epochs": [vars(e) for e in report.epochs],
    }


def fresh_projector(
    reader: LocalReader, node_dim: int, *, seed: int, hidden_dim: int = 2048
) -> NodeProjector:
    """A projector at its starting point, calibrated to the reader's token scale.
    The control arm uses exactly this, with a fixed seed."""
    torch.manual_seed(seed)
    projector = NodeProjector(node_dim, reader.llm_dim, hidden_dim).to(reader.device)
    sample = torch.randn((256, node_dim), device=reader.device)
    sample = sample / sample.norm(dim=-1, keepdim=True)
    projector.calibrate(sample, reader.mean_token_norm())
    return projector


# --------------------------------------------------------------------------- #
# The measurement                                                              #
# --------------------------------------------------------------------------- #

CONTROL_SEED = 12345


def _probe_node(runtime: MeshRuntime) -> ConsolidatedNode:
    """Any consolidated node, to learn the vector width of this mesh."""
    for node in runtime.nodes.iter_consolidated(page_size=1):
        return node
    raise ValueError("the mesh has no consolidated nodes")


def answer_gold_set_local(
    reader: LocalReader,
    runtime: MeshRuntime,
    embed: Callable[[str], Sequence[float]],
    *,
    projector: NodeProjector | None,
    arms: tuple[str, ...] = ARMS,
    gold: list[GoldQuestion] | None = None,
    top_k: int = DEFAULT_TOP_K,
    max_new_tokens: int = 120,
    mode: str = "semantic",
    log: Callable[[str], None] | None = None,
    **retrieve_kwargs: Any,
) -> list[AnswerResult]:
    """Ask every gold question once per arm through the local reader.

    The Constellation is retrieved once per question and handed to the text arm
    and the soft arms unchanged, so the arms differ in the medium only. Greedy
    decoding is deterministic, so a repeat of this function measures nothing;
    the spread of the soft arm comes from projectors trained with different
    seeds, which is the variance that is actually there.
    """
    say = log or (lambda _msg: None)
    questions = gold if gold is not None else load_gold()
    runtime.rebuild_csr()
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise ValueError(f"unknown arms {unknown}; choose from {ARMS}")
    if "soft" in arms and projector is None:
        raise ValueError("the soft arm needs a trained projector")
    if projector is not None and projector.llm_dim != reader.llm_dim:
        raise ValueError(
            f"projector was trained for a {projector.llm_dim}-d reader, "
            f"this reader is {reader.llm_dim}-d"
        )
    control_dim = projector.node_dim if projector else len(node_vector(_probe_node(runtime), mode))
    control = (
        fresh_projector(reader, control_dim, seed=CONTROL_SEED)
        if "soft_untrained" in arms
        else None
    )

    results: list[AnswerResult] = []
    for qi, gq in enumerate(questions, 1):
        vector = embed(gq.question)
        constellation: Constellation | None = None
        text_prompt: SoftPrompt | None = None
        soft_prompt: SoftPrompt | None = None
        if any(a != "closed_book" for a in arms):
            result = retrieve(
                runtime,
                vector,
                query=gq.question,
                top_k=top_k,
                record_firing=False,
                **retrieve_kwargs,
            )
            constellation = result.constellation
            text_prompt = SoftPrompt(
                text=f"Material:\n{render_constellation(constellation)}\n\nQuestion: {gq.question}"
            )
            ids = {n.node_id for n in constellation.nodes} | {
                x for e in constellation.edges for x in (e.source_id, e.target_id)
            }
            fetched = runtime.nodes.get_consolidated_many(ids)
            vectors_by_id = {k: node_vector(v, mode) for k, v in fetched.items()}
            soft = soft_context(constellation, vectors_by_id)
            soft_prompt = SoftPrompt(
                text=f"Material:\n{soft.text}\n\nQuestion: {gq.question}", vectors=soft.vectors
            )

        for arm in arms:
            t0 = time.time()
            if arm == "closed_book":
                embeds = reader.inputs_for(
                    _SYSTEM_CLOSED, SoftPrompt(f"Question: {gq.question}"), None
                )
            elif arm == "constellation":
                assert text_prompt is not None
                embeds = reader.inputs_for(_SYSTEM, text_prompt, None)
            else:
                assert soft_prompt is not None
                proj = projector if arm == "soft" else control
                assert proj is not None
                with torch.no_grad():
                    vec = torch.tensor(
                        soft_prompt.vectors, dtype=torch.float32, device=reader.device
                    )
                    embeds = reader.inputs_for(_SYSTEM, soft_prompt, proj(vec))
            answer = reader.greedy(embeds, max_new_tokens)
            found, missed = _score(answer, gq.expect)
            results.append(
                AnswerResult(
                    id=gq.id,
                    arm=arm,
                    kind=gq.kind,
                    question=gq.question,
                    expected=list(gq.expect),
                    answer=answer,
                    found=found,
                    missed=missed,
                    said_unknown=bool(re.fullmatch(r"\W*unknown\W*", answer, re.I)),
                    run=0,
                )
            )
            say(
                f"[{qi}/{len(questions)}] {arm:<16} {len(found)}/{len(gq.expect)} "
                f"({embeds.shape[0]} tokens, {time.time() - t0:.1f} s): {answer[:70]!r}"
            )
    return results
