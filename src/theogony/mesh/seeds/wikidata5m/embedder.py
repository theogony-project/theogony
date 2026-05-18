"""Pluggable local embedders for the wikidata5m seed path."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Protocol

import torch

from theogony.config.logging import get_logger

log = get_logger("mesh.seeds.wikidata5m.embedder")


class MeshEmbedder(Protocol):
    model_id: str
    dim: int

    async def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 64,
    ) -> list[list[float]]: ...


class EdgesOnlyEmbedder:
    """Placeholder when topping up edges on an existing workspace (no encoding)."""

    model_id = "edges-only"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    async def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 64,
    ) -> list[list[float]]:
        raise RuntimeError("edges-only seed pass must not embed text")


def _detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class SentenceTransformerMeshEmbedder:
    """Async wrapper around sentence-transformers with device autodetect."""

    def __init__(self, upstream_model_id: str) -> None:
        self._upstream_model_id = upstream_model_id
        self._device = _detect_device()
        self._load_lock = threading.Lock()
        self._model = None
        self.model_id = upstream_model_id
        self.dim = 0

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import SentenceTransformer

            log.info(
                "loading seed embedder model_id=%s device=%s",
                self._upstream_model_id,
                self._device,
            )
            model = SentenceTransformer(self._upstream_model_id, device=self._device)
            dim = model.get_sentence_embedding_dimension()
            if dim is None:
                raise ValueError(
                    f"model {self._upstream_model_id} did not report an embedding size"
                )
            self.dim = int(dim)
            self._model = model
        return self._model

    def _encode_sync(self, texts: list[str], batch_size: int) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [vector.tolist() for vector in vectors]

    async def embed_many(
        self,
        texts: list[str],
        *,
        batch_size: int = 64,
    ) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode_sync, texts, batch_size)


class BGEM3Embedder(SentenceTransformerMeshEmbedder):
    def __init__(self) -> None:
        super().__init__("BAAI/bge-m3")


class BGESmallEnEmbedder(SentenceTransformerMeshEmbedder):
    def __init__(self) -> None:
        super().__init__("BAAI/bge-small-en-v1.5")


def build_embedder(name: str) -> MeshEmbedder:
    normalized = name.strip().lower()
    if normalized == "bge-m3":
        return BGEM3Embedder()
    if normalized == "bge-small-en":
        return BGESmallEnEmbedder()
    raise ValueError(f"unsupported embedder: {name}")


async def build_default_embedder() -> tuple[str, MeshEmbedder]:
    preferred = build_embedder("bge-m3")
    try:
        await preferred.embed_many(["mesh seed smoke probe"], batch_size=1)
        return "bge-m3", preferred
    except Exception as exc:  # noqa: BLE001
        log.warning("bge-m3 unavailable for seed path, falling back: %s", exc)
    fallback = build_embedder("bge-small-en")
    await fallback.embed_many(["mesh seed smoke probe"], batch_size=1)
    return "bge-small-en", fallback
