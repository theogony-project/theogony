"""W13 settings guards for removed pre-gate configuration."""

from __future__ import annotations

import os

import pytest

from theogony.config.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [n for n in os.environ if n.startswith("THEOGONY_")]:
        monkeypatch.delenv(name, raising=False)


def test_settings_rejects_removed_sentinel_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__HESTIA_SENTINEL__ENABLED", "true")
    with pytest.raises(ValueError):
        Settings()


def test_settings_rejects_removed_lite_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THEOGONY_CURIOSITY__HESTIA_LITE__ENABLED", "true")
    with pytest.raises(ValueError):
        Settings()
