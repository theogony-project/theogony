"""Text-to-vector helpers for mesh ingestion.

Prefer the local sentence-transformer when the runtime dimensions match the
configured embedding model. Fall back to deterministic hash projections for
tests or non-default dimensions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from theogony.config.settings import Settings
from theogony.extraction.embedding import LocalSentenceTransformerEmbedder


def _hash_projection(text: str, dim: int, *, salt: str = "") -> list[float]:
    if dim <= 0:
        return []
    data = bytearray()
    seed = f"{salt}::{text}".encode()
    counter = 0
    while len(data) < dim * 4:
        data.extend(hashlib.sha256(seed + counter.to_bytes(4, "little")).digest())
        counter += 1

    values: list[float] = []
    for idx in range(dim):
        chunk = data[idx * 4 : (idx + 1) * 4]
        raw = int.from_bytes(chunk, "little", signed=False)
        values.append((raw / 2**32) * 2.0 - 1.0)
    norm = sum(value * value for value in values) ** 0.5
    if norm == 0.0:
        return [0.0] * dim
    return [value / norm for value in values]


class MeshTextVectorizer:
    """Semantic/description vectors plus lightweight frame projections."""

    def __init__(
        self,
        *,
        semantic_dim: int,
        frame_dim: int,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self.semantic_dim = semantic_dim
        self.frame_dim = frame_dim
        self._semantic_embedder = None
        if semantic_dim == self._settings.embedding.dim:
            self._semantic_embedder = LocalSentenceTransformerEmbedder(
                model_id=self._settings.embedding.model_id,
                dim=self._settings.embedding.dim,
            )

    @property
    def semantic_model_id(self) -> str:
        if self._semantic_embedder is not None:
            return self._semantic_embedder.model_id
        return f"hash-projection-semantic@{self.semantic_dim}"

    async def semantic_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._semantic_embedder is not None:
            return await self._semantic_embedder.embed_many(texts)
        return [_hash_projection(text, self.semantic_dim, salt="semantic") for text in texts]

    async def semantic(self, text: str) -> list[float]:
        return (await self.semantic_many([text]))[0]

    async def description_many(self, texts: list[str]) -> list[list[float]]:
        return await self.semantic_many(texts)

    async def description(self, text: str) -> list[float]:
        return await self.semantic(text)

    async def frame_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [_hash_projection(text, self.frame_dim, salt="frame") for text in texts]

    async def frame(self, text: str) -> list[float]:
        return _hash_projection(text, self.frame_dim, salt="frame")
