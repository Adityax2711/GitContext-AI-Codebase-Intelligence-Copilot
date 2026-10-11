"""Unit and integration tests for GitContext CLI."""

from pathlib import Path
import pytest
from gitcontext.cli import main


def test_cli_index_and_search_workflow(tmp_path: Path, capsys: pytest.CaptureFixture):
    repo_dir = tmp_path / "toy_repo"
    repo_dir.mkdir()
    py_file = repo_dir / "greeter.py"
    py_file.write_text(
        "def say_hello(name: str) -> str:\n    return f'Hello, {name}!'\n"
    )

    readme = repo_dir / "README.md"
    readme.write_text(
        "# Greeter Service\n\n## Usage\nCall `say_hello` to greet a user.\n"
    )

    index_dir = tmp_path / "index_storage"

    # 1. Test status with empty index
    ret_status_empty = main(["status", "--index-dir", str(index_dir)])
    assert ret_status_empty == 0
    captured = capsys.readouterr()
    assert "No repository currently indexed" in captured.out

    # 2. Test index command
    ret_index = main(["index", str(repo_dir), "--index-dir", str(index_dir)])
    assert ret_index == 0
    captured = capsys.readouterr()
    assert "Indexing Completed Successfully" in captured.out
    assert "toy_repo" in captured.out

    # 3. Test status with active index
    ret_status = main(["status", "--index-dir", str(index_dir)])
    assert ret_status == 0
    captured = capsys.readouterr()
    assert "toy_repo" in captured.out
    assert "Files Ingested : 2" in captured.out

    # 4. Test search command
    ret_search = main(["search", "how to greet user say_hello", "--index-dir", str(index_dir)])
    assert ret_search == 0
    captured = capsys.readouterr()
    assert "Query: \"how to greet user say_hello\"" in captured.out
    assert "say_hello" in captured.out
    assert "greeter.py" in captured.out


def test_cli_invalid_repo_path(tmp_path: Path, capsys: pytest.CaptureFixture):
    fake_path = tmp_path / "does_not_exist"
    ret = main(["index", str(fake_path)])
    assert ret == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
