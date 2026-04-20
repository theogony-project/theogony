"""
WikidataCache — persistent SQLite-backed read-through cache for WikidataClient.

W6 etappe (PR #33). Wikidata is the dominant bottleneck for repeat
ingest workloads: ``query.wikidata.org`` throttles aggressively at
Hedin scale, and the existing :class:`WikidataClient` explicitly does
not cache between calls. This module persists the four read operations
the client exposes — :meth:`WikidataClient.search`,
:meth:`WikidataClient.fetch_labels_aliases`,
:meth:`WikidataClient.fetch_types`,
:meth:`WikidataClient.fetch_bio_facts` — into a single local SQLite
file, so reruns of the same corpus and overlapping corpora reuse the
prior network work.

Design points (W6 brief, §A–§G):

- **One SQLite file**, default
  ``settings.data_dir / "wikidata_cache.sqlite"``. Same pattern as
  :class:`~theogony.extraction.audit.ExtractionAuditLog`: no extra
  service, no daemon, inspectable with ``sqlite3``.
- **One generic table** ``wikidata_cache(namespace, cache_key, payload, created_at)``.
  Per-method ``namespace`` keeps key spaces disjoint; deterministic
  key normalisation (mention casefold + whitespace collapse, sorted
  language tuple, plain Q-ID) keeps the schema readable from the
  CLI and makes mismatches easy to debug.
- **Per-item granularity for batched methods.** ``fetch_labels_aliases``,
  ``fetch_types``, and ``fetch_bio_facts`` are all naturally partial-hit:
  if 49 of 50 Q-IDs are cached the client should fetch only the miss.
  The cache stores one row per (Q-ID, language-set) / Q-ID /
  (Q-ID, language) so the client can do exactly that.
- **Successful payloads only.** Transport errors, retryable HTTP
  failures (429/502/503/504), and parse failures are *not* written to
  the cache — the caller (:class:`WikidataClient`) checks the cache
  before calling the API and writes back only after a clean,
  successfully-parsed payload. Empty-success results (Wikidata
  cleanly answered "nothing found") are cached so we do not re-probe
  invalid Q-IDs on every run.
- **No active expiry.** Plan §3.4 properties — labels, aliases, P31,
  the five Stage-4 properties — are stable enough at our current
  workflow scale. The cache is manually deletable by removing the
  SQLite file. PHX-0033 will eventually supersede this for serious
  offline operation.

What this module deliberately does NOT do:

- It does not interpret payloads. It is a JSON blob store keyed by a
  small handful of normalisations.
- It does not cache HTTP errors or transient failures. Those re-raise
  from :class:`WikidataClient` so the resolver / pipeline can decide
  what to do.
- It does not invalidate or warm. PHX-0033 owns the next step toward
  curated subsets / mirrors.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from theogony.config.logging import get_logger
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate

log = get_logger("extraction.wikidata_cache")


# Namespaces — one per cached operation. Disjoint key spaces; bumping
# the namespace string is the cheapest forward-compatible "invalidate
# everything cached for this method" lever if a future schema break
# forces it.
_NS_SEARCH = "search"
_NS_LABELS_ALIASES = "labels_aliases"
_NS_TYPES = "types"
_NS_BIO_FACTS = "bio_facts"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS wikidata_cache (
    namespace   TEXT NOT NULL,
    cache_key   TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (namespace, cache_key)
);

CREATE INDEX IF NOT EXISTS wikidata_cache_namespace_idx
    ON wikidata_cache (namespace);
"""


class WikidataCache:
    """Persistent SQLite-backed cache for the four :class:`WikidataClient` reads.

    Use as a context manager so the underlying SQLite connection
    closes on exit, mirroring :class:`ExtractionAuditLog`::

        with WikidataCache(path="data/wikidata_cache.sqlite") as cache:
            client = WikidataClient(cache=cache)
            ...

    Concurrency: every method that touches the database acquires an
    internal :class:`RLock`, and SQLite runs in WAL mode for on-disk
    paths. Concurrent ingest tasks at Plan §4.1 concurrency (8) write
    serialised; at our cache write volumes (a few hundred per ingest)
    the contention is negligible.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path: Path | None = Path(path) if path != ":memory:" else None
        self._memory_target: str = ":memory:"
        if path == ":memory:":
            self._memory_target = str(path)
        self._conn: sqlite3.Connection | None = None
        self._lock = RLock()

    # ------------------------------------------------------------------ search

    def get_search(
        self,
        mention: str,
        *,
        language: str,
        limit: int,
    ) -> list[WikidataCandidate] | None:
        """Return cached :meth:`WikidataClient.search` candidates for this key.

        ``None`` means "not in cache" — the client should call upstream.
        An empty list means "cached empty-success result" — the client
        must skip the upstream call.
        """
        key = _key_search(mention, language=language, limit=limit)
        payload = self._get(_NS_SEARCH, key)
        if payload is None:
            return None
        raw = json.loads(payload)
        return [WikidataCandidate.model_validate(item) for item in raw]

    def put_search(
        self,
        mention: str,
        *,
        language: str,
        limit: int,
        candidates: list[WikidataCandidate],
    ) -> None:
        """Cache one :meth:`WikidataClient.search` result."""
        key = _key_search(mention, language=language, limit=limit)
        payload = json.dumps([c.model_dump(mode="json") for c in candidates])
        self._put(_NS_SEARCH, key, payload)

    # ----------------------------------------------------------- labels_aliases

    def get_labels_aliases(
        self,
        qid: str,
        *,
        languages: Iterable[str],
    ) -> dict[str, list[str]] | None:
        """Return cached label-and-aliases for one Q-ID and a language set.

        Keyed per Q-ID and per *canonicalised* language tuple, so a
        partial-batch hit pattern works: of N requested Q-IDs, only
        the misses go upstream.
        """
        key = _key_labels_aliases(qid, languages=languages)
        payload = self._get(_NS_LABELS_ALIASES, key)
        if payload is None:
            return None
        raw = json.loads(payload)
        return {lang: list(strings) for lang, strings in raw.items()}

    def put_labels_aliases(
        self,
        qid: str,
        *,
        languages: Iterable[str],
        per_language: dict[str, list[str]],
    ) -> None:
        key = _key_labels_aliases(qid, languages=languages)
        payload = json.dumps(per_language)
        self._put(_NS_LABELS_ALIASES, key, payload)

    # -------------------------------------------------------------------- types

    def get_types(self, qid: str) -> set[str] | None:
        """Return cached ``wdt:P31`` set for ``qid`` (``None`` if not cached)."""
        payload = self._get(_NS_TYPES, qid)
        if payload is None:
            return None
        raw = json.loads(payload)
        return set(raw)

    def put_types(self, qid: str, *, types: set[str]) -> None:
        # Stored sorted so the on-disk JSON is byte-stable per Q-ID
        # (handy when humans diff cache contents during debugging).
        payload = json.dumps(sorted(types))
        self._put(_NS_TYPES, qid, payload)

    # ---------------------------------------------------------------- bio_facts

    def get_bio_facts(self, qid: str, *, language: str) -> BioFacts | None:
        """Return cached :class:`BioFacts` for ``(qid, language)``."""
        key = _key_bio_facts(qid, language=language)
        payload = self._get(_NS_BIO_FACTS, key)
        if payload is None:
            return None
        return BioFacts.model_validate_json(payload)

    def put_bio_facts(self, qid: str, *, language: str, facts: BioFacts) -> None:
        key = _key_bio_facts(qid, language=language)
        self._put(_NS_BIO_FACTS, key, facts.model_dump_json())

    # ---------------------------------------------------------------- internals

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            target = str(self._path)
        else:
            target = self._memory_target
        # check_same_thread=False: same rationale as ExtractionAuditLog;
        # the RLock above is what actually serialises writes for the
        # ingest tasks, and a rare asyncio.to_thread wrapper must not
        # hit a "different thread" sqlite3 error.
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if self._path is not None:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        self._conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._ensure_conn().cursor()
            try:
                yield cur
            finally:
                cur.close()

    def _get(self, namespace: str, cache_key: str) -> str | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT payload FROM wikidata_cache WHERE namespace = ? AND cache_key = ?",
                (namespace, cache_key),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return str(row["payload"])

    def _put(self, namespace: str, cache_key: str, payload: str) -> None:
        ts = datetime.now(UTC).isoformat()
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO wikidata_cache "
                "(namespace, cache_key, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (namespace, cache_key, payload, ts),
            )
            self._ensure_conn().commit()

    # ---------------------------------------------------------------- maintenance

    def row_count(self, namespace: str | None = None) -> int:
        """Number of cached rows, optionally filtered by namespace.

        Used by tests and ad-hoc inspection. Not part of the read-through
        cache contract; the client never calls this.
        """
        with self._cursor() as cur:
            if namespace is None:
                cur.execute("SELECT COUNT(*) FROM wikidata_cache")
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM wikidata_cache WHERE namespace = ?",
                    (namespace,),
                )
            return int(cur.fetchone()[0])

    # ---------------------------------------------------------------- lifecycle

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> WikidataCache:
        self._ensure_conn()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ============================================================ key normalisation


def _normalise_mention(mention: str) -> str:
    """Casefold + collapse internal whitespace.

    The brief asks for "fully normalised mention string" so that
    "Sven Hedin", "sven hedin", and "Sven  Hedin" share one cache
    entry. Wikidata's ``wbsearchentities`` is case- and
    whitespace-tolerant, so collapsing here only collapses keys —
    it never loses information the upstream API would have
    distinguished.
    """
    return " ".join(mention.split()).casefold()


def _canon_languages(languages: Iterable[str]) -> tuple[str, ...]:
    """Sort + dedup language codes for a stable, order-insensitive key."""
    return tuple(sorted({code.strip() for code in languages if code.strip()}))


def _key_search(mention: str, *, language: str, limit: int) -> str:
    """Cache key for :meth:`WikidataClient.search`.

    Format: ``<lang>|<limit>|<normalised_mention>``. Lang first so a
    range scan over the index by language is grep-able from the
    SQLite CLI when humans poke at the cache.
    """
    return f"{language}|{int(limit)}|{_normalise_mention(mention)}"


def _key_labels_aliases(qid: str, *, languages: Iterable[str]) -> str:
    """Cache key for one Q-ID's labels-plus-aliases at a language set."""
    canon = _canon_languages(languages)
    return f"{qid}|{','.join(canon)}"


def _key_bio_facts(qid: str, *, language: str) -> str:
    return f"{qid}|{language}"


__all__ = ["WikidataCache"]
