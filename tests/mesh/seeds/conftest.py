from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from theogony.reporting.writer import RunReportWriter


def _vector_for(text: str, *, dim: int) -> list[float]:
    data = bytearray()
    counter = 0
    seed = text.encode("utf-8")
    while len(data) < dim * 4:
        data.extend(hashlib.sha256(seed + counter.to_bytes(4, "little")).digest())
        counter += 1
    values: list[float] = []
    for idx in range(dim):
        chunk = data[idx * 4 : (idx + 1) * 4]
        raw = int.from_bytes(chunk, "little", signed=False)
        values.append((raw / 2**32) * 2.0 - 1.0)
    norm = sum(value * value for value in values) ** 0.5
    return [value / norm for value in values]


class DummySeedEmbedder:
    model_id = "dummy-seed-embedder"
    dim = 8

    async def embed_many(self, texts: list[str], *, batch_size: int = 64) -> list[list[float]]:
        del batch_size
        return [_vector_for(text, dim=self.dim) for text in texts]


@pytest.fixture
def wikidata_fixture_root() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def seed_embedder() -> DummySeedEmbedder:
    return DummySeedEmbedder()


@pytest.fixture
def seed_report_writer(tmp_path: Path) -> RunReportWriter:
    return RunReportWriter(tmp_path / "run_reports")
