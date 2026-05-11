"""
EmbeddingProvider protocol and the default local implementation.

Per Plan §2.3 + §3.2 the default Gen 1 embedder is BGE-small-en-v1.5
(384 dim) loaded via ``sentence-transformers``. Local + free + 33 MB +
hundreds of sentences/second on CPU. Optional alternatives
(OpenAI 3-small, gte-large) live behind the same Protocol.

Every embedder reports the model identity it commits to a vector
(``model_id``, ``dim``); ingest writes that identity onto every node
(:attr:`KnowledgeNode.embedding_model_id` per Plan §9.3) so a future
Phoenix re-embedding pass can target only stale-model nodes.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Protocol, runtime_checkable

from theogony.config.logging import get_logger

log = get_logger("extraction.embedding")


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Strategy interface for converting text to dense vectors.

    Implementations MUST:
        - return vectors of fixed ``dim``
        - be safe to call concurrently from asyncio tasks
        - not silently truncate input — if a string is too long for
          the underlying model, raise rather than return junk.

    They MAY batch internally for throughput; ``embed_many`` is
    expected to be substantially faster than N calls to ``embed``.
    """

    @property
    def model_id(self) -> str:
        """Stable identifier of the model + version, e.g. ``BAAI/bge-small-en-v1.5@v1``.

        This string is recorded on every node the embedder touches so
        the Phoenix process can find them later. Implementations
        SHOULD include a version suffix even when the upstream model
        does not — allows local re-embedding without coordinating
        with the upstream Hugging Face name.
        """
        ...

    @property
    def dim(self) -> int:
        """Dimensionality of returned vectors."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Embed a single string. Returns a vector of length ``dim``."""
        ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings, preserving order."""
        ...


class LocalSentenceTransformerEmbedder:
    """Default Gen 1 embedder: BGE-small-en-v1.5 via ``sentence-transformers``.

    The model is loaded lazily on first ``embed``/``embed_many`` call
    so importing this module does not pay the ~33 MB / few-hundred-ms
    cold-start cost. Subsequent calls reuse the cached model.

    Encoding runs in a thread executor (``asyncio.to_thread``) — the
    underlying ``sentence_transformers`` is synchronous CPU/GPU work,
    not async, so we keep the event loop responsive for other tasks.
    """

    def __init__(
        self,
        model_id: str = "BAAI/bge-small-en-v1.5",
        dim: int = 384,
        version: str = "v1",
        cache_folder: str | None = None,
    ) -> None:
        self._upstream_id = model_id
        self._version = version
        self._dim = dim
        self._cache_folder = cache_folder
        self._model: object | None = None  # SentenceTransformer; deferred import
        self._load_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return f"{self._upstream_id}@{self._version}"

    @property
    def dim(self) -> int:
        return self._dim

    def _load_model(self) -> object:
        """Lazy SentenceTransformer load with thread safety."""
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer

            log.info(
                "loading sentence-transformer model_id=%s cache=%s",
                self._upstream_id,
                self._cache_folder or "<default>",
            )
            self._model = SentenceTransformer(
                self._upstream_id,
                cache_folder=self._cache_folder,
            )
        return self._model

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        # SentenceTransformer.encode returns numpy.ndarray; we coerce to
        # plain Python lists to keep KnowledgeNode.embedding (list[float])
        # JSON-serialisable without a numpy round-trip every time.
        vectors = model.encode(  # type: ignore[attr-defined]
            texts,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        result: list[list[float]] = [v.tolist() for v in vectors]
        for v in result:
            if len(v) != self._dim:
                raise ValueError(
                    f"embedder returned dim={len(v)} but configured dim={self._dim}; "
                    f"model_id={self.model_id}"
                )
        return result

    async def embed(self, text: str) -> list[float]:
        result = await self.embed_many([text])
        return result[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_sync, texts)
