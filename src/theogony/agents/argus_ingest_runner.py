"""
IngestRunner — thin bridge from Argus-acquired bytes to IngestionPipeline (W7-B).

Argus must not import the full ingest stack at module level beyond this
adapter: the brief (Knob 5) isolates the contract so tests can inject a
fake runner while production wires :class:`RealIngestRunner` around a
fully configured :class:`~theogony.extraction.pipeline.IngestionPipeline`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from theogony.acquisition.base import RawContent
from theogony.extraction.pipeline import IngestionPipeline


@runtime_checkable
class IngestRunner(Protocol):
    """Minimal contract Argus needs to start an ingest from already-acquired bytes."""

    async def run_from_raw_content(self, raw: RawContent) -> str:
        """Run extraction → store; return the ingest_run_id (ULID)."""
        ...


class RealIngestRunner:
    """Wraps :class:`IngestionPipeline` — calls :meth:`IngestionPipeline.ingest`."""

    def __init__(self, pipeline: IngestionPipeline) -> None:
        self._pipeline = pipeline

    async def run_from_raw_content(self, raw: RawContent) -> str:
        result = await self._pipeline.ingest(raw)
        return result.run_id


__all__ = ["IngestRunner", "RealIngestRunner"]
