"""Hybrid retriever combining ChromaDB vector search and BM25 keyword search."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.config import get_index_config

logger = logging.getLogger(__name__)


class BM25Scorer:
    """Lightweight BM25 implementation for keyword scoring over a small corpus.

    Uses the standard BM25 scoring formula with default k1=1.5, b=0.75.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._corpus: list[str] = []
        self._tokenized: list[list[str]] = []
        self._doc_freq: dict[str, int] = {}
        self._avg_doc_len: float = 0.0
        self._N: int = 0

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer."""
        import re
        return re.findall(r"[\w一-鿿]+", text.lower())

    def index(self, documents: list[dict]) -> None:
        """Build BM25 index from a list of document dicts (each has 'question', 'answer')."""
        self._corpus = []
        self._tokenized = []
        self._doc_freq = {}
        total_len = 0

        for doc in documents:
            text = f"{doc.get('question', '')} {doc.get('answer', '')}"
            self._corpus.append(text)
            tokens = self._tokenize(text)
            self._tokenized.append(tokens)
            total_len += len(tokens)

            seen = set()
            for t in tokens:
                if t not in seen:
                    self._doc_freq[t] = self._doc_freq.get(t, 0) + 1
                    seen.add(t)

        self._N = len(self._corpus)
        self._avg_doc_len = total_len / self._N if self._N > 0 else 0.0

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Return scored documents as list of (doc_index, score)."""
        if self._N == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: list[float] = []
        for i, tokens in enumerate(self._tokenized):
            score = 0.0
            doc_len = len(tokens)
            for qt in query_tokens:
                df = self._doc_freq.get(qt, 0)
                if df == 0:
                    continue
                idf = max(0, ((self._N - df + 0.5) / (df + 0.5)) + 1.0)
                tf = tokens.count(qt)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_len)
                score += idf * (numerator / denominator)
            scores.append(score)

        # Rank and return top_k
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(idx, s) for idx, s in indexed if s > 0][:top_k]


class HybridRetriever:
    """Combines vector search (ChromaDB) with BM25 keyword search via RRF.

    Reciprocal Rank Fusion (RRF) merges two ranked lists into a single
    relevance-ordered result set.
    """

    RRF_K = 60  # standard RRF constant

    def __init__(self, embedding_service=None, indexer=None) -> None:
        self._config = get_index_config()
        self._embedding_service = embedding_service
        self._indexer = indexer
        self._bm25 = BM25Scorer()
        self._bm25_docs: list[dict] = []  # reference to indexed docs

    async def _ensure_services(self):
        if self._embedding_service is None:
            from app.rag.embedding import EmbeddingService
            self._embedding_service = await EmbeddingService.get_instance()
        if self._indexer is None:
            from app.rag.indexer import Indexer
            self._indexer = Indexer(embedding_service=self._embedding_service)

    async def retrieve(
        self,
        query: str,
        domain: str | None = None,
        top_k: int = 20,
    ) -> list[dict]:
        """Hybrid retrieval: vector + BM25 -> RRF merge -> top_k.

        Args:
            query:  User query string.
            domain: Optional domain filter for vector search.
            top_k:  Number of final merged results to return.

        Returns:
            List of result dicts with keys:
              id, domain, question, answer, keywords, score, source
        """
        await self._ensure_services()

        # ── 1. Vector search via ChromaDB ──────────────────────
        query_embedding = await self._embedding_service.embed_query(query)
        collection = self._indexer._get_collection()

        where_filter = None
        if domain:
            where_filter = {"domain": domain}

        vector_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=self._config.retrieval.vector_top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # ── 2. Fetch all documents for BM25 (may be cached in production) ──
        all_items = collection.get(
            where=where_filter,
            include=["documents", "metadatas"],
        )

        all_docs: list[dict] = []
        for i in range(len(all_items.get("ids", []))):
            doc_id = all_items["ids"][i]
            meta = all_items["metadatas"][i] if all_items["metadatas"] else {}
            all_docs.append({
                "id": doc_id,
                "domain": meta.get("domain", ""),
                "question": all_items["documents"][i] if all_items["documents"] else "",
                "answer": meta.get("answer", ""),
                "keywords": meta.get("keywords", ""),
            })

        # ── 3. BM25 search ─────────────────────────────────────
        self._bm25.index(all_docs)
        bm25_hits = self._bm25.search(query, top_k=self._config.retrieval.bm25_top_k)

        # ── 4. RRF merge ───────────────────────────────────────
        rrf_scores: dict[str, float] = {}

        # Vector rank scores (distance = 0 is best for cosine; invert)
        if vector_results.get("ids") and vector_results["ids"][0]:
            for rank, doc_id in enumerate(vector_results["ids"][0]):
                distance = vector_results["distances"][0][rank] if vector_results.get("distances") else 1.0
                # Convert cosine distance to similarity score
                sim_score = 1.0 - distance
                rrf_scores[doc_id] = self._rrf_score(rank + 1, extra=sim_score)

        # BM25 rank scores
        for rank, (doc_idx, bm25_score) in enumerate(bm25_hits):
            doc_id = all_docs[doc_idx]["id"]
            existing = rrf_scores.get(doc_id, 0.0)
            rrf_scores[doc_id] = existing + self._rrf_score(rank + 1, extra=bm25_score)

        # ── 5. Build result list ───────────────────────────────
        doc_map = {d["id"]: d for d in all_docs}
        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:top_k]

        results: list[dict] = []
        for doc_id in sorted_ids:
            doc = doc_map.get(doc_id)
            if doc is None:
                continue
            doc_copy = dict(doc)
            doc_copy["score"] = round(rrf_scores[doc_id], 4)
            doc_copy["source"] = "hybrid_rrf"
            results.append(doc_copy)

        return results

    @staticmethod
    def _rrf_score(rank: int, extra: float = 0.0) -> float:
        """Compute RRF score with optional extra weight multiplier."""
        base = 1.0 / (HybridRetriever.RRF_K + rank)
        return base * (1.0 + extra * 0.1)

# Singleton instance
hybrid_retriever = HybridRetriever()
