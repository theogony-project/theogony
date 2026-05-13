"""Fixtures for mesh substrate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from theogony.mesh.runtime.oneiros_tick import MeshRuntime


@pytest.fixture
def mesh_runtime(tmp_path: Path) -> MeshRuntime:
    root = tmp_path / "mesh_ws"
    return MeshRuntime(
        root,
        semantic_dim=8,
        frame_dim=4,
        structural_dim=0,
        temporal_dim=0,
        description_dim=0,
    )
