"""Multi-hop QA passage-retrieval benchmark — Spreading Activation vs kNN / BM25.

Operationalises README empirical question 2 — *does Spreading Activation over a
dense vector-graph retrieve better than kNN at high edge density?* — on the
standard multi-hop trio (MuSiQue / 2WikiMultihopQA / HotpotQA) using the
HippoRAG_v2 shared-corpus protocol: retrieve over the whole per-dataset corpus
and score **passage recall@2 / @5** against each question's gold supporting
passages.

This module is **pure compute** (torch + stdlib). The driver
(``scripts/mesh_qa_retrieval.py``) does the I/O — download, local embedding
(BGE), local NER (spaCy) — and passes plain arrays in, so the whole harness is
unit-testable offline on synthetic fixtures.

Graph construction is deliberately **cheap and LLM-free** (spaCy-NER entities +
embedding-kNN edges), which the literature establishes as a legitimate first
data point: LinearRAG (ICLR 2026, relation-free spaCy-entity graph) and SPRIG
(2026, NER co-occurrence + PPR) both beat or match LLM-KG GraphRAG on exactly
this trio. LLM (Kadmos) extraction is a documented *fidelity upgrade*, not a
prerequisite — the retrieval kernel (:func:`propagate`) is identical either way.

The headline is the **edge-density ablation**: hold the geometric edges fixed,
sweep the fraction of entity-bridge (co-occurrence) edges, and read whether the
SA recall curve pulls away from the (edge-independent, flat) kNN reference as
structural density rises. That crossover is the phase transition the
architecture bets on — and no published study has measured it as an explicit
density function for activation vs kNN.
"""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field

import torch
from pydantic import BaseModel, ConfigDict, Field

from theogony.mesh.eval.link_prediction import (
    EdgeRow,
    build_adjacency,
    build_csr_over_nodes,
    build_normalized_adjacency,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Corpus / question shapes
# ---------------------------------------------------------------------------


@dataclass
class QAPassage:
    """One retrievable passage from the shared corpus."""

    idx: int
    title: str
    text: str


@dataclass
class QAQuestion:
    """One question with the set of corpus indices that are gold-supporting."""

    qid: str
    question: str
    answer: str
    gold_idxs: set[int]


# ---------------------------------------------------------------------------
# Report shapes (extra="forbid" — RunReport discipline)
# ---------------------------------------------------------------------------


class QAMethodMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    recall_at_2: float
    recall_at_5: float
    mrr_at_10: float


class QADensityLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_edge_fraction: float
    entity_edges: int
    total_edges: int
    mean_out_degree: float
    sa_raw_recall_at_5: float
    sa_ppr_recall_at_5: float
    knn_recall_at_5: float
    sa_ppr_minus_knn_at_5: float


class QARetrievalReport(BaseModel):
    """Structured result of one QA-retrieval benchmark run (honest-failure discipline)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset: str
    construction: str  # e.g. "spacy-ner + bge-small-en kNN (LLM-free first-cut)"
    embedder_model_id: str
    passage_count: int
    entity_node_count: int
    question_count: int
    gold_coverage: float  # fraction of questions with >=1 gold matched in corpus
    knn_k: int
    seed_top_s: int
    hops: int
    damping: float
    seed: int
    methods: list[QAMethodMetrics] = Field(default_factory=list)
    density_levels: list[QADensityLevel] = Field(default_factory=list)
    timing_s: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


# ---------------------------------------------------------------------------
# BM25 (minimal, dependency-free)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class BM25:
    """Okapi BM25 over a fixed passage corpus (k1=1.5, b=0.75)."""

    docs: list[list[str]]
    k1: float = 1.5
    b: float = 0.75
    _idf: dict[str, float] = field(default_factory=dict)
    _doc_len: list[int] = field(default_factory=list)
    _avg_len: float = 0.0
    _tf: list[dict[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.docs)
        self._doc_len = [len(d) for d in self.docs]
        self._avg_len = (sum(self._doc_len) / n) if n else 0.0
        df: dict[str, int] = defaultdict(int)
        for d in self.docs:
            tf: dict[str, int] = defaultdict(int)
            for tok in d:
                tf[tok] += 1
            self._tf.append(dict(tf))
            for tok in tf:
                df[tok] += 1
        # Robertson-Sparck-Jones idf, floored at 0 so common terms don't go negative.
        self._idf = {t: max(0.0, math.log((n - c + 0.5) / (c + 0.5) + 1.0)) for t, c in df.items()}

    def scores(self, query: str) -> torch.Tensor:
        q_tokens = _tokenize(query)
        out = torch.zeros(len(self.docs), dtype=torch.float32)
        for i, tf in enumerate(self._tf):
            dl = self._doc_len[i]
            denom_len = self.k1 * (1.0 - self.b + self.b * dl / max(self._avg_len, 1e-9))
            s = 0.0
            for tok in q_tokens:
                f = tf.get(tok, 0)
                if f == 0:
                    continue
                s += self._idf.get(tok, 0.0) * (f * (self.k1 + 1.0)) / (f + denom_len)
            out[i] = s
        return out


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


@dataclass
class QAGraph:
    """A retrieval graph over passage + entity nodes, ready for CSR / SA."""

    node_ids: list[str]
    sem_unit: torch.Tensor  # (N, D) L2-normalised, aligned to node_ids
    passage_indices: list[int]  # CSR index of passage p (in passage order)
    containment_edges: list[EdgeRow]  # passage<->entity (always kept)
    knn_edges: list[EdgeRow]  # passage<->passage geometric (always kept)
    entity_edges: list[EdgeRow]  # entity<->entity co-occurrence (the density dial)


def _l2_unit(mat: torch.Tensor) -> torch.Tensor:
    out: torch.Tensor = mat / mat.norm(dim=1, keepdim=True).clamp_min(1e-12)
    return out


def _entity_bridge_edges(
    weighted_pairs: dict[tuple[int, int], float],
    *,
    max_entity_degree: int,
    seed: int,
) -> list[EdgeRow]:
    """Cap, shuffle, and symmetrise entity↔entity bridges.

    Shared by both constructions (co-occurrence and LLM relations) so the only
    thing that differs between them is *which pairs* are bridged — not how those
    bridges are capped or ordered. That keeps the ablation honest.

    Pairs are capped per entity (highest weight first) to bound hub degree, then
    shuffled at the *pair* level and flattened with both directions adjacent, so a
    nested-prefix density sweep keeps each undirected bridge whole.
    """
    per_entity: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for (a, b), w in weighted_pairs.items():
        per_entity[a].append((b, w))
        per_entity[b].append((a, w))
    kept: set[tuple[int, int]] = set()
    for a, neigh in per_entity.items():
        neigh.sort(key=lambda x: x[1], reverse=True)
        for b, _w in neigh[:max_entity_degree]:
            kept.add((min(a, b), max(a, b)))

    ordered_pairs = sorted(kept)
    random.Random(seed).shuffle(ordered_pairs)
    edges: list[EdgeRow] = []
    for a, b in ordered_pairs:
        w = float(weighted_pairs.get((a, b), weighted_pairs.get((b, a), 1.0)))
        edges.append((f"e{a}", f"e{b}", w))
        edges.append((f"e{b}", f"e{a}", w))
    return edges


def build_qa_graph(
    passage_emb: torch.Tensor,
    entity_emb: torch.Tensor,
    entities_per_passage: list[set[int]],
    *,
    knn_k: int = 10,
    max_entity_degree: int = 32,
    seed: int = 0,
    relation_pairs: dict[tuple[int, int], float] | None = None,
) -> QAGraph:
    """Build a symmetric passage+entity graph.

    * ``passage_emb`` (P, D) and ``entity_emb`` (E, D) are raw embeddings.
    * ``entities_per_passage[p]`` is the set of entity indices found in passage p.

    Edge types (all symmetric — SA propagates along edge direction, so both
    directions are added):

    * **containment** passage↔entity (weight 1.0) — connects a passage to its entities.
    * **knn** passage↔passage — top-``knn_k`` cosine neighbours (weight = cosine); the
      geometric baseline embedded *into* the graph.
    * **entity** entity↔entity — the structural bridge that carries multi-hop signal
      and the density-ablation dial. Two constructions:

      - default (**cheap**): co-occurrence within a passage, weight = #co-occurrences.
        Noisy — every pair of entities sharing a passage is bridged, related or not.
      - ``relation_pairs`` given (**Kadmos-grade**): only pairs the extractor asserted
        an actual relation between, weight = relation count. Sparser and typed.

    Passing ``relation_pairs`` is the whole experimental contrast: same passages,
    same embeddings, same kNN backbone, same capping — different bridges.
    """
    p = passage_emb.shape[0]
    e = entity_emb.shape[0]
    passage_ids = [f"p{i}" for i in range(p)]
    entity_ids = [f"e{i}" for i in range(e)]
    node_ids = passage_ids + entity_ids
    sem = torch.cat([passage_emb, entity_emb], dim=0) if e else passage_emb
    sem_unit = _l2_unit(sem)
    passage_indices = list(range(p))  # passages occupy CSR indices 0..P-1 by construction

    # containment: passage <-> its entities
    containment: list[EdgeRow] = []
    for pi, ents in enumerate(entities_per_passage):
        for ei in ents:
            containment.append((f"p{pi}", f"e{ei}", 1.0))
            containment.append((f"e{ei}", f"p{pi}", 1.0))

    # passage-passage kNN (geometric): top-knn_k by cosine, excluding self
    knn_edges: list[EdgeRow] = []
    if knn_k > 0 and p > 1:
        pu = _l2_unit(passage_emb)
        sims = pu @ pu.t()
        sims.fill_diagonal_(-2.0)
        k = min(knn_k, p - 1)
        top_vals, top_idx = torch.topk(sims, k, dim=1)
        for i in range(p):
            for val, j in zip(top_vals[i].tolist(), top_idx[i].tolist(), strict=True):
                w = max(0.0, float(val))
                knn_edges.append((f"p{i}", f"p{j}", w))
                knn_edges.append((f"p{j}", f"p{i}", w))

    # entity-entity bridges: LLM relations when supplied, else passage co-occurrence
    if relation_pairs is not None:
        weighted_pairs = {
            (min(a, b), max(a, b)): w for (a, b), w in relation_pairs.items() if a != b
        }
    else:
        cooc: dict[tuple[int, int], float] = defaultdict(float)
        for ents in entities_per_passage:
            ordered = sorted(ents)
            for a_idx in range(len(ordered)):
                for b_idx in range(a_idx + 1, len(ordered)):
                    cooc[(ordered[a_idx], ordered[b_idx])] += 1.0
        weighted_pairs = dict(cooc)
    entity_edges = _entity_bridge_edges(
        weighted_pairs, max_entity_degree=max_entity_degree, seed=seed
    )

    return QAGraph(
        node_ids=node_ids,
        sem_unit=sem_unit,
        passage_indices=passage_indices,
        containment_edges=containment,
        knn_edges=knn_edges,
        entity_edges=entity_edges,
    )


# ---------------------------------------------------------------------------
# Kadmos-grade construction (LLM concepts + typed relations)
# ---------------------------------------------------------------------------


def _normalize_entity(label: str) -> str:
    """Fold a concept label to its cross-passage identity key."""
    return " ".join(_TOKEN_RE.findall(label.lower()))


def graph_inputs_from_extractions(
    extractions: list[dict[str, object]],
) -> tuple[list[str], list[set[int]], dict[tuple[int, int], float]]:
    """Turn per-passage LLM readings into (entity_names, per-passage sets, relation pairs).

    ``extractions[p]`` is one passage's :class:`ParagraphReadingOutput` dump —
    ``{"concepts": [{"label": ...}], "relations": [{"source": ..., "target": ...}]}``.
    A missing or failed reading is an empty dict, which contributes no entities and
    no relations (honest-failure: the passage is still retrievable via its own
    embedding and kNN edges, it just carries no structural bridges).

    **Entity identity is normalized-label matching** — lowercase, punctuation
    stripped. This is deliberately the same naive resolution GraphRAG uses, and the
    literature flags it as a weakness (homonyms merge, variant names split). Using
    it here is the honest choice for *this* experiment: it isolates the variable
    under test — relation quality — instead of confounding it with an entity
    resolution scheme the cheap construction does not have either. The substrate's
    real eager linker (PHX-1051/1053) is a separate, later upgrade.

    Relations are folded to undirected pairs with weight = how many passages
    asserted them, mirroring the co-occurrence weighting so the two constructions
    stay comparable.
    """
    entity_to_idx: dict[str, int] = {}
    entity_names: list[str] = []
    per_passage: list[set[int]] = []
    relation_pairs: dict[tuple[int, int], float] = defaultdict(float)

    def _intern(label: str) -> int | None:
        key = _normalize_entity(label)
        if len(key) < 2:
            return None
        idx = entity_to_idx.get(key)
        if idx is None:
            idx = len(entity_names)
            entity_to_idx[key] = idx
            entity_names.append(key)
        return idx

    for reading in extractions:
        local: dict[str, int] = {}  # this passage's label -> global entity index
        ents: set[int] = set()
        concepts = reading.get("concepts") or []
        if isinstance(concepts, list):
            for concept in concepts:
                if not isinstance(concept, dict):
                    continue
                label = str(concept.get("label", ""))
                idx = _intern(label)
                if idx is None:
                    continue
                local[_normalize_entity(label)] = idx
                ents.add(idx)
        per_passage.append(ents)

        relations = reading.get("relations") or []
        if isinstance(relations, list):
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                src = local.get(_normalize_entity(str(rel.get("source", ""))))
                tgt = local.get(_normalize_entity(str(rel.get("target", ""))))
                # Only bridge endpoints the same passage actually declared as concepts;
                # a relation naming something never extracted is dropped, not invented.
                if src is None or tgt is None or src == tgt:
                    continue
                relation_pairs[(min(src, tgt), max(src, tgt))] += 1.0

    return entity_names, per_passage, dict(relation_pairs)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _seed_vector(
    query_unit: torch.Tensor,
    passage_unit: torch.Tensor,
    n_nodes: int,
    *,
    top_s: int,
) -> torch.Tensor:
    """Dense query→passage seeding (HippoRAG-2 finding: beats NER-to-node seeding).

    Returns an activation vector over all CSR nodes with mass on the top-``top_s``
    passages by query cosine (passages occupy indices 0..P-1).
    """
    sims = passage_unit @ query_unit
    k = min(top_s, sims.shape[0])
    vals, idx = torch.topk(sims, k)
    x = torch.zeros(n_nodes, dtype=torch.float32)
    for v, j in zip(vals.tolist(), idx.tolist(), strict=True):
        x[j] = max(0.0, float(v))
    return x


def seed_indices(
    query_unit: torch.Tensor,
    passage_unit: torch.Tensor,
    *,
    top_s: int,
) -> set[int]:
    """The passage indices that query→passage seeding would activate."""
    sims = passage_unit @ query_unit
    k = min(top_s, sims.shape[0])
    _vals, idx = torch.topk(sims, k)
    return {int(i) for i in idx.tolist()}


def build_seed_vector(
    query_unit: torch.Tensor,
    passage_unit: torch.Tensor,
    entity_unit: torch.Tensor,
    n_nodes: int,
    *,
    mode: str,
    top_s: int,
) -> torch.Tensor:
    """Seed activation over the graph under one of three schemes.

    The seeding scheme is the last untested structural variable in this benchmark.
    It matters because the default (``passage``) starts activation *inside* the
    neighbourhood dense kNN already returns — so a graph that merely re-ranks its
    seeds can never beat the retriever that produced them, no matter how good its
    edges are.

    * ``passage`` — top-``top_s`` passages by query cosine (the default; HippoRAG 2
      reports this beats NER-to-node seeding on their graph).
    * ``entity`` — top-``top_s`` *entity* nodes by query cosine. Activation must
      travel entity→passage, so the passage ranking is produced by the graph rather
      than inherited from the embedding ranking. This is closer to HippoRAG 1's
      query-NER seeding.
    * ``hybrid`` — both, each contributing its own cosine mass.
    """
    x = torch.zeros(n_nodes, dtype=torch.float32)
    n_passages = passage_unit.shape[0]

    if mode in ("passage", "hybrid"):
        sims = passage_unit @ query_unit
        k = min(top_s, sims.shape[0])
        vals, idx = torch.topk(sims, k)
        for v, j in zip(vals.tolist(), idx.tolist(), strict=True):
            x[j] = max(0.0, float(v))

    if mode in ("entity", "hybrid"):
        if entity_unit.shape[0] == 0:
            if mode == "entity":
                raise ValueError("entity seeding requested but the graph has no entity nodes")
        else:
            sims_e = entity_unit @ query_unit
            k = min(top_s, sims_e.shape[0])
            vals, idx = torch.topk(sims_e, k)
            for v, j in zip(vals.tolist(), idx.tolist(), strict=True):
                x[n_passages + int(j)] = max(0.0, float(v))

    if mode not in ("passage", "entity", "hybrid"):
        raise ValueError(f"unknown seeding mode: {mode!r}")
    return x


def sa_passage_scores(
    adj: torch.Tensor,
    seed_x: torch.Tensor,
    passage_indices: list[int],
    *,
    hops: int,
    damping: float,
) -> torch.Tensor:
    """Spreading Activation from a seed vector; return activation on passage nodes.

    Uses the same damped-diffusion kernel as the link-prediction eval
    (:func:`propagate`), generalised to a multi-node seed. Activation flows along
    edge direction (``x ← damping · Aᵀx``); the graph is symmetric so it spreads
    both ways. Passage scores are read off after propagation.
    """
    x = seed_x.clone()
    for _ in range(hops):
        x = damping * torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1) + seed_x
    return x[torch.tensor(passage_indices, dtype=torch.int64)]


def recall_at_k(ranked_passage_idx: list[int], gold_idxs: set[int], k: int) -> float:
    """Fraction of a question's gold passages present in the top-k (HippoRAG convention)."""
    if not gold_idxs:
        return 0.0
    topk = set(ranked_passage_idx[:k])
    return len(topk & gold_idxs) / len(gold_idxs)


def mrr_at_k(ranked_passage_idx: list[int], gold_idxs: set[int], k: int = 10) -> float:
    """Reciprocal rank of the first gold passage within the top-k, else 0."""
    for rank, pidx in enumerate(ranked_passage_idx[:k], start=1):
        if pidx in gold_idxs:
            return 1.0 / rank
    return 0.0


def rank_desc(scores: torch.Tensor) -> list[int]:
    """Argsort passage scores descending → list of passage indices (0..P-1)."""
    return torch.argsort(scores, descending=True).tolist()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _adjacencies(
    node_ids: list[str], edge_rows: list[EdgeRow]
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return (raw weighted adjacency, row-normalised random-walk adjacency)."""
    csr = build_csr_over_nodes(node_ids, edge_rows)
    device = torch.device("cpu")
    return build_adjacency(csr, device), build_normalized_adjacency(csr, device)


def evaluate_methods(
    graph: QAGraph,
    passage_emb: torch.Tensor,
    question_emb: torch.Tensor,
    bm25: BM25,
    questions: list[QAQuestion],
    *,
    hops: int = 3,
    damping: float = 0.5,
    seed_top_s: int = 10,
) -> list[QAMethodMetrics]:
    """Score BM25, kNN (dense), and two SA variants at the operating point.

    * ``sa_raw`` — Spreading Activation over raw weighted adjacency. This is the
      variant the substrate doctrine itself flags as hub-collapsing (PHX-1042):
      degree hubs (common entities — dates, frequent names) absorb activation.
    * ``sa_ppr`` — the *fair* variant: row-normalised (random-walk) adjacency with
      query→passage restart, i.e. Personalized PageRank — the operator HippoRAG
      actually uses and the closest analogue to the substrate's production
      degree-aware retrieval.

    ``question_emb`` rows are aligned to ``questions``. Every method retrieves
    over the same passage universe, so the comparison isolates the mechanism.
    """
    passage_unit = _l2_unit(passage_emb)
    question_unit = _l2_unit(question_emb)
    n_nodes = len(graph.node_ids)
    adj_raw, adj_ppr = _adjacencies(
        graph.node_ids, graph.containment_edges + graph.knn_edges + graph.entity_edges
    )

    rec2: dict[str, float] = defaultdict(float)
    rec5: dict[str, float] = defaultdict(float)
    mrr: dict[str, float] = defaultdict(float)
    names = ("bm25", "knn", "sa_raw", "sa_ppr")
    for qi, q in enumerate(questions):
        qu = question_unit[qi]
        seed_x = _seed_vector(qu, passage_unit, n_nodes, top_s=seed_top_s)
        scored = {
            "bm25": bm25.scores(q.question),
            "knn": passage_unit @ qu,
            "sa_raw": sa_passage_scores(
                adj_raw, seed_x, graph.passage_indices, hops=hops, damping=damping
            ),
            "sa_ppr": sa_passage_scores(
                adj_ppr, seed_x, graph.passage_indices, hops=hops, damping=damping
            ),
        }
        for name in names:
            ranked = rank_desc(scored[name])
            rec2[name] += recall_at_k(ranked, q.gold_idxs, 2)
            rec5[name] += recall_at_k(ranked, q.gold_idxs, 5)
            mrr[name] += mrr_at_k(ranked, q.gold_idxs, 10)
    nq = max(1, len(questions))
    return [
        QAMethodMetrics(
            method=m,
            recall_at_2=rec2[m] / nq,
            recall_at_5=rec5[m] / nq,
            mrr_at_10=mrr[m] / nq,
        )
        for m in names
    ]


class SeedingResult(BaseModel):
    """One seeding configuration, with diagnostics that explain *why* it scores so.

    The headline recalls say how well SA does. These fields say whether the graph
    is doing anything at all:

    * ``seed_recall_at_5`` — recall of the seed set itself, the ceiling SA inherits
      when it only re-ranks its seeds.
    * ``rescue_rate`` — of the gold passages the seeds **missed**, the fraction SA
      still pulls into its top-5. This is SA's unique contribution. Near zero means
      the graph cannot reach what the embedding did not already find, and parity
      with kNN is **structural**, not a tuning problem.
    * ``sa_only_hits`` / ``knn_only_hits`` — head-to-head gold passages found by one
      method's top-5 and not the other's. Equal and small means the two rankings are
      effectively the same; ``knn_only`` exceeding ``sa_only`` means propagation is
      actively displacing correct results.
    * ``seed_retention`` — fraction of SA's top-5 that were already seeds. Near 1.0
      means SA is a re-ranker of kNN output, by construction.

    These diagnostics only discriminate when the corpus is meaningfully larger than
    k: on a corpus of five or fewer passages every recall@5 is trivially 1.0.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str
    top_s: int
    operator: str
    sa_recall_at_5: float
    knn_recall_at_5: float
    seed_recall_at_5: float
    rescue_rate: float
    rescued_gold: int
    gold_missed_by_seeds: int
    sa_only_hits: int
    knn_only_hits: int
    seed_retention: float


def evaluate_seeding(
    graph: QAGraph,
    passage_emb: torch.Tensor,
    question_emb: torch.Tensor,
    questions: list[QAQuestion],
    *,
    modes: list[str],
    seed_counts: list[int],
    operator: str = "ppr",
    hops: int = 3,
    damping: float = 0.5,
) -> list[SeedingResult]:
    """Sweep seeding scheme × seed count, reporting recall plus the diagnostics.

    ``operator`` selects the propagation adjacency: ``ppr`` (row-normalised, the
    fair degree-aware operator) or ``raw``.
    """
    passage_unit = _l2_unit(passage_emb)
    question_unit = _l2_unit(question_emb)
    n_passages = passage_emb.shape[0]
    entity_unit = graph.sem_unit[n_passages:]
    n_nodes = len(graph.node_ids)

    adj_raw, adj_ppr = _adjacencies(
        graph.node_ids, graph.containment_edges + graph.knn_edges + graph.entity_edges
    )
    adj = adj_ppr if operator == "ppr" else adj_raw

    # kNN reference is seeding-independent — compute once.
    knn_top5: list[list[int]] = []
    knn_recall = 0.0
    for qi, q in enumerate(questions):
        ranked = rank_desc(passage_unit @ question_unit[qi])
        knn_top5.append(ranked[:5])
        knn_recall += recall_at_k(ranked, q.gold_idxs, 5)
    knn_recall /= max(1, len(questions))

    results: list[SeedingResult] = []
    for mode in modes:
        for top_s in seed_counts:
            sa_recall = 0.0
            seed_recall = 0.0
            retention = 0.0
            rescued = 0
            missed = 0
            sa_only = 0
            knn_only = 0

            for qi, q in enumerate(questions):
                qu = question_unit[qi]
                seeds = seed_indices(qu, passage_unit, top_s=top_s)
                seed_vec = build_seed_vector(
                    qu, passage_unit, entity_unit, n_nodes, mode=mode, top_s=top_s
                )
                sa = sa_passage_scores(
                    adj, seed_vec, graph.passage_indices, hops=hops, damping=damping
                )
                sa_top = rank_desc(sa)[:5]
                sa_set = set(sa_top)

                sa_recall += recall_at_k(sa_top, q.gold_idxs, 5)
                # Ceiling the seed set imposes, scored on the same top-5 basis.
                seed_recall += recall_at_k(sorted(seeds), q.gold_idxs, 5)
                retention += len(sa_set & seeds) / max(1, len(sa_top))

                # SA's unique contribution: gold the seeds never contained.
                gold_missed = q.gold_idxs - seeds
                missed += len(gold_missed)
                rescued += len(gold_missed & sa_set)

                knn_set = set(knn_top5[qi])
                sa_only += len(q.gold_idxs & sa_set - knn_set)
                knn_only += len(q.gold_idxs & knn_set - sa_set)

            nq = max(1, len(questions))
            results.append(
                SeedingResult(
                    mode=mode,
                    top_s=top_s,
                    operator=operator,
                    sa_recall_at_5=sa_recall / nq,
                    knn_recall_at_5=knn_recall,
                    seed_recall_at_5=seed_recall / nq,
                    rescue_rate=(rescued / missed) if missed else 0.0,
                    rescued_gold=rescued,
                    gold_missed_by_seeds=missed,
                    sa_only_hits=sa_only,
                    knn_only_hits=knn_only,
                    seed_retention=retention / nq,
                )
            )
    return results


def density_sweep(
    graph: QAGraph,
    passage_emb: torch.Tensor,
    question_emb: torch.Tensor,
    questions: list[QAQuestion],
    *,
    fractions: list[float],
    hops: int = 3,
    damping: float = 0.5,
    seed_top_s: int = 10,
) -> list[QADensityLevel]:
    """Sweep the entity-bridge edge fraction; SA recall@5 vs the flat kNN reference.

    The geometric backbone (containment + passage-kNN) is held fixed; only the
    structural entity-bridge edges grow, as nested prefixes of one shuffle. The
    kNN reference is edge-independent (flat). A widening ``sa_minus_knn_at_5`` as
    density rises is the phase-transition signal.
    """
    passage_unit = _l2_unit(passage_emb)
    question_unit = _l2_unit(question_emb)
    n_nodes = len(graph.node_ids)
    base_edges = graph.containment_edges + graph.knn_edges

    # kNN reference (constant across levels)
    knn_r5 = 0.0
    for qi, q in enumerate(questions):
        ranked = rank_desc(passage_unit @ question_unit[qi])
        knn_r5 += recall_at_k(ranked, q.gold_idxs, 5)
    knn_r5 /= max(1, len(questions))

    total_entity = len(graph.entity_edges)
    levels: list[QADensityLevel] = []
    for frac in fractions:
        k = int(round(frac * total_entity))
        edges = base_edges + graph.entity_edges[:k]
        adj_raw, adj_ppr = _adjacencies(graph.node_ids, edges)
        sa_raw_r5 = 0.0
        sa_ppr_r5 = 0.0
        for qi, q in enumerate(questions):
            qu = question_unit[qi]
            seed_x = _seed_vector(qu, passage_unit, n_nodes, top_s=seed_top_s)
            raw = sa_passage_scores(
                adj_raw, seed_x, graph.passage_indices, hops=hops, damping=damping
            )
            ppr = sa_passage_scores(
                adj_ppr, seed_x, graph.passage_indices, hops=hops, damping=damping
            )
            sa_raw_r5 += recall_at_k(rank_desc(raw), q.gold_idxs, 5)
            sa_ppr_r5 += recall_at_k(rank_desc(ppr), q.gold_idxs, 5)
        nq = max(1, len(questions))
        sa_raw_r5 /= nq
        sa_ppr_r5 /= nq
        levels.append(
            QADensityLevel(
                entity_edge_fraction=frac,
                entity_edges=k,
                total_edges=len(edges),
                mean_out_degree=len(edges) / max(1, n_nodes),
                sa_raw_recall_at_5=sa_raw_r5,
                sa_ppr_recall_at_5=sa_ppr_r5,
                knn_recall_at_5=knn_r5,
                sa_ppr_minus_knn_at_5=sa_ppr_r5 - knn_r5,
            )
        )
    return levels
