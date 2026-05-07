"""Tests for full-density chunk target heuristics."""

from __future__ import annotations

from theogony.extraction.topology_parser import (
    full_density_chunk_targets,
    hierarchical_macro_targets,
    subdivide_slice_targets,
)


def test_full_density_chunk_targets_16k_window() -> None:
    mn, st, mx = full_density_chunk_targets(16_000)
    assert mn == 260
    assert st == 320
    assert mx == 1820


def test_full_density_chunk_targets_tiny() -> None:
    mn, st, mx = full_density_chunk_targets(400)
    assert mn == 40
    assert st == 40
    assert mx == 400


def test_hierarchical_macro_targets_16k_expects_dense_synapses() -> None:
    lo, hi, mn_syn, mx_syn = hierarchical_macro_targets(16_000)
    assert 10 <= lo <= hi <= 34
    assert mn_syn >= 72
    assert mx_syn >= mn_syn
    assert mn_syn >= 16_000 // 40


def test_subdivide_slice_targets_scale_with_slice_len() -> None:
    a_lo, a_hi, a_sn_lo, a_sn_hi = subdivide_slice_targets(900)
    b_lo, b_hi, b_sn_lo, b_sn_hi = subdivide_slice_targets(12_000)
    assert b_lo >= a_lo
    assert b_sn_lo >= a_sn_lo
    assert b_sn_hi >= b_sn_lo
