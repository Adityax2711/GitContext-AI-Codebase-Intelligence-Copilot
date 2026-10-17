"""Tests for FastAPI backend routes and endpoints."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from gitcontext.server.app import app
from gitcontext.server.routes import state


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def synthetic_bug_repo_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "synthetic_bug_repo"


def test_api_status(client: TestClient):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_repository" in data
    assert "llm" in data


def test_api_repositories(client: TestClient):
    response = client.get("/api/repositories")
    assert response.status_code == 200
    repos = response.json()
    assert isinstance(repos, list)
    assert len(repos) >= 1
    assert any(r.get("is_active") for r in repos)


def test_api_repository_tree(client: TestClient, synthetic_bug_repo_path: Path):
    state.select_repo(str(synthetic_bug_repo_path))
    response = client.get("/api/repository/tree")
    assert response.status_code == 200
    tree = response.json()
    assert isinstance(tree, list)
    names = {node["name"] for node in tree}
    assert "math_ops.py" in names


def test_api_read_file(client: TestClient, synthetic_bug_repo_path: Path):
    state.select_repo(str(synthetic_bug_repo_path))
    response = client.get("/api/repository/file?file_path=math_ops.py&start_line=1&end_line=10")
    assert response.status_code == 200
    data = response.json()
    assert data["file_path"] == "math_ops.py"
    assert data["start_line"] == 1
    assert data["end_line"] == 10
    assert "divide_numbers" in data["content"]
    assert len(data["lines"]) == 10


def test_api_read_file_path_traversal(client: TestClient):
    response = client.get("/api/repository/file?file_path=../../etc/passwd")
    assert response.status_code == 404 or response.status_code == 400


def test_api_search(client: TestClient, synthetic_bug_repo_path: Path):
    state.select_repo(str(synthetic_bug_repo_path))
    response = client.get("/api/search?query=divide_numbers&top_k=2")
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data


def test_api_chat_and_investigate(client: TestClient, synthetic_bug_repo_path: Path):
    state.select_repo(str(synthetic_bug_repo_path))

    # Test Chat
    chat_resp = client.post("/api/chat", json={"message": "Investigate zero division in divide_numbers"})
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "final_answer" in chat_data
    assert len(chat_data["steps"]) >= 1

    # Test Investigate endpoint
    inv_resp = client.post("/api/investigate", json={"query": "Investigate zero division in divide_numbers"})
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert "findings" in inv_data
    assert "proposed_patch" in inv_data
