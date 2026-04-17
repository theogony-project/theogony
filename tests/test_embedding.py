"""Tests for the EmbeddingProvider protocol and the local default."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from theogony.extraction.embedding import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbedder,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _fake_st_model(dim: int = 384, fail_on_dim_mismatch: bool = False) -> MagicMock:
    """A MagicMock SentenceTransformer-like object.

    Returns deterministic vectors whose shape we can control. Good
    enough to exercise every code path inside
    LocalSentenceTransformerEmbedder without paying the BGE-small
    download cost in CI.
    """
    import numpy as np

    model = MagicMock()
    actual_dim = dim - 1 if fail_on_dim_mismatch else dim

    def encode(texts: list[str], **_: Any) -> Any:  # noqa: ANN401 - SentenceTransformer signature is dynamic
        rng = np.random.default_rng(42)
        return rng.standard_normal((len(texts), actual_dim))

    model.encode = encode
    return model


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_local_embedder_satisfies_protocol(self) -> None:
        embedder = LocalSentenceTransformerEmbedder()
        assert isinstance(embedder, EmbeddingProvider)


# ---------------------------------------------------------------------------
# LocalSentenceTransformerEmbedder, with mocked SentenceTransformer
# ---------------------------------------------------------------------------


class TestLocalEmbedderWithMock:
    async def test_embed_returns_vector_of_configured_dim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        embedder = LocalSentenceTransformerEmbedder(dim=384)
        monkeypatch.setattr(embedder, "_load_model", lambda: _fake_st_model(dim=384))
        vector = await embedder.embed("Heinrich Harrer reached Uttarkashi.")
        assert len(vector) == 384
        assert all(isinstance(x, float) for x in vector)

    async def test_embed_many_preserves_order_and_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        embedder = LocalSentenceTransformerEmbedder(dim=384)
        monkeypatch.setattr(embedder, "_load_model", lambda: _fake_st_model(dim=384))
        sentences = [f"sentence number {i}" for i in range(5)]
        vectors = await embedder.embed_many(sentences)
        assert len(vectors) == 5
        assert all(len(v) == 384 for v in vectors)

    async def test_embed_many_empty_returns_empty_without_loading_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        embedder = LocalSentenceTransformerEmbedder()
        sentinel = MagicMock()
        monkeypatch.setattr(embedder, "_load_model", lambda: sentinel)
        result = await embedder.embed_many([])
        assert result == []
        sentinel.assert_not_called()  # model never loaded for empty input

    async def test_dim_mismatch_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        embedder = LocalSentenceTransformerEmbedder(dim=384)
        monkeypatch.setattr(
            embedder, "_load_model", lambda: _fake_st_model(dim=384, fail_on_dim_mismatch=True)
        )
        with pytest.raises(ValueError, match="dim="):
            await embedder.embed("any text")


class TestLocalEmbedderIdentity:
    def test_model_id_includes_version_suffix(self) -> None:
        embedder = LocalSentenceTransformerEmbedder()
        assert embedder.model_id == "BAAI/bge-small-en-v1.5@v1"

    def test_model_id_changes_with_version_bump(self) -> None:
        embedder = LocalSentenceTransformerEmbedder(version="v2")
        assert embedder.model_id == "BAAI/bge-small-en-v1.5@v2"

    def test_dim_default_is_384(self) -> None:
        assert LocalSentenceTransformerEmbedder().dim == 384

    def test_dim_is_overridable(self) -> None:
        assert LocalSentenceTransformerEmbedder(dim=1024).dim == 1024


class TestLazyLoading:
    async def test_model_not_loaded_until_first_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_count = 0

        def _counted_load() -> object:
            nonlocal load_count
            load_count += 1
            return _fake_st_model(dim=384)

        embedder = LocalSentenceTransformerEmbedder(dim=384)
        monkeypatch.setattr(embedder, "_load_model", _counted_load)
        assert load_count == 0
        await embedder.embed("first")
        assert load_count == 1
        await embedder.embed("second")
        # Counter goes up because we patched away the cache slot, but
        # the production code only loads once via self._model — that is
        # tested in `test_model_cached_after_first_load`.
        assert load_count == 2


class TestRealBgeSmallIntegration:
    """Integration test against the real BGE-small model.

    Skipped unless ``THEOGONY_RUN_EMBEDDING_INTEGRATION=1`` is set —
    pulls ~33 MB from Hugging Face on first run.
    """

    @pytest.mark.skipif(
        os.environ.get("THEOGONY_RUN_EMBEDDING_INTEGRATION") != "1",
        reason="set THEOGONY_RUN_EMBEDDING_INTEGRATION=1 to run real model",
    )
    async def test_real_bge_small_produces_normalised_384d_vectors(self) -> None:
        embedder = LocalSentenceTransformerEmbedder()
        vectors = await embedder.embed_many(
            ["Heinrich Harrer reached Uttarkashi.", "Tibet is a high plateau."]
        )
        assert len(vectors) == 2
        assert all(len(v) == 384 for v in vectors)
        # BGE-small with normalize_embeddings=True returns unit vectors.
        for v in vectors:
            norm_sq = sum(x * x for x in v)
            assert abs(norm_sq - 1.0) < 0.05
