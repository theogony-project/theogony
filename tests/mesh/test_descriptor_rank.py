"""One pair, several edges — and only one of them worth showing.

The dedup key is `(source, target, relation_descriptor)`, so two nodes may be
joined more than once: `Cronos --father_of--> Zeus` and `Cronos
--co_mentions_in_paragraph--> Zeus` are different claims and both are stored.
`descriptor_index` holds one descriptor per pair, so something chooses.

Until PHX-1073 that something was scan order, and it chose badly: of the 1,323
node pairs on the founding mesh joined by a relation resolving to a Wikidata
property, **1,316 displayed the co-mention instead**. Every Constellation the
substrate returned labelled `Cronos -> Zeus` as two names sharing a paragraph.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

import theogony.mesh.ingestion as ingestion_pkg
from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import Edge
from theogony.mesh.storage.edges import STRUCTURAL_DESCRIPTORS, descriptor_rank


def test_a_named_relation_outranks_an_assertion_outranks_an_observation() -> None:
    assert descriptor_rank("father_of") == 2, "resolves to P40"
    assert descriptor_rank("killed") == 1, "asserts a relation; no faithful property"
    assert descriptor_rank("co_mentions_in_paragraph") == 0, "bookkeeping"
    assert descriptor_rank(None) == 0
    assert descriptor_rank("") == 0


def test_the_ranking_is_strict_where_it_matters() -> None:
    """The exact comparison `descriptor_index` makes for the founding mesh's 1,323 pairs."""
    assert descriptor_rank("father_of") > descriptor_rank("co_mentions_in_paragraph")
    assert descriptor_rank("killed") > descriptor_rank("appears_in_source")
    assert descriptor_rank("daughters_of") > descriptor_rank("mentions")


def test_every_descriptor_the_ingester_writes_literally_is_declared_structural() -> None:
    """The set is only trustworthy while it matches its writer.

    Descriptors the ingester hard-codes are bookkeeping by construction — the
    reader wrote them, not a judged relation. An eleventh literal added without
    a matching entry here would silently outrank a real assertion, which is the
    exact failure this module exists to prevent.
    """
    source = Path(ingestion_pkg.__file__).parent
    literals = {
        m.group(1)
        for path in source.glob("*.py")
        for m in re.finditer(r'relation_descriptor="([^"]+)"', path.read_text(encoding="utf-8"))
    }
    assert literals, "the scan found nothing — the pattern has drifted, not the code"
    assert literals <= STRUCTURAL_DESCRIPTORS, (
        f"undeclared bookkeeping descriptors: {sorted(literals - STRUCTURAL_DESCRIPTORS)}"
    )


def test_no_structural_descriptor_accidentally_resolves_to_a_property() -> None:
    """A bookkeeping word that typed itself would outrank every real relation."""
    for descriptor in STRUCTURAL_DESCRIPTORS:
        assert descriptor_rank(descriptor) == 0, descriptor


def test_the_claim_is_shown_and_not_the_co_mention(mesh_runtime: MeshRuntime) -> None:
    """The defect itself, on a store: two edges, one pair, one descriptor shown.

    Written so the co-mention is appended *after* the claim, which is the order
    that produced the bug — last write won.
    """
    now = datetime.now(UTC)
    cronos, zeus = ULID(), ULID()
    mesh_runtime.edges.append_edges(
        [
            Edge(
                source_id=cronos,
                target_id=zeus,
                weight=1.0,
                relation_descriptor="father_of",
                relation_kind="causal",
                born_at=now,
                last_fired_at=now,
            ),
            Edge(
                source_id=cronos,
                target_id=zeus,
                weight=1.0,
                relation_descriptor="co_mentions_in_paragraph",
                relation_kind="co_occurrence",
                born_at=now,
                last_fired_at=now,
            ),
        ]
    )
    index = mesh_runtime.edges.descriptor_index()
    assert index[(str(cronos), str(zeus))] == "father_of"


def test_both_edges_survive_the_choice(mesh_runtime: MeshRuntime) -> None:
    """Choosing what to *display* must not drop what is *stored*.

    Keying by the node pair alone once collapsed 27,824 rows to 15,628 and took
    2,520 typed relations with it (PHX-1033). This is a read-side view; the
    store keeps both edges.
    """
    now = datetime.now(UTC)
    a, b = ULID(), ULID()
    mesh_runtime.edges.append_edges(
        [
            Edge(
                source_id=a,
                target_id=b,
                weight=1.0,
                relation_descriptor=d,
                born_at=now,
                last_fired_at=now,
            )
            for d in ("father_of", "co_mentions_in_paragraph")
        ]
    )
    stored = [e for e in mesh_runtime.edges.load_all_edges() if str(e.source_id) == str(a)]
    assert {e.relation_descriptor for e in stored} == {"father_of", "co_mentions_in_paragraph"}
