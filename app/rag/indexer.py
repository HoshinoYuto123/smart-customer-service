"""ChromaDB index builder for the SCS knowledge base."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import get_index_config

logger = logging.getLogger(__name__)


class Indexer:
    """Builds and manages a ChromaDB collection for FAQ documents.

    Each document is stored with:
      - id:          unique document identifier
      - domain:      business domain label (metadata)
      - question:    the FAQ question (document content, used for embedding)
      - answer:      the FAQ answer text (metadata)
      - keywords:    list of keywords (metadata, stored as comma-joined string)
    """

    def __init__(self, embedding_service=None) -> None:
        self._config = get_index_config()
        self._client = None
        self._collection = None
        self._embedding_service = embedding_service

    async def _ensure_embedding_service(self):
        if self._embedding_service is not None:
            return
        from app.rag.embedding import EmbeddingService
        self._embedding_service = await EmbeddingService.get_instance()

    def _get_client(self) -> chromadb.PersistentClient:
        if self._client is None:
            persist_dir = self._config.chromadb.persist_directory
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = self._get_client()
            collection_name = self._config.chromadb.collection_name
            # Get or create the collection with cosine distance
            try:
                self._collection = client.get_collection(name=collection_name)
                logger.info("Opened existing ChromaDB collection: %s", collection_name)
            except Exception:
                self._collection = client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("Created new ChromaDB collection: %s", collection_name)
        return self._collection

    # ── Build / Rebuild ───────────────────────────────────────────

    async def build_index(self, faq_items: list[dict]) -> None:
        """Embed and upsert a batch of FAQ items into ChromaDB.

        Args:
            faq_items: list of dicts, each with at least:
                id, domain, question, answer, keywords
        """
        if not faq_items:
            logger.warning("build_index called with empty FAQ list; skipping.")
            return

        await self._ensure_embedding_service()

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        embeddings: list[list[float]] = []

        # Prepare documents
        for item in faq_items:
            ids.append(item["id"])
            documents.append(item["question"])

            meta = {
                "domain": item.get("domain", ""),
                "answer": item.get("answer", ""),
                "keywords": ",".join(item.get("keywords", [])),
            }
            metadatas.append(meta)

        # Embed
        logger.info("Embedding %d FAQ items for index build...", len(faq_items))
        embeddings = await self._embedding_service.embed_texts(documents)

        # Upsert
        collection = self._get_collection()
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info("Build index complete: upserted %d documents.", len(ids))

    # ── Incremental operations ────────────────────────────────────

    async def add_documents(self, docs: list[dict]) -> None:
        """Add new documents to the collection one at a time.

        Args:
            docs: list of dicts with id, domain, question, answer, keywords
        """
        if not docs:
            return
        await self._ensure_embedding_service()

        collection = self._get_collection()
        for doc in docs:
            emb = await self._embedding_service.embed_texts([doc["question"]])
            meta = {
                "domain": doc.get("domain", ""),
                "answer": doc.get("answer", ""),
                "keywords": ",".join(doc.get("keywords", [])),
            }
            collection.upsert(
                ids=[doc["id"]],
                documents=[doc["question"]],
                metadatas=[meta],
                embeddings=[emb[0]],
            )
        logger.info("Added %d document(s) to collection.", len(docs))

    def delete_documents(self, ids: list[str]) -> None:
        """Remove documents from the collection by their IDs."""
        if not ids:
            return
        collection = self._get_collection()
        collection.delete(ids=ids)
        logger.info("Deleted %d document(s) from collection.", len(ids))

    def collection_count(self) -> int:
        """Return the number of documents in the collection."""
        return self._get_collection().count()

    def delete_collection(self) -> None:
        """Drop the entire collection (use with care)."""
        client = self._get_client()
        collection_name = self._config.chromadb.collection_name
        try:
            client.delete_collection(name=collection_name)
            self._collection = None
            logger.info("Deleted ChromaDB collection: %s", collection_name)
        except Exception:
            logger.warning("Collection %s not found; nothing to delete.", collection_name)
