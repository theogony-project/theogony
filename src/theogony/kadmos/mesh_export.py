"""
Kadmos → MNLM MeshInput export (§7 of mesh_native_lm_brief.md).

Converts an AnnotatedReading (Kadmos cognitive-reading session output) into
a MeshInput (the MNLM's input contract), using the existing embedder to
produce node embeddings and a codebook-clustering step for edge relation types.

This is a post-embedding pass — it does not call the LLM again. It reads
already-produced Kadmos artifacts and emits MeshInput-shaped exports.

See mesh_native_lm_brief.md §7 for the binding amendment contract.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from theogony.agents.mnlm.dto import (
    MeshInput,
    MeshInputContext,
    MeshInputEdge,
    MeshInputNode,
)
from theogony.config.logging import get_logger
from theogony.kadmos.model import (
    ActiveConcept,
    ActiveEdge,
    AnnotatedReading,
    SynthesisNode,
)

if TYPE_CHECKING:
    from theogony.extraction.embedding import EmbeddingProvider

log = get_logger("kadmos.mesh_export")

# The 512-entry relation codebook is bootstrapped from Kadmos's emergent
# relation clusters. For the PoC, we use a deterministic hash-based mapping
# from relation description strings to codebook indices.
# A proper clustering step will be added in §8 production training.
_RELATION_CODEBOOK_SIZE = 512


def _relation_description_to_codebook_id(description: str) -> int:
    """Map a relation description string to a deterministic codebook entry.

    For the PoC: SHA-256 hash of the description mod CODEBOOK_SIZE.
    In production: cluster connection-description embeddings against the
    §3.5 codebook at the end of the embedding pass.

    Use hash('relation/codebook/' + description) for a deterministic,
    well-distributed mapping.
    """
    h = hashlib.sha256(f"relation/codebook/{description}".encode())
    return int(h.hexdigest(), 16) % _RELATION_CODEBOOK_SIZE


def _relation_description_to_nuance(
    description: str,
    codebook_id: int,
) -> list[float]:
    """Project the residual (description minus codebook centroid) to 32 dims.

    For the PoC: use a deterministic 32-dimensional hash of the description.
    In production: cluster the connection-description embedding against the
    codebook centroid and project the residual to 32 dimensions via PCA.
    """
    h = hashlib.sha256(f"nuance/{description}".encode())
    seed_bytes = h.digest()
    # Convert first 32 bytes to floats in [-0.1, 0.1]
    out = []
    for i in range(32):
        byte_val = seed_bytes[i % len(seed_bytes)]
        out.append((byte_val / 255.0 - 0.5) * 0.2)
    return out


def _compute_node_id(concept: ActiveConcept | SynthesisNode) -> str:
    """Compute a deterministic node ID for a Kadmos concept/synthesis.

    Uses a SHA-256 hash of the concept label + session info, producing
    a stable AKA-prefixed ID.
    """
    raw = f"kadmos/{concept.label}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"AKA-kadmos{h}"


def _compute_edge_id(source_id: str, target_id: str, description: str) -> str:
    """Compute a deterministic edge ID for a Kadmos edge."""
    raw = f"{source_id}->{target_id}:{description}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"EDGE-kadmos{h}"


async def _concept_to_mesh_node(
    concept: ActiveConcept,
    concept_node_id: str,
    source_url: str,
    embedder: EmbeddingProvider,
) -> MeshInputNode:
    """Convert an ActiveConcept into a MeshInputNode.

    The embedding is computed by the embedder on the concept's label.
    Activation flows directly. The source_anchor encodes provenance.
    """
    # Embed the concept label + description
    text_to_embed = concept.label
    if concept.description:
        text_to_embed += ": " + concept.description
    emb = list(await embedder.embed(text_to_embed))
    emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))

    source_passage = concept.source_passage or ""
    anchor = f"{source_url}#step-{concept.step_created}:{source_passage[:200]}"

    return MeshInputNode(
        node_id=concept_node_id,
        embedding=emb_vec,
        activation_weight=concept.activation,
        node_type="concept",
        layer="ephemera",
        revision_depth=len(concept.revision_history),
        source_anchor=anchor[:512],
    )


async def _synthesis_to_mesh_node(
    synthesis: SynthesisNode,
    synthesis_node_id: str,
    source_url: str,
    embedder: EmbeddingProvider,
) -> MeshInputNode:
    """Convert a SynthesisNode into a MeshInputNode with node_type='synthesis'."""
    text_to_embed = f"{synthesis.label}: {synthesis.description}"
    emb = list(await embedder.embed(text_to_embed))

    emb_vec = emb[:384] if len(emb) >= 384 else emb + [0.0] * (384 - len(emb))

    anchor = f"{source_url}#synthesis-{synthesis.synthesis_level}:{synthesis.label[:200]}"

    return MeshInputNode(
        node_id=synthesis_node_id,
        embedding=emb_vec,
        activation_weight=synthesis.confidence,
        node_type="synthesis",
        layer="ephemera",
        revision_depth=0,
        source_anchor=anchor[:512],
    )


def _make_concept_to_concept_edge(
    edge: ActiveEdge,
    source_node_id: str,
    target_node_id: str,
) -> MeshInputEdge:
    """Convert an ActiveEdge into a MeshInputEdge, with codebook mapping."""
    cid = _relation_description_to_codebook_id(edge.relation_description)
    nuance = _relation_description_to_nuance(edge.relation_description, cid)
    eid = _compute_edge_id(source_node_id, target_node_id, edge.relation_description)

    return MeshInputEdge(
        edge_id=eid,
        source_id=source_node_id,
        target_id=target_node_id,
        relation_codebook_id=cid,
        nuance=nuance,
        weight=edge.weight,
        hebbian_strength=0.0,
        bidirectional=False,
    )


def _make_synthesis_abstraction_edge(
    synthesis_node_id: str,
    basis_node_id: str,
) -> MeshInputEdge:
    """Create an 'abstraction_of' edge from a synthesis to its basis concept.

    Relation codebook id 1 is reserved for abstraction_of in the bootstrap
    codebook.
    """
    nuance = [0.0] * 32
    raw = f"{synthesis_node_id}-abstracts-{basis_node_id}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    eid = f"EDGE-kadmos{h}"

    return MeshInputEdge(
        edge_id=eid,
        source_id=synthesis_node_id,
        target_id=basis_node_id,
        relation_codebook_id=1,  # abstraction_of
        nuance=nuance,
        weight=0.8,
        hebbian_strength=0.0,
        bidirectional=False,
    )


async def annotated_reading_to_mesh_input(
    annotated: AnnotatedReading,
    embedder: EmbeddingProvider,
    role: str = "generic",
    run_id: str | None = None,
) -> MeshInput:
    """Convert an AnnotatedReading into a MeshInput for MNLM ingestion.

    Parameters
    ----------
    annotated:
        The Kadmos session record to convert.
    embedder:
        The embedding provider used to compute node embeddings.
        (Must produce vectors of dimensionality >= 384.)
    role:
        The MNLM role for the MeshInputContext. Defaults to "generic".
    run_id:
        Optional explicit run ID. If None, a new one is minted from the
        session ID and source URL.

    Returns
    -------
    A fully validated MeshInput instance ready for MNLM ingestion.

    Notes
    -----
    - The relation_codebook_id is computed deterministically from the
      relation description via hash (§7 PoC implementation). In production,
      a proper clustering step is required.
    - Nodes are deduplicated by label across concepts and syntheses.
    """
    log.info(
        "converting AnnotatedReading session=%s to MeshInput (%d concepts, %d syntheses)",
        annotated.session_id,
        len(annotated.final_active_concepts),
        len(annotated.final_syntheses),
    )

    effective_run_id = run_id or f"kadmos-poc-{annotated.session_id[:16]}"
    call_id = f"mesh-export-{annotated.session_id[:12]}"

    # Build node lookup: {concept_id in Kadmos → MeshInputNode}
    node_id_map: dict[str, str] = {}
    mesh_nodes: dict[str, MeshInputNode] = {}
    active_node_ids: list[str] = []
    mesh_edges: list[MeshInputEdge] = []

    source_url = annotated.source_url

    # Convert concepts
    for concept in annotated.final_active_concepts:
        cid = _compute_node_id(concept)
        node_id_map[concept.id] = cid
        node = await _concept_to_mesh_node(concept, cid, source_url, embedder)
        mesh_nodes[cid] = node
        active_node_ids.append(cid)

    # Convert syntheses
    for synthesis in annotated.final_syntheses:
        sid = _compute_node_id(synthesis)
        # Map original IDs
        for orig_id in synthesis.basis_concept_ids:
            node_id_map[orig_id] = node_id_map.get(orig_id, orig_id)
        node = await _synthesis_to_mesh_node(synthesis, sid, source_url, embedder)
        mesh_nodes[sid] = node
        active_node_ids.append(sid)

        # Create abstraction_of edges from synthesis to its basis concepts
        for basis_orig_id in synthesis.basis_concept_ids:
            basis_node_id = node_id_map.get(basis_orig_id)
            if basis_node_id and basis_node_id in mesh_nodes:
                edge = _make_synthesis_abstraction_edge(sid, basis_node_id)
                mesh_edges.append(edge)

    # Collect edges from reading steps
    seen_edge_ids: set[str] = set()
    for step in annotated.steps:
        for edge_id in step.edges_added:
            if edge_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge_id)

    # Reconstruct edges from the steps' active_edges
    # (Kadmos stores edges only in the live ReadingState, not in AnnotatedReading
    # final_active_edges. We reconstruct from the reading step LLM outputs.)
    for step in annotated.steps:
        for conn in step.llm_output.new_connections:
            source_label = conn.source_label or ""
            target_label = conn.target_label or ""
            relation_desc = conn.relation_description or ""

            # Find mesh node IDs by matching labels
            source_cid = None
            target_cid = None
            for kadmos_id, mesh_id in node_id_map.items():
                # Check concepts
                for c in annotated.final_active_concepts:
                    if c.id == kadmos_id and c.label == source_label:
                        source_cid = mesh_id
                    if c.id == kadmos_id and c.label == target_label:
                        target_cid = mesh_id

            if source_cid and target_cid and source_cid != target_cid:
                # Convert the LLM edge
                active_edge = ActiveEdge(
                    id=f"reconstructed-{step.step_index}-{source_label}->{target_label}",
                    source_id=source_cid,
                    target_id=target_cid,
                    source_label=source_label,
                    target_label=target_label,
                    relation_description=relation_desc,
                    weight=conn.weight,
                    step_created=step.step_index,
                )
                mesh_edge = _make_concept_to_concept_edge(
                    active_edge,
                    source_cid,
                    target_cid,
                )
                if mesh_edge.edge_id not in seen_edge_ids:
                    seen_edge_ids.add(mesh_edge.edge_id)
                    mesh_edges.append(mesh_edge)

    # Collect open tensions into aux
    aux: dict[str, Any] = {}
    all_tensions: list[str] = []
    for step in annotated.steps:
        all_tensions.extend(step.llm_output.open_tensions)
    if all_tensions:
        aux["kadmos_open_tensions"] = all_tensions

    context = MeshInputContext(
        role=role,  # type: ignore[arg-type]
        embedding_model_id=embedder.model_id if hasattr(embedder, "model_id") else "unknown",
    )

    now = datetime.now(UTC)

    return MeshInput(
        schema_version="mnlm-input/1",
        run_id=effective_run_id[:64],
        call_id=call_id[:64],
        nodes=list(mesh_nodes.values()),
        edges=mesh_edges,
        active_node_ids=active_node_ids,
        context=context,
        aux=aux,
        stamped_at=now,
    )
