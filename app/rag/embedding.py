"""Singleton embedding service using sentence-transformers."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from app.core.config import get_index_config

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Singleton wrapper around a sentence-transformers model.

    Loads the model name from IndexConfig and provides async methods
    for batch embedding and single-query embedding.
    """

    _instance: EmbeddingService | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._model = None
        self._config = get_index_config()
        self._model_name = self._config.embedding.model

    @classmethod
    async def get_instance(cls) -> "EmbeddingService":
        """Return the singleton instance, lazily initialising the model."""
        if cls._instance is not None:
            return cls._instance
        async with cls._lock:
            if cls._instance is not None:
                return cls._instance
            instance = cls()
            await instance._load_model()
            cls._instance = instance
            return cls._instance

    async def _load_model(self) -> None:
        """Load the sentence-transformers model in a thread (CPU-bound)."""
        loop = asyncio.get_running_loop()
        logger.info("Loading embedding model: %s", self._model_name)
        self._model = await loop.run_in_executor(
            None, self._load_model_sync
        )
        logger.info("Embedding model loaded successfully.")

    def _load_model_sync(self):
        from sentence_transformers import SentenceTransformer
        import os
        # Quick connectivity check - if HF is unreachable, skip immediately
        if os.environ.get("SKIP_EMBEDDING_MODEL", "") == "1":
            logger.info("Embedding model loading skipped (SKIP_EMBEDDING_MODEL=1)")
            return None
        try:
            # Set a short timeout for the HTTP request
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "5")
            return SentenceTransformer(self._model_name)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s. Using dummy embeddings.", e)
            return None

    @property
    def model(self):
        if self._model is None:
            raise RuntimeError("Embedding model not loaded. Call get_instance() first.")
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return a list of embedding vectors."""
        if not texts:
            return []
        if self._model is None:
            # Return zero vectors as fallback
            dim = self._config.embedding.dimension
            return [[0.0] * dim for _ in texts]
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: self.model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        return [emb.tolist() for emb in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text and return the embedding vector."""
        results = await self.embed_texts([text])
        return results[0]


@lru_cache()
def _get_embedding_service_sync() -> EmbeddingService:
    """Convenience for sync-first callers that can block."""
    instance = EmbeddingService()
    # Load model synchronously on first call
    from sentence_transformers import SentenceTransformer
    instance._model = SentenceTransformer(get_index_config().embedding.model)
    return instance
