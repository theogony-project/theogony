"""Held-out link-prediction evaluation over a seeded MESH workspace.

This harness operationalises the README's central, falsifiable claim — *can a
dense vector-graph surface relations that were never inserted?* — as a standard
knowledge-graph completion metric (MRR / Hits@k), and quantifies the
hub-collapse failure mode that naive Spreading Activation exhibits.

At Step S1 / S2.5 the substrate is **relation-agnostic**: Spreading Activation
propagates over weighted adjacency without conditioning on relation type.  A
test triple ``(h, r, t)`` is therefore scored as *"given head ``h``, how highly
does the substrate rank the held-out tail ``t`` among all candidate nodes?"*.
Relation-conditioned retrieval and diversified injection are Step S3; this
harness is the measurement baseline that S3 must beat.

Five rankers are compared so the result is interpretable rather than a single
opaque number:

* ``random``      — control; the floor.
* ``degree``      — rank candidates by incoming-edge count (popularity).  If a
                    structural ranker cannot beat this, it is only doing
                    popularity.
* ``knn``         — cosine similarity of the head's ``semantic_vector`` to each
                    candidate's.  Pure geometry, no edges.  (README hypothesis 2:
                    does structure beat geometry?)
* ``sa_raw``      — Spreading Activation over raw weighted adjacency (current
                    Step-S1 primitive).  Expected to collapse onto hubs.
* ``sa_degnorm``  — Spreading Activation over row-normalised (random-walk)
                    adjacency; the hypothesised hub-collapse fix.

The harness is read-only with respect to the substrate and emits a structured
:class:`LinkPredictionReport` (honest-failure / RunReport discipline).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import torch
from pydantic import BaseModel, ConfigDict, Field

from theogony.mesh.storage.edges import EdgeCSR

RANKERS: tuple[str, ...] = ("random", "degree", "knn", "sa_raw", "sa_degnorm")

# A directed edge as ``(source_id, target_id, conductance)`` in node-id space.
EdgeRow = tuple[str, str, float]


# ---- report shapes -------------------------------------------------------


class RankerMetrics(BaseModel):
    """Ranking quality for a single ranker over the held-out test set."""

    model_config = ConfigDict(extra="forbid")

    ranker: str
    mrr: float
    hits_at_1: float
    hits_at_3: float
    hits_at_10: float
    mean_rank: float


class LinkPredictionReport(BaseModel):
    """Structured result of one link-prediction evaluation run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    workspace: str
    mode: str
    test_fraction: float | None
    triplet_source: str
    node_count: int
    csr_node_count: int
    edge_count: int
    test_triples: int
    skipped_endpoint_not_in_csr: int
    hops: int
    damping: float
    seed: int
    rankers: list[RankerMetrics] = Field(default_factory=list)
    timing_s: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


# ---- adjacency / context -------------------------------------------------


@dataclass
class RankerContext:
    """Precomputed structures shared across all test triples and rankers."""

    n: int
    device: torch.device
    adj: torch.Tensor  # sparse CSR (N, N), row = source, weighted
    adj_norm: torch.Tensor  # sparse CSR (N, N), row-normalised (random walk)
    in_degree: torch.Tensor  # (N,) float32, incoming-edge count
    sem_unit: torch.Tensor  # (N, D) float32, L2-normalised semantic vectors


def l2_normalize_rows(matrix: torch.Tensor) -> torch.Tensor:
    """Row-wise L2 normalisation (safe for zero rows)."""
    norms = matrix.norm(dim=1, keepdim=True).clamp_min(1e-12)
    normalized: torch.Tensor = matrix / norms
    return normalized


def build_adjacency(csr: EdgeCSR, device: torch.device) -> torch.Tensor:
    """Construct the weighted sparse CSR adjacency (row = source, col = target)."""
    n = len(csr.node_ids)
    return torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        csr.values.to(device),
        size=(n, n),
        dtype=torch.float32,
        device=device,
    )


def row_normalized_values(csr: EdgeCSR) -> torch.Tensor:
    """Return edge values divided by each source node's total out-strength."""
    n = len(csr.node_ids)
    counts = csr.crow_indices[1:] - csr.crow_indices[:-1]
    row_idx = torch.repeat_interleave(torch.arange(n, dtype=torch.int64), counts)
    vals = csr.values.to(torch.float32)
    row_sums = torch.zeros(n, dtype=torch.float32).scatter_add_(0, row_idx, vals)
    denom = row_sums[row_idx].clamp_min(1e-12)
    return vals / denom


def build_normalized_adjacency(csr: EdgeCSR, device: torch.device) -> torch.Tensor:
    """Construct the row-normalised (random-walk) sparse CSR adjacency."""
    n = len(csr.node_ids)
    return torch.sparse_csr_tensor(
        csr.crow_indices.to(device),
        csr.col_indices.to(device),
        row_normalized_values(csr).to(device),
        size=(n, n),
        dtype=torch.float32,
        device=device,
    )


def in_degree_from_csr(csr: EdgeCSR) -> torch.Tensor:
    """Incoming-edge count per node (popularity baseline)."""
    n = len(csr.node_ids)
    return torch.bincount(csr.col_indices, minlength=n).to(torch.float32)


def build_context(
    csr: EdgeCSR,
    sem_unit: torch.Tensor,
    *,
    device: torch.device | None = None,
) -> RankerContext:
    device = device or torch.device("cpu")
    return RankerContext(
        n=len(csr.node_ids),
        device=device,
        adj=build_adjacency(csr, device),
        adj_norm=build_normalized_adjacency(csr, device),
        in_degree=in_degree_from_csr(csr).to(device),
        sem_unit=sem_unit.to(device),
    )


# ---- propagation / scoring ----------------------------------------------


def propagate(
    adj: torch.Tensor,
    head_index: int,
    n: int,
    *,
    hops: int,
    damping: float,
) -> torch.Tensor:
    """Propagate unit activation from ``head_index`` along outgoing edges."""
    device = adj.device
    x = torch.zeros(n, dtype=torch.float32, device=device)
    x[head_index] = 1.0
    for _ in range(hops):
        x = damping * torch.sparse.mm(adj.t(), x.unsqueeze(1)).squeeze(1)
    return x


def score_head(
    ctx: RankerContext,
    ranker: str,
    head_index: int,
    *,
    hops: int,
    damping: float,
    generator: torch.Generator | None = None,
) -> torch.Tensor:
    """Return a score vector over all nodes for one ranker and one head."""
    if ranker == "random":
        return torch.rand(ctx.n, generator=generator)
    if ranker == "degree":
        return ctx.in_degree
    if ranker == "knn":
        return ctx.sem_unit @ ctx.sem_unit[head_index]
    if ranker == "sa_raw":
        return propagate(ctx.adj, head_index, ctx.n, hops=hops, damping=damping)
    if ranker == "sa_degnorm":
        return propagate(ctx.adj_norm, head_index, ctx.n, hops=hops, damping=damping)
    raise ValueError(f"unknown ranker: {ranker!r}")


def filtered_rank(
    scores: torch.Tensor,
    head_index: int,
    tail_index: int,
    known_tail_indices: set[int],
) -> float:
    """Average-tie rank (1-based) of the true tail under the filtered protocol.

    The head itself and every *other* known tail of the head are removed from
    the candidate pool so the model is not penalised for ranking already-known
    true tails above the held-out one.  Ties share the average of the ranks they
    span, which keeps the popularity baseline honest (it produces many ties).
    """
    mask = torch.ones_like(scores, dtype=torch.bool)
    mask[head_index] = False
    for k in known_tail_indices:
        if k != tail_index:
            mask[k] = False
    valid = scores[mask]
    true_score = scores[tail_index]
    greater = int((valid > true_score).sum().item())
    equal = int((valid == true_score).sum().item())  # includes the true tail
    return greater + (equal + 1) / 2.0


def rank_metrics(ranker: str, ranks: list[float]) -> RankerMetrics:
    """Aggregate per-triple ranks into MRR / Hits@k / mean rank."""
    if not ranks:
        return RankerMetrics(
            ranker=ranker,
            mrr=0.0,
            hits_at_1=0.0,
            hits_at_3=0.0,
            hits_at_10=0.0,
            mean_rank=0.0,
        )
    count = len(ranks)
    mrr = sum(1.0 / r for r in ranks) / count
    return RankerMetrics(
        ranker=ranker,
        mrr=mrr,
        hits_at_1=sum(1.0 for r in ranks if r <= 1) / count,
        hits_at_3=sum(1.0 for r in ranks if r <= 3) / count,
        hits_at_10=sum(1.0 for r in ranks if r <= 10) / count,
        mean_rank=sum(ranks) / count,
    )


def evaluate(
    ctx: RankerContext,
    test_pairs: list[tuple[int, int]],
    known_tails_by_head: dict[int, set[int]],
    *,
    rankers: tuple[str, ...] = RANKERS,
    hops: int = 3,
    damping: float = 0.5,
    seed: int = 0,
) -> dict[str, RankerMetrics]:
    """Run every ranker over every test pair and aggregate metrics.

    ``test_pairs`` are ``(head_index, tail_index)`` in CSR index space.
    """
    generator = torch.Generator().manual_seed(seed)
    ranks: dict[str, list[float]] = {r: [] for r in rankers}
    for head_index, tail_index in test_pairs:
        known = known_tails_by_head.get(head_index, set())
        for ranker in rankers:
            scores = score_head(
                ctx,
                ranker,
                head_index,
                hops=hops,
                damping=damping,
                generator=generator if ranker == "random" else None,
            )
            ranks[ranker].append(filtered_rank(scores, head_index, tail_index, known))
    return {r: rank_metrics(r, ranks[r]) for r in rankers}


# ---- edge-split test-set construction ------------------------------------
#
# When a workspace is *edge-saturated* over its node set (every dataset triple
# among its nodes was already inserted — as the Wikidata5m Smoke-2 seed is),
# held-out positives cannot be drawn from the raw triplet file.  The canonical
# knowledge-graph-completion protocol applies instead: hide a fraction of the
# substrate's own edges, build the runtime from the remainder, and measure
# whether the rankers recover the hidden tails.  This is still "surface a
# relation the substrate has no edge for" — the spirit of the README claim.


def split_edge_rows(
    edge_rows: list[EdgeRow],
    *,
    test_fraction: float,
    seed: int = 0,
) -> tuple[list[EdgeRow], list[EdgeRow]]:
    """Deterministically split directed edges into (train, test)."""
    rows = list(edge_rows)
    random.Random(seed).shuffle(rows)
    n_test = int(round(len(rows) * test_fraction))
    return rows[n_test:], rows[:n_test]


def build_csr_over_nodes(node_ids: list[str], edge_rows: list[EdgeRow]) -> EdgeCSR:
    """Build a CSR over a *fixed* node universe, populated by ``edge_rows`` only.

    The node universe is pinned (rather than derived from the edges) so that a
    train-only CSR shares an index space with the full mesh — held-out tail
    indices stay valid even when a node has no surviving train edges.
    """
    id_to_index = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    rows = [(s, t, w) for (s, t, w) in edge_rows if s in id_to_index and t in id_to_index]

    row_counts = [0] * n
    for s, _t, _w in rows:
        row_counts[id_to_index[s]] += 1
    crow = [0]
    for c in row_counts:
        crow.append(crow[-1] + c)
    nnz = crow[-1]
    col = [0] * nnz
    val = [0.0] * nnz
    write = crow[:-1].copy()
    for s, t, w in rows:
        si = id_to_index[s]
        pos = write[si]
        col[pos] = id_to_index[t]
        val[pos] = float(w)
        write[si] += 1

    return EdgeCSR(
        crow_indices=torch.tensor(crow, dtype=torch.int64),
        col_indices=torch.tensor(col, dtype=torch.int64),
        values=torch.tensor(val, dtype=torch.float32),
        node_ids=list(node_ids),
        id_to_index=id_to_index,
    )


# ---- raw-file held-out test-set construction -----------------------------


def build_heldout_testset(
    triplet_path: Path,
    mesh_qids: set[str],
    known_pairs: set[tuple[str, str]],
    *,
    max_test: int,
    seed: int = 0,
    scan_limit: int | None = None,
) -> list[tuple[str, str, str]]:
    """Reservoir-sample held-out triples ``(h_qid, rel, t_qid)``.

    A triple qualifies when both endpoints are nodes in the mesh, the directed
    ``(h, t)`` pair is *not* already an inserted edge, and ``h != t``.  These are
    true relations the substrate was never told about — the prediction targets.

    Reservoir sampling gives a uniform sample over the qualifying stream without
    materialising all of it; ``scan_limit`` optionally bounds the lines read.
    """
    rng = random.Random(seed)
    reservoir: list[tuple[str, str, str]] = []
    seen = 0
    with triplet_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle):
            if scan_limit is not None and line_no >= scan_limit:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            head, rel, tail = parts
            if head == tail:
                continue
            if head not in mesh_qids or tail not in mesh_qids:
                continue
            if (head, tail) in known_pairs:
                continue
            seen += 1
            if len(reservoir) < max_test:
                reservoir.append((head, rel, tail))
            else:
                j = rng.randint(0, seen - 1)
                if j < max_test:
                    reservoir[j] = (head, rel, tail)
    return reservoir
