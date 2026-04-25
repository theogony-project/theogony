"""Mnemosyne experiment nodes (W17)."""

from __future__ import annotations

from theogony.core.model import EpistemicStatus, Layer, NodeType
from theogony.curiosity.mnemosyne_conductor_report import MetricDefinition
from theogony.curiosity.mnemosyne_experiment import MnemosyneExperiment


def test_mnemosyne_experiment_to_knowledge_node_uses_experiment_type() -> None:
    m = MetricDefinition(
        metric_id="pool_clearance_ratio",
        name="Pool clearance ratio",
        rationale="r",
        numerator="a",
        denominator="b",
        desired_direction="increase",
        source="fixture",
    )
    exp = MnemosyneExperiment(
        experiment_id="MNEMO-PROPOSAL-test-1",
        metric_definition=m,
        hypothesis="h",
        regime_a={"k": "a"},
        regime_b={"k": "b"},
        rationale="because",
    )
    node = exp.to_knowledge_node()
    assert node.node_type == NodeType.EXPERIMENT


def test_experiment_node_properties_include_metric_and_regimes() -> None:
    m = MetricDefinition(
        metric_id="unresolved_finding_ratio",
        name="Unresolved finding ratio",
        rationale="r",
        numerator="u",
        denominator="t",
        desired_direction="decrease",
        source="fixture",
    )
    exp = MnemosyneExperiment(
        experiment_id="MNEMO-PROPOSAL-test-2",
        metric_definition=m,
        hypothesis="hyp",
        regime_a={"manual_frequency": "once"},
        regime_b={"manual_frequency": "twice"},
        rationale="rationale text",
    )
    node = exp.to_knowledge_node()
    props = node.properties or {}
    assert props["metric_id"] == "unresolved_finding_ratio"
    assert props["regime_a"] == {"manual_frequency": "once"}
    assert props["regime_b"] == {"manual_frequency": "twice"}
    assert props["hypothesis"] == "hyp"
    assert "metric_definition" in props


def test_experiment_node_is_hypothesized_ephemera() -> None:
    m = MetricDefinition(
        metric_id="red_team_failure_count",
        name="Red team failure count",
        rationale="r",
        numerator="f",
        denominator="p",
        desired_direction="decrease",
        source="fixture",
    )
    exp = MnemosyneExperiment(
        experiment_id="MNEMO-PROPOSAL-test-3",
        metric_definition=m,
        hypothesis="h",
        regime_a={},
        regime_b={},
        rationale="r",
    )
    node = exp.to_knowledge_node()
    assert node.epistemic_status == EpistemicStatus.HYPOTHESIZED
    assert node.layer == Layer.EPHEMERA
