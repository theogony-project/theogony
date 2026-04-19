"""Tests for the AcquisitionAdapter protocol + DTOs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from theogony.acquisition import (
    AcquisitionAdapter,
    RawContent,
    SourceCandidate,
)


def _hedin_candidate() -> SourceCandidate:
    return SourceCandidate(
        source_type="gutenberg",
        identifier="43497",
        title="Trans-Himalaya: Discoveries and Adventurers in Tibet. Vol. 1 (of 2)",
        authors=["Hedin, Sven Anders"],
        languages=["en"],
        url="https://www.gutenberg.org/ebooks/43497",
        download_url="https://www.gutenberg.org/ebooks/43497.txt.utf-8",
        metadata={"download_count": 1398},
    )


def _hedin_raw(content: str = "Some text from Trans-Himalaya.") -> RawContent:
    return RawContent(
        source_type="gutenberg",
        identifier="43497",
        title="Trans-Himalaya: Discoveries and Adventurers in Tibet. Vol. 1 (of 2)",
        authors=["Hedin, Sven Anders"],
        language="en",
        content=content,
        content_format="text/plain; charset=utf-8",
        url="https://www.gutenberg.org/ebooks/43497",
        bytes_acquired=len(content.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# SourceCandidate
# ---------------------------------------------------------------------------


class TestSourceCandidate:
    def test_basic_construction(self) -> None:
        c = _hedin_candidate()
        assert c.source_type == "gutenberg"
        assert c.identifier == "43497"
        assert c.languages == ["en"]
        assert c.metadata["download_count"] == 1398

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            SourceCandidate(source_type="gutenberg")  # type: ignore[call-arg]

    def test_extra_field_rejected(self) -> None:
        # Plan §2.11.4 discipline: typos must fail loudly, not silently drop.
        with pytest.raises(ValidationError):
            SourceCandidate(
                source_type="gutenberg",
                identifier="43497",
                title="x",
                misspelled_field="oops",  # type: ignore[call-arg]
            )

    def test_round_trip_json(self) -> None:
        c = _hedin_candidate()
        restored = SourceCandidate.model_validate_json(c.model_dump_json())
        assert restored == c


# ---------------------------------------------------------------------------
# RawContent
# ---------------------------------------------------------------------------


class TestRawContent:
    def test_basic_construction(self) -> None:
        r = _hedin_raw()
        assert r.source_type == "gutenberg"
        assert r.identifier == "43497"
        assert r.bytes_acquired == len(r.content.encode("utf-8"))

    def test_acquired_at_default_is_recent(self) -> None:
        r = _hedin_raw()
        delta = (datetime.now(UTC) - r.acquired_at).total_seconds()
        assert delta < 5.0  # constructed just now

    def test_negative_bytes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawContent(
                source_type="gutenberg",
                identifier="43497",
                title="x",
                content="abc",
                content_format="text/plain; charset=utf-8",
                bytes_acquired=-1,
            )

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawContent(
                source_type="gutenberg",
                identifier="43497",
                title="x",
                content="abc",
                content_format="text/plain; charset=utf-8",
                bytes_acquired=3,
                misspelled_field="oops",  # type: ignore[call-arg]
            )

    def test_round_trip_json(self) -> None:
        r = _hedin_raw()
        restored = RawContent.model_validate_json(r.model_dump_json())
        assert restored.content == r.content
        assert restored.identifier == r.identifier


# ---------------------------------------------------------------------------
# RawContent.to_source_ref
# ---------------------------------------------------------------------------


class TestToSourceRef:
    def test_round_trip_metadata(self) -> None:
        r = _hedin_raw()
        ref = r.to_source_ref(location="ch3:offset_18433", snippet="At midnight…")
        assert ref.source_type == "gutenberg"
        assert ref.identifier == "43497"
        assert ref.url == r.url
        assert ref.language == "en"
        assert ref.location == "ch3:offset_18433"
        assert ref.snippet == "At midnight…"
        assert ref.accessed_at == r.acquired_at

    def test_location_and_snippet_optional(self) -> None:
        ref = _hedin_raw().to_source_ref()
        assert ref.location is None
        assert ref.snippet is None


# ---------------------------------------------------------------------------
# AcquisitionAdapter protocol — structural conformance via runtime_checkable
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Minimal stub satisfying every method the protocol requires."""

    @property
    def source_type(self) -> str:
        return "stub"

    def supports(self, source_type: str) -> bool:
        return source_type == "stub"

    async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
        return []

    async def acquire(self, candidate: SourceCandidate) -> RawContent:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class TestProtocol:
    def test_minimal_stub_is_recognised(self) -> None:
        assert isinstance(_StubAdapter(), AcquisitionAdapter)

    def test_incomplete_stub_is_not_recognised(self) -> None:
        # Missing `aclose` ⇒ should NOT satisfy the protocol.
        class _Incomplete:
            @property
            def source_type(self) -> str:
                return "x"

            def supports(self, source_type: str) -> bool:
                return False

            async def search(self, query: str, *, limit: int = 10) -> list[SourceCandidate]:
                return []

            async def acquire(self, candidate: SourceCandidate) -> RawContent:
                raise NotImplementedError

        assert not isinstance(_Incomplete(), AcquisitionAdapter)
