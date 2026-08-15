"""Typing shim for LanceDB's vector-query builder.

``Table.search(vector)`` is declared to return the base ``LanceQueryBuilder``, but
at runtime a vector search returns ``LanceVectorQueryBuilder`` — the subclass that
carries ``.metric()``, ``.nprobes()``, ``.refine_factor()`` and the rest of the
vector-specific surface. lancedb 0.37 moved ``.metric`` off the base class, so
every ``search(...).metric("cosine")`` chain in this repo became a type error even
though the call is correct and works.

Rather than scatter five casts (or five suppressions) across the query sites, the
narrowing lives here once, with the reason attached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover - import only needed for the annotation
    from lancedb.query import LanceVectorQueryBuilder


def as_vector_query(builder: Any) -> LanceVectorQueryBuilder:
    """Narrow a ``Table.search(vector)`` result to the vector-query builder.

    Only valid for searches that were given a vector — a full-text or plain
    search returns a different builder without the vector-specific methods.
    """
    return cast("LanceVectorQueryBuilder", builder)
