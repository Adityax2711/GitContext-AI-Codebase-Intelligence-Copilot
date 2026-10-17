"""Qdrant and FastEmbed dense vector store integration for GitContext."""

import hashlib
import logging
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

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


def compute_deterministic_embedding(text: str, dim: int = 384) -> List[float]:
    """Generate a deterministic normalized dense embedding vector from text.

    Acts as a reliable offline/test fallback when external neural models are unavailable.
    """
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        return vec

    for i, word in enumerate(words):
        # Hash word into dimension index and sign
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        weight = 1.0 / (1.0 + math.log1p(i))
        vec[idx] += sign * weight

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        vec = [v / norm for v in vec]
    return vec


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
        embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None,
    ) -> None:
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.in_memory = in_memory
        self.client: Optional[Any] = None
        self.embed_model: Optional[Any] = None
        self.custom_embed_fn = embed_fn
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

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using custom embedder, FastEmbed, or deterministic fallback."""
        if self.custom_embed_fn is not None:
            return self.custom_embed_fn(texts)

        embedder = self._get_embedding_model()
        if embedder is not None:
            try:
                raw_embs = list(embedder.embed(texts))
                return [
                    emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    for emb in raw_embs
                ]
            except Exception as e:
                logger.warning(f"FastEmbed embedding failed, using fallback: {e}")

        # Deterministic fallback
        return [compute_deterministic_embedding(t, self.VECTOR_SIZE) for t in texts]

    def is_available(self) -> bool:
        """Return True if Qdrant client is functional."""
        return self._initialized and self.client is not None and QDRANT_AVAILABLE

    def index_chunks(self, chunks: Sequence[CodeChunk]) -> int:
        """Embed and upsert CodeChunks into Qdrant."""
        if not self.is_available() or not chunks:
            return 0

        texts = [
            f"{c.symbol_or_heading} in {c.file_path}: {c.content[:500]}"
            for c in chunks
        ]

        try:
            embeddings = self._embed_texts(texts)
            points = []
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                points.append(
                    qmodels.PointStruct(
                        id=idx + 1,
                        vector=emb,
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
        chunks: Optional[Sequence[CodeChunk]] = None,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Dense semantic search using Qdrant (supports both query_points and search APIs)."""
        if not self.is_available() or not query.strip():
            return []

        try:
            embs = self._embed_texts([query])
            if not embs:
                return []
            q_emb = embs[0]
            chunk_by_id = {c.chunk_id: c for c in chunks} if chunks else {}

            hits = []
            if hasattr(self.client, "query_points"):
                resp = self.client.query_points(
                    collection_name=self.collection_name,
                    query=q_emb,
                    limit=top_k,
                )
                hits = getattr(resp, "points", resp)
            elif hasattr(self.client, "search"):
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=q_emb,
                    limit=top_k,
                )

            results: List[SearchResult] = []
            for rank, hit in enumerate(hits, start=1):
                payload = getattr(hit, "payload", {}) or {}
                cid = payload.get("chunk_id")
                matched_chunk = chunk_by_id.get(cid) if cid and chunk_by_id else None
                if matched_chunk is None and payload:
                    try:
                        matched_chunk = CodeChunk.from_dict(payload)
                    except Exception:
                        matched_chunk = None

                if matched_chunk:
                    score_val = float(getattr(hit, "score", 0.0))
                    results.append(
                        SearchResult(
                            chunk=matched_chunk,
                            score=score_val,
                            rank=rank,
                        )
                    )
            return results
        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return []
