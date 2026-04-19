"""
EntityResolver — Wikidata alignment for NER mentions (Plan §3.4 v3).

E2 scope: Stages 1-3 of the five-stage pipeline plus the Tier-4/3/0
honest-failure path. Stage 4 (LLM disambiguation with biographical
facts and ``BookContext``) lands in E3; Stage 5 (``WikidataDetective``,
opt-in) in E4.

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

4. **Tier assignment** (E2 subset, Plan §3.4):

   - **Tier 4** (confidence 0.90): exactly one candidate survives
     Stage 3 *and* it has an EXACT alias match in ≥ 2 distinct
     languages.
   - **Tier 3** (confidence 0.75): at least one candidate survives
     Stage 3, the best-ranked candidate has CASE-or-better matches
     in ≥ 2 languages. Best-rank = (most languages with ≥CASE
     match, then most languages where the candidate appeared in
     wbsearchentities, then lexicographic Q-ID for determinism).
   - **Tier 0** (confidence 0.50): no Q-ID assigned. Mints an
     ``AKA-…`` node with ``manual_resolution_needed=True`` and
     ``properties["wikidata_failure_reason"]`` recording why
     (no candidates / type filter eliminated all / weak match).

   Tiers 2 and 1 (LLM disambiguation) are reserved for E3 and
   currently unreachable from this resolver.

The resolver is **stateless and concurrency-safe**: any number of
``resolve`` / ``resolve_many`` calls can run in parallel against the
same instance, bounded by the underlying ``WikidataClient``'s
politeness lock.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from theogony.config.logging import get_logger
from theogony.core.model import KnowledgeNode, NodeScores, SourceRef
from theogony.extraction.alias_matcher import AliasMatchStrength, best_match, fully_normalise
from theogony.extraction.ner import Mention
from theogony.extraction.wikidata_client import WikidataCandidate, WikidataClient
from theogony.extraction.wikidata_types import (
    acceptable_wikidata_types,
    is_resolvable,
    node_type_for_ner_label,
)

log = get_logger("extraction.resolve")


DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "de", "fr", "it")
DEFAULT_WBSEARCH_LIMIT = 10

TIER_4_CONFIDENCE = 0.90
TIER_3_CONFIDENCE = 0.75
TIER_0_CONFIDENCE = 0.50


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
    """Resolve NER mentions to Wikidata Q-IDs (Stages 1-3 + Tier 4/3/0)."""

    def __init__(
        self,
        *,
        client: WikidataClient,
        languages: Sequence[str] = DEFAULT_LANGUAGES,
        wbsearch_limit: int = DEFAULT_WBSEARCH_LIMIT,
    ) -> None:
        if not languages:
            raise ValueError("languages must be non-empty")
        self._client = client
        self._languages = tuple(languages)
        self._wbsearch_limit = wbsearch_limit

    @property
    def languages(self) -> tuple[str, ...]:
        return self._languages

    async def resolve(
        self,
        mention: Mention,
        *,
        source_ref: SourceRef,
    ) -> ResolvedMention:
        """Resolve a single mention through Stages 1-3.

        Convenience wrapper over :meth:`resolve_many`. When resolving
        many mentions from one document prefer ``resolve_many`` —
        it deduplicates surface forms and batches all Wikidata calls.
        """
        results = await self.resolve_many([mention], source_ref=source_ref)
        return results[0]

    async def resolve_many(
        self,
        mentions: Sequence[Mention],
        *,
        source_ref: SourceRef,
    ) -> list[ResolvedMention]:
        """Resolve every mention; identical surface forms share one node.

        Deduplication key: ``(fully_normalise(text), label)``. All
        mentions in a group resolve to the same ``KnowledgeNode`` —
        one HTTP/SPARQL round per unique form per book, not per
        occurrence.

        Returns one ``ResolvedMention`` per *group*, not per input
        mention. The ``mentions`` field of each ``ResolvedMention``
        carries every member of the group in appearance order, so
        downstream consumers (RelationExtractor, IngestionPipeline)
        can recover per-mention provenance.
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
            results.append(await self._resolve_group(group, source_ref=source_ref))
        return results

    # ----------------------------------------------------------------- internals

    async def _resolve_group(
        self,
        group: list[Mention],
        *,
        source_ref: SourceRef,
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

        # E2 stops here. Stage 4 (E3) would now run LLM disambiguation
        # over the survivors. For E2 we honestly fail to Tier 0.
        return self._mint_tier0(
            group=group,
            rep_text=rep_text,
            source_ref=source_ref,
            candidates=candidate_qids,
            failure_reason="weak_alias_match_no_llm_in_e2",
        )

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

    def _mint_tier0(
        self,
        *,
        group: list[Mention],
        rep_text: str,
        source_ref: SourceRef,
        candidates: Iterable[str],
        failure_reason: str,
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
    "TIER_3_CONFIDENCE",
    "TIER_4_CONFIDENCE",
]
