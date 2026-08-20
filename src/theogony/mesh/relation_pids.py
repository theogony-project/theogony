"""Map a relation descriptor onto the Wikidata property that names it.

Lives beside the substrate rather than inside `mesh.ingestion` because both the
reading path and the Oneiros maintenance pass need it, and importing it from
`mesh.ingestion` into the runtime closes an import cycle.

The reading model invents a descriptor per relation: 2,672 distinct strings
across 6,489 judged edges on the founding mesh, 1,913 of them occurring exactly
once, with `father_of` (190) sitting beside `father of` (58). A relation
vocabulary that free is not a vocabulary — nothing downstream can group by it.

`Edge.pids` exists for this and was empty on every edge. MESH_SUBSTRATE §Edge:
"P-IDs are one-to-one identifiers (each P-ID refers to exactly one Wikidata
property); the substrate honours this just as it honours Q-ID uniqueness on
nodes."

Two rules, and both of them are about not repeating today's mistakes.

**The model is never asked.** Of 130 Q-IDs the reading model produced for the
founding mesh, 127 named something else entirely — Gaia carried the identifier
of analytical chemistry (PHX-1063). The same model would confabulate P-IDs with
the same confidence. This is a curated table, verified against the live Wikidata
API, not an extraction output.

**Only direction-faithful mappings exist.** Our edges read source-descriptor-
target: `father_of(Cronos, Zeus)`. Wikidata's P22 reads "male parent *of the
subject*", so that same fact is `P22(Zeus, Cronos)` — reversed. A mapping table
with an inversion flag would work until someone forgets to honour it, and then
the genealogy is silently backwards. Relations whose property reads the other
way round are therefore absent from the table rather than present with a
caveat: `killed` maps to nothing, because P157 is "killed by".
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_TABLE_PATH = Path(__file__).parent / "vocab" / "relation_pids.json"


def _normalise(descriptor: str) -> str:
    """Fold spelling variants: `father of`, `Father_Of` and `father-of` are one."""
    text = re.sub(r"[^a-z0-9]+", "_", (descriptor or "").lower())
    return text.strip("_")


@lru_cache(maxsize=1)
def _mappings() -> dict[str, str]:
    raw = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    return {_normalise(key): value for key, value in raw["mappings"].items()}


def pid_for(descriptor: str | None) -> str | None:
    """Return the Wikidata property naming this relation, if one reads the same way.

    Returns ``None`` for the long tail and for every relation whose property is
    the inverse of ours — see the module docstring for why that is refusal
    rather than an oversight.
    """
    if not descriptor:
        return None
    return _mappings().get(_normalise(descriptor))


def known_descriptors() -> frozenset[str]:
    """The normalised descriptors this table covers, for reporting."""
    return frozenset(_mappings())
