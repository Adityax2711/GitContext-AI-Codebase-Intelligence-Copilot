"""Indexing engine for storing and loading code chunks and metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from gitcontext.chunking import chunk_file
from gitcontext.ingestion import discover_repository_files, read_source_file
from gitcontext.models import CodeChunk, IndexMetadata

DEFAULT_INDEX_DIR = Path("data") / "index"
CHUNKS_FILE = "chunks.jsonl"
METADATA_FILE = "metadata.json"


def get_default_index_dir() -> Path:
    """Return default index directory path."""
    return DEFAULT_INDEX_DIR


def save_index(
    chunks: List[CodeChunk],
    metadata: IndexMetadata,
    index_dir: Path,
) -> None:
    """Save chunks to JSONL and metadata to JSON file."""
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = index_dir / CHUNKS_FILE
    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

    metadata_path = index_dir / METADATA_FILE
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)


def load_index(index_dir: Path) -> Tuple[List[CodeChunk], Optional[IndexMetadata]]:
    """Load chunks and metadata from index directory.

    Returns an empty list and None if index does not exist.
    """
    chunks_path = index_dir / CHUNKS_FILE
    metadata_path = index_dir / METADATA_FILE

    if not chunks_path.is_file():
        return [], None

    chunks: List[CodeChunk] = []
    with open(chunks_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                chunks.append(CodeChunk.from_dict(data))
            except json.JSONDecodeError:
                continue

    metadata: Optional[IndexMetadata] = None
    if metadata_path.is_file():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
                metadata = IndexMetadata.from_dict(meta_dict)
        except (json.JSONDecodeError, KeyError):
            metadata = None

    return chunks, metadata


def index_repository(
    repo_path: Path,
    index_dir: Optional[Path] = None,
) -> IndexMetadata:
    """Read a local repository, extract code and doc chunks, and persist the index."""
    resolved_repo = repo_path.resolve()
    target_index_dir = (index_dir or get_default_index_dir()).resolve()

    files = discover_repository_files(resolved_repo)
    repo_name = resolved_repo.name

    all_chunks: List[CodeChunk] = []
    processed_files = 0

    for file_path in files:
        rel_path = str(file_path.relative_to(resolved_repo)).replace("\\", "/")
        content = read_source_file(file_path)
        if content is None:
            continue

        file_chunks = chunk_file(
            repo_name=repo_name,
            relative_path=rel_path,
            content=content,
        )
        all_chunks.extend(file_chunks)
        processed_files += 1

    iso_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    metadata = IndexMetadata(
        repository_name=repo_name,
        repository_path=str(resolved_repo),
        total_files=processed_files,
        total_chunks=len(all_chunks),
        last_indexed_at=iso_timestamp,
    )

    save_index(all_chunks, metadata, target_index_dir)
    return metadata
