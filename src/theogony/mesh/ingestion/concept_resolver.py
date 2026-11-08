"""Bootstrap cache for eager-linking over existing consolidated nodes, and the naming rule."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from theogony.mesh.schemas import ConsolidatedNode, QIDTag
from theogony.mesh.storage.nodes import MeshNodeStore

_STOP_WORDS = frozenset(
    {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are", "was", "were"}
)


def _normalize(label: str) -> str:
    raw = label.lower().strip()
    raw = re.sub(r"'s\b", "", raw)
    raw = re.sub(r"[^a-z0-9\s]", "", raw)
    return raw.strip()


def _tokens(label: str) -> set[str]:
    return {t for t in _normalize(label).split() if t not in _STOP_WORDS and len(t) > 1}


@dataclass
class CachedConcept:
    node: ConsolidatedNode
    labels: set[str] = field(default_factory=set)
    qids: set[str] = field(default_factory=set)


class ConceptResolver:
    """In-memory cache of consolidated-node aliases and Q-IDs for one ingest run."""

    def __init__(self, node_store: MeshNodeStore) -> None:
        self._store = node_store
        self._nodes_by_id: dict[str, CachedConcept] = {}
        self._label_to_id: dict[str, str] = {}
        self._qid_to_id: dict[str, str] = {}

    def remember(
        self,
        node: ConsolidatedNode,
        *,
        aliases: list[str] | None = None,
        qids: list[QIDTag] | None = None,
    ) -> None:
        node_id = str(node.id)
        cached = self._nodes_by_id.get(node_id)
        if cached is None:
            cached = CachedConcept(node=node)
            self._nodes_by_id[node_id] = cached
        else:
            cached.node = node

        alias_values = list(aliases or [])
        if node.description:
            alias_values.append(node.description)
        alias_values.extend(node.tags)

        for alias in alias_values:
            norm = _normalize(alias)
            if not norm:
                continue
            cached.labels.add(norm)
            self._label_to_id.setdefault(norm, node_id)

        qid_values = list(qids or []) + list(node.qids)
        for qid_tag in qid_values:
            cached.qids.add(qid_tag.qid)
            self._qid_to_id.setdefault(qid_tag.qid, node_id)

    def refresh(self, node: ConsolidatedNode) -> None:
        """Replace the cached copy of ``node`` without registering a new alias.

        ``remember`` adds the node's description and tags as aliases; a revised
        description (PHX-1118) is not a name and must not become one, but the
        cached copy must follow the row just written, or the Q-ID path — which
        answers from the cache without a store read — hands back the text the
        revision replaced.
        """
        cached = self._nodes_by_id.get(str(node.id))
        if cached is None:
            self.remember(node)
        else:
            cached.node = node

    def get_by_id(self, node_id: str) -> ConsolidatedNode | None:
        cached = self._nodes_by_id.get(node_id)
        if cached is not None:
            return cached.node
        node = self._store.get_consolidated(node_id)
        if node is not None:
            self.remember(node)
        return node

    def get_by_label(self, label: str) -> ConsolidatedNode | None:
        normalized = _normalize(label)
        node_id = self._label_to_id.get(normalized)
        if node_id is not None:
            return self.get_by_id(node_id)
        node = self._store.get_consolidated_by_label(normalized)
        if node is not None:
            self.remember(node)
        return node

    def get_by_qid(self, qid: str) -> ConsolidatedNode | None:
        node_id = self._qid_to_id.get(qid)
        if node_id is not None:
            return self.get_by_id(node_id)
        node = self._store.get_consolidated_by_qid(qid)
        if node is not None:
            self.remember(node)
        return node

    def iter_nodes(self) -> list[ConsolidatedNode]:
        return [cached.node for cached in self._nodes_by_id.values()]

    def find_by_description_vector(
        self,
        description_vector: list[float] | None,
        *,
        limit: int = 16,
    ) -> list[ConsolidatedNode]:
        if description_vector is None:
            return []
        nodes = self._store.search_consolidated_by_vector(
            description_vector,
            vector_column_name="description_vector",
            limit=limit,
        )
        for node in nodes:
            self.remember(node)
        return nodes

    def find_by_labels(self, labels: list[str], *, limit: int = 32) -> list[ConsolidatedNode]:
        nodes = self._store.find_consolidated_by_labels(labels, limit=limit)
        for node in nodes:
            self.remember(node)
        return nodes

    def known_labels(self, node_id: str) -> set[str]:
        cached = self._nodes_by_id.get(node_id)
        return set(cached.labels) if cached is not None else set()

    def score_token_overlap(self, label: str, node: ConsolidatedNode) -> float:
        query_tokens = _tokens(label)
        if not query_tokens:
            return 0.0
        best = 0.0
        for alias in self.known_labels(str(node.id)):
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            overlap = len(query_tokens & alias_tokens) / max(len(query_tokens), len(alias_tokens))
            best = max(best, overlap)
        return best


# --- Naming: does a mention's label name a candidate node? (PHX-1122) --------
#
# Under the names guard an eager link stands only on name evidence. A node's
# name is its first tag, the label it was created with; no later link changes
# it, nor its other tags. (A paragraph-concept node is created without its label
# among its tags and bears no name: `EagerLinker._names`.) A shared tag is not a
# name: it names a related entity (an author on his book) or a category ("film
# festival" on every festival) as often as the entity itself. The PHX-1120 audit
# judged a random sample of the 2Wiki mesh under the v2 guard: a re-mention
# placed on a node of another name was wrong 45 times in 54 decided cases, one
# placed on a node bearing its name right 71 times in 77 (the 261 mentions that
# minted their own node set apart).
#
# The rule is name equality, once what a name may be written with or without is
# set aside (`name_key`). Each variant beyond that which was tried — a plural, a
# qualifier, an acronym, a dropped article, words run together — also joined
# different entities ("The Rolling Stones" and "Rolling Stone", "King James I
# of Scotland" and "King James I", "NY" and "Neil Young", "The Predator" and
# "Predator", "Golmaal" and "Gol Maal"), so variants are left to consolidation:
# a missed merge leaves two nodes for it to join, a wrong merge corrupts one
# silently (MESH_SUBSTRATE.md, identity). The one exception is a pair the
# reader tied together from both sides (`naming_rule`, ``mutual``).

# What a name may be written with or without: abbreviation marks and
# apostrophes ("U.S." = "US", "K.J. Apa" = "KJ Apa", "O'Brien", the okina of
# "Kauaʻi"), and a hyphen, dash or comma for a space ("Washington, D.C." =
# "Washington DC").
_NAME_DROPPED = frozenset(".'`") | frozenset(map(chr, (0x2018, 0x2019, 0x02BB, 0x02BC)))
_NAME_SPACES = frozenset("-,") | frozenset(
    map(chr, (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015))
)
# Diacritics of the Latin, Greek and Cyrillic letters. Other scripts' combining
# marks carry vowels and voicing, and stay.
_LATIN_DIACRITICS = range(0x0300, 0x0370)
# Regnal numbers, ordinals and years: what tells a father from a son.
_NUMERAL = re.compile(
    r"^(?:\d+(?:st|nd|rd|th)?|(?=[ivxlc]+$)c{0,3}(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))$"
)


@lru_cache(maxsize=1 << 17)
def name_key(text: str) -> str:
    """A name with only what it may be written with or without set aside.

    Set aside: case, a diacritic on a Latin, Greek or Cyrillic letter ("México",
    "İstanbul"), abbreviation marks and apostrophes, a hyphen, dash or comma
    read as a space, and runs of spaces. Kept: the words and the spaces between
    them ("Golmaal" is not "Gol Maal", "Mud-man" not "Mudman"), a leading
    article ("The Predator" is not "Predator"), symbols ("C++" is not "C#"), a
    possessive's s ("St. Peter's" is not "St. Peter"), and the marks of every
    other script (सीता is not सती, パリ is not バリ).
    """
    folded = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    folded = "".join(c for c in folded if ord(c) not in _LATIN_DIACRITICS)
    folded = unicodedata.normalize("NFC", folded)
    folded = "".join(" " if c in _NAME_SPACES else c for c in folded if c not in _NAME_DROPPED)
    return " ".join(folded.split())


def _numerals(text: str) -> frozenset[str]:
    """The numeral words of a name, read on its folded form, so an apostrophe's
    letter ("I'll", "l'affaire") is no numeral."""
    return frozenset(word for word in name_key(text).split() if _NUMERAL.match(word))


def naming_rule(
    label: str,
    name: str,
    *,
    mention_tags: Sequence[str] = (),
    node_tags: Sequence[str] = (),
) -> str | None:
    """The rule by which ``label`` names a node called ``name``, or None.

    ``exact``   the same name (`name_key`). Common nouns too: "sea" names "sea".
    ``mutual``  the reader tied the two together from both sides: the mention
                carries the node's name among its tags, and the node was created
                with the mention's label among its tags ("Siam" tagged
                "Thailand", onto "Thailand" tagged "Siam"). One side alone names
                a related entity as often as an alias, and a numeral tells two
                that tag each other apart: a father and a son do ("Edward II",
                "Edward III").

    ``mention_tags`` and ``node_tags`` are read by ``mutual`` only.
    """
    mention, node = name_key(label), name_key(name)
    if not mention or not node:
        return None
    if mention == node:
        return "exact"
    if (
        any(name_key(tag) == node for tag in mention_tags)
        and any(name_key(tag) == mention for tag in node_tags)
        and _numerals(label) == _numerals(name)
    ):
        return "mutual"
    return None
