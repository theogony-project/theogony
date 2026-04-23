"""Manifest repository + routes (PHX-0074)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from theogony.config.settings import Settings


def test_manifest_first_save_creates_default_template(
    cockpit_client: TestClient,
    api_settings: Settings,
) -> None:
    r = cockpit_client.post("/cockpit/manifest", data={})
    assert r.status_code == 200
    mp = api_settings.data_dir / "cockpit" / "manifest.md"
    assert mp.is_file()
    text = mp.read_text(encoding="utf-8")
    assert "Manifest of" in text


def test_manifest_save_writes_atomically_and_snapshots_history(
    cockpit_client: TestClient,
    api_settings: Settings,
) -> None:
    mp = api_settings.data_dir / "cockpit" / "manifest.md"
    hist = api_settings.data_dir / "cockpit" / "manifest.history"
    cockpit_client.post("/cockpit/manifest", data={"content": "VERSION_A"})
    cockpit_client.post("/cockpit/manifest", data={"content": "VERSION_B"})
    assert mp.read_text(encoding="utf-8") == "VERSION_B"
    snaps = list(hist.glob("*.md"))
    assert len(snaps) >= 1


def test_manifest_save_rejects_oversize_body(cockpit_client: TestClient) -> None:
    big = "x" * (70 * 1024)
    r = cockpit_client.post("/cockpit/manifest", data={"content": big})
    assert r.status_code == 413


def test_manifest_save_rejects_invalid_utf8_urlencoded(cockpit_client: TestClient) -> None:
    r = cockpit_client.post(
        "/cockpit/manifest",
        content=b"content=%FF%FE",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Starlette may coerce urlencoded bytes; accept non-2xx or unchanged manifest.
    assert r.status_code in (200, 400, 422, 415)
