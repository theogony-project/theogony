"""The shipped retrieval defaults are values someone chose. Pin them.

A mutation test against a green baseline (1,696 passed) found that every one of
these could be changed to nonsense without a single failure: `top_k` to 7,
`k_seeds` to 1, `mmr_lambda` to 0.0, `ppr_iters` to 1, `name_anchors` to False.
Numbers nothing asserts are numbers nothing protects, and the damage had already
happened unnoticed — PHX-1069 raised the answer budget from 30 to 50 in the
library and the Cockpit kept serving 30, so the demo surface behaved like a
system whose documented recall was measured elsewhere (PHX-1079).

Each assertion carries the ticket that chose the value, so a future change is a
decision with a paper trail rather than a silent edit.
"""

from __future__ import annotations

import inspect

from theogony.mesh.eval.corpus_qa import evaluate
from theogony.mesh.retrieval.constellation import assemble_constellation
from theogony.mesh.retrieval.defaults import (
    DEFAULT_ANN_LIMIT,
    DEFAULT_K_SEEDS,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_NAME_ANCHORS,
    DEFAULT_PPR_ALPHA,
    DEFAULT_PPR_ITERS,
    DEFAULT_TOP_K,
    DEFAULT_TYPED_EDGE_BOOST,
)
from theogony.mesh.retrieval.retrieve import retrieve


def _default(fn: object, name: str) -> object:
    return inspect.signature(fn).parameters[name].default  # type: ignore[arg-type]


def test_the_constants_hold_their_measured_values() -> None:
    assert DEFAULT_TOP_K == 50, "PHX-1069: 65% at 30, 74% at 50, for 3.2 ms"
    assert DEFAULT_K_SEEDS == 5, (
        "PHX-1091: narrowed 8 -> 5 on a tune/test split, not on the sweep. The sweep "
        "alone says 1, and 1 loses 9 points of complete answers on held-out data"
    )
    assert DEFAULT_ANN_LIMIT == 64
    assert DEFAULT_MMR_LAMBDA == 0.6, "MESH_RETRIEVAL: diversified injection, not pure relevance"
    assert DEFAULT_PPR_ALPHA == 0.15
    assert DEFAULT_PPR_ITERS == 12, "PHX-1034 chose PPR as the default operator"
    assert DEFAULT_NAME_ANCHORS is True, "PHX-1068: +17 points of recall for 8 ms"
    assert DEFAULT_TYPED_EDGE_BOOST == 1.0, "PHX-1070: measured, deliberately off"


def test_retrieve_actually_uses_them() -> None:
    """A constant nothing reads is decoration."""
    assert _default(retrieve, "top_k") == DEFAULT_TOP_K
    assert _default(retrieve, "k_seeds") == DEFAULT_K_SEEDS
    assert _default(retrieve, "ann_limit") == DEFAULT_ANN_LIMIT
    assert _default(retrieve, "mmr_lambda") == DEFAULT_MMR_LAMBDA
    assert _default(retrieve, "ppr_alpha") == DEFAULT_PPR_ALPHA
    assert _default(retrieve, "ppr_iters") == DEFAULT_PPR_ITERS
    assert _default(retrieve, "name_anchors") is DEFAULT_NAME_ANCHORS
    assert _default(retrieve, "typed_edge_boost") == DEFAULT_TYPED_EDGE_BOOST


def test_every_surface_agrees_with_the_library() -> None:
    """The Cockpit sat at 30 for a day after the library moved to 50.

    Constellation assembly, the benchmark and the CLI all had their own literal.
    Whatever a user reaches the substrate through, they must get the configuration
    the published numbers were measured on.
    """
    assert _default(assemble_constellation, "top_k") == DEFAULT_TOP_K
    assert _default(evaluate, "top_k") == DEFAULT_TOP_K

    from theogony.cockpit.mesh_explorer import MeshExplorerService

    assert _default(MeshExplorerService.ask, "top_k") == DEFAULT_TOP_K
    assert _default(MeshExplorerService.ask, "k_seeds") == DEFAULT_K_SEEDS
    assert _default(MeshExplorerService.ask_streaming, "top_k") == DEFAULT_TOP_K
    assert _default(MeshExplorerService.ask_streaming, "k_seeds") == DEFAULT_K_SEEDS


def test_no_surface_hardcodes_the_budget_again() -> None:
    """Source-level guard: the literal is what let the Cockpit drift.

    Scanning the source is coarse, but it pins the exact thing that went wrong —
    a second copy of the number living somewhere the constant does not reach.
    """
    from pathlib import Path

    import theogony

    root = Path(theogony.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "defaults.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "top_k" in stripped and ("= 30" in stripped or "=30" in stripped):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {stripped}")
    assert not offenders, "top_k hardcoded to the pre-PHX-1069 budget:\n" + "\n".join(offenders)
