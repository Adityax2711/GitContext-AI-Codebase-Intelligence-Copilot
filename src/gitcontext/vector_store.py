"""Qdrant and FastEmbed dense vector store integration for GitContext."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from gitcontext.models import CodeChunk, SearchResult

logger = logging.getLogger(__name__)

# Check if Qdrant and FastEmbed are available
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    QdrantClient = None  # type: ignore
    qmodels = None  # type: ignore

try:
    from fastembed import TextEmbedding

    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False
    TextEmbedding = None  # type: ignore


class QdrantVectorStore:
    """Manages dense vector indexing and cosine similarity retrieval using Qdrant."""

    COLLECTION_NAME = "gitcontext_chunks"
    EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
    VECTOR_SIZE = 384

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        in_memory: bool = True,
        collection_name: Optional[str] = None,
    ) -> None:
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.in_memory = in_memory
        self.client: Optional[Any] = None
        self.embed_model: Optional[Any] = None
        self._initialized = False

        if not QDRANT_AVAILABLE:
            logger.info("Qdrant client not installed; dense vector search will be skipped.")
            return

        try:
            if in_memory or not storage_path:
                self.client = QdrantClient(":memory:")
            else:
                p = Path(storage_path).resolve()
                p.mkdir(parents=True, exist_ok=True)
                self.client = QdrantClient(path=str(p))

            self._init_collection()
            self._initialized = True
        except Exception as e:
            logger.warning(f"Could not initialize Qdrant client: {e}")
            self.client = None

    def _init_collection(self) -> None:
        """Create or recreate the vector collection."""
        if not self.client:
            return

        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def _get_embedding_model(self) -> Optional[Any]:
        """Lazy load FastEmbed embedding model."""
        if not FASTEMBED_AVAILABLE:
            return None
        if self.embed_model is None:
            try:
                self.embed_model = TextEmbedding(model_name=self.EMBEDDING_MODEL)
            except Exception as e:
                logger.warning(f"Could not load FastEmbed model: {e}")
                self.embed_model = None
        return self.embed_model

    def is_available(self) -> bool:
        """Return True if both Qdrant and embedding model are functional."""
        return (
            self._initialized
            and self.client is not None
            and QDRANT_AVAILABLE
            and FASTEMBED_AVAILABLE
        )

    def index_chunks(self, chunks: Sequence[CodeChunk]) -> int:
        """Embed and upsert CodeChunks into Qdrant."""
        if not self.is_available() or not chunks:
            return 0

        embedder = self._get_embedding_model()
        if not embedder:
            return 0

        texts = [
            f"{c.symbol_or_heading} in {c.file_path}: {c.content[:500]}"
            for c in chunks
        ]

        try:
            embeddings = list(embedder.embed(texts))
            points = []
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                points.append(
                    qmodels.PointStruct(
                        id=idx + 1,
                        vector=emb.tolist(),
                        payload=chunk.to_dict(),
                    )
                )

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            return len(points)
        except Exception as e:
            logger.warning(f"Failed to index chunks into Qdrant: {e}")
            return 0

    def search(
        self,
        query: str,
        chunks: Sequence[CodeChunk],
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Dense semantic search using Qdrant."""
        if not self.is_available() or not chunks:
            return []

        embedder = self._get_embedding_model()
        if not embedder:
            return []

        try:
            q_emb = list(embedder.embed([query]))[0].tolist()
            chunk_by_id = {c.chunk_id: c for c in chunks}

            hits = self.client.search(
                collection_name=self.collection_name,
                query_vector=q_emb,
                limit=top_k,
            )

            results: List[SearchResult] = []
            for rank, hit in enumerate(hits, start=1):
                cid = hit.payload.get("chunk_id")
                matched_chunk = chunk_by_id.get(cid) or CodeChunk.from_dict(hit.payload)
                results.append(
                    SearchResult(
                        chunk=matched_chunk,
                        score=float(hit.score),
                        rank=rank,
                    )
                )
            return results
        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return []
