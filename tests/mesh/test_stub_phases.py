"""S5 stubs must remain explicit until the full Oneiros tick lands."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from theogony.mesh.runtime.oneiros_tick import (
    stub_consolidation_phase,
    stub_pathology_phase,
    stub_split_phase,
    stub_therapy_phase,
)


@pytest.mark.parametrize(
    "fn",
    [
        stub_consolidation_phase,
        stub_split_phase,
        stub_pathology_phase,
        stub_therapy_phase,
    ],
)
def test_stub_phases_raise_not_implemented(fn: Callable[[], None]) -> None:
    with pytest.raises(NotImplementedError):
        fn()
