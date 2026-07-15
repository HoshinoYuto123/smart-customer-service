"""Cross-Encoder reranker for improving retrieval precision."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """Reranks candidate documents using a cross-encoder model.

    The cross-encoder scores each (query, candidate_text) pair jointly,
    yielding more accurate relevance judgements than bi-encoder similarity.
    """

    def __init__(self, model_name: str = _DEFAULT_CROSS_ENCODER) -> None:
        self._model_name = model_name
        self._model = None

    async def _load_model(self) -> None:
        """Load the cross-encoder model in a thread."""
        if self._model is not None:
            return
        loop = asyncio.get_running_loop()
        logger.info("Loading cross-encoder model: %s", self._model_name)
        self._model = await loop.run_in_executor(None, self._load_model_sync)
        logger.info("Cross-encoder model loaded.")

    def _load_model_sync(self):
        from sentence_transformers import CrossEncoder
        return CrossEncoder(self._model_name)

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Rerank candidate documents using the cross-encoder.

        Each candidate is scored on: "query [SEP] question answer"

        Args:
            query:      User query string.
            candidates: List of candidate dicts (each has 'question' and 'answer').
            top_k:      Number of top results to return after reranking.

        Returns:
            Re-ranked list of candidate dicts with an added 'rerank_score' field.
        """
        if not candidates:
            return []

        await self._load_model()

        # Build (query, document) pairs for the cross-encoder
        pairs: list[tuple[str, str]] = []
        for c in candidates:
            doc_text = f"{c.get('question', '')} {c.get('answer', '')}"
            pairs.append((query, doc_text))

        # Score in a thread
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(
            None, lambda: self._model.predict(pairs, show_progress_bar=False)
        )

        # Attach scores and sort
        for i, c in enumerate(candidates):
            c["rerank_score"] = round(float(scores[i]), 4)

        sorted_candidates = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return sorted_candidates[:top_k]

# Singleton instance
reranker = Reranker()
