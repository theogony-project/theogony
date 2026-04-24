"""ResearchExecutor — run :class:`~theogony.curiosity.trigger.ResearchStep` plans (W11)."""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

from theogony.acquisition.base import AcquisitionAdapter, RawContent, SourceCandidate
from theogony.agents.research_evaluator import EvaluatorCandidate
from theogony.config.logging import get_logger
from theogony.curiosity.trigger import ResearchStep, ResearchStepKind

log = get_logger("curiosity.research_executor")


@runtime_checkable
class _WikidataSidecar(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]: ...

    async def acquire(self, candidate: SourceCandidate) -> RawContent: ...


def _web_id16(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class ResearchExecutor:
    """Dispatches planned steps to acquisition adapters (W11 + W12)."""

    def __init__(
        self,
        *,
        wikidata: _WikidataSidecar,
        gutenberg: AcquisitionAdapter,
        wikipedia: AcquisitionAdapter | None = None,
        web_fetch: AcquisitionAdapter | None = None,
    ) -> None:
        self._wikidata = wikidata
        self._gutenberg = gutenberg
        self._wikipedia = wikipedia
        self._web_fetch = web_fetch

    async def acquire_source(self, candidate: SourceCandidate) -> RawContent:
        st = candidate.source_type
        if st == "wikidata":
            return await self._wikidata.acquire(candidate)
        if st == "gutenberg":
            return await self._gutenberg.acquire(candidate)
        if st == "wikipedia":
            if self._wikipedia is None:
                raise ValueError("WikipediaAdapter not configured on ResearchExecutor")
            return await self._wikipedia.acquire(candidate)
        if st == "web":
            if self._web_fetch is None:
                raise ValueError("WebFetchAdapter not configured on ResearchExecutor")
            return await self._web_fetch.acquire(candidate)
        raise ValueError(f"unsupported source_type: {st!r}")

    async def execute_step(self, step: ResearchStep) -> list[EvaluatorCandidate]:
        kind = step.kind
        if kind == ResearchStepKind.WIKIDATA_LOOKUP:
            cands = await self._wikidata.search(step.target, limit=5)
            out: list[EvaluatorCandidate] = []
            for c in cands:
                label = f"{c.title} ({c.identifier})"
                est = int(c.metadata.get("estimated_bytes", 0) or 0)
                meta = dict(c.metadata)
                meta["_source_candidate"] = c.model_dump()
                out.append(
                    EvaluatorCandidate(
                        source_step=step,
                        candidate_label=label,
                        summary=c.metadata.get("wikidata_description", "") or "",
                        estimated_bytes=est,
                        metadata=meta,
                    )
                )
            return out
        if kind == ResearchStepKind.GUTENBERG_SEARCH:
            cands = await self._gutenberg.search(step.target, limit=10)
            rows: list[EvaluatorCandidate] = []
            for c in cands:
                meta = dict(c.metadata)
                meta["_source_candidate"] = c.model_dump()
                rows.append(
                    EvaluatorCandidate(
                        source_step=step,
                        candidate_label=f"#{c.identifier} {c.title}",
                        summary="; ".join(c.authors) if c.authors else "",
                        estimated_bytes=int(c.metadata.get("estimated_bytes", 0) or 0),
                        metadata=meta,
                    )
                )
            return rows
        if kind == ResearchStepKind.WIKIPEDIA_FETCH:
            if self._wikipedia is None:
                log.warning(
                    "research executor: WikipediaAdapter not configured for wikipedia_fetch (W12)"
                )
                return []
            cands = await self._wikipedia.search(step.target, limit=5)
            wiki_rows: list[EvaluatorCandidate] = []
            for c in cands:
                meta = dict(c.metadata)
                meta["_source_candidate"] = c.model_dump()
                est = int(c.metadata.get("estimated_bytes", 0) or 200 * 1024)
                wiki_rows.append(
                    EvaluatorCandidate(
                        source_step=step,
                        candidate_label=f"{c.title} ({c.identifier})",
                        summary=str(meta.get("summary") or meta.get("wikipedia_description") or ""),
                        estimated_bytes=est,
                        metadata=meta,
                    )
                )
            return wiki_rows
        if kind == ResearchStepKind.WEB_FETCH:
            if self._web_fetch is None:
                log.warning("research executor: WebFetchAdapter not configured for web_fetch (W12)")
                return []
            url = step.target.strip()
            sc = SourceCandidate(
                source_type="web",
                identifier=_web_id16(url),
                title=url,
                authors=[],
                languages=[],
                url=url,
                download_url=None,
                metadata={"estimated_bytes": 5 * 1024 * 1024},
            )
            meta = dict(sc.metadata)
            meta["_source_candidate"] = sc.model_dump()
            return [
                EvaluatorCandidate(
                    source_step=step,
                    candidate_label=url,
                    summary="",
                    estimated_bytes=int(meta.get("estimated_bytes", 0) or 0),
                    metadata=meta,
                )
            ]
        return []


__all__ = ["ResearchExecutor"]
