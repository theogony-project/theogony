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

from theogony.mesh.ingestion.relation_pids import _TABLE_PATH, known_descriptors, pid_for


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
    assert pid_for("authored") is None, "P50 is 'author' — attached to the work"
    assert pid_for("includes") is None, "P361 is 'part of' — the other direction"
    # Their inverses, which do read forwards, are mapped.
    assert pid_for("killed_by") == "P157"
    assert pid_for("authored_by") == "P50"
    assert pid_for("part_of") == "P361"


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
