"""
Mesh-Native Language Model — locked Pydantic v2 DTOs.

These schemas are the binding contract between Kadmos's post-embedding
output and every MNLM-class agent (Nous, Oneiros, Kalypso, generic).

MeshInput (§4.1):  Kadmos → MNLM
MeshDelta (§4.2):  MNLM → substrate (via LFM-GAE decoder or discrete fallback)

See mesh_native_lm_brief.md §4 for the binding architecture decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

# ---------------------------------------------------------------------------
# Common vector types
# ---------------------------------------------------------------------------

Vector384 = Annotated[list[float], Field(min_length=384, max_length=384)]
Vector32 = Annotated[list[float], Field(min_length=32, max_length=32)]

# ---------------------------------------------------------------------------
# §4.1 — MeshInput: Kadmos-to-MNLM contract
# ---------------------------------------------------------------------------


class MeshInputNode(BaseModel):
    """One concept node in the input subgraph."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    embedding: Vector384
    activation_weight: float = Field(ge=0.0, le=1.0)
    node_type: Literal[
        "person",
        "place",
        "concept",
        "event",
        "claim",
        "work",
        "organization",
        "time",
        "quantity",
        "source",
        "finding",
        "experiment",
        "synthesis",
        "other",
    ] = "other"
    layer: Literal["ephemera", "mneme"] = "ephemera"
    revision_depth: int = Field(default=0, ge=0, le=64)
    source_anchor: str = Field(min_length=1, max_length=512)


class MeshInputEdge(BaseModel):
    """One typed, weighted edge in the input subgraph."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str = Field(pattern=r"^(EDGE|TMPEDGE)-[A-Za-z0-9_-]{6,}$")
    source_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    target_id: str = Field(pattern=r"^(AKA|TMP|UUID)-[A-Za-z0-9_-]{6,}$")
    relation_codebook_id: int = Field(ge=0, lt=512)
    nuance: Vector32
    weight: float = Field(ge=0.0, le=1.0)
    hebbian_strength: float = Field(default=0.0, ge=0.0)
    bidirectional: bool = False


class MeshInputContext(BaseModel):
    """Per-call context — determines role behaviour and recurrence budget."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["nous", "oneiros", "kalypso", "generic"]
    role_config_id: str | None = Field(default=None, max_length=128)
    intent_vector: Vector384 | None = None
    mutation_budget: int = Field(default=64, ge=1, le=1024)
    latent_step_cap: int = Field(default=16, ge=1, le=64)
    sa_interleave_K: int = Field(default=3, ge=0, le=16)
    sa_recurrence_top_k: int = Field(default=8, ge=1, le=64)
    sa_recurrence_max_hops: Literal[1, 2] = 1
    embedding_model_id: str = Field(min_length=1, max_length=128)


class MeshInput(BaseModel):
    """Kadmos → MNLM contract: a vector subgraph with context.

    schema_version is locked at "mnlm-input/1".
    graph integrity is enforced by the model_validator below.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-input/1"] = "mnlm-input/1"
    run_id: str = Field(min_length=1, max_length=64)
    call_id: str = Field(min_length=1, max_length=64)
    nodes: list[MeshInputNode] = Field(min_length=1, max_length=1024)
    edges: list[MeshInputEdge] = Field(default_factory=list, max_length=8192)
    active_node_ids: list[str] = Field(min_length=1, max_length=512)
    context: MeshInputContext
    aux: dict[str, Any] = Field(default_factory=dict)
    stamped_at: datetime

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> MeshInput:
        node_ids = {n.node_id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("nodes must have unique node_id values")
        if not set(self.active_node_ids).issubset(node_ids):
            raise ValueError("active_node_ids must be a subset of nodes[].node_id")
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError("each edge endpoint must exist in nodes")
        return self


# ---------------------------------------------------------------------------
# §4.2 — MutationPrimitives: the sealed union of graph operations
# ---------------------------------------------------------------------------


class _MutationBase(BaseModel):
    """Shared base for all mutation primitives."""

    model_config = ConfigDict(extra="forbid")
    op_id: str = Field(min_length=1, max_length=64)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale_embedding: Vector384 | None = None


class AddNode(_MutationBase):
    """Create a new concept node in the substrate."""

    kind: Literal["add_node"] = "add_node"
    proposed_node_id: str = Field(pattern=r"^AKA-[A-Za-z0-9_-]{6,}$")
    embedding: Vector384
    node_type: Literal[
        "person",
        "place",
        "concept",
        "event",
        "claim",
        "work",
        "organization",
        "time",
        "quantity",
        "source",
        "finding",
        "experiment",
        "synthesis",
        "other",
    ]
    layer: Literal["ephemera", "mneme"] = "ephemera"
    parent_node_ids: list[str] = Field(default_factory=list, max_length=64)
    label_for_provenance_only: str | None = Field(default=None, max_length=512)
    source_anchor: str = Field(min_length=1, max_length=512)


class AddEdge(_MutationBase):
    """Create a new typed, weighted edge between two nodes."""

    kind: Literal["add_edge"] = "add_edge"
    edge_id: str = Field(pattern=r"^EDGE-[A-Za-z0-9_-]{6,}$")
    source_id: str
    target_id: str
    relation_codebook_id: int = Field(ge=0, lt=512)
    nuance: Vector32
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    bidirectional: bool = False


class ReviseNode(_MutationBase):
    """Revise an existing node with a new embedding."""

    kind: Literal["revise_node"] = "revise_node"
    target_node_id: str
    supersedes_node_id: str
    new_embedding: Vector384
    revision_kind: Literal["update", "reinterpretation", "confidence_shift", "reweight"]
    new_layer: Literal["ephemera", "mneme"] | None = None


class MergeNodes(_MutationBase):
    """Merge multiple nodes into one surviving node."""

    kind: Literal["merge_nodes"] = "merge_nodes"
    surviving_id: str
    absorbed_ids: list[str] = Field(min_length=2, max_length=16)
    merged_embedding: Vector384


class SplitNode(_MutationBase):
    """Split one node into multiple child nodes."""

    kind: Literal["split_node"] = "split_node"
    original_id: str
    child_node_ids: list[str] = Field(min_length=2, max_length=16)
    child_embeddings: list[Vector384] = Field(min_length=2, max_length=16)


class Invalidate(_MutationBase):
    """Mark a node as invalid — supersession, not deletion."""

    kind: Literal["invalidate"] = "invalidate"
    target_node_id: str
    reason_embedding: Vector384
    finding_code: Literal[
        "contradiction", "unsupported", "stale", "schema_conflict", "structural_anomaly"
    ]


class EmitFinding(_MutationBase):
    """Emit an immune-system finding about subgraph health."""

    kind: Literal["emit_finding"] = "emit_finding"
    finding_node_id: str = Field(pattern=r"^FIND-[A-Za-z0-9_-]{6,}$")
    finding_type: Literal[
        "internal_contradiction",
        "unsupported_claim",
        "echo_chamber",
        "pheromone_autobahn",
        "confidence_inflation",
        "structural_anomaly",
        "other",
    ]
    target_node_ids: list[str] = Field(default_factory=list, max_length=64)
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"


class EmitActivationPacket(_MutationBase):
    """Emit a packet of energy deltas for Spreading Activation."""

    kind: Literal["emit_activation_packet"] = "emit_activation_packet"
    packet_id: str = Field(pattern=r"^PKT-[A-Za-z0-9_-]{6,}$")
    node_energy_deltas: list[tuple[str, float]] = Field(max_length=4096)


MutationPrimitive = Annotated[
    Annotated[AddNode, Tag("add_node")]
    | Annotated[AddEdge, Tag("add_edge")]
    | Annotated[ReviseNode, Tag("revise_node")]
    | Annotated[MergeNodes, Tag("merge_nodes")]
    | Annotated[SplitNode, Tag("split_node")]
    | Annotated[Invalidate, Tag("invalidate")]
    | Annotated[EmitFinding, Tag("emit_finding")]
    | Annotated[EmitActivationPacket, Tag("emit_activation_packet")],
    Discriminator(lambda v: v["kind"] if isinstance(v, dict) else v.kind),
]

# ---------------------------------------------------------------------------
# §4.2 — TrajectoryMetadata: LFM-specific output telemetry
# ---------------------------------------------------------------------------


class TrajectoryMetadata(BaseModel):
    """LFM-specific output telemetry. Read by the immune system; not by other agents."""

    model_config = ConfigDict(extra="forbid")

    trajectory_entropy: float = Field(ge=0.0)
    integration_steps: int = Field(ge=1, le=128)
    final_basin_id: str = Field(min_length=1, max_length=64)
    bifurcations_observed: int = Field(default=0, ge=0)
    max_curvature: float = Field(default=0.0, ge=0.0)
    converged: bool


# ---------------------------------------------------------------------------
# §4.2 — MeshDelta: MNLM-to-substrate contract
# ---------------------------------------------------------------------------


class MeshDelta(BaseModel):
    """MNLM → substrate contract: a bounded structural delta.

    schema_version is locked at "mnlm-output/1".
    Produced by the LFM-GAE decoder (or discrete-mutation fallback).
    Contains primitives + trajectory telemetry + provenance.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["mnlm-output/1"] = "mnlm-output/1"
    run_id: str
    call_id: str
    model_id: str = Field(min_length=1, max_length=128)
    produced_at: datetime
    primitives: list[MutationPrimitive] = Field(default_factory=list, max_length=4096)
    trajectory: TrajectoryMetadata
    latent_steps_used: int = Field(ge=0, le=64)
    sa_cycles_used: int = Field(ge=0, le=64)
    halted_reason: Literal[
        "stable",
        "budget_exhausted",
        "step_cap",
        "lfm_converged",
        "lfm_failed_convergence",
        "decoder_constraint_violation",
        "error",
    ]
    provenance_hash: str = Field(min_length=16, max_length=128)
    failure_reason_code: str | None = None

    @model_validator(mode="after")
    def validate_provenance_hash_length(self) -> MeshDelta:
        # SHA-256 hex is 64 chars; ensure minimum 16
        if len(self.provenance_hash) < 16:
            raise ValueError("provenance_hash must be at least 16 characters")
        return self
