"""
spaCy NER label → Wikidata type mapping (Plan §3.4 Stage 3).

Stage 3 of the v3 EntityResolver pipeline filters candidate Q-IDs by their
``wdt:P31`` ("instance of") values, so that a ``PERSON`` mention cannot
resolve to a town and a ``GPE`` mention cannot resolve to a footballer
who happens to share a surname with a place. The mapping table is
intentionally small and explicit — when a future contributor wants to
broaden it (e.g. accept ``Q3024240`` historical countries for ``GPE``
mentions in a 19th-century travel ingest), they edit one frozenset
here, not five files across the resolver.

Three categorisations are encoded here, all derived from the spaCy
``en_core_web_sm`` label set:

1. **Resolvable labels** — those that warrant a Wikidata round trip.
   Pure literals (``DATE``, ``TIME``, ``MONEY``, ``PERCENT``,
   ``QUANTITY``, ``ORDINAL``, ``CARDINAL``) are not entities; they
   short-circuit out of the resolver before the first HTTP call.

2. **Acceptable Wikidata types** — per resolvable label, the frozenset
   of ``wdt:P31`` values the type-pass filter accepts. An empty set
   (``frozenset()``) means "no type filter, accept any candidate";
   used for labels whose Wikidata type space is too diffuse to enumerate
   defensibly without measurement (``PRODUCT``, ``LAW``).

3. **Node type for minting** — when resolution fails (tier 0) or
   succeeds (tier 4/3), the ``KnowledgeNode`` minted carries a
   ``NodeType``. The mapping is the cheapest defensible interpretation
   of each NER label as a Theogony node category.

The five Wikidata types listed in Plan §3.4 Stage 3 verbatim are kept
verbatim (``Q5`` for PERSON; ``Q486972 ∪ Q515 ∪ Q6256 ∪ Q3024240`` for
GPE; ``Q43229`` for ORG). Additional accepted Q-IDs are minimal,
documented expansions for the travel-history corpus (``Q3957`` town,
``Q15284`` municipality, ``Q8502`` mountain, ``Q571`` book, etc.) that
real Project-Gutenberg material is full of. Each addition has a
docstring justification — not "I felt like it".
"""

from __future__ import annotations

from theogony.core.model import NodeType

PERSON: frozenset[str] = frozenset({"Q5"})
"""Q5 = human. The single canonical instance-of for any named person."""

GPE: frozenset[str] = frozenset(
    {
        "Q486972",  # human settlement (umbrella for villages, towns, cities)
        "Q515",  # city
        "Q6256",  # country
        "Q3024240",  # historical country
        "Q3957",  # town
        "Q15284",  # municipality
        "Q5119",  # capital
        "Q35657",  # state of the United States
        "Q15642541",  # historical administrative division — for 19th-century gazetteer entries
        # Real Wikidata data: famous modern cities are P31-classified
        # as more specific subclasses than Q515. Without these the
        # type filter rejects Berlin (Q64), Beijing, etc. — a
        # measurable failure mode caught by the live smoke test.
        "Q1549591",  # big city ("Großstadt")
        "Q133442",  # city-state (covers Berlin-as-state, Singapore, etc.)
        "Q1637706",  # city with millions of inhabitants (megacity)
        "Q1093829",  # city in the United States
        "Q484170",  # commune of France
        "Q1221156",  # state of Germany
    }
)
"""GPE — geo-political entities. Plan §3.4 Stage 3 lists the original
quartet (Q486972, Q515, Q6256, Q3024240); the additional entries are
minimal, empirically-justified expansions for the travel-literature
corpus. The "modern subclasses" group (Q1549591 big city, Q133442
city-state, Q1637706 megacity, Q1093829 US city, Q484170 French
commune, Q1221156 German state) was added after the live smoke test
revealed that Berlin (Q64) and similar famous cities never carry
Q515 directly — Wikidata classifies them under more specific types."""

LOC: frozenset[str] = frozenset(
    {
        "Q8205328",  # geographical object
        "Q47521",  # river
        "Q23397",  # lake
        "Q8502",  # mountain
        "Q39594",  # mountain pass
        "Q46831",  # mountain range
        "Q5107",  # continent
        "Q205895",  # landmass
        "Q35509",  # cave
        "Q124714",  # plateau
        "Q9259",  # peninsula
    }
)
"""LOC — non-GPE geographic features. Travel literature is dense with
these: passes, rivers, mountains, plateaus."""

ORG: frozenset[str] = frozenset(
    {
        "Q43229",  # organization (umbrella from Plan §3.4 Stage 3)
        "Q4830453",  # business
        "Q3918",  # university
        "Q1391145",  # learned society
        "Q484652",  # international organization
        "Q15911314",  # association
    }
)
"""ORG — organisations. Q43229 from the plan plus the obvious sub-forms
the travel-publication frontmatter throws at us (Macmillan & Co. as a
business; the Royal Geographical Society as a learned society)."""

FAC: frozenset[str] = frozenset(
    {
        "Q41176",  # building
        "Q1248784",  # airport
        "Q12280",  # bridge
        "Q44539",  # temple
        "Q16970",  # church building
        "Q137321",  # palace
        "Q174782",  # square
    }
)
"""FAC — facilities. Buildings and named infrastructural points that
appear as named entities in travel narratives (palaces, temples,
bridges, train stations approximated as buildings)."""

EVENT: frozenset[str] = frozenset(
    {
        "Q1656682",  # event
        "Q1190554",  # occurrence
        "Q198",  # war
        "Q178561",  # battle
        "Q40231",  # election
        "Q3839081",  # disaster
    }
)
"""EVENT — historical and political events. Wars and battles dominate
historical travelogue references."""

WORK_OF_ART: frozenset[str] = frozenset(
    {
        "Q838948",  # work of art (umbrella)
        "Q571",  # book
        "Q11424",  # film
        "Q43196",  # painting
        "Q15401930",  # sculpture
        "Q1004",  # comics
        "Q7725634",  # literary work
    }
)
"""WORK_OF_ART — books, films, paintings, sculptures, literary works.
Travel narratives cite many books and a few paintings."""

NORP: frozenset[str] = frozenset(
    {
        "Q41710",  # ethnic group
        "Q9174",  # religion
        "Q12909644",  # political ideology
        "Q231002",  # nationality
        "Q4392985",  # religious identity
    }
)
"""NORP — nationalities, religious or political groups. spaCy mixes
these; we accept ethnicity, religion, ideology, nationality, religious
identity."""

LANGUAGE: frozenset[str] = frozenset({"Q34770"})
"""LANGUAGE — language. Q34770 covers natural and constructed languages."""

# Labels we attempt but with no type filter (accept any candidate that
# survives Stages 1+2). Wikidata type space for these is too diffuse to
# enumerate defensibly without empirical measurement; the alias-match
# Stage 2 still constrains selection. Documented in the resolver to
# admit this caveat downstream rather than silently accepting all.
PRODUCT: frozenset[str] = frozenset()
LAW: frozenset[str] = frozenset()


_ACCEPTABLE_WIKIDATA_TYPES: dict[str, frozenset[str]] = {
    "PERSON": PERSON,
    "GPE": GPE,
    "LOC": LOC,
    "ORG": ORG,
    "FAC": FAC,
    "EVENT": EVENT,
    "WORK_OF_ART": WORK_OF_ART,
    "NORP": NORP,
    "LANGUAGE": LANGUAGE,
    "PRODUCT": PRODUCT,
    "LAW": LAW,
}


# Labels we never resolve against Wikidata. Pure literals — DATE/TIME
# are temporal, MONEY/PERCENT/QUANTITY/ORDINAL/CARDINAL are numeric.
# They short-circuit before the first HTTP call. The IngestionPipeline
# (E3+) will route them to a separate temporal/numeric handler if and
# when one materialises.
_NON_RESOLVABLE: frozenset[str] = frozenset(
    {"DATE", "TIME", "MONEY", "PERCENT", "QUANTITY", "ORDINAL", "CARDINAL"}
)


_NER_LABEL_TO_NODE_TYPE: dict[str, NodeType] = {
    "PERSON": NodeType.PERSON,
    "GPE": NodeType.PLACE,
    "LOC": NodeType.PLACE,
    "FAC": NodeType.PLACE,
    "ORG": NodeType.ORGANIZATION,
    "EVENT": NodeType.EVENT,
    "WORK_OF_ART": NodeType.WORK,
    "NORP": NodeType.OTHER,
    "LANGUAGE": NodeType.OTHER,
    "PRODUCT": NodeType.OTHER,
    "LAW": NodeType.OTHER,
    "DATE": NodeType.TIME,
    "TIME": NodeType.TIME,
    "MONEY": NodeType.QUANTITY,
    "PERCENT": NodeType.QUANTITY,
    "QUANTITY": NodeType.QUANTITY,
    "ORDINAL": NodeType.QUANTITY,
    "CARDINAL": NodeType.QUANTITY,
}


def is_resolvable(ner_label: str) -> bool:
    """True iff a mention with this NER label warrants Wikidata lookup.

    Returns False for pure literals (``DATE``, ``MONEY``, ``CARDINAL``,
    etc.) and for any label not in the spaCy ``en_core_web_sm`` label
    set we have a mapping for. The latter is conservative — an unknown
    label is not silently routed through the resolver.
    """
    if ner_label in _NON_RESOLVABLE:
        return False
    return ner_label in _ACCEPTABLE_WIKIDATA_TYPES


def acceptable_wikidata_types(ner_label: str) -> frozenset[str]:
    """Return the frozenset of acceptable ``wdt:P31`` Q-IDs for this label.

    An empty frozenset means "no type filter, accept any candidate that
    survives prior stages" — used for labels whose Wikidata type space
    is too diffuse to enumerate defensibly (``PRODUCT``, ``LAW``).

    Raises :class:`KeyError` for unknown labels — callers should gate
    on :func:`is_resolvable` first to keep error paths explicit.
    """
    return _ACCEPTABLE_WIKIDATA_TYPES[ner_label]


def node_type_for_ner_label(ner_label: str) -> NodeType:
    """Map an NER label to the :class:`NodeType` for minting.

    Used both for tier-0 honest-failure nodes (where no Q-ID was found
    but we still mint an ``AKA-`` node so downstream relations have a
    target) and for tier-4/3 nodes (where the type is recorded for
    consistency even though ``external_ids['wikidata']`` is the
    primary identity claim).

    Unknown labels fall back to :attr:`NodeType.OTHER` rather than
    raising — the caller has already extracted the mention; refusing
    to mint a node would be a worse failure mode than mistyping it.
    """
    return _NER_LABEL_TO_NODE_TYPE.get(ner_label, NodeType.OTHER)


__all__ = [
    "EVENT",
    "FAC",
    "GPE",
    "LANGUAGE",
    "LAW",
    "LOC",
    "NORP",
    "ORG",
    "PERSON",
    "PRODUCT",
    "WORK_OF_ART",
    "acceptable_wikidata_types",
    "is_resolvable",
    "node_type_for_ner_label",
]
