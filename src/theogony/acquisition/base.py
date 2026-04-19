"""
Acquisition layer — protocol and DTOs (Plan §2.4 + ARCHITECTURE §0).

Acquisition adapters bring raw content from external sources into
Theogony. The protocol is deliberately thin: ``search`` discovers
candidates, ``acquire`` downloads one of them, ``supports`` declares
which source-type strings the adapter can handle. The downstream
extraction pipeline does not care where the content came from.

Two DTOs:

- :class:`SourceCandidate` is **pre-acquisition**. It carries enough
  metadata for a human (or an agent) to choose between candidates
  without paying the cost of fetching the full content.
- :class:`RawContent` is **post-acquisition**. It carries the actual
  text plus the size and timestamp the run report wants.

Both are pydantic models with ``extra="forbid"`` so a typo at the
adapter boundary becomes a loud ValidationError, not a silently
dropped field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from theogony.core import SourceRef


class SourceCandidate(BaseModel):
    """Pre-acquisition record describing one candidate source.

    The shape is intentionally provider-agnostic: ``source_type`` and
    ``identifier`` together address the candidate; everything else is
    descriptive metadata. Provider-specific extra fields go in
    ``metadata``.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(
        description='e.g. "gutenberg", "web", "wikidata", "arxiv".',
    )
    identifier: str = Field(
        description=(
            "Provider-native identifier — Gutenberg book number, "
            "DOI, Wikidata Q-id, etc. Plain string, no provider "
            "prefix (the source_type field already carries that)."
        ),
    )
    title: str
    authors: list[str] = Field(default_factory=list)
    languages: list[str] = Field(
        default_factory=list,
        description="ISO 639-1 codes — the source's declared languages, in order.",
    )
    url: str | None = Field(
        default=None,
        description="Canonical landing page URL, e.g. the Project Gutenberg book page.",
    )
    download_url: str | None = Field(
        default=None,
        description=(
            "Direct text-content URL the adapter will GET in `acquire()`. "
            "When None the adapter must derive it from `identifier` or "
            "fail loudly — never silently fall back to scraping HTML."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawContent(BaseModel):
    """Acquired content + provenance, ready for the extraction pipeline.

    The extraction pipeline consumes ``content`` (the text), records
    ``source_type``/``identifier``/``url`` on every node it produces
    (via :meth:`to_source_ref`), and stamps the IngestRunReport's
    acquired-stage row with ``bytes_acquired`` + ``acquired_at``.
    """

    model_config = ConfigDict(extra="forbid")

    source_type: str
    identifier: str
    title: str
    authors: list[str] = Field(default_factory=list)
    language: str | None = Field(
        default=None,
        description=(
            "Primary language (ISO 639-1). Picked by the adapter from "
            "the source's declared languages — usually the first one."
        ),
    )
    content: str
    content_format: str = Field(
        description=(
            'Mime type + charset, e.g. "text/plain; charset=utf-8". '
            "TextCleaner uses this to decide cleaning strategy."
        ),
    )
    url: str | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bytes_acquired: int = Field(
        ge=0,
        description=(
            "Length of the content in *bytes* (UTF-8). Always equals "
            "len(content.encode('utf-8')) at construction time; reported "
            "to IngestRunReport so it does not have to re-compute."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_source_ref(
        self,
        *,
        location: str | None = None,
        snippet: str | None = None,
    ) -> SourceRef:
        """Build a :class:`SourceRef` for a node extracted from this content.

        ``location`` and ``snippet`` are caller-supplied: the
        extraction pipeline knows the chapter/sentence offset that
        each mention came from; this DTO does not. Everything else
        is copied straight off the RawContent.
        """
        return SourceRef(
            source_type=self.source_type,
            url=self.url,
            identifier=self.identifier,
            location=location,
            snippet=snippet,
            language=self.language,
            accessed_at=self.acquired_at,
        )


@runtime_checkable
class AcquisitionAdapter(Protocol):
    """Contract every acquisition adapter implements.

    Implementations MUST:
        - be safe to call concurrently from asyncio tasks (the future
          Argus / Jason agent classes will fan out across many
          adapters at once);
        - close any owned HTTP clients on ``aclose()`` so the FastAPI
          ``serve`` lifespan (Plan §4.4) can shut down cleanly;
        - never call ``acquire()`` on an unsupported candidate —
          callers route via ``supports()``.
    """

    @property
    def source_type(self) -> str:
        """The single source-type string this adapter advertises."""
        ...

    def supports(self, source_type: str) -> bool:
        """True iff this adapter knows how to acquire from ``source_type``."""
        ...

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        """Discover candidates matching ``query``. Returns at most ``limit``."""
        ...

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        """Download the candidate's content. Raises on transport / decode failure."""
        ...

    async def aclose(self) -> None:
        """Release any owned resources (HTTP client, connections)."""
        ...
