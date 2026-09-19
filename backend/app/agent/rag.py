"""RAG (Retrieval-Augmented Generation) service.

Provides document indexing and semantic search using Qdrant vector database
and Alibaba's text-embedding-v4 model.
"""
from __future__ import annotations
import hashlib
import json
import logging
import uuid
from typing import Optional
import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class RagService:
    """RAG service with Qdrant vector store and Alibaba embedding."""

    def __init__(
        self,
        qdrant_url: str,
        embedding_base_url: str,
        embedding_api_key: str,
        embedding_model: str = "text-embedding-v4",
        collection: str = "finalboost_chunks",
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
        default_top_k: int = 5,
        min_score: float = 0.55,
    ):
        self.qdrant_url = qdrant_url.rstrip("/")
        self.embedding_base_url = embedding_base_url.rstrip("/")
        self.embedding_api_key = embedding_api_key
        self.embedding_model = embedding_model
        self.collection = collection
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.default_top_k = default_top_k
        self.min_score = min_score
        self._collection_ready = False

    def _ensure_collection(self) -> None:
        """Ensure Qdrant collection exists."""
        if self._collection_ready:
            return

        try:
            resp = httpx.get(f"{self.qdrant_url}/collections/{self.collection}")
            if resp.status_code == 404:
                # Create collection with vector config
                payload = {
                    "vectors": {
                        "size": 1024,  # text-embedding-v4 dimensions
                        "distance": "Cosine",
                    }
                }
                resp = httpx.put(
                    f"{self.qdrant_url}/collections/{self.collection}",
                    json=payload,
                    timeout=10,
                )
                resp.raise_for_status()
                logger.info("Created Qdrant collection: %s", self.collection)
            elif resp.status_code == 200:
                logger.info("Qdrant collection already exists: %s", self.collection)
            else:
                raise RuntimeError(f"Qdrant check failed: {resp.status_code}")

            self._collection_ready = True
        except httpx.ConnectError:
            logger.warning("Cannot connect to Qdrant at %s", self.qdrant_url)
            raise

    def embed_text(self, text: str) -> list[float]:
        """Get embedding vector for a single text using Alibaba API."""
        resp = httpx.post(
            f"{self.embedding_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.embedding_model,
                "input": text,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embedding vectors for multiple texts."""
        resp = httpx.post(
            f"{self.embedding_base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.embedding_model,
                "input": texts,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        # Sort by index to maintain order
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings]

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks for indexing."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "],
        )
        return splitter.split_text(text)

    def add_document(
        self,
        user_id: str,
        doc_id: str,
        content: str,
        metadata: dict = None,
    ) -> int:
        """Index a document: chunk → embed → store in Qdrant.

        Args:
            user_id: Owner user ID
            doc_id: Document identifier
            content: Full document text
            metadata: Additional metadata (title, filename, etc.)

        Returns:
            Number of chunks indexed
        """
        self._ensure_collection()

        chunks = self.chunk_text(content)
        if not chunks:
            return 0

        logger.info("Indexing document %s: %d chunks", doc_id, len(chunks))

        # Embed all chunks
        vectors = self.embed_batch(chunks)

        # Prepare points for Qdrant
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = hashlib.md5(f"{doc_id}:{i}".encode()).hexdigest()
            payload = {
                "user_id": user_id,
                "document_id": doc_id,
                "chunk_index": i,
                "content": chunk,
                **(metadata or {}),
            }
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": payload,
            })

        # Upsert to Qdrant in batches
        batch_size = 100
        for start in range(0, len(points), batch_size):
            batch = points[start:start + batch_size]
            resp = httpx.put(
                f"{self.qdrant_url}/collections/{self.collection}/points?wait=true",
                json={"points": batch},
                timeout=30,
            )
            resp.raise_for_status()

        logger.info("Indexed %d chunks for document %s", len(chunks), doc_id)
        return len(chunks)

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = None,
        min_score: float = None,
    ) -> list[dict]:
        """Search for relevant document chunks.

        Args:
            user_id: Search within this user's documents
            query: Search query text
            top_k: Number of results (default: self.default_top_k)
            min_score: Minimum similarity score (default: self.min_score)

        Returns:
            List of {content, score, document_id, chunk_index, ...}
        """
        self._ensure_collection()

        top_k = top_k or self.default_top_k
        min_score = min_score if min_score is not None else self.min_score

        query_vector = self.embed_text(query)

        # Search with user filter
        payload = {
            "vector": query_vector,
            "limit": top_k,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "user_id", "match": {"value": user_id}}
                ]
            },
        }

        resp = httpx.post(
            f"{self.qdrant_url}/collections/{self.collection}/points/query",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for point in data.get("result", {}).get("points", []):
            score = point.get("score", 0)
            if score < min_score:
                continue
            payload = point.get("payload", {})
            results.append({
                "content": payload.get("content", ""),
                "score": score,
                "document_id": payload.get("document_id", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "title": payload.get("title", ""),
            })

        return results

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks of a document."""
        self._ensure_collection()

        payload = {
            "filter": {
                "must": [
                    {"key": "document_id", "match": {"value": doc_id}}
                ]
            }
        }
        resp = httpx.post(
            f"{self.qdrant_url}/collections/{self.collection}/points/delete?wait=true",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("Deleted document %s from vector store", doc_id)

    def delete_user_documents(self, user_id: str) -> None:
        """Delete all documents for a user."""
        self._ensure_collection()

        payload = {
            "filter": {
                "must": [
                    {"key": "user_id", "match": {"value": user_id}}
                ]
            }
        }
        resp = httpx.post(
            f"{self.qdrant_url}/collections/{self.collection}/points/delete?wait=true",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("Deleted all documents for user %s", user_id)
