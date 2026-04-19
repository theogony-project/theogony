"""
Live E1 chain smoke test — Hedin Trans-Himalaya Vol. I (Gutenberg #43497).

Exercises the full Etappe-E1 path against real data:

    GutenbergAdapter.acquire(Hedin #43497)
        → TextCleaner.clean
        → Sentencizer.sentencize
        → NerExtractor.extract_flat

Asserts plausibility at each stage and reports concrete numbers
(byte counts, sentence counts, mention counts, label histogram)
so a reviewer can sanity-check what the pipeline actually does.

Gated by **two** env vars — both must be ``"1"``:

    THEOGONY_RUN_GUTENBERG_INTEGRATION=1
    THEOGONY_RUN_NER_INTEGRATION=1

Plus the spaCy model must be installed:

    python -m spacy download en_core_web_sm
"""

from __future__ import annotations

import os
from collections import Counter

import pytest

from theogony.acquisition import GutenbergAdapter
from theogony.extraction import NerExtractor, Sentencizer, TextCleaner

HEDIN_ID = "43497"

pytestmark = pytest.mark.skipif(
    os.environ.get("THEOGONY_RUN_GUTENBERG_INTEGRATION") != "1"
    or os.environ.get("THEOGONY_RUN_NER_INTEGRATION") != "1",
    reason=(
        "set THEOGONY_RUN_GUTENBERG_INTEGRATION=1 AND "
        "THEOGONY_RUN_NER_INTEGRATION=1 to run the live E1 chain"
    ),
)


class TestE1ChainAgainstHedin:
    async def test_full_chain_produces_plausible_extraction(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # ---------------------------------------------------------------- 1. acquire
        async with GutenbergAdapter(inter_request_delay_s=0.0) as adapter:
            cands = await adapter.search("Trans-Himalaya Hedin", limit=10)
            hedin_cand = next(c for c in cands if c.identifier == HEDIN_ID)
            raw = await adapter.acquire(hedin_cand)

        assert raw.bytes_acquired > 500_000

        # ---------------------------------------------------------------- 2. clean
        cleaner = TextCleaner()
        cleaned = cleaner.clean(raw.content)

        # Hedin #43497 has both PG markers — the cleaner must find them.
        assert cleaned.header_stripped is True
        assert cleaned.footer_stripped is True
        assert cleaned.warnings == []
        # Boilerplate gone, body retained.
        assert "Project Gutenberg eBook of" not in cleaned.content
        assert "Updated editions will replace" not in cleaned.content
        assert "Tibet" in cleaned.content
        # Body is a substantial fraction of the raw download.
        body_ratio = len(cleaned.content) / cleaned.raw_length
        assert body_ratio > 0.90

        # ---------------------------------------------------------------- 3. sentencize
        sentencizer = Sentencizer()
        sentences = await sentencizer.sentencize(cleaned)

        # Hedin Vol. I is ~110k words → expect tens of thousands of sentences.
        # Lower bound is generous to catch obviously-broken segmentation.
        assert len(sentences) >= 3_000
        # Indices are dense and 0-based.
        assert sentences[0].index == 0
        assert sentences[-1].index == len(sentences) - 1
        # Substring invariant survives the full corpus.
        for sent in sentences[:50]:
            assert cleaned.content[sent.start_char : sent.end_char] == sent.text

        # ---------------------------------------------------------------- 4. NER
        # NER over the full book takes ~20-30 s on en_core_web_sm. Restrict
        # to a representative slice for the smoke test — first 200 sentences
        # cover preface + opening narrative, which is dense in named entities
        # (people, places, dates).
        slice_size = 200
        slice_sentences = sentences[:slice_size]
        ner = NerExtractor()
        per_sentence_mentions = await ner.extract(slice_sentences)
        flat = [m for sent_ms in per_sentence_mentions for m in sent_ms]

        # Plausibility: 200 sentences of Hedin's preface/opening contain
        # plenty of named entities. Lower bound is conservative (20 mentions
        # in 200 sentences = 1 every 10 sentences).
        assert len(flat) >= 20

        # Distribution: PERSON and GPE should both be present (the book is
        # about a person travelling through places).
        labels = Counter(m.label for m in flat)
        assert labels["PERSON"] > 0, f"no PERSON mentions in first {slice_size} sentences"
        assert labels["GPE"] > 0, f"no GPE mentions in first {slice_size} sentences"

        # Substring invariant on every mention.
        for m in flat:
            sent = slice_sentences[m.sentence_index]
            assert sent.text[m.start_char_in_sentence : m.end_char_in_sentence] == m.text
            # Source-absolute offset round-trips through cleaned content.
            assert cleaned.content[m.start_char_in_source : m.end_char_in_source] == m.text

        # ---------------------------------------------------------------- report
        # Print a small RunReport-shaped summary for human review when
        # the test runs with -s. Useful for dialing thresholds later.
        with capsys.disabled():
            print("\n--- E1 chain smoke report (Hedin #43497) ---")
            print(f"raw bytes:           {raw.bytes_acquired:,}")
            print(f"cleaned chars:       {len(cleaned.content):,}")
            print(f"body ratio:          {body_ratio:.3f}")
            print(f"total sentences:     {len(sentences):,}")
            print(f"NER slice size:      {slice_size}")
            print(f"mentions in slice:   {len(flat)}")
            print(f"label histogram:     {dict(labels.most_common())}")
            # Show a few sample mentions for human eyeball.
            print("First 8 mentions:")
            for m in flat[:8]:
                print(
                    f"  [{m.label:8}] {m.text!r:40} "
                    f"(sent {m.sentence_index}, src {m.start_char_in_source})"
                )
