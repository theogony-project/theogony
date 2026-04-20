"""
EntityResolver — Wikidata alignment for NER mentions (Plan §3.4 v3).

E2 scope: Stages 1-3 of the five-stage pipeline plus the Tier-4/3/0
honest-failure path.
E3 scope: Stage 4 LLM disambiguation with biographical facts and
``BookContext``, plus Tier 2 / Tier 1 minting. When constructed
without an ``llm`` argument the resolver behaves exactly as in E2.

Pipeline per mention:

1. **Stage 1 — multi-language search.** Fan out ``wbsearchentities``
   in parallel across the configured languages (default: en, de, fr,
   it). The union of returned Q-IDs is the candidate set; per-language
   appearance is recorded for the Tier-4 "EXACT in ≥ 2 languages"
   check.

2. **Stage 2 — alias matching.** Fetch labels-plus-aliases for every
   candidate via ``wbgetentities``. For each (candidate, language)
   pair, compute the strongest alias-match strength against the
   mention surface form. EXACT hits are the Tier-4 signal; CASE/
   WHITESPACE/NORMALISED hits feed Tier 3.

3. **Stage 3 — type filter.** Fetch ``wdt:P31`` for every candidate
   via SPARQL. A candidate survives when its types intersect the
   acceptable-types frozenset for the mention's NER label
   (:func:`acceptable_wikidata_types`). For ``PRODUCT`` and ``LAW``
   the acceptable set is empty — that is documented to mean
   "no type filter, accept anything".

4. **Stage 4 — LLM disambiguation with bio facts** (E3, only when an
   ``llm`` is configured). Triggered when Stages 1-3 leave at least
   one survivor but Tier 4/3 conditions are not met. Fetches the five
   Plan-§3.4 properties (P569/P570/P106/P19/P937) for each survivor,
   builds a structured prompt with the source mention + sentence
   context + ``BookContext`` + each candidate's bio facts, and asks
   the LLM to pick a Q-ID or refuse (chosen=null).

5. **Tier assignment** (Plan §3.4):

   - **Tier 4** (confidence 0.90): exactly one candidate survives
     Stage 3 *and* it has an EXACT alias match in ≥ 2 distinct
     languages.
   - **Tier 3** (confidence 0.75): at least one candidate survives
     Stage 3, the best-ranked candidate has CASE-or-better matches
     in ≥ 2 languages. Best-rank = (most languages with ≥CASE
     match, then most languages where the candidate appeared in
     wbsearchentities, then lexicographic Q-ID for determinism).
   - **Tier 2** (confidence 0.65, E3): Stage 4 LLM disambiguation
     succeeded *and* at least one survivor had non-empty
     :class:`~theogony.extraction.wikidata_client.BioFacts`.
   - **Tier 1** (confidence 0.55, E3): Stage 4 LLM disambiguation
     succeeded but every survivor had empty bio facts (LLM had only
     sentence context to work with).
   - **Tier 0** (confidence 0.50): no Q-ID assigned. Mints an
     ``AKA-…`` node with ``manual_resolution_needed=True`` and
     ``properties["wikidata_failure_reason"]`` recording why.

The resolver is **stateless and concurrency-safe**: any number of
``resolve`` / ``resolve_many`` calls can run in parallel against the
same instance, bounded by the underlying ``WikidataClient``'s
politeness lock.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.agents.llm import LLMProvider
from theogony.config.logging import get_logger
from theogony.core.model import KnowledgeNode, NodeScores, SourceRef
from theogony.extraction.alias_matcher import AliasMatchStrength, best_match, fully_normalise
from theogony.extraction.audit import ExtractionAuditLog
from theogony.extraction.book_context import BookContext
from theogony.extraction.ner import Mention
from theogony.extraction.sentence import Sentence
from theogony.extraction.wikidata_client import BioFacts, WikidataCandidate, WikidataClient
from theogony.extraction.wikidata_types import (
    acceptable_wikidata_types,
    is_resolvable,
    node_type_for_ner_label,
)

log = get_logger("extraction.resolve")


_AUDIT_STAGE_STAGE4 = "stage4_disambiguation"


DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "de", "fr", "it")
DEFAULT_WBSEARCH_LIMIT = 10

TIER_4_CONFIDENCE = 0.90
TIER_3_CONFIDENCE = 0.75
TIER_2_CONFIDENCE = 0.65
TIER_1_CONFIDENCE = 0.55
TIER_0_CONFIDENCE = 0.50


_STAGE4_SYSTEM_PROMPT = (
    "You are a careful entity disambiguator. You read a mention from "
    "a source text together with sentence context, book context, and "
    "a small set of Wikidata candidates with biographical facts. You "
    "pick the single Q-ID that best matches the source — or refuse "
    "if no candidate is a confident match (chosen=null). You answer "
    "ONLY with JSON matching the supplied schema. You never invent "
    "facts about candidates and never invent Q-IDs that were not in "
    "the candidate list."
)

_STAGE4_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "chosen": {
            "type": ["string", "null"],
            "description": (
                "The Q-ID picked from the candidate list, or null when "
                "no candidate is a confident match. Pattern: ^Q\\d+$ "
                "when non-null."
            ),
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Self-rated confidence in the pick (or in the refusal).",
        },
        "reasoning": {
            "type": "string",
            "maxLength": 1000,
            "description": "1-3 sentences justifying the choice (or refusal).",
        },
    },
    "required": ["chosen", "confidence", "reasoning"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------- DTO


class ResolvedMention(BaseModel):
    """Outcome of resolving one or more identical mentions to a single node.

    The same node can be referenced by multiple ``Mention`` instances
    (every occurrence of "Tibet" in a single book deduplicates to one
    ``KnowledgeNode``); the ``mentions`` list holds them all in
    appearance order.
    """

    model_config = ConfigDict(extra="forbid")

    mentions: list[Mention] = Field(
        description="All input Mentions that resolved to this node, in appearance order."
    )
    node: KnowledgeNode = Field(
        description=(
            "The minted node. For Tier 4/3 nodes external_ids carries "
            "{'wikidata': 'Q…'}; for Tier 0 it is empty and "
            "manual_resolution_needed=True."
        )
    )
    tier: int = Field(
        ge=0,
        le=4,
        description=(
            "The five-tier confidence level from Plan §3.4. E2 produces "
            "tiers 4, 3, and 0; tiers 2 and 1 are reserved for E3."
        ),
    )
    chosen_qid: str | None = Field(
        default=None,
        description="The Q-ID assigned (Tier 4/3) or None (Tier 0).",
    )
    candidates_considered: list[str] = Field(
        default_factory=list,
        description=(
            "Q-IDs surfaced by Stage 1 across all languages. Recorded "
            "in node.properties for audit and to support future "
            "re-resolution by Detective Mode."
        ),
    )
    failure_reason: str | None = Field(
        default=None,
        description=(
            "Why a Tier-0 outcome happened. None for Tier 4/3 (the "
            "match itself is the success record)."
        ),
    )


# ---------------------------------------------------------------------------- helpers


def _select_canonical_label(
    mention_text: str,
    qid: str,
    aliases_by_language: dict[str, dict[str, list[str]]],
    preferred_languages: Sequence[str],
) -> str:
    """Pick the human-readable label for a resolved Tier-4/3 node.

    Preference order: first language in ``preferred_languages`` that
    has a Wikidata label for ``qid``. Falls back to the original
    mention text when Wikidata returned nothing — should be impossible
    in practice (we got the Q-ID *because* a wbsearchentities hit
    exists) but the fallback keeps the function total.
    """
    per_lang = aliases_by_language.get(qid, {})
    for lang in preferred_languages:
        labels = per_lang.get(lang) or []
        if labels:
            return labels[0]
    return mention_text


def _representative_mention_text(mentions: Sequence[Mention]) -> str:
    """Most common surface form among the deduplicated mentions, ties broken by first.

    Used as the label for Tier-0 nodes — the node has no Wikidata
    canonical, so we keep the form the source most often used.
    """
    counts: dict[str, int] = {}
    for m in mentions:
        counts[m.text] = counts.get(m.text, 0) + 1
    # max() with a tuple key (count, -first_seen_index) gives the
    # most common form; ties resolved by earliest occurrence.
    first_seen: dict[str, int] = {}
    for i, m in enumerate(mentions):
        first_seen.setdefault(m.text, i)
    return max(counts, key=lambda t: (counts[t], -first_seen[t]))


def _languages_with_strength(
    aliases_by_qid: dict[str, list[str]],
    mention: str,
    minimum: AliasMatchStrength,
) -> set[str]:
    """Languages in which the candidate has an alias match ≥ ``minimum``."""
    out: set[str] = set()
    for lang, aliases in aliases_by_qid.items():
        if best_match(mention, aliases) >= minimum:
            out.add(lang)
    return out


def _rank_key(
    qid: str,
    case_or_better_languages: set[str],
    appearance_count: int,
) -> tuple[int, int, str]:
    """Tier-3 rank key: prefer more languages with ≥CASE match, then more
    wbsearchentities appearances, then lexicographic for determinism.

    Returns a tuple suitable for ``max(..., key=_rank_key)``; higher
    is better. Negation of the Q-ID at the end inverts string sort
    so ``max`` picks the lexicographically *smallest* Q-ID on ties
    (matches the plan's "deterministic, no thrashing" intent — Q42 < Q44).
    """
    # Negate Q-ID by sorting on a transformed value: max() is highest,
    # so we want the smallest Q-ID to be "highest" → negate via reverse.
    # Easiest: store as -qid_ordinal (impossible for str), so pick a
    # different approach: return (lang_count, appearances, "") and
    # add the negation by sorting Q-IDs externally before max().
    # Simpler alternative: include the Q-ID positively but sort
    # candidates by Q-ID ascending first, then take max() — max() is
    # stable and returns the first-seen on ties.
    return (len(case_or_better_languages), appearance_count, qid)


# ---------------------------------------------------------------------------- core


class EntityResolver:
    """Resolve NER mentions to Wikidata Q-IDs (Stages 1-3 always; Stage 4
    when an ``llm`` is configured)."""

    def __init__(
        self,
        *,
        client: WikidataClient,
        languages: Sequence[str] = DEFAULT_LANGUAGES,
        wbsearch_limit: int = DEFAULT_WBSEARCH_LIMIT,
        llm: LLMProvider | None = None,
        book_context: BookContext | None = None,
        llm_timeout_s: float = 30.0,
        bio_facts_language: str = "en",
        audit_log: ExtractionAuditLog | None = None,
        audit_run_id: str | None = None,
    ) -> None:
        if not languages:
            raise ValueError("languages must be non-empty")
        self._client = client
        self._languages = tuple(languages)
        self._wbsearch_limit = wbsearch_limit
        self._llm = llm
        self._book_context = book_context
        self._llm_timeout_s = llm_timeout_s
        self._bio_facts_language = bio_facts_language
        self._audit_log = audit_log
        self._audit_run_id = audit_run_id

    @property
    def languages(self) -> tuple[str, ...]:
        return self._languages

    @property
    def has_llm(self) -> bool:
        """True iff Stage 4 LLM disambiguation is wired up."""
        return self._llm is not None

    @property
    def book_context(self) -> BookContext | None:
        """Currently configured BookContext (Plan §3.4 Stage 4 input)."""
        return self._book_context

    def wikidata_counters_snapshot(self) -> dict[str, int]:
        """Snapshot the underlying :class:`WikidataClient` lifetime counters.

        Returned keys mirror W6 §D: ``api_requests``, ``cache_hits``,
        ``failures_after_retry``. The :class:`IngestionPipeline` takes
        a delta around the resolve stage so the per-run
        ``ResolutionSummary`` reflects this run's network use, not the
        client's whole lifetime.

        Falls back to zeros for any counter the underlying client
        does not expose — keeps the in-memory ``FakeWikidataClient``
        used by ``tests/test_extraction_pipeline.py`` working without
        change.
        """
        return {
            "api_requests": int(getattr(self._client, "api_requests", 0)),
            "cache_hits": int(getattr(self._client, "cache_hits", 0)),
            "failures_after_retry": int(getattr(self._client, "failures_after_retry", 0)),
        }

    def set_book_context(self, ctx: BookContext | None) -> None:
        """Update the BookContext used for Stage 4 prompts.

        The IngestionPipeline (E5+) constructs the resolver before
        the BookContext is available (BookContext is itself an
        ingest-time LLM call), then calls this setter once the
        context is extracted. Outside the pipeline, prefer the
        constructor kwarg.

        Concurrency: not safe across overlapping ingest runs that
        share a resolver instance. Gen 1 single-tenant single-
        ingest semantics make this fine; revisit if Gen 2 fans
        out concurrent ingests against one resolver.
        """
        self._book_context = ctx

    async def resolve(
        self,
        mention: Mention,
        *,
        source_ref: SourceRef,
        sentences: Sequence[Sentence] | None = None,
        run_id: str | None = None,
    ) -> ResolvedMention:
        """Resolve a single mention.

        Convenience wrapper over :meth:`resolve_many`. When resolving
        many mentions from one document prefer ``resolve_many`` —
        it deduplicates surface forms and batches all Wikidata calls.

        ``sentences`` is the cleaned-text sentence list from
        :class:`~theogony.extraction.sentence.Sentencizer`. Required
        for Stage 4 to inline the source sentence into the
        disambiguation prompt; optional otherwise (Tier 4/3/0 paths
        do not consume it).
        """
        results = await self.resolve_many(
            [mention], source_ref=source_ref, sentences=sentences, run_id=run_id
        )
        return results[0]

    async def resolve_many(
        self,
        mentions: Sequence[Mention],
        *,
        source_ref: SourceRef,
        sentences: Sequence[Sentence] | None = None,
        run_id: str | None = None,
    ) -> list[ResolvedMention]:
        """Resolve every mention; identical surface forms share one node.

        Deduplication key: ``(fully_normalise(text), label)``. All
        mentions in a group resolve to the same ``KnowledgeNode`` —
        one HTTP/SPARQL round per unique form per book, not per
        occurrence.

        ``sentences`` is the cleaned-text sentence list. When
        provided and an ``llm`` is configured, Stage 4 prompts include
        the source sentence; otherwise the mention text alone is the
        sentence context.

        Returns one ``ResolvedMention`` per *group*, not per input
        mention. The ``mentions`` field of each ``ResolvedMention``
        carries every member of the group in appearance order.
        """
        if not mentions:
            return []

        # Group mentions by deduplication key. Preserve appearance
        # order of group keys (important for stable resolution order
        # in tests and reports).
        groups: dict[tuple[str, str], list[Mention]] = {}
        order: list[tuple[str, str]] = []
        for m in mentions:
            key = (fully_normalise(m.text), m.label)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(m)

        results: list[ResolvedMention] = []
        for key in order:
            group = groups[key]
            results.append(
                await self._resolve_group(
                    group,
                    source_ref=source_ref,
                    sentences=sentences,
                    run_id=run_id,
                )
            )
        return results

    # ----------------------------------------------------------------- internals

    async def _resolve_group(
        self,
        group: list[Mention],
        *,
        source_ref: SourceRef,
        sentences: Sequence[Sentence] | None = None,
        run_id: str | None = None,
    ) -> ResolvedMention:
        """Run Stages 1-3 on one deduplication group."""
        rep_mention = group[0]
        rep_text = _representative_mention_text(group)
        ner_label = rep_mention.label

        # Non-resolvable labels (DATE, MONEY, …) skip Wikidata entirely
        # and mint a Tier-0 node directly. The IngestionPipeline (E3+)
        # may route them to a separate temporal/numeric handler later.
        if not is_resolvable(ner_label):
            log.debug(
                "label %r is not Wikidata-resolvable; minting tier-0 node for %r",
                ner_label,
                rep_text,
            )
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=[],
                failure_reason="ner_label_not_resolvable",
            )

        # ---- Stage 1: multi-language search ----
        per_lang = await self._client.search_multi_language(
            rep_text,
            languages=self._languages,
            limit=self._wbsearch_limit,
        )
        all_candidates: dict[str, list[WikidataCandidate]] = {}
        # Q-ID → set of languages it appeared in (Stage-1 evidence)
        appearance_languages: dict[str, set[str]] = {}
        for lang, hits in per_lang.items():
            for cand in hits:
                all_candidates.setdefault(cand.qid, []).append(cand)
                appearance_languages.setdefault(cand.qid, set()).add(lang)

        if not all_candidates:
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=[],
                failure_reason="no_candidates_from_search",
            )

        candidate_qids = sorted(all_candidates.keys())  # sort for determinism

        # ---- Stage 2: labels & aliases ----
        aliases = await self._client.fetch_labels_aliases(
            candidate_qids,
            languages=self._languages,
        )

        # ---- Stage 3: type filter ----
        types = await self._client.fetch_types(candidate_qids)
        accepted_types = acceptable_wikidata_types(ner_label)
        if accepted_types:
            survivors = [q for q in candidate_qids if types.get(q, set()) & accepted_types]
        else:
            # Empty acceptable set means "no type filter, accept all".
            survivors = list(candidate_qids)

        if not survivors:
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="all_candidates_failed_type_filter",
            )

        # ---- Tier assignment ----
        # Per-survivor: which languages had EXACT match? Which had ≥CASE?
        exact_languages_by_qid: dict[str, set[str]] = {}
        case_languages_by_qid: dict[str, set[str]] = {}
        for qid in survivors:
            qid_aliases = aliases.get(qid, {})
            exact_languages_by_qid[qid] = _languages_with_strength(
                qid_aliases, rep_text, AliasMatchStrength.EXACT
            )
            case_languages_by_qid[qid] = _languages_with_strength(
                qid_aliases, rep_text, AliasMatchStrength.CASE
            )

        # Tier 4: exactly one survivor, EXACT in ≥ 2 languages.
        if len(survivors) == 1:
            sole = survivors[0]
            if len(exact_languages_by_qid[sole]) >= 2:
                return self._mint_tier4(
                    group=group,
                    qid=sole,
                    aliases=aliases,
                    source_ref=source_ref,
                    candidates=candidate_qids,
                )

        # Tier 3: best-ranked survivor with CASE-or-better in ≥ 2 languages.
        # Sort survivors by Q-ID ascending so max() with rank key picks
        # the lexicographically smallest on ties.
        ranked = max(
            survivors,
            key=lambda q: _rank_key(
                q, case_languages_by_qid[q], len(appearance_languages.get(q, set()))
            ),
        )
        if len(case_languages_by_qid[ranked]) >= 2:
            return self._mint_tier3(
                group=group,
                qid=ranked,
                aliases=aliases,
                source_ref=source_ref,
                candidates=candidate_qids,
            )

        # ---- Stage 4: LLM disambiguation (E3) ----
        # Only when an LLM is configured. Otherwise (E2 backward-compat
        # path) honestly fail to Tier 0.
        if self._llm is None:
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="weak_alias_match_no_llm_configured",
            )
        return await self._stage4_disambiguate(
            group=group,
            rep_text=rep_text,
            source_ref=source_ref,
            survivors=survivors,
            aliases=aliases,
            candidate_qids=candidate_qids,
            sentences=sentences,
            run_id=run_id,
        )

    async def _stage4_disambiguate(
        self,
        *,
        group: list[Mention],
        rep_text: str,
        source_ref: SourceRef,
        survivors: list[str],
        aliases: dict[str, dict[str, list[str]]],
        candidate_qids: list[str],
        sentences: Sequence[Sentence] | None,
        run_id: str | None = None,
    ) -> ResolvedMention:
        """Run Stage 4: bio facts + LLM disambiguation.

        Falls back to Tier 0 with a specific failure reason on any
        of: LLM transport error, JSON parse failure, schema-invalid
        response, chosen Q-ID not in survivor set.

        Tier 2 vs Tier 1 split: if at least one survivor returned
        non-empty :class:`BioFacts`, the LLM had Plan-§3.4 Stage-4
        evidence to work with → Tier 2 (conf 0.65). If all bio facts
        were empty (e.g. GPE candidates, or a person Wikidata has no
        biographical statements for) → Tier 1 (conf 0.55, "LLM with
        sentence context only" per Plan §3.4).
        """
        # Defensive: this method is private but the resolver could
        # have been constructed without an LLM by mistake.
        if self._llm is None:  # pragma: no cover - guarded above
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="weak_alias_match_no_llm_configured",
            )

        bio_facts = await self._client.fetch_bio_facts(survivors, language=self._bio_facts_language)
        sentence_text = self._lookup_sentence_text(group[0], sentences)
        prompt = self._build_stage4_prompt(
            mention_text=rep_text,
            ner_label=group[0].label,
            sentence_text=sentence_text,
            survivors=survivors,
            aliases=aliases,
            bio_facts=bio_facts,
        )

        try:
            result = await self._llm.complete(
                prompt,
                system=_STAGE4_SYSTEM_PROMPT,
                json_schema=_STAGE4_OUTPUT_SCHEMA,
                temperature=0.0,
                timeout_s=self._llm_timeout_s,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "stage 4 LLM call failed for mention=%r ner=%s: %s — minting tier 0",
                rep_text,
                group[0].label,
                exc,
            )
            self._maybe_audit_stage4(
                run_id=run_id,
                sentence_index=group[0].sentence_index,
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                cost_eur=0.0,
                latency_ms=0,
                model_id=getattr(self._llm, "model_id", ""),
                parse_error=f"transport_error:{type(exc).__name__}",
            )
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="stage4_llm_transport_error",
            )

        chosen, llm_confidence, reasoning, parse_error = self._parse_stage4_response(result.text)
        self._maybe_audit_stage4(
            run_id=run_id,
            sentence_index=group[0].sentence_index,
            prompt=prompt,
            response=result.text,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_eur=result.cost_eur,
            latency_ms=result.latency_ms,
            model_id=result.model_id,
            parse_error=parse_error,
        )
        if parse_error is not None:
            log.warning(
                "stage 4 response parse failed for mention=%r: %s — minting tier 0",
                rep_text,
                parse_error,
            )
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason=f"stage4_parse_error:{parse_error}",
            )

        if chosen is None:
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="stage4_llm_refused",
                stage4_reasoning=reasoning,
                stage4_llm_confidence=llm_confidence,
            )
        if chosen not in survivors:
            log.warning(
                "stage 4 LLM picked non-survivor %s for mention=%r (survivors=%s)",
                chosen,
                rep_text,
                survivors,
            )
            return self._mint_tier0(
                group=group,
                rep_text=rep_text,
                source_ref=source_ref,
                candidates=candidate_qids,
                failure_reason="stage4_llm_chose_invalid_qid",
                stage4_reasoning=reasoning,
                stage4_llm_confidence=llm_confidence,
            )

        # Tier 2 vs Tier 1: did at least one survivor have bio facts?
        any_bio_facts = any(not bio_facts.get(q, BioFacts(qid=q)).is_empty for q in survivors)
        if any_bio_facts:
            return self._mint_tier2(
                group=group,
                qid=chosen,
                aliases=aliases,
                source_ref=source_ref,
                candidates=candidate_qids,
                stage4_reasoning=reasoning,
                stage4_llm_confidence=llm_confidence,
            )
        return self._mint_tier1(
            group=group,
            qid=chosen,
            aliases=aliases,
            source_ref=source_ref,
            candidates=candidate_qids,
            stage4_reasoning=reasoning,
            stage4_llm_confidence=llm_confidence,
        )

    def _maybe_audit_stage4(
        self,
        *,
        run_id: str | None,
        sentence_index: int | None,
        prompt: str,
        response: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
        latency_ms: int,
        model_id: str,
        parse_error: str | None,
    ) -> None:
        if self._audit_log is None:
            return
        effective_run_id = run_id or self._audit_run_id
        if not effective_run_id:
            return
        self._audit_log.record(
            run_id=effective_run_id,
            stage=_AUDIT_STAGE_STAGE4,
            sentence_index=sentence_index,
            prompt=prompt,
            response=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=cost_eur,
            latency_ms=latency_ms,
            model_id=model_id,
            parse_error=parse_error,
        )

    @staticmethod
    def _lookup_sentence_text(
        mention: Mention,
        sentences: Sequence[Sentence] | None,
    ) -> str | None:
        """Return the source sentence for a mention, or None when unavailable.

        spaCy sentence indexing is contiguous from 0, so the natural
        lookup is by index. Out-of-range indices fall through to None
        defensively (a mismatch between the sentencizer that produced
        ``mention.sentence_index`` and the ``sentences`` passed here
        is a data-flow bug, but the resolver should not crash on it).
        """
        if sentences is None:
            return None
        idx = mention.sentence_index
        if idx < 0 or idx >= len(sentences):
            return None
        return sentences[idx].text

    def _build_stage4_prompt(
        self,
        *,
        mention_text: str,
        ner_label: str,
        sentence_text: str | None,
        survivors: list[str],
        aliases: dict[str, dict[str, list[str]]],
        bio_facts: dict[str, BioFacts],
    ) -> str:
        """Assemble the per-mention Stage 4 prompt body.

        Layout (stable across mentions):

            Mention: "<text>"
            NER label: <PERSON|GPE|...>
            Source sentence: "<sentence text>"  (or "(not available)")
            <BookContext block>
            Candidates:
              <BioFacts block per survivor>

            Question + JSON instructions.
        """
        if sentence_text:
            sentence_line = f'Source sentence: "{sentence_text}"'
        else:
            sentence_line = "Source sentence: (not available)"
        context_block = (
            self._book_context.to_prompt_block()
            if self._book_context is not None
            else "Book context: (not available)"
        )
        candidate_blocks: list[str] = []
        for qid in survivors:
            facts_block = bio_facts.get(qid, BioFacts(qid=qid)).to_prompt_block()
            # Inline canonical labels so the LLM can reason about
            # surface-form alignment too — alias dict may have multiple
            # languages, so we surface the EN label and short alias list.
            qid_aliases = aliases.get(qid, {})
            en_strings = qid_aliases.get("en") or []
            label_hint = f' (label: "{en_strings[0]}")' if en_strings else ""
            candidate_blocks.append(facts_block.replace(f"{qid}:", f"{qid}{label_hint}:"))
        candidates_section = "Candidates:\n" + "\n".join(candidate_blocks)

        return (
            f'Mention: "{mention_text}"\n'
            f"NER label: {ner_label}\n"
            f"{sentence_line}\n"
            f"{context_block}\n"
            f"{candidates_section}\n\n"
            "Pick the single Q-ID from the candidates that best matches "
            "the mention in this source. If no candidate is a confident "
            "match, respond with chosen=null. Reply ONLY with JSON: "
            '{"chosen": "Q…" or null, "confidence": 0.0-1.0, "reasoning": "..."}'
        )

    @staticmethod
    def _parse_stage4_response(
        text: str,
    ) -> tuple[str | None, float, str, str | None]:
        """Parse the LLM's JSON response.

        Returns ``(chosen, confidence, reasoning, parse_error)``.
        ``parse_error`` is None on success and a short tag string on
        failure (so the resolver can pass it into the Tier-0 reason).
        """
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None, 0.0, "", "json_decode"
        if not isinstance(payload, dict):
            return None, 0.0, "", "non_object_payload"
        chosen = payload.get("chosen")
        confidence = payload.get("confidence", 0.0)
        reasoning = payload.get("reasoning", "")
        if chosen is not None and (
            not isinstance(chosen, str) or not chosen.startswith("Q") or not chosen[1:].isdigit()
        ):
            return None, 0.0, "", "invalid_chosen_format"
        if not isinstance(confidence, (int, float)):  # noqa: UP038
            confidence = 0.0
        if not isinstance(reasoning, str):
            reasoning = ""
        return chosen, float(confidence), reasoning, None

    # ---- minting helpers --------------------------------------------------

    def _mint_tier4(
        self,
        *,
        group: list[Mention],
        qid: str,
        aliases: dict[str, dict[str, list[str]]],
        source_ref: SourceRef,
        candidates: list[str],
    ) -> ResolvedMention:
        label = _select_canonical_label(group[0].text, qid, aliases, self._languages)
        node = KnowledgeNode(
            label=label,
            node_type=node_type_for_ner_label(group[0].label),
            external_ids={"wikidata": qid},
            source_ref=source_ref,
            scores=NodeScores(confidence=TIER_4_CONFIDENCE),
            resolution_tier=4,
            properties=_node_properties(
                ner_label=group[0].label,
                qid=qid,
                candidates=candidates,
                first_mention=group[0],
                mention_count=len(group),
            ),
        )
        return ResolvedMention(
            mentions=list(group),
            node=node,
            tier=4,
            chosen_qid=qid,
            candidates_considered=list(candidates),
        )

    def _mint_tier3(
        self,
        *,
        group: list[Mention],
        qid: str,
        aliases: dict[str, dict[str, list[str]]],
        source_ref: SourceRef,
        candidates: list[str],
    ) -> ResolvedMention:
        label = _select_canonical_label(group[0].text, qid, aliases, self._languages)
        node = KnowledgeNode(
            label=label,
            node_type=node_type_for_ner_label(group[0].label),
            external_ids={"wikidata": qid},
            source_ref=source_ref,
            scores=NodeScores(confidence=TIER_3_CONFIDENCE),
            resolution_tier=3,
            properties=_node_properties(
                ner_label=group[0].label,
                qid=qid,
                candidates=candidates,
                first_mention=group[0],
                mention_count=len(group),
            ),
        )
        return ResolvedMention(
            mentions=list(group),
            node=node,
            tier=3,
            chosen_qid=qid,
            candidates_considered=list(candidates),
        )

    def _mint_tier2(
        self,
        *,
        group: list[Mention],
        qid: str,
        aliases: dict[str, dict[str, list[str]]],
        source_ref: SourceRef,
        candidates: list[str],
        stage4_reasoning: str,
        stage4_llm_confidence: float,
    ) -> ResolvedMention:
        label = _select_canonical_label(group[0].text, qid, aliases, self._languages)
        properties = _node_properties(
            ner_label=group[0].label,
            qid=qid,
            candidates=candidates,
            first_mention=group[0],
            mention_count=len(group),
        )
        properties["stage4_llm_reasoning"] = stage4_reasoning
        properties["stage4_llm_confidence"] = stage4_llm_confidence
        properties["stage4_llm_model_id"] = getattr(self._llm, "model_id", "")
        node = KnowledgeNode(
            label=label,
            node_type=node_type_for_ner_label(group[0].label),
            external_ids={"wikidata": qid},
            source_ref=source_ref,
            scores=NodeScores(confidence=TIER_2_CONFIDENCE),
            resolution_tier=2,
            properties=properties,
        )
        return ResolvedMention(
            mentions=list(group),
            node=node,
            tier=2,
            chosen_qid=qid,
            candidates_considered=list(candidates),
        )

    def _mint_tier1(
        self,
        *,
        group: list[Mention],
        qid: str,
        aliases: dict[str, dict[str, list[str]]],
        source_ref: SourceRef,
        candidates: list[str],
        stage4_reasoning: str,
        stage4_llm_confidence: float,
    ) -> ResolvedMention:
        label = _select_canonical_label(group[0].text, qid, aliases, self._languages)
        properties = _node_properties(
            ner_label=group[0].label,
            qid=qid,
            candidates=candidates,
            first_mention=group[0],
            mention_count=len(group),
        )
        properties["stage4_llm_reasoning"] = stage4_reasoning
        properties["stage4_llm_confidence"] = stage4_llm_confidence
        properties["stage4_llm_model_id"] = getattr(self._llm, "model_id", "")
        properties["stage4_no_bio_facts"] = True
        node = KnowledgeNode(
            label=label,
            node_type=node_type_for_ner_label(group[0].label),
            external_ids={"wikidata": qid},
            source_ref=source_ref,
            scores=NodeScores(confidence=TIER_1_CONFIDENCE),
            resolution_tier=1,
            properties=properties,
        )
        return ResolvedMention(
            mentions=list(group),
            node=node,
            tier=1,
            chosen_qid=qid,
            candidates_considered=list(candidates),
        )

    def _mint_tier0(
        self,
        *,
        group: list[Mention],
        rep_text: str,
        source_ref: SourceRef,
        candidates: Iterable[str],
        failure_reason: str,
        stage4_reasoning: str | None = None,
        stage4_llm_confidence: float | None = None,
    ) -> ResolvedMention:
        candidates_list = list(candidates)
        properties = _node_properties(
            ner_label=group[0].label,
            qid=None,
            candidates=candidates_list,
            first_mention=group[0],
            mention_count=len(group),
        )
        properties["wikidata_search_attempted"] = True
        properties["wikidata_failure_reason"] = failure_reason
        if stage4_reasoning is not None:
            properties["stage4_llm_reasoning"] = stage4_reasoning
        if stage4_llm_confidence is not None:
            properties["stage4_llm_confidence"] = stage4_llm_confidence
            properties["stage4_llm_model_id"] = getattr(self._llm, "model_id", "")
        node = KnowledgeNode(
            label=rep_text,
            node_type=node_type_for_ner_label(group[0].label),
            external_ids={},  # honest emptiness — no Q-ID claim
            source_ref=source_ref,
            scores=NodeScores(confidence=TIER_0_CONFIDENCE),
            resolution_tier=0,
            manual_resolution_needed=True,
            properties=properties,
        )
        return ResolvedMention(
            mentions=list(group),
            node=node,
            tier=0,
            chosen_qid=None,
            candidates_considered=candidates_list,
            failure_reason=failure_reason,
        )


def _node_properties(
    *,
    ner_label: str,
    qid: str | None,
    candidates: list[str],
    first_mention: Mention,
    mention_count: int,
) -> dict[str, Any]:
    """Build the ``properties`` dict every minted node carries.

    Records audit fields the future Reviewer agent (PHX-0035) and the
    ``theogony resolve`` CLI need: which NER label produced this node,
    which Wikidata candidates were considered, where the entity first
    appears in the source, how many times it occurs.
    """
    return {
        "ner_label": ner_label,
        "wikidata_candidates_considered": list(candidates),
        "first_mention_sentence_index": first_mention.sentence_index,
        "first_mention_start_char_in_source": first_mention.start_char_in_source,
        "first_mention_end_char_in_source": first_mention.end_char_in_source,
        "mention_count": mention_count,
        # When ``qid`` is set, the resolver's chosen Q-ID is duplicated
        # here so a callsite that only has the node (not the
        # ResolvedMention) can still see it. ``external_ids['wikidata']``
        # is the canonical home; ``properties`` is the convenience copy.
        "wikidata_qid": qid,
    }


__all__ = [
    "DEFAULT_LANGUAGES",
    "DEFAULT_WBSEARCH_LIMIT",
    "EntityResolver",
    "ResolvedMention",
    "TIER_0_CONFIDENCE",
    "TIER_1_CONFIDENCE",
    "TIER_2_CONFIDENCE",
    "TIER_3_CONFIDENCE",
    "TIER_4_CONFIDENCE",
]
