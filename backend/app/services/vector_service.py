from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass
class RetrievedChunk:
    article_id: str
    title: str | None
    category_id: str | None
    chunk_index: int
    text: str
    score: float | None


class VectorService:
    _ready: bool | None = None
    _client: Any = None
    _collection: Any = None
    _embedder: Any = None

    @classmethod
    def reset_cache(cls) -> None:
        cls._ready = None
        cls._client = None
        cls._collection = None
        cls._embedder = None

    @classmethod
    def _ensure_ready(cls) -> bool:
        if cls._ready is not None:
            return cls._ready

        if not settings.VECTOR_DB_ENABLED:
            cls._ready = False
            return False

        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError:
            cls._ready = False
            return False

        try:
            cls._client = chromadb.PersistentClient(path=settings.VECTOR_DB_PATH)
            cls._collection = cls._client.get_or_create_collection(
                name=settings.VECTOR_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            cls._embedder = SentenceTransformer(settings.EMBED_MODEL)
            cls._ready = True
            return True
        except Exception:
            cls._ready = False
            return False

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        size = max(settings.VECTOR_CHUNK_SIZE, 100)
        overlap = min(max(settings.VECTOR_CHUNK_OVERLAP, 0), size - 1)
        step = size - overlap

        chunks: list[str] = []
        index = 0
        while index < len(raw):
            chunk = raw[index : index + size].strip()
            if chunk:
                chunks.append(chunk)
            index += step
        return chunks

    @classmethod
    def upsert_article(
        cls,
        article_id: str,
        title: str,
        text_content: str,
        category_id: str,
    ) -> None:
        if not cls._ensure_ready():
            return

        chunks = cls._chunk_text(text_content)
        if not chunks:
            cls.delete_article(article_id)
            return

        ids = [f"{article_id}:{idx}" for idx in range(len(chunks))]
        vectors = cls._embedder.encode(chunks, normalize_embeddings=True).tolist()
        metadatas = [
            {
                "article_id": article_id,
                "title": title,
                "category_id": category_id,
                "chunk_index": idx,
            }
            for idx in range(len(chunks))
        ]

        cls._collection.delete(where={"article_id": article_id})
        cls._collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=vectors,
        )

    @classmethod
    def delete_article(cls, article_id: str) -> None:
        if not cls._ensure_ready():
            return
        cls._collection.delete(where={"article_id": article_id})

    @classmethod
    def search(
        cls,
        query: str,
        top_k: int | None = None,
        category_id: str | None = None,
    ) -> list[RetrievedChunk]:
        if not cls._ensure_ready():
            return []

        clean_query = (query or "").strip()
        if not clean_query:
            return []

        effective_top_k = max(1, top_k or settings.VECTOR_TOP_K)
        query_vector = cls._embedder.encode([clean_query], normalize_embeddings=True).tolist()

        params: dict[str, Any] = {
            "query_embeddings": query_vector,
            "n_results": effective_top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if category_id:
            params["where"] = {"category_id": category_id}

        result = cls._collection.query(**params)
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for idx, text in enumerate(documents):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            distance = distances[idx] if idx < len(distances) else None
            score = None if distance is None else max(0.0, 1.0 - float(distance))

            chunks.append(
                RetrievedChunk(
                    article_id=str(metadata.get("article_id", "")),
                    title=metadata.get("title"),
                    category_id=metadata.get("category_id"),
                    chunk_index=int(metadata.get("chunk_index", idx)),
                    text=text,
                    score=score,
                )
            )

        return chunks
