"""SSE status channel (PHX-0074)."""

from __future__ import annotations

from theogony.cockpit.sse import sse_tick_interval_s
from theogony.config.settings import CockpitSettings, Settings


def test_sse_status_respects_minimum_interval() -> None:
    s = Settings.model_construct(
        cockpit=CockpitSettings.model_construct(status_sse_interval_s=1.0),
    )
    assert sse_tick_interval_s(s) == 5.0
