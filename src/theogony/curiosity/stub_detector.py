"""Per-query stub detection (PHX-0058 Phase 1 / W3)."""

from __future__ import annotations

from theogony.config.settings import StubThresholds
from theogony.core.model import Constellation
from theogony.reporting.models import StubVerdict
from theogony.retrieval.synthesize import Answer


class StubDetector:
    """Compute a :class:`~theogony.reporting.models.StubVerdict` from inputs.

    Pure: no store access, no LLM call, no I/O.
    """

    def __init__(self, thresholds: StubThresholds) -> None:
        self._t = thresholds

    def detect(
        self,
        *,
        query: str,  # noqa: ARG002 — reserved for Phase 2 NER / logging
        constellation: Constellation,
        answer: Answer,
        named_entities_in_query: list[str] | None = None,
    ) -> StubVerdict:
        node_count = len(constellation.nodes)
        low_node_count = node_count < self._t.min_node_count

        edges = len(constellation.edges)
        edge_density = edges / max(1, node_count)
        low_edge_density = edge_density < self._t.min_edge_density

        if constellation.nodes:
            mean_vitality = sum(n.confidence for n in constellation.nodes) / node_count
        else:
            mean_vitality = 0.0
        low_vitality = mean_vitality < self._t.min_mean_vitality

        source_types = {n.source_ref.source_type for n in constellation.nodes}
        distinct_source_types = len(source_types)
        narrow_source_diversity = distinct_source_types < self._t.min_distinct_source_types

        mean_confidence = mean_vitality
        low_confidence_aggregate = mean_confidence < self._t.min_mean_confidence

        if named_entities_in_query:
            cited_set = set(answer.cited_node_ids)
            label_set = {n.label for n in constellation.nodes}
            resolved = sum(
                1 for ent in named_entities_in_query if ent in cited_set or ent in label_set
            )
            ratio = resolved / max(1, len(named_entities_in_query))
        else:
            ratio = 1.0
        poor_named_entity_coverage = ratio < self._t.min_named_entities_resolved_ratio

        fired = int(
            low_node_count
            + low_edge_density
            + low_vitality
            + narrow_source_diversity
            + low_confidence_aggregate
            + poor_named_entity_coverage
        )
        strength = fired / 6.0

        return StubVerdict(
            low_node_count=low_node_count,
            low_edge_density=low_edge_density,
            low_vitality=low_vitality,
            narrow_source_diversity=narrow_source_diversity,
            low_confidence_aggregate=low_confidence_aggregate,
            poor_named_entity_coverage=poor_named_entity_coverage,
            node_count=node_count,
            edge_density=edge_density,
            mean_vitality=mean_vitality,
            distinct_source_types=distinct_source_types,
            mean_confidence=mean_confidence,
            named_entities_resolved_ratio=ratio,
            stub_signal_strength=strength,
            is_stub=strength > 0.0,
        )


__all__ = ["StubDetector"]
