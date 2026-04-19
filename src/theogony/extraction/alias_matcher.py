"""
Alias matching with explicit strictness levels (Plan §3.4 Stage 2).

Stage 2 of the EntityResolver pipeline matches a source mention against
the labels-plus-aliases set of each candidate Q-ID. The plan calls for
four progressively-lenient steps, in this order:

1. Exact byte-for-byte equality.
2. Case-folded equality.
3. Whitespace-collapsed equality (multiple spaces → one, trim).
4. NFKD-normalised equality with combining marks stripped.

Each step that produces a hit is also a hint about confidence: an
exact match across multiple languages is the Tier-4 signal Plan §3.4
explicitly names; a normalisation-only match still resolves the
mention but warrants a lower tier and a more cautious downstream
treatment. The matcher therefore returns the *strongest* level
achieved, not just yes/no — the tier-assignment logic in
``EntityResolver`` consumes that level directly.

Worked examples:

- ``"Aufschnaiter" == "Aufschnaiter"`` → :attr:`AliasMatchStrength.EXACT`
- ``"AUFSCHNAITER" matches "Aufschnaiter"`` → :attr:`AliasMatchStrength.CASE`
- ``"Uttar Kashi" matches "Uttarkashi"`` → :attr:`AliasMatchStrength.NORMALISED`
  (NFKD alone is not enough; whitespace-collapse on its own would
  not catch this either; the combination does.)
- ``"Kämpa" matches "Kampa"`` → :attr:`AliasMatchStrength.NORMALISED`
  (NFKD splits ``ä`` into ``a`` + combining diaeresis; we strip the
  combining mark.)
- ``"Tibet" vs "China"`` → :attr:`AliasMatchStrength.NONE`

The four-step ladder is intentionally short. Anything fuzzier
(Levenshtein, Jaro-Winkler, phonetic) is deferred — the LLM
disambiguation step in E3 is the proper home for fuzzy reasoning,
not a regex pass that pretends to certainty it does not have.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from enum import IntEnum


class AliasMatchStrength(IntEnum):
    """Strength of the strongest alias match found.

    Higher value = more confident match. ``IntEnum`` is deliberate:
    the resolver compares strengths with ``>=``, so a tier threshold
    like "Tier 4 requires EXACT" is one comparison, not a switch
    statement.
    """

    NONE = 0
    """No alias matched at any normalisation level."""

    NORMALISED = 1
    """Match only after the full normalisation stack (NFKD + strip combining
    marks + case-fold + whitespace-collapse). Weakest accepted hit."""

    WHITESPACE = 2
    """Match after whitespace-collapse, no case-folding or NFKD needed."""

    CASE = 3
    """Match after case-folding, no whitespace or NFKD differences."""

    EXACT = 4
    """Byte-for-byte equal to an alias as fetched from Wikidata."""


def _collapse_whitespace(text: str) -> str:
    """Replace runs of whitespace with a single space and trim ends.

    Internal whitespace differences (``"Uttar Kashi"`` vs ``"Uttar  Kashi"``)
    collapse to the same string. Different *kinds* of whitespace —
    tabs, NBSPs — also collapse, since :py:meth:`str.split` with no
    argument splits on any Unicode whitespace.
    """
    return " ".join(text.split())


def _strip_combining(text: str) -> str:
    """NFKD-normalise then drop combining marks (Unicode category Mn).

    Turns ``"Kämpa"`` into ``"Kampa"`` (NFKD splits ``ä`` → ``a`` plus
    combining diaeresis; ``Mn`` removes the diaeresis). Ligatures and
    compatibility forms (``"ﬁ"`` → ``"fi"``) collapse via NFKD too.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def fully_normalise(text: str) -> str:
    """Apply the full normalisation stack used at the weakest match level.

    Equivalent to: NFKD-decompose → strip combining marks →
    whitespace-collapse → case-fold. Exposed as a public helper because
    the resolver also uses it to deduplicate normalised mention forms
    before issuing ``wbsearchentities`` queries.
    """
    return _collapse_whitespace(_strip_combining(text)).casefold()


def best_match(mention: str, aliases: Iterable[str]) -> AliasMatchStrength:
    """Return the strongest match strength found across the alias set.

    Iterates the alias set once, tracking the maximum strength
    achieved. Returns early on :attr:`AliasMatchStrength.EXACT` since
    nothing can beat it. An empty alias iterable returns
    :attr:`AliasMatchStrength.NONE` — no aliases means no match,
    not "everything matches".
    """
    if not aliases:
        return AliasMatchStrength.NONE

    mention_case = mention.casefold()
    mention_ws = _collapse_whitespace(mention)
    mention_full = fully_normalise(mention)

    best = AliasMatchStrength.NONE
    for alias in aliases:
        if alias == mention:
            return AliasMatchStrength.EXACT
        if best < AliasMatchStrength.CASE and alias.casefold() == mention_case:
            best = AliasMatchStrength.CASE
            continue
        if best < AliasMatchStrength.WHITESPACE and _collapse_whitespace(alias) == mention_ws:
            best = AliasMatchStrength.WHITESPACE
            continue
        if best < AliasMatchStrength.NORMALISED and fully_normalise(alias) == mention_full:
            best = AliasMatchStrength.NORMALISED
    return best


def is_match(mention: str, aliases: Iterable[str]) -> bool:
    """Convenience: did *any* normalisation level produce a hit?

    Equivalent to ``best_match(mention, aliases) > AliasMatchStrength.NONE``
    — useful when the caller does not care about the strength.
    """
    return best_match(mention, aliases) > AliasMatchStrength.NONE


__all__ = [
    "AliasMatchStrength",
    "best_match",
    "fully_normalise",
    "is_match",
]
