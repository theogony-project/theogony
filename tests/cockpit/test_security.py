"""Cockpit local-only + public binding rules (PHX-0074)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from theogony.cockpit.dependencies import get_settings as cockpit_get_settings
from theogony.config.settings import CockpitSettings, Settings


def test_public_false_blocks_external_origin(cockpit_client: TestClient) -> None:
    r = cockpit_client.get("/cockpit/", headers={"Host": "external.example.com"})
    assert r.status_code == 403


def test_public_true_allows_external_origin(
    api_app: FastAPI,
    api_settings: Settings,
) -> None:
    s = api_settings.model_copy(
        update={
            "cockpit": CockpitSettings(
                public=True,
                bind_host="0.0.0.0",
            ),
        },
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as client:
        r = client.get("/cockpit/", headers={"Host": "external.example.com"})
        assert r.status_code == 200


def test_only_setting_public_without_bind_host_raises_at_startup() -> None:
    with pytest.raises(ValueError):
        CockpitSettings(public=True, bind_host="127.0.0.1")


def test_sample_only_mode_warning_in_status_panel(
    api_app: FastAPI,
    api_settings: Settings,
) -> None:
    s = api_settings.model_copy(
        update={"cockpit": CockpitSettings(sample_only=True)},
    )
    api_app.dependency_overrides[cockpit_get_settings] = lambda: s
    with TestClient(api_app) as client:
        r = client.get("/cockpit/")
        assert r.status_code == 200
        assert "Sample-only mode active" in r.text
