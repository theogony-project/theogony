"""Relation descriptors resolve to Wikidata properties — carefully, or not at all.

The reading model invents a descriptor per relation: 2,672 distinct strings for
6,489 judged edges on the founding mesh, 1,913 of them appearing exactly once,
`father_of` (190) beside `father of` (58). `Edge.pids` exists for precisely this
and was empty on every edge.

Two properties are load-bearing here and both are refusals.

The model is never asked for a P-ID. It produced 130 Q-IDs for this corpus and
127 named something else — Gaia carried the identifier of analytical chemistry
(PHX-1063). A curated, API-verified table replaces that guess.

And only direction-faithful mappings exist. `killed(Zeus, Asclepius)` would be
`P157(Asclepius, Zeus)`, because P157 reads "killed by". A table with an
inversion flag works until someone forgets it and the genealogy is silently
backwards, so those relations are absent rather than flagged (PHX-1072).
"""

from __future__ import annotations

import json
from pathlib import Path

from theogony.mesh.relation_pids import _TABLE_PATH, known_descriptors, pid_for


def test_spelling_variants_fold_together() -> None:
    """`father_of` and `father of` were two relations in the mesh; now they are one."""
    assert pid_for("father_of") == pid_for("father of") == pid_for("Father-Of") == "P40"


def test_kinship_reads_in_our_direction() -> None:
    """source --descriptor--> target must map to property(source, target).

    `father_of(Cronos, Zeus)` is "Cronos has child Zeus" — P40. `son_of(Zeus,
    Cronos)` is "Zeus's parent is Cronos" — P8810. Both read forwards; neither
    needs the edge reversed.
    """
    assert pid_for("father_of") == "P40"
    assert pid_for("mother_of") == "P40"
    assert pid_for("son_of") == "P8810"
    assert pid_for("daughter_of") == "P8810"


def test_inverse_reading_relations_are_refused() -> None:
    """The whole reason there is no inversion flag."""
    assert pid_for("killed") is None, "P157 is 'killed by' — the other direction"
    assert pid_for("slew") is None, "same relation, same refusal"
    assert pid_for("attributed_to") is None, "the work is the source, the creator the target"
    # Their inverses, which do read forwards, are mapped.
    assert pid_for("killed_by") == "P157"
    assert pid_for("authored_by") == "P50"
    assert pid_for("part_of") == "P361"


def test_a_faithful_property_is_preferred_over_refusing_the_relation() -> None:
    """Refusal is for relations with no forward-reading property, not for all of them.

    `includes` was refused while the only candidate considered was P361 "part
    of", which reads the other way. P527 "has part(s)" reads ours — `Gorgons
    --includes--> Medusa` is P527(Gorgons, Medusa) — so the relation is mapped
    rather than dropped, and its inverse keeps P361.
    """
    assert pid_for("includes") == "P527"
    assert pid_for("contains") == "P527"
    assert pid_for("part_of") == "P361"


def test_rejected_candidates_stay_out_of_the_mappings() -> None:
    """The table documents what it refused; the refusals must actually hold.

    Each of these resolves in Wikidata and reads plausibly from the descriptor
    alone. Each was then checked against the edges carrying it and failed —
    `authored` runs backwards in this corpus (`Theogony --authored--> Works and
    Days`), `quotes` targets phrases rather than works, `describes` would call
    thirty incidental subjects the "main" one. See `_rejected` in the table.
    """
    raw = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))
    assert raw["_rejected"], "the reasoning has to travel with the table"
    for descriptor in ("authored", "quotes", "cites", "describes", "owns", "gave_birth_in"):
        assert pid_for(descriptor) is None, descriptor
    for prop in ("P800", "P2860", "P921", "P1830"):
        assert prop not in set(raw["mappings"].values()), prop


def test_the_long_tail_maps_to_nothing() -> None:
    assert pid_for("roamed in") is None
    assert pid_for("") is None
    assert pid_for(None) is None


def test_every_mapped_property_is_documented_in_the_table() -> None:
    """A bare P-ID in a data file is unreviewable; each carries its gloss."""
    raw = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))
    assert set(raw["mappings"].values()) <= set(raw["properties"])


def test_the_table_is_not_empty_and_covers_kinship() -> None:
    covered = known_descriptors()
    assert {"father_of", "mother_of", "son_of", "daughter_of"} <= covered
    assert len(covered) >= 20
    # Plurals and tense variants are the same relation, and the reading model
    # emits all of them: `daughters_of` (10) beside `daughter_of`, `fathered`
    # and `begot` beside `father_of`.
    assert {"sons_of", "daughters_of", "children_of"} <= covered
    assert {"fathered", "begot", "brought_forth"} <= covered
