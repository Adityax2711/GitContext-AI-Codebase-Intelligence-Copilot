"""Data models for GitContext."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal


@dataclass(frozen=True)
class CodeChunk:
    """Represents an extracted unit of code, documentation, or test."""

    chunk_id: str
    repository: str
    source_type: Literal["code", "documentation", "test"]
    file_path: str
    symbol_or_heading: str
    programming_language: str
    start_line: int
    end_line: int
    content: str
    content_hash: str

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute deterministic SHA-256 hash of text content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_chunk_id(
        repository: str,
        file_path: str,
        symbol_or_heading: str,
        start_line: int,
        end_line: int,
        content_hash: str,
    ) -> str:
        """Generate a deterministic chunk ID.

        Stable across indexing runs when content and structural location match.
        """
        raw_key = f"{repository}:{file_path}:{symbol_or_heading}:{start_line}:{end_line}:{content_hash}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def create(
        cls,
        repository: str,
        source_type: Literal["code", "documentation", "test"],
        file_path: str,
        symbol_or_heading: str,
        programming_language: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> CodeChunk:
        """Factory constructor that automatically computes hashes and ID."""
        content_hash = cls.compute_content_hash(content)
        chunk_id = cls.compute_chunk_id(
            repository=repository,
            file_path=file_path,
            symbol_or_heading=symbol_or_heading,
            start_line=start_line,
            end_line=end_line,
            content_hash=content_hash,
        )
        return cls(
            chunk_id=chunk_id,
            repository=repository,
            source_type=source_type,
            file_path=file_path,
            symbol_or_heading=symbol_or_heading,
            programming_language=programming_language,
            start_line=start_line,
            end_line=end_line,
            content=content,
            content_hash=content_hash,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CodeChunk:
        """Reconstruct CodeChunk from dictionary."""
        return cls(
            chunk_id=data["chunk_id"],
            repository=data["repository"],
            source_type=data["source_type"],
            file_path=data["file_path"],
            symbol_or_heading=data["symbol_or_heading"],
            programming_language=data["programming_language"],
            start_line=int(data["start_line"]),
            end_line=int(data["end_line"]),
            content=data["content"],
            content_hash=data["content_hash"],
        )


@dataclass
class SearchResult:
    """Represents a scored search retrieval result."""

    chunk: CodeChunk
    score: float
    rank: int


@dataclass
class IndexMetadata:
    """Represents summary metadata about the latest indexing run."""

    repository_name: str
    repository_path: str
    total_files: int
    total_chunks: int
    last_indexed_at: str
    dense_indexed: bool = False
    dense_vectors_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IndexMetadata:
        return cls(
            repository_name=data["repository_name"],
            repository_path=data["repository_path"],
            total_files=int(data["total_files"]),
            total_chunks=int(data["total_chunks"]),
            last_indexed_at=data["last_indexed_at"],
            dense_indexed=bool(data.get("dense_indexed", False)),
            dense_vectors_count=int(data.get("dense_vectors_count", 0)),
        )
