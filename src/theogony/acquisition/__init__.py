"""Acquisition adapters — bring raw content into Theogony.

Gen 1 ships :class:`GutenbergAdapter` only (Plan §2.4). Future
adapters (web search, Wikidata, ArXiv, library robotics, sensor
feeds) implement the same :class:`AcquisitionAdapter` protocol;
the extraction pipeline is unaffected by which adapter produced
its :class:`RawContent`.
"""

from theogony.acquisition.base import (
    AcquisitionAdapter,
    RawContent,
    SourceCandidate,
)

__all__ = [
    "AcquisitionAdapter",
    "RawContent",
    "SourceCandidate",
]
