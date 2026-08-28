"""The backlog must not lie about the project's state.

It is what work gets prioritised from, and in a research repo it is also the
record of what was tried. Audited 2026-08-26 (PHX-1086):

  - 19 of 42 tickets sat at `in_progress` with their implementation merged; 15
    were simply finished and 5 had a named remainder nobody had written down.
  - The catalogue and the YAMLs disagreed on **8 rows in both directions**, so a
    reader could not tell from either side alone which was stale.
  - Ten tickets carried a `status` no document sanctioned, because the schema
    section the README links to did not exist. `done` had quietly displaced the
    `resolved` that the lifecycle rule names.
  - **0 of 42** had the `resolution:` field the README lists as a baseline
    schema field — including every terminal ticket.

These tests pin the two properties that make the backlog readable: the two sides
agree, and the vocabulary is one someone wrote down.

Deliberately not a YAML parse: pyyaml is not a declared dependency, and this repo
has been broken by relying on a transitively-present library resolving
differently in CI (AGENTS.md §5). The fields this reads are plain and unquoted at
column 0.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CATALOGUE = REPO / "docs" / "PHOENIX_BACKLOG.md"
BACKLOG = REPO / "phoenix-backlog"

# Anchored at ^| so prose lines and the |---| separator never match, and only
# the first three cells are consumed — everything after the priority column is
# free text containing backticks, arrows, bold, and pipes inside code spans.
_ROW = re.compile(r"^\|\s*(PHX-\d{4})\s*\|([^|]*)\|\s*([^|]*?)\s*\|")
_STATUS = re.compile(r"^status:\s*(\S+)\s*$", re.M)

# Ratified in docs/PHOENIX_BACKLOG.md §"Ticket format". The three `measured_*`
# values were in use before they were written down and are kept rather than
# migrated away: the distinction between "unfinished" and "finished, and the
# answer was no" is the one this project is about.
ALLOWED = {
    "open",
    "in_progress",
    "done",
    "resolved",
    "superseded",
    "measured_and_rejected",
    "measured_viable",
    "measured_and_shipped_as_a_lever",
}


def _catalogue_rows() -> dict[str, tuple[str, int]]:
    """Status per ticket id from the main table, with the line it sits on."""
    rows: dict[str, tuple[str, int]] = {}
    inside = False
    for lineno, line in enumerate(CATALOGUE.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## Catalogue"):
            inside = True
            continue
        if inside and line.startswith("#"):
            break
        if not inside:
            continue
        match = _ROW.match(line)
        if match:
            rows[match.group(1)] = (match.group(3).replace("*", "").strip(), lineno)
    return rows


def _yaml_statuses() -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted(BACKLOG.glob("PHX-*.yaml")):
        text = path.read_text(encoding="utf-8")
        match = _STATUS.search(text)
        assert match, f"{path.name}: no `status:` field"
        lineno = text[: match.start()].count("\n") + 1
        out[path.stem] = (match.group(1), lineno)
    return out


def test_the_catalogue_and_the_yamls_agree_on_status() -> None:
    """Eight rows disagreed, in both directions. Either side alone was unreadable."""
    catalogue, yamls = _catalogue_rows(), _yaml_statuses()
    problems = []
    for ticket, (yaml_status, yaml_line) in yamls.items():
        if ticket not in catalogue:
            problems.append(f"{ticket}: no row in the catalogue (phoenix-backlog/{ticket}.yaml)")
            continue
        cat_status, cat_line = catalogue[ticket]
        if cat_status != yaml_status:
            problems.append(
                f"{ticket}: catalogue says {cat_status!r} "
                f"(docs/PHOENIX_BACKLOG.md:{cat_line}) but YAML says {yaml_status!r} "
                f"(phoenix-backlog/{ticket}.yaml:{yaml_line})"
            )
    assert not problems, "backlog disagrees with itself:\n  " + "\n  ".join(problems)


def test_every_status_is_one_someone_wrote_down() -> None:
    """`done` displaced `resolved` unnoticed because nothing enumerated the values."""
    problems = [
        f"{ticket}: {status!r} (phoenix-backlog/{ticket}.yaml:{line})"
        for ticket, (status, line) in _yaml_statuses().items()
        if status not in ALLOWED
    ]
    assert not problems, (
        "status values not in docs/PHOENIX_BACKLOG.md §'Ticket format':\n  " + "\n  ".join(problems)
    )


def test_the_allowed_set_is_the_one_the_document_states() -> None:
    """A set defined in two places is a set that will disagree with itself."""
    section = CATALOGUE.read_text(encoding="utf-8")
    start = section.index("## Ticket format")
    section = section[start : section.index("## Catalogue", start)]
    documented = set(re.findall(r"^\| `(\w+)` \|", section, re.M))
    assert documented == ALLOWED, (
        f"only in the document: {sorted(documented - ALLOWED)}; "
        f"only in this test: {sorted(ALLOWED - documented)}"
    )


def test_a_finished_ticket_says_what_was_done() -> None:
    """`resolution:` was absent from 42 of 42 files, terminal ones included."""
    terminal = {
        "done",
        "resolved",
        "superseded",
        "measured_and_rejected",
        "measured_viable",
        "measured_and_shipped_as_a_lever",
    }
    problems = []
    for ticket, (status, _) in _yaml_statuses().items():
        if status not in terminal:
            continue
        text = (BACKLOG / f"{ticket}.yaml").read_text(encoding="utf-8")
        if not re.search(r"^resolution:\s*\S", text, re.M):
            problems.append(f"{ticket} ({status})")
    assert not problems, (
        "finished tickets with no `resolution:` — what was done, and the number "
        "if there is one:\n  " + "\n  ".join(problems)
    )


def test_a_partially_shipped_ticket_names_what_is_left() -> None:
    """Five entries had merged code and an unwritten remainder.

    An `in_progress` ticket whose work is half-merged is the hardest kind to
    pick up: the code looks done. Naming the remainder in the ticket's own words
    is what makes it resumable.
    """
    problems = []
    for ticket, (status, _) in _yaml_statuses().items():
        if status != "in_progress":
            continue
        text = (BACKLOG / f"{ticket}.yaml").read_text(encoding="utf-8")
        if not re.search(r"^remaining:\s*\S", text, re.M):
            problems.append(ticket)
    assert not problems, (
        "in_progress tickets with no `remaining:` field saying what is left:\n  "
        + "\n  ".join(problems)
    )
