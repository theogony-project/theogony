"""
Run-report layer (Plan §2.11).

Three Pydantic schemas (`IngestRunReport`, `QueryRunReport`,
`OneirosTickReport`) summarise what happened in each kind of run,
and the future Reviewer agent (PHX-0035) reads them to spot trends.

Gen 1 ships only the **write side**: schemas, atomic writer, the
self-verdict heuristics (`verdict.py`), and the four named anomaly
rules (`anomaly.py`). Cross-run analytics, dashboards, and automated
re-tuning all belong to the Reviewer agent and stay deferred.
"""

from theogony.reporting.anomaly import (
    cost_spike_anomaly,
    detect_ingest_anomalies,
    embedding_skew_anomaly,
    stage_slow_anomalies,
    wikidata_failure_burst_anomaly,
)
from theogony.reporting.models import (
    CitationQuality,
    ClusteringRunReport,
    DepthBandBreakdown,
    EmbeddingSummary,
    IngestRunReport,
    IngestStageReport,
    MnlmRunReport,
    MorpheusBreakdown,
    MultiHopBreakdown,
    NerSummary,
    OneirosTickReport,
    QualityFlags,
    QueryRunReport,
    RelationSummary,
    ResolutionSummary,
    RunReportBase,
    StoreSummary,
    SynthesisBreakdown,
    VitalityShift,
    new_run_id,
)
from theogony.reporting.verdict import (
    Verdict,
    ingest_verdict,
    oneiros_verdict,
    query_verdict,
)
from theogony.reporting.writer import RunReportWriter

__all__ = [
    "CitationQuality",
    "ClusteringRunReport",
    "DepthBandBreakdown",
    "EmbeddingSummary",
    "IngestRunReport",
    "IngestStageReport",
    "MnlmRunReport",
    "MultiHopBreakdown",
    "MorpheusBreakdown",
    "NerSummary",
    "OneirosTickReport",
    "QualityFlags",
    "QueryRunReport",
    "RelationSummary",
    "ResolutionSummary",
    "RunReportBase",
    "RunReportWriter",
    "StoreSummary",
    "SynthesisBreakdown",
    "Verdict",
    "VitalityShift",
    "cost_spike_anomaly",
    "detect_ingest_anomalies",
    "embedding_skew_anomaly",
    "ingest_verdict",
    "new_run_id",
    "oneiros_verdict",
    "query_verdict",
    "stage_slow_anomalies",
    "wikidata_failure_burst_anomaly",
]
