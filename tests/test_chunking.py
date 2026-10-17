"""Unit tests for code and documentation chunking engine."""

from gitcontext.chunking import (
    chunk_file,
    chunk_markdown_source,
    chunk_python_source,
)
from gitcontext.models import CodeChunk


def test_chunk_python_functions_and_classes():
    source_code = """\"\"\"Module docstring for auth.\"\"\"

import hashlib

def hash_password(password: str) -> str:
    \"\"\"Hash a user password.\"\"\"
    return hashlib.sha256(password.encode()).hexdigest()

class UserManager:
    \"\"\"Manages user lifecycle.\"\"\"

    def __init__(self, db_url: str):
        self.db_url = db_url

    async def authenticate_user(self, username: str, password_hash: str) -> bool:
        \"\"\"Async check of user credentials.\"\"\"
        return True
"""
    chunks = chunk_python_source("test_repo", "auth/manager.py", source_code)

    # Verify chunks extracted
    symbols = [c.symbol_or_heading for c in chunks]
    assert "<module_preamble>" in symbols
    assert "def hash_password" in symbols
    assert "class UserManager" in symbols
    assert "UserManager.__init__" in symbols
    assert "UserManager.authenticate_user" in symbols

    # Verify line numbers
    hash_chunk = next(c for c in chunks if c.symbol_or_heading == "def hash_password")
    assert hash_chunk.start_line == 5
    assert hash_chunk.end_line == 7
    assert "def hash_password(password: str)" in hash_chunk.content

    class_chunk = next(c for c in chunks if c.symbol_or_heading == "class UserManager")
    assert class_chunk.start_line == 9
    assert class_chunk.end_line == 17

    method_chunk = next(c for c in chunks if c.symbol_or_heading == "UserManager.authenticate_user")
    assert method_chunk.start_line == 15
    assert method_chunk.end_line == 17
    assert "async def authenticate_user" in method_chunk.content


def test_chunk_python_syntax_error_graceful_handling():
    malformed_code = """def broken_function(:
        print("broken syntax)
"""
    chunks = chunk_python_source("test_repo", "broken.py", malformed_code)

    assert len(chunks) == 1
    assert "<syntax_error" in chunks[0].symbol_or_heading
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2


def test_chunk_markdown_headings_and_hierarchy():
    markdown_doc = """# GitContext Copilot

An AI codebase intelligence assistant.

## Architecture

The project has two key layers:

### Ingestion Engine
Discovers repository files and parses code AST.

### Retrieval Engine
Uses BM25 keyword search.

## Installation
Run `pip install -e .` to install.
"""
    chunks = chunk_markdown_source("test_repo", "README.md", markdown_doc)

    headings = [c.symbol_or_heading for c in chunks]
    assert "GitContext Copilot" in headings
    assert "GitContext Copilot > Architecture" in headings
    assert "GitContext Copilot > Architecture > Ingestion Engine" in headings
    assert "GitContext Copilot > Architecture > Retrieval Engine" in headings
    assert "GitContext Copilot > Installation" in headings

    # Verify line bounds
    ingest_chunk = next(c for c in chunks if "Ingestion Engine" in c.symbol_or_heading)
    assert "Discovers repository files" in ingest_chunk.content
    assert ingest_chunk.start_line < ingest_chunk.end_line


def test_deterministic_chunk_ids():
    content = "def add(a, b):\n    return a + b\n"
    c1 = CodeChunk.create(
        repository="repo_a",
        source_type="code",
        file_path="math.py",
        symbol_or_heading="def add",
        programming_language="python",
        start_line=1,
        end_line=2,
        content=content,
    )
    c2 = CodeChunk.create(
        repository="repo_a",
        source_type="code",
        file_path="math.py",
        symbol_or_heading="def add",
        programming_language="python",
        start_line=1,
        end_line=2,
        content=content,
    )
    # Different line or content should produce different ID
    c3 = CodeChunk.create(
        repository="repo_a",
        source_type="code",
        file_path="math.py",
        symbol_or_heading="def add",
        programming_language="python",
        start_line=5,
        end_line=6,
        content=content,
    )

    assert c1.chunk_id == c2.chunk_id
    assert c1.content_hash == c2.content_hash
    assert c1.chunk_id != c3.chunk_id


def test_chunk_file_dispatcher():
    py_chunks = chunk_file("repo", "src/main.py", "def run():\n    pass\n")
    assert len(py_chunks) >= 1
    assert py_chunks[0].programming_language == "python"

    md_chunks = chunk_file("repo", "docs/index.md", "# Guide\n\nSome text")
    assert len(md_chunks) == 1
    assert md_chunks[0].programming_language == "markdown"

    unknown_chunks = chunk_file("repo", "data.json", '{"key": 1}')
    assert unknown_chunks == []


def test_chunk_test_file():
    test_content = "def test_addition():\n    assert 1 + 1 == 2\n"
    chunks = chunk_file("repo", "tests/test_math.py", test_content)
    assert len(chunks) == 1
    assert chunks[0].source_type == "test"
    assert chunks[0].symbol_or_heading == "def test_addition"
