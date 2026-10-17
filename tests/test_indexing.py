"""Unit tests for indexing engine persistence and loading."""

from pathlib import Path
from gitcontext.indexing import index_repository, load_index


def test_index_synthetic_repo(tmp_path: Path):
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    # Add a python module
    code_file = repo_dir / "calculator.py"
    code_file.write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
    )

    # Add markdown docs
    doc_file = repo_dir / "README.md"
    doc_file.write_text("# Calculator Docs\n\n## Operations\nSupports add and multiply.\n")

    index_dir = tmp_path / "custom_index"

    meta = index_repository(repo_path=repo_dir, index_dir=index_dir)
    assert meta.total_files == 2
    assert meta.total_chunks >= 3
    assert (index_dir / "chunks.jsonl").exists()
    assert (index_dir / "metadata.json").exists()

    # Load back and verify
    chunks, loaded_meta = load_index(index_dir)
    assert loaded_meta is not None
    assert loaded_meta.repository_name == "sample_repo"
    assert len(chunks) == meta.total_chunks


def test_index_empty_repo(tmp_path: Path):
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()
    index_dir = tmp_path / "index"

    meta = index_repository(repo_path=empty_repo, index_dir=index_dir)
    assert meta.total_files == 0
    assert meta.total_chunks == 0

    chunks, loaded_meta = load_index(index_dir)
    assert len(chunks) == 0
    assert loaded_meta is not None
    assert loaded_meta.dense_indexed is False


def test_index_repo_with_dense_store(tmp_path: Path):
    repo_dir = tmp_path / "code_repo"
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("def start_server():\n    print('listening')\n")

    index_dir = tmp_path / "repo_index"
    meta = index_repository(repo_path=repo_dir, index_dir=index_dir, enable_dense=True)

    assert meta.total_files == 1
    assert meta.total_chunks >= 1
    # Check that metadata reflects indexing
    _, loaded_meta = load_index(index_dir)
    assert loaded_meta is not None
    assert loaded_meta.total_chunks == meta.total_chunks
