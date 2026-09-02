"""One way to put a string into a Lance filter, on every lancedb this repo meets.

lancedb 0.38 (lance-datafusion 11) reads a double-quoted token in a `where` /
`delete` filter as an **identifier**, the way standard SQL does; 0.37 and
earlier tolerated it as a string. Every filter in the store used double quotes,
so the first code PR after the version moved failed 40 tests in CI while
passing 1,851 locally — the exact gap AGENTS.md §5 warns about, seen a fourth
time (PHX-1105).

Single-quoted literals with `''` escaping are standard SQL and are accepted by
both versions. Nothing else in this package may build a string literal for a
filter any other way.
"""

from __future__ import annotations

from collections.abc import Iterable


def sql_literal(value: object) -> str:
    """``'value'`` with embedded quotes doubled. Never wrap this in quotes again."""
    return "'" + str(value).replace("'", "''") + "'"


def sql_in(values: Iterable[object]) -> str:
    """``('a','b',...)`` for an ``IN`` clause; the caller guarantees non-empty."""
    return "(" + ",".join(sql_literal(v) for v in values) + ")"
