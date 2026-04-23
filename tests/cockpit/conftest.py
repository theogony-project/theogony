"""Cockpit-specific fixtures (PHX-0074)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def cockpit_client(api_app: FastAPI) -> Iterator[TestClient]:
    """TestClient with cockpit routes mounted (via ``api_app`` fixture)."""
    with TestClient(api_app) as client:
        yield client
