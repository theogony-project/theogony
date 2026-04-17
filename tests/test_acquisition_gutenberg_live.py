"""
Live integration test for GutenbergAdapter against Hedin #43497.

Gated by ``THEOGONY_RUN_GUTENBERG_INTEGRATION=1``. Pulls the real
Project Gutenberg text for *Trans-Himalaya: Discoveries and
Adventurers in Tibet, Vol. 1* (Sven Hedin, 1909) over the network.

This is the Etappe-D smoke test: it exercises the full path from
Gutendex search to text download, verifies the text is plausibly
the right book, and reports back its size so we have a reference
point for the extraction pipeline that lands in Etappe E.

Why Hedin #43497 and not "Seven Years in Tibet" (Plan §1's main
demo): travel-literature genre is the same, language is the same
(English), entity-resolution failure modes are similar, but #43497
is canonically multi-volume which means future work on cross-volume
deduplication has a real test corpus.

Run::

    THEOGONY_RUN_GUTENBERG_INTEGRATION=1 \\
        pytest tests/test_acquisition_gutenberg_live.py -v
"""

from __future__ import annotations

import os

import pytest

from theogony.acquisition import GutenbergAdapter

HEDIN_ID = "43497"
HEDIN_TITLE_FRAGMENT = "Trans-Himalaya"
HEDIN_AUTHOR_FRAGMENT = "Hedin"
# A few content tokens we know must be in any real copy of this book.
EXPECTED_CONTENT_TOKENS = ("Tibet", "expedition", "Hedin")
# Project Gutenberg lists the text format at ~960 KB. We assert a
# generous lower bound to catch obviously-truncated downloads without
# being brittle to PG's small-edit churn.
MIN_BYTES = 500_000


pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_GUTENBERG_INTEGRATION") != "1",
    reason="set THEOGONY_RUN_GUTENBERG_INTEGRATION=1 to run live Gutenberg integration",
)


class TestHedin:
    async def test_search_finds_hedin(self) -> None:
        async with GutenbergAdapter() as adapter:
            cands = await adapter.search("Trans-Himalaya Hedin", limit=10)
        assert len(cands) >= 1
        # The book may or may not be the top hit depending on Gutendex's
        # current ranking; we just need it in the result set.
        ids = {c.identifier for c in cands}
        assert HEDIN_ID in ids
        hedin = next(c for c in cands if c.identifier == HEDIN_ID)
        assert HEDIN_TITLE_FRAGMENT in hedin.title
        assert any(HEDIN_AUTHOR_FRAGMENT in a for a in hedin.authors)
        assert "en" in hedin.languages
        assert hedin.download_url is not None
        assert "gutenberg.org" in hedin.download_url

    async def test_acquire_returns_real_book(self) -> None:
        async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
            cands = await adapter.search("Trans-Himalaya Hedin", limit=10)
            hedin_cand = next(c for c in cands if c.identifier == HEDIN_ID)
            raw = await adapter.acquire(hedin_cand)

        # Provenance round-trips
        assert raw.source_type == "gutenberg"
        assert raw.identifier == HEDIN_ID
        assert HEDIN_TITLE_FRAGMENT in raw.title
        assert any(HEDIN_AUTHOR_FRAGMENT in a for a in raw.authors)
        assert raw.language == "en"
        assert raw.url == f"https://www.gutenberg.org/ebooks/{HEDIN_ID}"
        assert raw.content_format.startswith("text/plain")
        assert raw.metadata["http_status"] == 200

        # Content sanity
        assert raw.bytes_acquired >= MIN_BYTES, (
            f"download is suspiciously small: {raw.bytes_acquired} bytes; "
            "expected ≥ ~500 KB for a full Hedin volume"
        )
        assert raw.bytes_acquired == len(raw.content.encode("utf-8"))
        for token in EXPECTED_CONTENT_TOKENS:
            assert token in raw.content, (
                f"expected content token {token!r} not found — "
                "the download appears incomplete or corrupted"
            )

        # to_source_ref produces something extraction can use
        ref = raw.to_source_ref(location="ch1:offset_0", snippet="...")
        assert ref.source_type == "gutenberg"
        assert ref.identifier == HEDIN_ID
        assert ref.url == raw.url
        assert ref.language == "en"
