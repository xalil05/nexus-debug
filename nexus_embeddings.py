"""
nexus_embeddings.py — Recherche sémantique dans la KB via embeddings ChromaDB
Améliore kb_search en utilisant la similarité vectorielle au lieu du mot-à-mot.

Prérequis : pip install chromadb sentence-transformers
Usage :
    from nexus_embeddings import embedder
    await embedder.init()  # un coup au démarrage
    results = await embedder.search("null pointer user auth")
    embedder.store("BUG-001", "Null check manquant dans user.py")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from loguru import logger

CHROMA_DIR = os.getenv("NEXUS_CHROMA_DIR", "/data/nexus/chroma")
COLLECTION_NAME = "nexus-kb"
EMBED_MODEL = os.getenv("NEXUS_EMBED_MODEL", "all-MiniLM-L6-v2")


class EmbeddingSearch:
    """Recherche vectorielle dans la KB via ChromaDB."""

    def __init__(self) -> None:
        self._collection: Any = None
        self._ready = False

    async def init(self) -> None:
        """Initialise ChromaDB (à appeler au démarrage)."""
        try:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path=CHROMA_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            logger.info("ChromaDB prête: {} documents", self._collection.count())
        except ImportError:
            logger.warning("chromadb non installé — désactiver les embeddings")
            self._ready = False
        except Exception as exc:
            logger.warning("ChromaDB init échoué: {}", exc)
            self._ready = False

    def _is_ready(self) -> bool:
        return self._ready and self._collection is not None

    async def store(self, doc_id: str, text: str, metadata: dict[str, str] | None = None) -> None:
        """Stocke un document dans ChromaDB."""
        if not self._is_ready():
            return
        try:
            self._collection.add(
                documents=[text[:2000]],  # limite pour éviter embeddings trop longs
                ids=[doc_id],
                metadatas=[metadata or {}],
            )
        except Exception as exc:
            logger.warning("ChromaDB store failed: {}", exc)

    async def search(
        self, query: str, n_results: int = 5
    ) -> list[dict[str, Any]]:
        """Recherche les documents les plus similaires."""
        if not self._is_ready():
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
            )
            docs = []
            for i, doc in enumerate(results.get("documents", [[]])[0]):
                docs.append({
                    "content": doc,
                    "score": float(results["distances"][0][i]) if results.get("distances") else 0.0,
                    "metadata": (results.get("metadatas", [{}])[0] or {}).get(str(i), {}),
                })
            return docs
        except Exception as exc:
            logger.warning("ChromaDB search failed: {}", exc)
            return []

    async def delete(self, doc_id: str) -> None:
        """Supprime un document."""
        if not self._is_ready():
            return
        try:
            self._collection.delete(ids=[doc_id])
        except Exception:
            pass

    async def count(self) -> int:
        """Nombre de documents dans ChromaDB."""
        if not self._is_ready():
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0


# Singleton
embedder = EmbeddingSearch()
