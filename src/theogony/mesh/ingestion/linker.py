"""Three-signal eager linker for doctrine-conformant Tier-1 identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ulid import ULID

from theogony.mesh.ingestion.concept_resolver import ConceptResolver, _normalize
from theogony.mesh.schemas import ConsolidatedNode, Edge, QIDTag
from theogony.mesh.storage.edges import EdgeStore
from theogony.mesh.storage.nodes import MeshNodeStore


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if a is None or b is None or not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


@dataclass(frozen=True)
class LinkDecision:
    node: ConsolidatedNode
    signal: str
    is_new: bool
    score: float


class EagerLinker:
    """Q-ID, description+context, then tag+context matching."""

    DESCRIPTION_CANDIDATE_LIMIT = 24
    TAG_CANDIDATE_LIMIT = 48

    # Sanity floor on the Q-ID path. Deliberately far below the description
    # threshold (0.72): a matching Q-ID is strong evidence and must keep bridging
    # entities whose *names* differ — Venus/Aphrodite, Jove/Zeus, cross-language
    # variants. This only rejects a Q-ID that lands on something semantically
    # unrelated, which is what a hallucinated identifier looks like.
    QID_PLAUSIBILITY_FLOOR = 0.35

    def __init__(
        self,
        node_store: MeshNodeStore,
        edge_store: EdgeStore,
        *,
        semantic_dim: int,
        frame_dim: int,
        registry: ConceptResolver | None = None,
    ) -> None:
        self._store = node_store
        self._edge_store = edge_store
        self._semantic_dim = semantic_dim
        self._frame_dim = frame_dim
        self._registry = registry or ConceptResolver(node_store)
        self._adjacency: dict[str, set[str]] = {}
        self._adjacency_primed = False

    def _prime_adjacency(self) -> None:
        """Load the whole adjacency index once, keeping edges learned this run."""
        if self._adjacency_primed:
            return
        self._adjacency_primed = True
        for node_id, neighbours in self._edge_store.adjacency_index().items():
            # Union rather than overwrite: edges appended earlier in this run are
            # already in memory and may not be flushed to storage yet.
            self._adjacency.setdefault(node_id, set()).update(neighbours)

    def remember_edge(self, edge: Edge) -> None:
        source_id = str(edge.source_id)
        target_id = str(edge.target_id)
        self._adjacency.setdefault(source_id, set()).add(target_id)
        self._adjacency.setdefault(target_id, set()).add(source_id)

    def _context_score(self, candidate_id: str, context_node_ids: set[str]) -> float:
        if not context_node_ids:
            return 0.0
        neighbours = self._adjacency.get(candidate_id)
        if neighbours is None:
            # One full-table scan builds every node's neighbours; the per-node
            # query costs two filtered scans of the same table (~597 ms on the
            # founding mesh) and this is called for up to 24 ANN candidates per
            # concept. Fetching the whole index once is cheaper than asking about
            # two nodes, and it is what made ingestion collapse as a mesh grew
            # (PHX-1047 — the cost is here, in context scoring, not in the ANN).
            self._prime_adjacency()
            neighbours = self._adjacency.get(candidate_id, set())
        if not neighbours:
            return 0.0
        overlap = len(neighbours & context_node_ids)
        return overlap / max(1, len(context_node_ids))

    def _best_description_match(
        self,
        *,
        label: str,
        description_vector: list[float] | None,
        tags: list[str],
        context_node_ids: set[str],
    ) -> tuple[ConsolidatedNode | None, float]:
        if description_vector is None:
            return None, 0.0
        best_node: ConsolidatedNode | None = None
        best_score = 0.0
        tag_set = {tag.lower().strip() for tag in tags}
        norm_label = _normalize(label)

        for candidate in self._registry.find_by_description_vector(
            description_vector,
            limit=self.DESCRIPTION_CANDIDATE_LIMIT,
        ):
            if candidate.is_source_anchor:
                continue
            desc_score = _cosine_similarity(description_vector, candidate.description_vector)
            if desc_score <= 0.0:
                continue
            context_score = self._context_score(str(candidate.id), context_node_ids)
            shared_tags = tag_set & {tag.lower().strip() for tag in candidate.tags}
            tag_overlap = len(shared_tags)
            tag_score = tag_overlap / max(1, len(tag_set)) if tag_set else 0.0
            known_labels = self._registry.known_labels(str(candidate.id))
            label_score = 1.0 if norm_label in known_labels else 0.0
            label_tokens = set(norm_label.split())
            naming_tags = {
                tag for tag in shared_tags if label_tokens & set(_normalize(tag).split())
            }
            if not naming_tags and label_score == 0.0:
                # PHX-1051 doctrine guard (v2): pure vector similarity is not "clear
                # evidence" of identity. Semantically generic, high-degree nodes
                # (measured live: the work-node itself) sit close to *every*
                # in-domain description AND collect the context bonus through
                # their degree — without lexical corroboration (shared tag or
                # known label) they absorb entities: Venus, Dione, and Zeus all
                # merged into "An ancient Greek epic poem …", leaving
                # daughter_of self-loops on the hub. And category tags are not
                # corroboration either (v2, measured live: shared 'Titaness'
                # routed Dione's Q-ID onto Tethys, shared generic tags routed
                # Aphrodite onto Apollo's neighborhood) — the shared tag must
                # NAME the entity, i.e. token-overlap the incoming label, or
                # the label must already be a known alias. No naming, no merge.
                continue
            score = desc_score + (0.20 * context_score) + (0.08 * tag_score) + (0.05 * label_score)
            if score > best_score:
                best_node = candidate
                best_score = score

        return best_node, best_score

    def _best_tag_match(
        self,
        *,
        label: str,
        tags: list[str],
        context_node_ids: set[str],
    ) -> tuple[ConsolidatedNode | None, float]:
        best_node: ConsolidatedNode | None = None
        best_score = 0.0
        tag_set = {tag.lower().strip() for tag in tags}

        norm_label = _normalize(label)
        label_tokens = set(norm_label.split())
        for candidate in self._registry.find_by_labels(
            [label, *tags],
            limit=self.TAG_CANDIDATE_LIMIT,
        ):
            if candidate.is_source_anchor:
                continue
            candidate_tags = {tag.lower().strip() for tag in candidate.tags}
            shared = tag_set & candidate_tags
            overlap = len(shared)
            if overlap <= 0:
                continue
            # PHX-1051 v2: category tags ('Titaness', 'person') are not identity
            # evidence — a shared tag corroborates only when it NAMES the
            # entity, or the label itself is a known alias of the candidate.
            names_entity = any(label_tokens & set(_normalize(tag).split()) for tag in shared)
            if not names_entity and norm_label not in self._registry.known_labels(
                str(candidate.id)
            ):
                continue
            tag_score = overlap / max(len(tag_set), len(candidate_tags), 1)
            context_score = self._context_score(str(candidate.id), context_node_ids)
            token_score = self._registry.score_token_overlap(label, candidate)
            score = tag_score + (0.25 * context_score) + (0.15 * token_score)
            if score > best_score:
                best_node = candidate
                best_score = score

        return best_node, best_score

    def _create_candidate(
        self,
        *,
        label: str,
        description: str,
        tags: list[str],
        qids: list[QIDTag],
        semantic_vector: list[float],
        frame_vector: list[float],
        description_vector: list[float] | None,
    ) -> ConsolidatedNode:
        now = datetime.now(UTC)
        node = ConsolidatedNode(
            id=ULID(),
            born_at=now,
            last_fired_at=now,
            consolidation_tier=1,
            is_candidate=True,
            semantic_vector=semantic_vector,
            frame_vector=frame_vector,
            description=description or label,
            description_vector=description_vector,
            tags=tags,
            qids=qids,
        )
        self._store.append_consolidated(node)
        self._registry.remember(node, aliases=[label, description], qids=qids)
        return node

    def _qid_is_plausible(
        self,
        node: ConsolidatedNode,
        *,
        label: str,
        description_vector: list[float] | None,
        semantic_vector: list[float] | None,
    ) -> bool:
        """Is this Q-ID match defensible, or does it look hallucinated?

        Either signal suffices, because each covers the other's blind spot:

        * **Naming** — the incoming label is a known alias of the node, or shares a
          token with its description or tags. This carries the cases where vectors
          are weak or meaningless: the bulk seed stores the entity *name* as the
          description and hash-projection embedders make semantically identical
          entities near-orthogonal.
        * **Semantics** — cosine over whatever vector pairs both sides actually
          have. This carries the cases the Q-ID path exists for, where the names
          deliberately differ: Venus/Aphrodite, Jove/Zeus, cross-language variants.

        A Q-ID is rejected only when the vectors *can* be compared, disagree, and
        nothing in the naming corroborates — which is what a hallucinated
        identifier looks like. When neither signal has anything to work with, the
        Q-ID stands: the guard does not invent a verdict from absent evidence.
        """
        norm_label = _normalize(label)
        if norm_label:
            if norm_label in self._registry.known_labels(str(node.id)):
                return True
            label_tokens = set(norm_label.split())
            node_tokens = set(_normalize(node.description or "").split())
            for tag in node.tags:
                node_tokens |= set(_normalize(tag).split())
            if label_tokens & node_tokens:
                return True

        def _has_signal(vector: list[float] | None) -> bool:
            return bool(vector) and any(value != 0.0 for value in vector or [])

        pairs = (
            (description_vector, node.description_vector),
            (description_vector, node.semantic_vector),
            (semantic_vector, node.semantic_vector),
        )
        comparable = [(a, b) for a, b in pairs if _has_signal(a) and _has_signal(b)]
        if not comparable:
            # Absent vectors are not evidence of a mismatch. Cosine 0.0 means both
            # "unrelated" and "nothing to compare" — conflating them would reject
            # every vectorless caller.
            return True
        return max(_cosine_similarity(a, b) for a, b in comparable) >= self.QID_PLAUSIBILITY_FLOOR

    def link_reference(
        self,
        *,
        label: str,
        description: str,
        tags: list[str],
        qids: list[QIDTag],
        semantic_vector: list[float],
        frame_vector: list[float],
        description_vector: list[float] | None,
        context_node_ids: set[str] | None = None,
        qids_are_authoritative: bool = True,
    ) -> LinkDecision:
        """Resolve a reference to a node, creating one if nothing matches.

        ``qids_are_authoritative=False`` says the caller got these Q-IDs from a
        language model rather than an authority. They are still used to *look up*
        an existing node — a match against a Q-ID the mesh already holds from the
        wikidata5m seed is exactly what the tier-4 path is for, and a made-up
        identifier simply finds nothing. What they must not do is get *written*:
        storing them turns a guess into durable, Q-ID-addressable identity.

        That distinction is not theoretical. Of 130 model-asserted Q-IDs found in
        the founding mesh after the Theogony full read, 3 were plausible, 122
        pointed at an unrelated entity and 5 did not exist — Gaia carried the
        Q-ID of analytical chemistry, Cronus that of Anubis, Hera that of Willy
        Brandt. Across all 1,210 paragraphs the tier-4 path fired zero times, so
        refusing to persist them costs no merges that were happening (PHX-1063).
        """
        context_ids = set(context_node_ids or set())
        # Lookup uses every Q-ID offered; persistence uses only trusted ones.
        persist_qids = qids if qids_are_authoritative else []

        for qid_tag in qids:
            node = self._registry.get_by_qid(qid_tag.qid)
            if node is None:
                continue
            if not self._qid_is_plausible(
                node,
                label=label,
                description_vector=description_vector,
                semantic_vector=semantic_vector,
            ):
                # The Q-ID is the only signal here and it is asserted by an LLM with
                # no corroboration — the strongest remaining identity-corruption
                # vector after the PHX-1051 naming guard, and a durable one, since
                # merge_identity_evidence writes the merged Q-ID back to the store.
                # A hallucinated identifier looks exactly like this: it resolves to a
                # real node that has nothing semantically to do with the reference.
                # Fall through to the corroborated signals instead of merging.
                continue
            persisted = self._store.merge_identity_evidence(
                str(node.id), qids=persist_qids, node=node, aliases=[label]
            )
            node = persisted or node
            self._registry.remember(node, aliases=[label, description], qids=persist_qids)
            return LinkDecision(node=node, signal="qid", is_new=False, score=1.0)

        matched, score = self._best_description_match(
            label=label,
            description_vector=description_vector,
            tags=tags,
            context_node_ids=context_ids,
        )
        if matched is not None and score >= 0.72:
            # The alias goes to the store as well as the registry now: a merge
            # that learns "this passage's 'the Earth-Shaker' is the node we call
            # Poseidon" used to teach the substrate nothing, because the registry
            # is in-memory and dies with the run (PHX-1071).
            persisted = self._store.merge_identity_evidence(
                str(matched.id), qids=persist_qids, node=matched, aliases=[label]
            )
            matched = persisted or matched
            self._registry.remember(matched, aliases=[label, description], qids=persist_qids)
            return LinkDecision(node=matched, signal="description", is_new=False, score=score)

        matched, score = self._best_tag_match(
            label=label,
            tags=tags,
            context_node_ids=context_ids,
        )
        if matched is not None and score >= 0.55:
            persisted = self._store.merge_identity_evidence(
                str(matched.id), qids=persist_qids, node=matched, aliases=[label]
            )
            matched = persisted or matched
            self._registry.remember(matched, aliases=[label, description], qids=persist_qids)
            return LinkDecision(node=matched, signal="tag", is_new=False, score=score)

        node = self._create_candidate(
            label=label,
            description=description,
            tags=tags,
            qids=persist_qids,
            semantic_vector=semantic_vector,
            frame_vector=frame_vector,
            description_vector=description_vector,
        )
        return LinkDecision(node=node, signal="emergent", is_new=True, score=0.0)
