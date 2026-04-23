"""Mnemosyne meta-query classifier (PHX-0071 Phase 1 / W5)."""

from __future__ import annotations

import re

from theogony.agents.llm import LLMProvider
from theogony.agents.mnemosyne_llm_fallback import MnemosyneLLMFallback
from theogony.config.settings import MnemosyneSettings, Settings
from theogony.core.model import Constellation
from theogony.reporting.models import MetaClassification, MetaClassificationVerdict
from theogony.retrieval.synthesize import Answer

_META_KEYWORDS_HIGH = frozenset(
    {
        "chronik",
        "chronicle",
        "pantheon",
        "theogony",
        "embedding",
        "vector dimension",
        "vector database",
        "schema",
        "knowledge node",
        "knowledge edge",
        "oneirosworker",
        "morpheus",
        "athene",
        "hestia",
        "argus",
        "zeus",
        "helios",
        "cluster_id",
        "depth_band",
        "pheromone",
        "constellation",
        "stub_verdict",
        "blindspot",
        "backlog",
        "phx-",
    }
)
_META_KEYWORDS_MID = frozenset(
    {
        "agent",
        "retrieval",
        "store",
        "ingest",
        "tick",
        "phase",
        "report",
        "audit",
        "graph",
        "modality",
        "model_id",
        "provider",
    }
)


def _keyword_hit_count(text_lower: str, keywords: frozenset[str]) -> int:
    """Count keyword hits without mid-word false positives (e.g. *graph* in *paragraph*)."""
    token_set = set(re.findall(r"[a-z0-9]+", text_lower))
    hits = 0
    for kw in keywords:
        if " " in kw or kw.endswith("-"):
            if kw in text_lower:
                hits += 1
        elif kw in token_set:
            hits += 1
    return hits


def _heuristic_breakdown(
    *,
    query: str,
    answer: Answer | None,
    cited_node_ids: tuple[str, ...],
    constellation: Constellation | None,
) -> tuple[MetaClassificationVerdict, int, int, int]:
    q = query.lower()
    high_q = _keyword_hit_count(q, _META_KEYWORDS_HIGH)
    mid_q = _keyword_hit_count(q, _META_KEYWORDS_MID)
    cited_high = 0
    if constellation is not None and cited_node_ids:
        by_id = {n.id: n for n in constellation.nodes}
        for cid in cited_node_ids:
            node = by_id.get(cid)
            if node is None:
                continue
            cited_high += _keyword_hit_count(node.label.lower(), _META_KEYWORDS_HIGH)
    mid_answer = 0
    if answer is not None and answer.text:
        a = answer.text.lower()
        mid_answer = _keyword_hit_count(a, _META_KEYWORDS_MID)
    mid_total = mid_q + mid_answer

    if high_q > 0 or cited_high > 0 or mid_total >= 2:
        verdict = MetaClassificationVerdict.SELF_REFERENTIAL
    elif mid_total == 1 and len(query) >= 50:
        verdict = MetaClassificationVerdict.UNCERTAIN
    else:
        verdict = MetaClassificationVerdict.NOT_SELF_REFERENTIAL

    return verdict, high_q, mid_total, cited_high


class MetaQueryClassifier:
    """Decide whether a query is self-referential to the Chronik."""

    name = "mnemosyne"

    def __init__(
        self,
        *,
        cfg: MnemosyneSettings,
        llm_fallback: MnemosyneLLMFallback | None = None,
    ) -> None:
        self._cfg = cfg
        self._llm_fallback = llm_fallback

    def classify_heuristic_query_only(self, query: str) -> MetaClassification:
        """CLI diagnostic: query text only (no answer, no constellation)."""
        verdict, high_q, mid_total, _cited = _heuristic_breakdown(
            query=query,
            answer=None,
            cited_node_ids=(),
            constellation=None,
        )
        return MetaClassification(
            verdict=verdict,
            high_keyword_hits=high_q,
            mid_keyword_hits=mid_total,
            cited_label_meta_hits=0,
            classifier_mode_used="heuristic",
            llm_fallback_skipped=False,
            llm_cost_eur=0.0,
        )

    async def classify(
        self,
        *,
        query: str,
        answer: Answer,
        cited_node_ids: tuple[str, ...] | list[str],
        constellation: Constellation,
    ) -> MetaClassification:
        if not self._cfg.enabled:
            return MetaClassification(
                verdict=MetaClassificationVerdict.NOT_SELF_REFERENTIAL,
                high_keyword_hits=0,
                mid_keyword_hits=0,
                cited_label_meta_hits=0,
                classifier_mode_used="heuristic",
                llm_fallback_skipped=False,
                llm_cost_eur=0.0,
            )

        ids = tuple(cited_node_ids)
        verdict, high_q, mid_total, cited_high = _heuristic_breakdown(
            query=query,
            answer=answer,
            cited_node_ids=ids,
            constellation=constellation,
        )
        base = MetaClassification(
            verdict=verdict,
            high_keyword_hits=high_q,
            mid_keyword_hits=mid_total,
            cited_label_meta_hits=cited_high,
            classifier_mode_used="heuristic",
            llm_fallback_skipped=False,
            llm_cost_eur=0.0,
        )

        if verdict != MetaClassificationVerdict.UNCERTAIN:
            return base

        if self._cfg.classifier_mode != "heuristic_with_llm_fallback" or self._llm_fallback is None:
            return MetaClassification(
                verdict=MetaClassificationVerdict.NOT_SELF_REFERENTIAL,
                high_keyword_hits=high_q,
                mid_keyword_hits=mid_total,
                cited_label_meta_hits=cited_high,
                classifier_mode_used="heuristic",
                llm_fallback_skipped=True,
                llm_cost_eur=0.0,
            )

        fb = await self._llm_fallback.classify(query=query, answer=answer)
        if fb is None:
            return MetaClassification(
                verdict=MetaClassificationVerdict.NOT_SELF_REFERENTIAL,
                high_keyword_hits=high_q,
                mid_keyword_hits=mid_total,
                cited_label_meta_hits=cited_high,
                classifier_mode_used="heuristic",
                llm_fallback_skipped=True,
                llm_cost_eur=0.0,
            )

        return MetaClassification(
            verdict=fb.verdict,
            high_keyword_hits=high_q,
            mid_keyword_hits=mid_total,
            cited_label_meta_hits=cited_high,
            classifier_mode_used="llm_fallback",
            llm_fallback_skipped=False,
            llm_cost_eur=fb.llm_cost_eur,
        )


def build_mnemosyne_classifier(
    settings: Settings,
    llm: LLMProvider | None,
) -> MetaQueryClassifier:
    """Factory matching production wiring (API / CLI / MCP)."""
    cfg = settings.mnemosyne
    fallback: MnemosyneLLMFallback | None = None
    if (
        cfg.enabled
        and cfg.classifier_mode == "heuristic_with_llm_fallback"
        and settings.llm.provider != "stub"
        and llm is not None
    ):
        fallback = MnemosyneLLMFallback(
            llm,
            max_calls_per_hour=cfg.max_llm_classifications_per_hour,
            max_cost_eur_per_call=cfg.llm_classification_max_cost_eur,
        )
    return MetaQueryClassifier(cfg=cfg, llm_fallback=fallback)


__all__ = [
    "MetaQueryClassifier",
    "build_mnemosyne_classifier",
]
