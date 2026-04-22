"""W6 verification benchmark — measure persistent Wikidata cache impact.

Replaces the brief's two ``theogony ingest 43497 --sentences 50``
runs with a resolver-only fixture: no LLM cost, no Neo4j dependency,
honest empirical signal on cache impact.

The fixture is a small set of mentions drawn from the Hedin /
Trans-Himalaya corpus that exercises every cached method:

- ``search()`` per mention × 4 languages
- ``fetch_labels_aliases()`` for the union of returned Q-IDs
- ``fetch_types()`` for the same Q-IDs
- ``fetch_bio_facts()`` for the survivors (same set; we don't filter
  here — this is a network-cost benchmark, not a resolver test)

Run it twice in a row against the same SQLite cache file (default
``data/wikidata_cache.sqlite``):

    python scripts/bench_wikidata_cache.py
    python scripts/bench_wikidata_cache.py

The first run populates the cache; the second should report
``cache_hits >> api_requests`` and a substantially shorter wall-clock.
"""

from __future__ import annotations

import asyncio
import time

from theogony.config.settings import Settings
from theogony.extraction.wikidata_cache import WikidataCache
from theogony.extraction.wikidata_client import WikidataClient

MENTIONS = [
    "Sven Hedin",
    "Lhasa",
    "Tibet",
    "Dalai Lama",
    "Aufschnaiter",
    "Stockholm",
    "Trans-Himalaya",
    "Heinrich Harrer",
    "Karakoram",
    "Kashgar",
]

LANGUAGES = ("en", "de", "fr", "it")


async def main() -> None:
    settings = Settings()
    cache_path = settings.wikidata_cache_path
    print(f"cache path: {cache_path}")
    print(f"mentions: {len(MENTIONS)} × languages: {len(LANGUAGES)}")
    print()

    started = time.perf_counter()
    with WikidataCache(cache_path) as cache:
        async with WikidataClient(cache=cache) as client:
            # search() — one call per (mention, language) = 40 logical
            # operations on a cold cache.
            search_results: dict[str, list[str]] = {}
            for mention in MENTIONS:
                multi = await client.search_multi_language(mention, languages=LANGUAGES, limit=5)
                qids = sorted({c.qid for cands in multi.values() for c in cands})
                search_results[mention] = qids

            all_qids = sorted({q for qids in search_results.values() for q in qids})

            # labels_aliases / types / bio_facts — partial-batch hit
            # behaviour kicks in here on rerun.
            await client.fetch_labels_aliases(all_qids, languages=list(LANGUAGES))
            await client.fetch_types(all_qids)
            await client.fetch_bio_facts(all_qids[:10], language="en")

            duration = time.perf_counter() - started

            print(f"wall_clock_s         : {duration:.2f}")
            print(f"api_requests         : {client.api_requests}")
            print(f"cache_hits           : {client.cache_hits}")
            print(f"failures_after_retry : {client.failures_after_retry}")
            print()
            print(f"unique Q-IDs touched : {len(all_qids)}")
            print(f"cache rows total     : {cache.row_count()}")
            print(f"  search             : {cache.row_count('search')}")
            print(f"  labels_aliases     : {cache.row_count('labels_aliases')}")
            print(f"  types              : {cache.row_count('types')}")
            print(f"  bio_facts          : {cache.row_count('bio_facts')}")


if __name__ == "__main__":
    asyncio.run(main())
