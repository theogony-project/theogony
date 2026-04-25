"""Mnemosyne experiment nodes (Living Demo W17)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from theogony.core.model import EpistemicStatus, KnowledgeNode, Layer, NodeType, SourceRef
from theogony.curiosity.mnemosyne_conductor_report import MetricDefinition


class MnemosyneExperiment(BaseModel):
    """Proposed experiment materialised as a chronicle node (read-only until accepted)."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(default_factory=lambda: f"MNEMO-EXP-{uuid.uuid4()}")
    metric_definition: MetricDefinition
    hypothesis: str
    regime_a: dict[str, str]
    regime_b: dict[str, str]
    status: Literal["proposed", "dry_run_completed", "accepted", "rejected"] = "proposed"
    winner: Literal["a", "b", "inconclusive"] | None = None
    auto_applied: bool = False
    rationale: str
    drafted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

    def to_knowledge_node(self) -> KnowledgeNode:
        """Persist as ``node_type=experiment`` in Ephemera (hypothesized)."""
        props: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "metric_id": self.metric_definition.metric_id,
            "metric_definition": self.metric_definition.model_dump(mode="json"),
            "hypothesis": self.hypothesis,
            "regime_a": dict(self.regime_a),
            "regime_b": dict(self.regime_b),
            "status": self.status,
            "winner": self.winner,
            "auto_applied": self.auto_applied,
            "rationale": self.rationale,
            "drafted_at": self.drafted_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
        return KnowledgeNode(
            id=self.experiment_id,
            node_type=NodeType.EXPERIMENT,
            label=f"Mnemosyne experiment: {self.metric_definition.name}",
            description=self.hypothesis,
            epistemic_status=EpistemicStatus.HYPOTHESIZED,
            layer=Layer.EPHEMERA,
            source_ref=SourceRef(
                source_type="mnemosyne",
                identifier=self.experiment_id,
            ),
            properties=props,
        )


__all__ = ["MnemosyneExperiment"]
