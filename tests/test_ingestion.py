"""Unit tests for repository ingestion and file filtering."""

from pathlib import Path
import pytest
from gitcontext.ingestion import (
    discover_repository_files,
    read_source_file,
)


def test_gitignore_filtering(tmp_path: Path):
    # Setup temporary directory structure
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("dummy")

    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").write_text("dummy")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "script.py").write_text("dummy")

    (tmp_path / ".env").write_text("SECRET_KEY=123")
    (tmp_path / "credentials.json").write_text('{"secret": true}')

    (tmp_path / ".gitignore").write_text("ignored_folder/\n*.tmp.py\nsecret_notes.md\n")

    (tmp_path / "ignored_folder").mkdir()
    (tmp_path / "ignored_folder" / "temp.py").write_text("dummy")

    (tmp_path / "secret_notes.md").write_text("# Secret")
    (tmp_path / "test.tmp.py").write_text("dummy")

    # Valid files that must be included
    (tmp_path / "src").mkdir()
    valid_py = tmp_path / "src" / "app.py"
    valid_py.write_text("def main(): pass")
    valid_md = tmp_path / "README.md"
    valid_md.write_text("# Title")

    discovered = discover_repository_files(tmp_path)
    discovered_rel = [str(f.relative_to(tmp_path)).replace("\\", "/") for f in discovered]

    assert "src/app.py" in discovered_rel
    assert "README.md" in discovered_rel
    assert len(discovered) == 2

    # Verify exclusions
    assert "venv/lib.py" not in discovered_rel
    assert ".env" not in discovered_rel
    assert "credentials.json" not in discovered_rel
    assert "secret_notes.md" not in discovered_rel
    assert "test.tmp.py" not in discovered_rel


def test_discover_invalid_path():
    with pytest.raises(FileNotFoundError):
        discover_repository_files(Path("/non/existent/path/for/repo/12345"))


def test_read_source_file_binary_and_valid(tmp_path: Path):
    text_file = tmp_path / "valid.py"
    text_file.write_text("print('Hello')", encoding="utf-8")
    assert read_source_file(text_file) == "print('Hello')"

    binary_file = tmp_path / "binary.dat"
    binary_file.write_bytes(b"\x00\x01\x02\x03\x04\xff")
    assert read_source_file(binary_file) is None
