"""The vector index must return the nearest neighbours, not merely nearby ones.

An IVF-PQ index compresses each vector into 8 sub-quantisers. On the founding
mesh (5,002 nodes, 384-d) the indexed top-64 overlapped the *exact* top-64 by a
median of **22%** — minimum 9%. That is not an approximation of the answer, it is
a different answer, and it cost 2 points of gold-set recall and 3 questions
answered in full (PHX-1085).

`nprobes` does not help (22% at 20 probes and at 64), because the loss is the
quantiser rather than partition coverage. `refine_factor` re-ranks the candidates
against their stored vectors and recovers all of it, for 2.8 ms.

The defect was invisible because it only appears when you have something exact to
compare against — and every measurement was taken on the same indexed mesh.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode
from theogony.mesh.storage import nodes as nodes_module


def _node(runtime: MeshRuntime, vec: list[float], name: str) -> ConsolidatedNode:
    now = datetime.now(UTC)
    return ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=vec,
        frame_vector=[0.0] * runtime.frame_dim,
        description=name,
        tags=[name.lower()],
    )


def test_the_refine_factor_is_set_and_not_a_token_value() -> None:
    """50 is where median overlap reaches 100% and minimum reaches 94%.

    Pinned because a smaller value silently degrades the candidate set rather
    than failing: 10 gives 72% median / 45% minimum, and nothing would notice.
    """
    assert nodes_module._VECTOR_REFINE_FACTOR == 50


def test_search_returns_the_actual_nearest_neighbours(mesh_runtime: MeshRuntime) -> None:
    """On an unindexed table this is exact; the assertion is what refinement restores.

    The fixture is below `_MIN_ROWS_FOR_INDEX`, so no index is built and the
    search is a flat scan. What this pins is that the query path itself does not
    reorder or drop the true nearest neighbour — the refine call must be
    additive, not a filter.
    """
    dim = mesh_runtime.semantic_dim
    target = [1.0] + [0.0] * (dim - 1)
    near = [0.9] + [0.1] * (dim - 1)
    far = [0.0] * (dim - 1) + [1.0]

    wanted = _node(mesh_runtime, target, "Target")
    mesh_runtime.nodes.append_consolidated_many(
        [wanted, _node(mesh_runtime, near, "Near"), _node(mesh_runtime, far, "Far")]
    )

    hits = mesh_runtime.nodes.search_consolidated_by_vector(
        target, vector_column_name="semantic_vector", limit=2
    )
    assert [h.description for h in hits][:1] == ["Target"]
    assert len(hits) == 2


def test_refinement_is_skipped_rather_than_fatal_without_an_index(
    mesh_runtime: MeshRuntime,
) -> None:
    """A table with no vector index has nothing to refine; that must not raise."""
    dim = mesh_runtime.semantic_dim
    mesh_runtime.nodes.append_consolidated(_node(mesh_runtime, [1.0] + [0.0] * (dim - 1), "Only"))
    hits = mesh_runtime.nodes.search_consolidated_by_vector(
        [1.0] + [0.0] * (dim - 1), vector_column_name="semantic_vector", limit=4
    )
    assert [h.description for h in hits] == ["Only"]


def test_refine_factor_is_actually_applied_to_the_query(mesh_runtime: MeshRuntime) -> None:
    """The one assertion that would catch the regression.

    The tests above run on a fixture too small for an index, so they cannot
    reproduce the 22%-overlap defect — they only pin that the query path stays
    correct. This one watches the query object: if the `refine_factor` call is
    removed or its value drops, this fails, and nothing else in the suite would.
    """
    dim = mesh_runtime.semantic_dim
    mesh_runtime.nodes.append_consolidated(_node(mesh_runtime, [1.0] + [0.0] * (dim - 1), "Only"))

    seen: list[int] = []
    original = nodes_module.as_vector_query

    class _Spy:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def refine_factor(self, value: int) -> _Spy:
            seen.append(value)
            return _Spy(self._inner.refine_factor(value))  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> object:
            attr = getattr(self._inner, name)
            if name in {"metric", "limit"}:

                def wrapped(*args: object, **kwargs: object) -> _Spy:
                    return _Spy(attr(*args, **kwargs))

                return wrapped
            return attr

    nodes_module.as_vector_query = lambda q: _Spy(original(q))  # type: ignore[assignment]
    try:
        mesh_runtime.nodes.search_consolidated_by_vector(
            [1.0] + [0.0] * (dim - 1), vector_column_name="semantic_vector", limit=4
        )
    finally:
        nodes_module.as_vector_query = original  # type: ignore[assignment]

    assert seen == [nodes_module._VECTOR_REFINE_FACTOR], (
        "the vector search must ask for refinement; without it the IVF-PQ index "
        "returns a median of 22% of the true nearest neighbours"
    )
