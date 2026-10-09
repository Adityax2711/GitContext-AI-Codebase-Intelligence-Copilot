"""BM25-based keyword retrieval engine with code-aware tokenization."""

from __future__ import annotations

import re
from typing import List

from rank_bm25 import BM25Okapi

from gitcontext.models import CodeChunk, SearchResult

# Regex to split CamelCase and snake_case tokens
SPLIT_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize_code_and_text(text: str) -> List[str]:
    """Tokenize source code or queries with support for camelCase and snake_case."""
    if not text:
        return []

    tokens: List[str] = []
    # 1. Extract base tokens
    base_words = WORD_RE.findall(text)
    for word in base_words:
        w_lower = word.lower()
        tokens.append(w_lower)

        # 2. Split snake_case
        if "_" in w_lower:
            parts = [p for p in w_lower.split("_") if p]
            tokens.extend(parts)

        # 3. Split camelCase
        camel_split = SPLIT_CAMEL_RE.sub(r"\1 \2", word)
        if camel_split != word:
            sub_words = WORD_RE.findall(camel_split)
            for sub in sub_words:
                sub_lower = sub.lower()
                if sub_lower != w_lower:
                    tokens.append(sub_lower)

    return tokens


def prepare_chunk_text_for_indexing(chunk: CodeChunk) -> str:
    """Combine symbol, file path, and body into a rich document for BM25 retrieval."""
    # Repeat symbol and file path slightly to provide appropriate keyword weight
    return f"{chunk.symbol_or_heading} {chunk.symbol_or_heading} {chunk.file_path} {chunk.content}"


class BM25Retriever:
    """Index and retrieve CodeChunks using BM25 Okapi."""

    def __init__(self, chunks: List[CodeChunk]) -> None:
        self.chunks = chunks
        if self.chunks:
            corpus = [
                tokenize_code_and_text(prepare_chunk_text_for_indexing(c))
                for c in self.chunks
            ]
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search indexed chunks for query and return top_k ranked results."""
        if not self.chunks or self.bm25 is None:
            return []

        query_tokens = tokenize_code_and_text(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        # Pair scores with original chunks and sort descending
        indexed_scores = [(idx, score) for idx, score in enumerate(scores) if score > 0.0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results: List[SearchResult] = []
        for rank, (chunk_idx, score) in enumerate(indexed_scores[:top_k], start=1):
            results.append(
                SearchResult(
                    chunk=self.chunks[chunk_idx],
                    score=float(score),
                    rank=rank,
                )
            )

        return results


def search_index(
    query: str,
    chunks: List[CodeChunk],
    top_k: int = 5,
) -> List[SearchResult]:
    """Convenience functional interface for BM25 retrieval."""
    retriever = BM25Retriever(chunks)
    return retriever.search(query, top_k=top_k)
