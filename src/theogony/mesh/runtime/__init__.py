"""Mesh runtime operators (Spreading Activation, Oneiros tick)."""

from theogony.mesh.runtime.oneiros_tick import MeshRuntime, MinimalTickResult
from theogony.mesh.runtime.spreading import spreading_activation

__all__ = ["MeshRuntime", "MinimalTickResult", "spreading_activation"]
