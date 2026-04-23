"""Small asyncio helpers for cockpit tests (PHX-0074)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable


def run_async[T](coro: Awaitable[T]) -> T:
    """Run ``coro`` from synchronous tests (no ``pytest.mark.asyncio``)."""
    return asyncio.run(coro)
