"""Shared fixtures for mesh substrate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.mesh.runtime.oneiros_tick import MeshRuntime


@pytest.fixture
def mesh_runtime(tmp_path: Path) -> MeshRuntime:
    """Minimal workspace with 8-d semantic and 4-d frame vectors."""
    return MeshRuntime(
        tmp_path / "mesh_ws",
        semantic_dim=8,
        frame_dim=4,
    )
