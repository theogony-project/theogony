"""
Live integration smoke for :class:`EntityResolver` against real Wikidata.

Gated by ``THEOGONY_RUN_WIKIDATA_INTEGRATION=1``. Issues real
``wbsearchentities``, ``wbgetentities``, and SPARQL calls. Verifies
the resolver resolves three well-known entities to their stable
Q-IDs at Tier 4 / 3, and one made-up entity to Tier 0 honestly.

The known Q-IDs (Q205184 Sven Hedin, Q64 Berlin, Q34770 language) are
extremely stable in Wikidata; this test would only fail if Wikidata
itself stopped returning them, which would be a system-wide outage,
not a regression in our code.

Runtime: ~5-10 s wall clock for all four resolutions (4 langs × 4
entities = 16 wbsearchentities calls + 4 wbgetentities + 4 SPARQL).
Cost: 0 EUR — Wikidata's APIs are free.

Run::

    THEOGONY_RUN_WIKIDATA_INTEGRATION=1 \\
        pytest tests/test_extraction_resolve_live.py -v
"""

from __future__ import annotations

import os

import pytest

from theogony.core.model import SourceRef
from theogony.extraction.ner import Mention
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.wikidata_client import WikidataClient

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_WIKIDATA_INTEGRATION") != "1",
    reason="set THEOGONY_RUN_WIKIDATA_INTEGRATION=1 to run live Wikidata integration",
)


def _book_ref() -> SourceRef:
    return SourceRef(
        source_type="gutenberg",
        identifier="43497",
        url="https://www.gutenberg.org/ebooks/43497",
        language="en",
    )


def _mention(text: str, label: str) -> Mention:
    return Mention(
        text=text,
        label=label,
        sentence_index=0,
        start_char_in_sentence=0,
        end_char_in_sentence=len(text),
        start_char_in_source=0,
        end_char_in_source=len(text),
    )


class TestLiveResolution:
    async def test_resolves_sven_hedin_to_q154759(self) -> None:
        # Q154759 is the Swedish geographer/explorer (1865–1952), aliased as
        # "Sven Anders Hedin", "S. A. Hedin" etc., P31=Q5 (human). Verified
        # against live Wikidata at E2 implementation time.
        async with WikidataClient() as client:
            resolver = EntityResolver(client=client)
            resolved = await resolver.resolve(
                _mention("Sven Hedin", "PERSON"),
                source_ref=_book_ref(),
            )

        assert resolved.tier in (3, 4), (
            f"expected Tier 3 or 4 for Sven Hedin; got {resolved.tier} "
            f"(reason={resolved.failure_reason})"
        )
        assert resolved.chosen_qid == "Q154759", (
            f"expected Q154759 (Sven Hedin) — got {resolved.chosen_qid}"
        )
        assert resolved.node.external_ids["wikidata"] == "Q154759"
        assert resolved.node.scores.confidence >= 0.75

    async def test_resolves_berlin_to_q64(self) -> None:
        async with WikidataClient() as client:
            resolver = EntityResolver(client=client)
            resolved = await resolver.resolve(
                _mention("Berlin", "GPE"),
                source_ref=_book_ref(),
            )

        assert resolved.tier in (3, 4), (
            f"expected Tier 3 or 4 for Berlin; got {resolved.tier} "
            f"(reason={resolved.failure_reason})"
        )
        assert resolved.chosen_qid == "Q64", f"expected Q64 (Berlin) — got {resolved.chosen_qid}"
        assert resolved.node.external_ids["wikidata"] == "Q64"

    async def test_resolves_invented_word_to_tier_0(self) -> None:
        # A truly invented surface form must land at Tier 0.
        # Using a deliberately uncommon Q-unfriendly string.
        async with WikidataClient() as client:
            resolver = EntityResolver(client=client)
            resolved = await resolver.resolve(
                _mention("Glorpzizzlewicketblamfoo", "PERSON"),
                source_ref=_book_ref(),
            )

        assert resolved.tier == 0
        assert resolved.chosen_qid is None
        assert resolved.node.manual_resolution_needed is True
        assert resolved.node.external_ids == {}
        assert resolved.failure_reason in {
            "no_candidates_from_search",
            "all_candidates_failed_type_filter",
            "weak_alias_match_no_llm_in_e2",
        }

    async def test_resolve_many_with_mixed_outcomes(self) -> None:
        # Three real, one fake — exercises dedup + tier mix in one round.
        mentions = [
            _mention("Sven Hedin", "PERSON"),
            _mention("Sven Hedin", "PERSON"),  # repeat — should dedupe
            _mention("Berlin", "GPE"),
            _mention("Glorpzizzlewicketblamfoo", "PERSON"),
        ]
        async with WikidataClient() as client:
            resolver = EntityResolver(client=client)
            results = await resolver.resolve_many(mentions, source_ref=_book_ref())

        # Three groups (Sven Hedin × 2 dedupes; Berlin; Glorpzizzle…)
        assert len(results) == 3

        by_text = {r.node.label.lower(): r for r in results}
        # Resolved nodes: their label is the canonical Wikidata label,
        # which for both "Sven Hedin" and "Berlin" is the same string.
        # Tier-0 node label is the verbatim mention.
        assert any("sven hedin" in label for label in by_text)
        assert any("berlin" in label for label in by_text)
        assert any("glorpzizzle" in label for label in by_text)

        tier0_results = [r for r in results if r.tier == 0]
        assert len(tier0_results) == 1
        assert tier0_results[0].node.manual_resolution_needed is True
