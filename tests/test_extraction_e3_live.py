"""
Live integration smoke for Etappe E3 — BookContext + Stage 4 LLM disambiguation.

Gated by ``THEOGONY_RUN_E3_INTEGRATION=1``. Requires a Gemini API key
in the environment (``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``).

Two tests:

1. ``BookContextExtractor`` against real Gemini 2.5 Flash Lite — fed a
   plausible Hedin / Trans-Himalaya opening, must produce a non-empty
   ``BookContext`` whose places include Tibet (or similar).

2. ``EntityResolver`` Stage 4 against real Wikidata + real Gemini —
   Heinrich Harrer disambiguation. Wikidata returns at least two Q5
   humans named "Harrer" (Q84211 the Austrian Tibet-explorer
   1912–2006; Q25726941 a 19th-century painter). With Hedin/Tibet
   book context and a Tibet-mentioning sentence, the resolver must
   pick Q84211 at Tier 2.

Cost: ~3 LLM calls (~0.001 EUR), ~10 s wall-clock for both tests.

Run::

    THEOGONY_RUN_E3_INTEGRATION=1 \\
        pytest tests/test_extraction_e3_live.py -v
"""

from __future__ import annotations

import os

import pytest

from theogony.acquisition.base import RawContent
from theogony.agents.llm_gemini import GeminiLLMProvider
from theogony.config.settings import Settings
from theogony.core.model import SourceRef
from theogony.extraction.book_context import BookContextExtractor
from theogony.extraction.ner import Mention
from theogony.extraction.resolve import EntityResolver
from theogony.extraction.sentence import Sentence
from theogony.extraction.wikidata_client import WikidataClient

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_E3_INTEGRATION") != "1",
    reason="set THEOGONY_RUN_E3_INTEGRATION=1 to run live E3 integration",
)


def _book_ref() -> SourceRef:
    return SourceRef(
        source_type="gutenberg",
        identifier="944",
        url="https://www.gutenberg.org/ebooks/944",
        language="en",
    )


def _hedin_raw() -> RawContent:
    return RawContent(
        source_type="gutenberg",
        identifier="944",
        title="Seven Years in Tibet",
        authors=["Harrer, Heinrich"],
        language="en",
        content="(opening text supplied separately as sentences)",
        content_format="text/plain; charset=utf-8",
        bytes_acquired=100,
    )


def _hedin_opening() -> list[Sentence]:
    parts = [
        ("I left Stockholm in October 1905 to begin my third great journey to Tibet. "),
        (
            "The aim was to chart the high plateau between the Himalayas "
            "and the Trans-Himalaya range. "
        ),
        (
            "My companions were drawn from many nations: a Buryat lama, "
            "two Cossacks, a Pathan caravan-bashi. "
        ),
        "Beyond the passes lay regions no European had ever surveyed. ",
        "We crossed into Indian territory in early 1906. ",
        ("From Leh we marched eastward through Kashmir into the western Himalayan ranges. "),
        "The cold was relentless and the altitude often above 5,000 metres. ",
    ]
    out: list[Sentence] = []
    cursor = 0
    for i, text in enumerate(parts):
        out.append(Sentence(index=i, text=text, start_char=cursor, end_char=cursor + len(text)))
        cursor += len(text)
    return out


def _gemini() -> GeminiLLMProvider:
    """Build a real Gemini provider from the active Settings."""
    settings = Settings()  # type: ignore[call-arg]
    api_key = settings.active_llm_api_key()
    if api_key is None:
        pytest.skip("no Gemini/Google API key in environment")
    return GeminiLLMProvider(
        api_key=api_key,
        model_id=settings.llm.model_id,
    )


class TestBookContextLive:
    async def test_extracts_plausible_context_from_hedin_opening(self) -> None:
        llm = _gemini()
        extractor = BookContextExtractor(llm=llm)
        ctx = await extractor.extract(
            raw_content=_hedin_raw(),
            opening_sentences=_hedin_opening(),
        )

        # Loose contract: any well-behaved LLM with this material
        # should infer Tibet as a central place. Date / people /
        # summary may vary in wording across model versions.
        assert ctx.derived_from_book == "gutenberg:944"
        assert ctx.derived_from_model_id != ""
        # places list non-empty + mentions Tibet (or "Asia" / "Himalayas").
        joined = " | ".join(p.lower() for p in ctx.places)
        assert any(token in joined for token in ("tibet", "himalaya", "asia")), (
            f"expected places to mention Tibet/Himalayas/Asia; got {ctx.places}"
        )
        # Summary is non-empty.
        assert ctx.summary, "expected non-empty summary"


class TestStage4LiveDisambiguation:
    async def test_resolves_harrer_to_q84211_via_stage4(self) -> None:
        # Two surviving Q5 humans called "Harrer": Q84211 (Tibet
        # explorer, 1912-2006) and Q25726941 (19th-century painter).
        # Stage 4 with Hedin/Tibet context must pick Q84211.
        llm = _gemini()
        # BookContext fixed by hand — keeps this test independent of
        # the BookContext extraction quality (tested separately above).
        from theogony.extraction.book_context import BookContext

        ctx = BookContext(
            time_period="early-to-mid 20th century",
            places=["Tibet", "India", "Nepal"],
            people_descriptors=[
                "Austrian mountaineer",
                "European explorer in Asia",
            ],
            summary=(
                "An Austrian mountaineer's escape from a British "
                "internment camp in India to Lhasa, where he became "
                "a tutor of the young Dalai Lama."
            ),
            derived_from_book="gutenberg:944",
            derived_from_model_id="hand-crafted-fixture",
        )
        async with WikidataClient() as client:
            resolver = EntityResolver(client=client, llm=llm, book_context=ctx)
            sentences = [
                Sentence(
                    index=0,
                    text=(
                        "After many days of trekking through the high "
                        "passes, Harrer and Aufschnaiter reached the "
                        "outskirts of Lhasa."
                    ),
                    start_char=0,
                    end_char=120,
                ),
            ]
            mention = Mention(
                text="Harrer",
                label="PERSON",
                sentence_index=0,
                start_char_in_sentence=44,
                end_char_in_sentence=50,
                start_char_in_source=44,
                end_char_in_source=50,
            )
            resolved = await resolver.resolve(
                mention,
                source_ref=_book_ref(),
                sentences=sentences,
            )

        assert resolved.tier in (2, 4), (
            f"expected Tier 2 (Stage 4) or Tier 4 (Stages 1-3 nailed it); "
            f"got tier {resolved.tier} (reason={resolved.failure_reason})"
        )
        # Either way Q84211 must be the chosen Q-ID.
        assert resolved.chosen_qid == "Q84211", (
            f"expected Q84211 (Heinrich Harrer the Tibet explorer); got {resolved.chosen_qid}"
        )
        assert resolved.node.external_ids["wikidata"] == "Q84211"
        # Stage 4 wired in audit fields when it ran.
        if resolved.tier == 2:
            assert "stage4_llm_reasoning" in resolved.node.properties
            assert resolved.node.properties["stage4_llm_model_id"]
