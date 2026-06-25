"""Mesh retrieval (Step S3) — diversified injection + Spreading Activation.

The production retrieval path over the MESH substrate:

- :mod:`propagation` — the Spreading-Activation operators (PPR default; raw / degnorm;
  relation-conditioned masked hop). Operator choice is empirically grounded in PHX-1034.
- :mod:`diversified` — Maximum Marginal Relevance seed selection + weight-class
  stratification (MESH_RETRIEVAL §"Diversified injection").
- :mod:`frame_routing` — masked-SpMV frame routing (MESH_RETRIEVAL §"Frame routing").
- :mod:`constellation` — assembly of the activated subgraph into a structured working set.
- :func:`retrieve.retrieve` — the single-query orchestrator: query vector -> Constellation.

Per MESH_MIGRATION_PLAN.md §"Step S3". No three-factor RL yet (feedback hard-coded
off); no multi-agent routing; no Cockpit/MCP integration (those are S4).
"""

from theogony.mesh.retrieval.constellation import (
    Constellation,
    ConstellationEdge,
    ConstellationNode,
    assemble_constellation,
)
from theogony.mesh.retrieval.propagation import Propagator
from theogony.mesh.retrieval.retrieve import RetrievalResult, retrieve

__all__ = [
    "Constellation",
    "ConstellationEdge",
    "ConstellationNode",
    "Propagator",
    "RetrievalResult",
    "assemble_constellation",
    "retrieve",
]
