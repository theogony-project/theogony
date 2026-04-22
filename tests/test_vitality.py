"""Unit tests for linear vitality helpers in ``theogony.core.vitality``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from theogony.core.vitality import compute_connectivity_linear, compute_freshness_linear


def test_compute_freshness_linear_at_zero_idle_returns_one() -> None:
    now = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
    assert compute_freshness_linear(now, 7.0, now=now) == pytest.approx(1.0)


def test_compute_freshness_linear_at_horizon_returns_zero() -> None:
    now = datetime(2026, 4, 10, 0, 0, 0, tzinfo=UTC)
    horizon = 10.0
    last = now - timedelta(days=horizon)
    assert compute_freshness_linear(last, horizon, now=now) == pytest.approx(0.0)


def test_compute_freshness_linear_above_horizon_clamps_to_zero() -> None:
    now = datetime(2026, 4, 10, 0, 0, 0, tzinfo=UTC)
    horizon = 5.0
    last = now - timedelta(days=horizon + 3.0)
    assert compute_freshness_linear(last, horizon, now=now) == pytest.approx(0.0)


def test_compute_freshness_linear_handles_naive_datetime_when_now_provided() -> None:
    now = datetime(2026, 3, 15, 8, 30, tzinfo=UTC)
    last_naive = datetime(2026, 3, 15, 8, 30)
    last_aware = datetime(2026, 3, 15, 8, 30, tzinfo=UTC)
    h = 14.0
    assert compute_freshness_linear(last_naive, h, now=now) == pytest.approx(
        compute_freshness_linear(last_aware, h, now=now)
    )


def test_compute_freshness_linear_handles_none_last_accessed_returns_one() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert compute_freshness_linear(None, 30.0, now=now) == pytest.approx(1.0)


def test_compute_connectivity_linear_at_zero_degree_returns_zero() -> None:
    assert compute_connectivity_linear(0, 10) == pytest.approx(0.0)


def test_compute_connectivity_linear_at_full_credit_returns_one() -> None:
    assert compute_connectivity_linear(8, 8) == pytest.approx(1.0)


def test_compute_connectivity_linear_above_full_credit_clamps_to_one() -> None:
    assert compute_connectivity_linear(100, 10) == pytest.approx(1.0)


def test_compute_connectivity_linear_zero_full_credit_handled_gracefully() -> None:
    assert compute_connectivity_linear(0, 0) == pytest.approx(0.0)
    assert compute_connectivity_linear(3, 0) == pytest.approx(1.0)
