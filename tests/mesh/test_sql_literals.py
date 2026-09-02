"""Every string in a Lance filter is a single-quoted SQL literal (PHX-1105).

lancedb 0.38 (lance-datafusion 11) reads a double-quoted token in `where` /
`delete` as an identifier, as standard SQL does; 0.37 tolerated it as a string.
Every filter in the store used double quotes, so the first code PR after the
version moved failed 40 tests in CI while 1,851 passed locally on 0.37 — the
gap AGENTS.md §5 warns about, seen for the fourth time.

Two guards. The static one reads the store sources and refuses the shape that
broke, so the next filter written from habit fails here rather than in CI. The
functional one puts an apostrophe through every lookup, because that is the one
character the new quoting has to escape.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ulid import ULID

from theogony.mesh.runtime.oneiros_tick import MeshRuntime
from theogony.mesh.schemas import ConsolidatedNode, Edge, QIDTag
from theogony.mesh.storage.sql import sql_in, sql_literal

STORE = Path(__file__).resolve().parents[2] / "src" / "theogony" / "mesh" / "storage"
# An f-string filter that wraps its value in double quotes: `= "{x}"`, `("{x}"`.
_DOUBLE_QUOTED_VALUE = re.compile(r'[=(,]\s*\\?"\{')


@pytest.mark.parametrize("path", sorted(STORE.glob("*.py")), ids=lambda p: p.name)
def test_no_filter_wraps_a_value_in_double_quotes(path: Path) -> None:
    offending = [
        f"{path.name}:{i}: {line.strip()}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if (".where(" in line or ".delete(" in line or "quoted" in line)
        and _DOUBLE_QUOTED_VALUE.search(line)
    ]
    assert not offending, "\n".join(offending)


def test_the_helper_escapes_the_one_character_that_matters() -> None:
    assert sql_literal("o'neil") == "'o''neil'"
    assert sql_literal("plain") == "'plain'"
    assert sql_in(["a", "b'c"]) == "('a','b''c')"


def test_every_lookup_survives_an_apostrophe(tmp_path: Path) -> None:
    """The store's own labels are normalised to [a-z0-9 ], so no apostrophe reaches
    the label index today — but ids, Q-IDs and node ids are passed through as
    given, and a caller is one `'` away from a broken filter."""
    runtime = MeshRuntime(tmp_path / "ws", semantic_dim=8, frame_dim=4)
    now = datetime(2026, 9, 2, tzinfo=UTC)
    node = ConsolidatedNode(
        id=ULID(),
        born_at=now,
        last_fired_at=now,
        semantic_vector=[0.1] * 8,
        frame_vector=[0.1] * 4,
        description="O'Neil — a person with an apostrophe",
        tags=["O'Neil"],
        qids=[QIDTag(qid="Q1", confidence=0.9, attached_at=now)],
    )
    other = node.model_copy(
        update={"id": ULID(), "description": "Other — x", "tags": ["Other"], "qids": []}
    )
    runtime.nodes.append_consolidated_many([node, other])
    runtime.edges.append_edges(
        [Edge(source_id=node.id, target_id=other.id, weight=0.5, born_at=now, last_fired_at=now)]
    )

    assert runtime.nodes.get_consolidated(str(node.id)) is not None
    assert set(runtime.nodes.get_consolidated_many([str(node.id), str(other.id)])) == {
        str(node.id),
        str(other.id),
    }
    assert runtime.nodes.get_consolidated_by_qid("Q1") is not None
    assert runtime.nodes.get_consolidated_by_label("O'Neil") is not None
    assert [str(n.id) for n in runtime.nodes.find_consolidated_by_labels(["O'Neil"])] == [
        str(node.id)
    ]
    assert runtime.edges.neighbor_ids(str(node.id)) == {str(other.id)}
    assert runtime.edges.load_metadata_for_sources([str(node.id)]) == {}
    # A lookup for a value that is only an apostrophe must not be a syntax error.
    assert runtime.nodes.get_consolidated("'") is None
