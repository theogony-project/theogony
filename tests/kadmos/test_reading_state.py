"""
Unit tests for Kadmos v2 ReadingStateStore (E3).

All tests use an in-process LanceDB with a fresh tmp directory.
No network, no external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    RevisionRecord,
    SynthesisNode,
)
from theogony.kadmos.reading_state import (
    ReadingStateStore,
    new_concept_id,
    new_edge_id,
    new_synthesis_id,
)

DIM = 4


def _store(tmp_path: Path) -> ReadingStateStore:
    return ReadingStateStore(
        session_id="test-sess",
        embedding_dim=DIM,
        db_path=tmp_path / "lancedb",
    )


def _emb(val: float = 0.5) -> list[float]:
    return [val, val, val, val]


def _concept(label: str = "Tibet", step: int = 0) -> ActiveConcept:
    return ActiveConcept(id=new_concept_id(), label=label, step_created=step)


def _edge(src_id: str, tgt_id: str, step: int = 0) -> ActiveEdge:
    return ActiveEdge(
        id=new_edge_id(),
        source_id=src_id,
        target_id=tgt_id,
        relation_description="Test connection",
        step_created=step,
    )


# ---------------------------------------------------------------------------
# Basic concept / edge write + count
# ---------------------------------------------------------------------------


def test_add_concept_and_count(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c = _concept("Tibet")
    store.add_concept(c, _emb(0.1), step=0)
    assert store.concept_count() == 1


def test_add_multiple_concepts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        c = _concept(f"Concept {i}")
        store.add_concept(c, _emb(float(i) / 5), step=i)
    assert store.concept_count() == 5


def test_add_edge_and_count(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c1 = _concept("Tibet")
    c2 = _concept("Hedin")
    store.add_concept(c1, _emb(0.1), step=0)
    store.add_concept(c2, _emb(0.9), step=0)
    e = _edge(c1.id, c2.id)
    store.add_edge(e, _emb(0.5), step=0)
    assert store.edge_count(implicit=False) == 1


def test_empty_store_counts_zero(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.concept_count() == 0
    assert store.edge_count() == 0


def test_embedding_dim_mismatch_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c = _concept()
    with pytest.raises(ValueError, match="dim mismatch"):
        store.add_concept(c, [0.1, 0.2], step=0)  # only 2 dims, need 4


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


def test_revise_concept_adds_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c = _concept("Tibet")
    store.add_concept(c, _emb(0.1), step=0)

    rr = RevisionRecord(
        step_index=3,
        revision_type="update",
        reason="Better understanding",
        triggering_passage="passage text",
        new_understanding="Updated description",
    )
    c.description = "Updated description"
    store.revise_concept(c, _emb(0.2), rr, step=3)

    # Original + revision = 2 rows when include_revisions=True
    assert store.concept_count(include_revisions=True) == 2
    # Only the original (supersedes_id='') counts in default count
    assert store.concept_count() == 1


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def test_add_synthesis_as_concept(tmp_path: Path) -> None:
    store = _store(tmp_path)
    s = SynthesisNode(
        id=new_synthesis_id(),
        label="Tibetan Exploration",
        description="Synthesis of exploration themes",
        basis_concept_ids=["c1", "c2"],
        synthesis_level="paragraph",
        step_created=5,
    )
    store.add_synthesis_as_concept(s, _emb(0.5), step=5)
    assert store.concept_count() == 1


# ---------------------------------------------------------------------------
# kNN similarity search
# ---------------------------------------------------------------------------


def test_similarity_candidates_returns_results(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # Add 3 concepts with different embeddings
    for i, label in enumerate(["Tibet", "Hedin", "Himalayas"]):
        c = _concept(label)
        store.add_concept(c, _emb(float(i + 1) / 4), step=i)

    # Query near the first concept
    hits = store.similarity_candidates([0.25, 0.25, 0.25, 0.25], k=2)
    assert len(hits) <= 2
    for h in hits:
        assert h.hypothesis_type == "similarity"
        assert 0.0 <= h.score <= 1.0


def test_similarity_candidates_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    hits = store.similarity_candidates([0.1, 0.2, 0.3, 0.4])
    assert hits == []


def test_similarity_candidates_excludes_invalidated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c = _concept("Tibet")
    c.invalidated = True
    store.add_concept(c, _emb(0.9), step=0)
    # Add one valid concept
    c2 = _concept("Hedin")
    store.add_concept(c2, _emb(0.1), step=0)

    hits = store.similarity_candidates([0.9, 0.9, 0.9, 0.9], k=5)
    labels = [h.label for h in hits]
    assert "Tibet" not in labels


# ---------------------------------------------------------------------------
# Traversal candidates
# ---------------------------------------------------------------------------


def test_traversal_candidates_follows_edges(tmp_path: Path) -> None:
    store = _store(tmp_path)
    c1 = _concept("Tibet")
    c2 = _concept("Hedin")
    store.add_concept(c1, _emb(0.1), step=0)
    store.add_concept(c2, _emb(0.9), step=0)
    e = _edge(c1.id, c2.id)
    store.add_edge(e, _emb(0.5), step=0)

    candidates = store.traversal_candidates([c1.id], k=3)
    assert any(cand.concept_id == c2.id for cand in candidates)


def test_traversal_candidates_empty_graph(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidates = store.traversal_candidates(["c1"], k=3)
    assert candidates == []


def test_traversal_candidates_no_self_loop(tmp_path: Path) -> None:
    """Traversal must not return concepts already in the active set."""
    store = _store(tmp_path)
    c1 = _concept("Tibet")
    c2 = _concept("Hedin")
    store.add_concept(c1, _emb(0.1), step=0)
    store.add_concept(c2, _emb(0.9), step=0)
    e = _edge(c1.id, c2.id)
    store.add_edge(e, _emb(0.5), step=0)

    # Both c1 and c2 are "active" — traversal should return nothing
    candidates = store.traversal_candidates([c1.id, c2.id], k=3)
    assert candidates == []


# ---------------------------------------------------------------------------
# Post-read kNN implicit edges
# ---------------------------------------------------------------------------


def test_add_implicit_edges_increases_edge_count(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        c = _concept(f"Concept {i}")
        store.add_concept(c, _emb(float(i) / 6), step=i)

    added = store.add_implicit_edges(k=3)
    assert added > 0
    # Implicit edges should be counted
    assert store.edge_count(implicit=True) > 0
    # Explicit edge count should still be 0
    assert store.edge_count(implicit=False) == 0


def test_add_implicit_edges_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    added = store.add_implicit_edges(k=3)
    assert added == 0


# ---------------------------------------------------------------------------
# ID minting helpers
# ---------------------------------------------------------------------------


def test_new_concept_id_is_unique() -> None:
    ids = {new_concept_id() for _ in range(100)}
    assert len(ids) == 100


def test_new_edge_id_prefix() -> None:
    assert new_edge_id().startswith("E-")


def test_new_synthesis_id_prefix() -> None:
    assert new_synthesis_id().startswith("S-")


# ---------------------------------------------------------------------------
# db_path property
# ---------------------------------------------------------------------------


def test_db_path_is_accessible(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.db_path.exists()
    assert str(store.db_path).startswith(str(tmp_path))
