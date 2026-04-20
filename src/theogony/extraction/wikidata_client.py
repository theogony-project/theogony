"""
WikidataClient — thin async surface over the three Wikidata endpoints
EntityResolver Stages 1–3 need (Plan §3.4 v3).

Three operations, three endpoints:

1. ``search(mention, language)`` — calls the MediaWiki action API
   ``wbsearchentities`` (Plan §3.4 Stage 1: multi-language candidate
   gathering). Returns up to ``limit`` candidates per language.

2. ``fetch_labels_aliases(qids, languages)`` — calls ``wbgetentities``
   with ``props=labels|aliases`` (Plan §3.4 Stage 2: alias matching
   needs the canonical label-plus-aliases set per language). Batched
   up to 50 IDs per request — the API's documented per-call limit.

3. ``fetch_types(qids)`` — single SPARQL ``VALUES``-batched query
   asking for ``wdt:P31`` of each Q-ID (Plan §3.4 Stage 3: type-pass
   filter). Batched up to 50 IDs per query — comfortably under the
   60-req/min SPARQL rate limit even at full ingest concurrency.

Politeness (mirrors :class:`~theogony.acquisition.gutenberg.GutenbergAdapter`):

- Descriptive User-Agent identifying Theogony with a contact URL.
  Required by Wikidata; anonymous calls without User-Agent are
  blocked at the WAF.
- Configurable per-request delay (default 0.1 s, much shorter than
  the 2 s for Gutenberg downloads — Wikidata's API allows higher
  throughput and we have ~2000 calls per book vs. one).
- Exponential-backoff retry on 429 / 502 / 503 / 504.
- Lazy ``httpx.AsyncClient`` creation; ``aclose`` on context exit.

What this module deliberately does NOT do:

- It does not interpret Wikidata payloads beyond the cheapest
  defensible projection. The full :class:`WikidataCandidate` carries
  the structural fields the resolver needs; richer reasoning lives
  in EntityResolver and (E3) the LLM disambiguator.
- It does not fetch biographical facts (``P569``, ``P570``, ``P106``,
  ``P19``, ``P937``). That is Stage 4 work, deferred to E3 with the
  ``BookContextExtractor`` and Stage-4 LLM disambiguation.

Persistent caching (W6, PR #33)
-------------------------------

When constructed with a :class:`~theogony.extraction.wikidata_cache.WikidataCache`,
the client transparently consults the cache before issuing any of the
four read operations and writes successful payloads back. Partial-hit
methods (``fetch_labels_aliases``, ``fetch_types``, ``fetch_bio_facts``)
fan misses through to upstream while still serving cached items. The
client also exposes lifetime counters — ``api_requests``,
``cache_hits``, ``failures_after_retry`` — that the
:class:`~theogony.extraction.pipeline.IngestionPipeline` snapshots into
``IngestRunReport.resolution`` so reports finally tell the truth about
network use rather than reporting hard-coded zeros.

The cache is opt-in: passing ``cache=None`` (the default) preserves
the no-cache behaviour the resolver tests rely on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from theogony import __version__
from theogony.config.logging import get_logger

if TYPE_CHECKING:
    # Imported lazily for typing only; ``wikidata_cache`` re-imports
    # ``WikidataCandidate`` and ``BioFacts`` from this module, so a
    # runtime import here would form a cycle.
    from theogony.extraction.wikidata_cache import WikidataCache

log = get_logger("extraction.wikidata_client")


DEFAULT_API_URL = "https://www.wikidata.org/w/api.php"
DEFAULT_SPARQL_URL = "https://query.wikidata.org/sparql"
DEFAULT_USER_AGENT = (
    f"theogony/{__version__} "
    "(+https://github.com/theogony-project/theogony; "
    "open knowledge infrastructure)"
)
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_INTER_REQUEST_DELAY_S = 0.1  # well under any Wikidata limit at concurrency 8
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_S = 1.0
DEFAULT_BATCH_SIZE = 50  # wbgetentities and SPARQL VALUES both cope with 50

_RETRYABLE_STATUS = {429, 502, 503, 504}


class WikidataCandidate(BaseModel):
    """A single Q-ID candidate as returned by ``wbsearchentities``.

    Slim by design — the resolver enriches with aliases and P31 types
    in subsequent stages. ``label`` and ``description`` come from
    the search response in the queried language; ``match_text`` is the
    specific alias that matched (when ``wbsearchentities`` returns it,
    which is most of the time).
    """

    model_config = ConfigDict(extra="forbid")

    qid: str = Field(pattern=r"^Q\d+$")
    label: str | None = None
    description: str | None = None
    match_text: str | None = None
    """The specific alias the search engine matched on. ``None`` for
    candidates returned without an explicit alias annotation (e.g. when
    the match is the canonical label itself)."""
    language: str
    """ISO 639-1 code of the language the search was issued in."""


class BioFacts(BaseModel):
    """Biographical fingerprint for a Q-ID (Plan §3.4 Stage 4).

    The five properties Plan §3.4 lists for disambiguating people
    (P569 birth, P570 death, P106 occupation, P19 birth place,
    P937 work location). Date fields are kept as raw Wikidata
    literal strings (e.g. ``"1865-02-19T00:00:00Z"``); place /
    occupation fields carry their human-readable labels in the
    SPARQL query's language (default ``en``).

    Empty lists / ``None`` fields are honest emptiness — the entity
    has no statement for that property in Wikidata. The resolver
    treats a candidate with *all* fields empty as "no facts" and
    routes it to Tier 1 (sentence-context-only) instead of Tier 2.
    """

    model_config = ConfigDict(extra="forbid")

    qid: str = Field(pattern=r"^Q\d+$")
    birth_date: str | None = None
    death_date: str | None = None
    birth_place: str | None = None
    occupations: list[str] = Field(default_factory=list)
    work_locations: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True iff none of the five Stage-4 properties has a value.

        EntityResolver uses this to choose between Tier 2 (bio facts
        available) and Tier 1 (no bio facts).
        """
        return (
            self.birth_date is None
            and self.death_date is None
            and self.birth_place is None
            and not self.occupations
            and not self.work_locations
        )

    def to_prompt_block(self) -> str:
        """Render as a compact, prompt-ready block for Stage 4.

        Stable format across all candidates so the LLM does not see
        different wrappers per entry. Empty fields are omitted to
        avoid suggesting facts that do not exist.
        """
        lines: list[str] = []
        if self.birth_date or self.death_date:
            lifespan = " – ".join(d for d in (self.birth_date, self.death_date) if d)
            lines.append(f"lifespan: {lifespan}")
        if self.birth_place:
            lines.append(f"born in: {self.birth_place}")
        if self.occupations:
            lines.append("occupation: " + ", ".join(self.occupations))
        if self.work_locations:
            lines.append("worked in: " + ", ".join(self.work_locations))
        if not lines:
            return f"  {self.qid}: (no biographical facts in Wikidata)"
        return f"  {self.qid}:\n" + "\n".join(f"    {ln}" for ln in lines)


class WikidataClient:
    """Async client for the three Wikidata endpoints E2 needs.

    Use as a context manager so the underlying HTTP client closes::

        async with WikidataClient() as client:
            cands = await client.search("Sven Hedin", language="en")
            ...

    Or inject an ``httpx.AsyncClient`` (e.g. for connection-pool
    sharing across adapters)::

        async with httpx.AsyncClient() as http:
            client = WikidataClient(client=http)
            ...
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        cache: WikidataCache | None = None,
        api_url: str = DEFAULT_API_URL,
        sparql_url: str = DEFAULT_SPARQL_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        inter_request_delay_s: float = DEFAULT_INTER_REQUEST_DELAY_S,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._api_url = api_url
        self._sparql_url = sparql_url
        self._user_agent = user_agent
        self._timeout_s = timeout_s
        self._inter_request_delay_s = inter_request_delay_s
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_s = retry_backoff_s
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive; got {batch_size}")
        self._batch_size = batch_size
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None
        self._cache = cache
        # Lifetime counters (W6 brief §D). One client instance, one
        # set of counters; the IngestionPipeline takes a delta around
        # the resolve stage so per-run reports stay honest even when
        # a single client services many ingests.
        #
        # - api_requests:        upstream HTTP calls actually issued
        #                        after a cache miss.
        # - cache_hits:          *logical items* served from cache
        #                        (one search result, one Q-ID's
        #                        labels-aliases entry, one Q-ID's P31
        #                        set, one (Q-ID, lang) bio-facts row),
        #                        not raw SQL lookups.
        # - failures_after_retry: upstream requests that still failed
        #                        after every retry was exhausted.
        self.api_requests: int = 0
        self.cache_hits: int = 0
        self.failures_after_retry: int = 0

    # ------------------------------------------------------------------ public

    async def search(
        self,
        mention: str,
        *,
        language: str,
        limit: int = 10,
    ) -> list[WikidataCandidate]:
        """Stage 1: ``wbsearchentities`` for a single mention in one language.

        Returns up to ``limit`` candidates. Empty list when the search
        returns no hits or when ``mention`` is empty / whitespace.
        """
        if not mention.strip() or limit <= 0:
            return []
        if self._cache is not None:
            cached = self._cache.get_search(mention, language=language, limit=limit)
            if cached is not None:
                self.cache_hits += 1
                return cached
        client = self._ensure_client()
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "search": mention,
            "language": language,
            "type": "item",
            "limit": str(limit),
            "uselang": language,
        }
        await self._respect_rate_limit()
        response = await self._request_with_retry(client, "GET", self._api_url, params=params)
        payload = response.json()
        hits = payload.get("search", []) or []
        candidates: list[WikidataCandidate] = []
        for hit in hits:
            qid = hit.get("id")
            if not isinstance(qid, str) or not qid.startswith("Q"):
                continue
            match_block = hit.get("match") if isinstance(hit.get("match"), dict) else None
            match_text = match_block.get("text") if match_block else None
            candidates.append(
                WikidataCandidate(
                    qid=qid,
                    label=hit.get("label"),
                    description=hit.get("description"),
                    match_text=match_text,
                    language=language,
                )
            )
        # Cache the parsed-and-validated payload only — never the raw
        # transport response. Empty-success ("Wikidata cleanly answered
        # 'no hits'") is cached intentionally so identical reruns
        # short-circuit instead of probing upstream for every miss.
        if self._cache is not None:
            self._cache.put_search(mention, language=language, limit=limit, candidates=candidates)
        return candidates

    async def search_multi_language(
        self,
        mention: str,
        *,
        languages: Iterable[str],
        limit: int = 10,
    ) -> dict[str, list[WikidataCandidate]]:
        """Stage 1: ``wbsearchentities`` in parallel across multiple languages.

        Returns ``{language: [candidates...]}``. The resolver then
        intersects / unions across languages to derive Plan §3.4
        Stage 1's "candidate set per mention".
        """
        langs = list(languages)
        if not langs:
            return {}
        coros = [self.search(mention, language=lang, limit=limit) for lang in langs]
        results = await asyncio.gather(*coros)
        return dict(zip(langs, results, strict=True))

    async def fetch_labels_aliases(
        self,
        qids: Iterable[str],
        *,
        languages: Iterable[str],
    ) -> dict[str, dict[str, list[str]]]:
        """Stage 2: ``wbgetentities`` for labels-plus-aliases in many languages.

        Returns ``{qid: {language: [label, alias_1, alias_2, ...]}}``.
        The label sits at index 0 of each language's list; the rest
        are aliases in the order Wikidata returned them. Languages
        with no label *and* no alias for a given Q-ID get an empty
        list (not absent — explicit emptiness is easier for callers
        to reason about).

        Batched up to ``batch_size`` Q-IDs per HTTP call. Q-IDs not
        returned by Wikidata (e.g. invalid IDs) are silently absent
        from the result.
        """
        qid_list = [q for q in qids if q]
        lang_list = list(languages)
        if not qid_list or not lang_list:
            return {}
        out: dict[str, dict[str, list[str]]] = {}
        # Per-Q-ID cache lookup. Keying per (qid, canonical-language-set)
        # is what makes 49-of-50 partial hits actually cheap: misses fan
        # through to the existing batched HTTP path; hits never touch
        # the wire. The brief calls this out explicitly under §B.
        misses: list[str] = []
        if self._cache is not None:
            for qid in qid_list:
                cached = self._cache.get_labels_aliases(qid, languages=lang_list)
                if cached is not None:
                    out[qid] = cached
                    self.cache_hits += 1
                else:
                    misses.append(qid)
        else:
            misses = list(qid_list)
        if not misses:
            return out
        client = self._ensure_client()
        for batch in _chunks(misses, self._batch_size):
            params = {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "labels|aliases",
                "languages": "|".join(lang_list),
            }
            await self._respect_rate_limit()
            response = await self._request_with_retry(client, "GET", self._api_url, params=params)
            payload = response.json()
            entities: Mapping[str, Any] = payload.get("entities", {})
            for qid, entity in entities.items():
                per_lang: dict[str, list[str]] = {}
                labels = entity.get("labels", {}) if isinstance(entity, dict) else {}
                aliases = entity.get("aliases", {}) if isinstance(entity, dict) else {}
                for lang in lang_list:
                    lang_strings: list[str] = []
                    label_block = labels.get(lang)
                    if isinstance(label_block, dict):
                        label_value = label_block.get("value")
                        if isinstance(label_value, str) and label_value:
                            lang_strings.append(label_value)
                    alias_block = aliases.get(lang, [])
                    if isinstance(alias_block, list):
                        for alias_entry in alias_block:
                            if isinstance(alias_entry, dict):
                                value = alias_entry.get("value")
                                if isinstance(value, str) and value:
                                    lang_strings.append(value)
                    per_lang[lang] = lang_strings
                out[qid] = per_lang
                if self._cache is not None:
                    self._cache.put_labels_aliases(qid, languages=lang_list, per_language=per_lang)
        return out

    async def fetch_bio_facts(
        self,
        qids: Iterable[str],
        *,
        language: str = "en",
    ) -> dict[str, BioFacts]:
        """Stage 4: biographical fingerprints batched via SPARQL.

        Issues one SPARQL query per ``batch_size``-sized chunk of
        Q-IDs covering the five properties Plan §3.4 lists for
        disambiguation:

            P569 (date of birth), P570 (date of death),
            P106 (occupation), P19 (place of birth),
            P937 (work location)

        Returns ``{qid: BioFacts}``. Q-IDs absent from the response
        (e.g. invalid Q-ID, network glitch) get an *empty* :class:`BioFacts`
        rather than being missing — easier for the resolver to reason
        about uniformly. Use :attr:`BioFacts.is_empty` to detect "no
        facts" downstream.

        Per-property OPTIONAL clauses produce a Cartesian product when
        properties are multi-valued (occupation ∪ work_location can
        return many rows per item); the result-merging loop below
        deduplicates labels into the per-Q-ID lists.

        Cost: ~5–10 SPARQL queries per typical book (Plan §4.1 v3).
        Comfortably inside Wikidata's 60-req/min SPARQL endpoint
        limit even at full ingest concurrency.
        """
        qid_list = [q for q in qids if q]
        if not qid_list:
            return {}
        out: dict[str, BioFacts] = {qid: BioFacts(qid=qid) for qid in qid_list}
        misses: list[str] = []
        if self._cache is not None:
            for qid in qid_list:
                cached = self._cache.get_bio_facts(qid, language=language)
                if cached is not None:
                    out[qid] = cached
                    self.cache_hits += 1
                else:
                    misses.append(qid)
        else:
            misses = list(qid_list)
        if not misses:
            return out
        client = self._ensure_client()
        # Track per-Q-ID dedup sets for multi-valued fields.
        occupations_set: dict[str, set[str]] = {qid: set() for qid in misses}
        work_locations_set: dict[str, set[str]] = {qid: set() for qid in misses}
        for batch in _chunks(misses, self._batch_size):
            values_clause = " ".join(f"wd:{q}" for q in batch)
            query = (
                "SELECT ?item ?birth ?death ?occupationLabel "
                "?birthPlaceLabel ?workLocationLabel WHERE { "
                f"VALUES ?item {{ {values_clause} }} "
                "OPTIONAL { ?item wdt:P569 ?birth } "
                "OPTIONAL { ?item wdt:P570 ?death } "
                "OPTIONAL { ?item wdt:P106 ?occupation } "
                "OPTIONAL { ?item wdt:P19 ?birthPlace } "
                "OPTIONAL { ?item wdt:P937 ?workLocation } "
                "SERVICE wikibase:label { "
                f'bd:serviceParam wikibase:language "{language}" '
                "} "
                "}"
            )
            await self._respect_rate_limit()
            response = await self._request_with_retry(
                client,
                "POST",
                self._sparql_url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            payload = response.json()
            bindings = (payload.get("results") or {}).get("bindings", []) or []
            for binding in bindings:
                bound_qid = _qid_from_uri((binding.get("item") or {}).get("value", ""))
                if not bound_qid or bound_qid not in out:
                    continue
                fact = out[bound_qid]
                # Birth / death dates: literal values, take the first
                # non-empty reading (multiple statements rare; if they
                # exist Wikidata's ranking already gives us "preferred").
                birth = (binding.get("birth") or {}).get("value")
                if birth and fact.birth_date is None:
                    fact.birth_date = birth
                death = (binding.get("death") or {}).get("value")
                if death and fact.death_date is None:
                    fact.death_date = death
                # Birth place label: same logic — first wins.
                bp = (binding.get("birthPlaceLabel") or {}).get("value")
                if bp and fact.birth_place is None:
                    fact.birth_place = bp
                # Multi-valued: dedup via set, materialise into list at end.
                occ = (binding.get("occupationLabel") or {}).get("value")
                if occ:
                    occupations_set[bound_qid].add(occ)
                wl = (binding.get("workLocationLabel") or {}).get("value")
                if wl:
                    work_locations_set[bound_qid].add(wl)
        # Materialise dedup sets into sorted lists for stable output.
        # Touch only the Q-IDs we actually fetched — cache hits keep
        # their already-populated occupations / work_locations.
        for qid in misses:
            out[qid].occupations = sorted(occupations_set[qid])
            out[qid].work_locations = sorted(work_locations_set[qid])
            if self._cache is not None:
                self._cache.put_bio_facts(qid, language=language, facts=out[qid])
        return out

    async def fetch_types(self, qids: Iterable[str]) -> dict[str, set[str]]:
        """Stage 3: ``wdt:P31`` (instance-of) per Q-ID, batched via SPARQL.

        Returns ``{qid: {p31_qid_1, p31_qid_2, ...}}``. Q-IDs with no
        P31 statements get an empty set (not absent). The SPARQL
        ``VALUES`` clause batches up to ``batch_size`` Q-IDs per
        request — well within the SPARQL endpoint's 60-req/min limit.
        """
        qid_list = [q for q in qids if q]
        if not qid_list:
            return {}
        # Initialise every *requested* QID to an empty set so callers
        # see an explicit "no P31 for this entity" rather than KeyError.
        out: dict[str, set[str]] = {qid: set() for qid in qid_list}
        # Per-Q-ID cache lookup, partial-hit-friendly.
        misses: list[str] = []
        if self._cache is not None:
            for qid in qid_list:
                cached = self._cache.get_types(qid)
                if cached is not None:
                    out[qid] = set(cached)
                    self.cache_hits += 1
                else:
                    misses.append(qid)
        else:
            misses = list(qid_list)
        if not misses:
            return out
        client = self._ensure_client()
        # Track which Q-IDs were successfully covered by upstream so we
        # can write empty-success rows for those that came back with
        # no P31 binding (e.g. a brand-new entity stub). This keeps
        # reruns from re-probing them.
        miss_set = set(misses)
        for batch in _chunks(misses, self._batch_size):
            values_clause = " ".join(f"wd:{q}" for q in batch)
            query = (
                "SELECT ?item ?type WHERE { "
                f"VALUES ?item {{ {values_clause} }} "
                "?item wdt:P31 ?type . "
                "}"
            )
            await self._respect_rate_limit()
            response = await self._request_with_retry(
                client,
                "POST",
                self._sparql_url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            payload = response.json()
            bindings = (payload.get("results") or {}).get("bindings", []) or []
            for binding in bindings:
                item_uri = (binding.get("item") or {}).get("value", "")
                type_uri = (binding.get("type") or {}).get("value", "")
                bound_qid = _qid_from_uri(item_uri)
                type_qid = _qid_from_uri(type_uri)
                if bound_qid and type_qid and bound_qid in out:
                    out[bound_qid].add(type_qid)
            if self._cache is not None:
                # Only cache Q-IDs in this batch — partial batch failure
                # would otherwise risk caching empties for un-fetched
                # Q-IDs. (Failures here actually raise above; this is
                # belt-and-braces.)
                for qid in batch:
                    if qid in miss_set:
                        self._cache.put_types(qid, types=out[qid])
        return out

    # ------------------------------------------------------------- lifecycle

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> WikidataClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # --------------------------------------------------------------- internals

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_s,
                follow_redirects=True,
            )
        return self._client

    async def _respect_rate_limit(self) -> None:
        if self._inter_request_delay_s <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if self._last_request_at is not None:
                deficit = self._inter_request_delay_s - (now - self._last_request_at)
                if deficit > 0:
                    await asyncio.sleep(deficit)
            self._last_request_at = loop.time()

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        # ``api_requests`` increments once per logical upstream attempt
        # (per call to this method), not once per retry — the brief
        # under §D defines it as "actual upstream HTTP calls made
        # after cache misses", which we read as "logical operations
        # routed to upstream", so retries of the same operation do
        # not double-count.
        self.api_requests += 1
        last_exc: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                wait = self._retry_backoff_s * (2 ** (attempt - 1))
                log.warning(
                    "wikidata transport error url=%s attempt=%d/%d err=%s — retrying in %.1fs",
                    url,
                    attempt,
                    self._retry_attempts,
                    exc,
                    wait,
                )
                if attempt < self._retry_attempts:
                    await asyncio.sleep(wait)
                continue
            if response.status_code in _RETRYABLE_STATUS:
                wait = self._retry_backoff_s * (2 ** (attempt - 1))
                log.warning(
                    "wikidata retryable status=%d url=%s attempt=%d/%d — retrying in %.1fs",
                    response.status_code,
                    url,
                    attempt,
                    self._retry_attempts,
                    wait,
                )
                if attempt < self._retry_attempts:
                    await asyncio.sleep(wait)
                    continue
                # Exhausted retries on a retryable status: fall through
                # the loop so the post-loop block increments
                # ``failures_after_retry`` once before re-raising.
                break
            response.raise_for_status()
            return response
        # Either every attempt raised a transport error, or every
        # attempt came back with a retryable status. Both are
        # "failure_after_retry" by the brief's §D definition.
        self.failures_after_retry += 1
        if last_exc is not None:
            raise last_exc
        # All attempts returned a retryable status; raise the most
        # recent response to surface the failure.
        assert response is not None  # noqa: S101 — invariant: loop ran ≥ once
        response.raise_for_status()
        return response


# ---------------------------------------------------------------- helpers


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    """Yield successive ``size``-length chunks from ``items``.

    Local helper rather than ``itertools.batched`` (3.12+) so the
    function is unit-testable and the module's chunking discipline
    is in one place.
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _qid_from_uri(uri: str) -> str | None:
    """Extract ``Q\\d+`` from a Wikidata entity URI.

    Wikidata SPARQL responses return entity URIs like
    ``http://www.wikidata.org/entity/Q42``. We pull the trailing
    ``Q42`` so callers work in Q-IDs throughout. Returns ``None``
    when the URI does not look like a Wikidata entity URI — defensive
    against responses that include statement URIs etc. by mistake.
    """
    if not uri:
        return None
    tail = uri.rsplit("/", 1)[-1]
    if tail.startswith("Q") and tail[1:].isdigit():
        return tail
    return None


__all__ = [
    "DEFAULT_API_URL",
    "DEFAULT_SPARQL_URL",
    "DEFAULT_USER_AGENT",
    "BioFacts",
    "WikidataCandidate",
    "WikidataClient",
]
