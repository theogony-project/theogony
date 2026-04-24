"""ResearchExecutor — run :class:`~theogony.curiosity.trigger.ResearchStep` plans (W11)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from theogony.acquisition.base import AcquisitionAdapter, RawContent, SourceCandidate
from theogony.agents.research_evaluator import EvaluatorCandidate
from theogony.config.logging import get_logger
from theogony.curiosity.trigger import ResearchStep, ResearchStepKind

log = get_logger("curiosity.research_executor")


@runtime_checkable
class _WikidataSidecar(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> list[SourceCandidate]: ...

    async def acquire(self, candidate: SourceCandidate) -> RawContent: ...


@runtime_checkable
class WikipediaAdapter(Protocol):
    """W12 placeholder — executor warns when steps need this but it is absent."""

    async def search(self, query: str, *, limit: int = 10) -> list[Any]: ...


@runtime_checkable
class WebFetchAdapter(Protocol):
    """W12 placeholder."""

    async def fetch(self, url: str) -> Any: ...


class ResearchExecutor:
    """Dispatches planned steps to acquisition adapters (W11: Wikidata + Gutenberg)."""

    def __init__(
        self,
        *,
        wikidata: _WikidataSidecar,
        gutenberg: AcquisitionAdapter,
        wikipedia: WikipediaAdapter | None = None,
        web_fetch: WebFetchAdapter | None = None,
    ) -> None:
        self._wikidata = wikidata
        self._gutenberg = gutenberg
        self._wikipedia = wikipedia
        self._web_fetch = web_fetch

    async def acquire_source(self, candidate: SourceCandidate) -> RawContent:
        if candidate.source_type == "wikidata":
            return await self._wikidata.acquire(candidate)
        if candidate.source_type == "gutenberg":
            return await self._gutenberg.acquire(candidate)
        raise ValueError(f"unsupported source_type: {candidate.source_type!r}")

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
        if kind in (ResearchStepKind.WIKIPEDIA_FETCH, ResearchStepKind.WEB_FETCH):
            log.warning(
                "research executor: adapter not yet wired (W12) for step kind=%s",
                kind.value,
            )
            return []
        return []


__all__ = ["ResearchExecutor", "WebFetchAdapter", "WikipediaAdapter"]
