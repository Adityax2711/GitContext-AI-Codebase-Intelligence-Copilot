"""Unit tests for GitHubService and GitHub import/login API endpoints."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from gitcontext.github_service import (
    GitHubRepoSummary,
    GitHubService,
    GitHubUser,
    parse_github_identifier,
)
from gitcontext.server.app import app
from gitcontext.server.routes import state


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_parse_github_identifier():
    # Standard full HTTPS URL
    assert parse_github_identifier("https://github.com/pallets/flask") == ("pallets", "flask")
    assert parse_github_identifier("https://github.com/pallets/flask.git") == ("pallets", "flask")
    assert parse_github_identifier("http://github.com/owner/my-repo") == ("owner", "my-repo")

    # Short format
    assert parse_github_identifier("tiangolo/fastapi") == ("tiangolo", "fastapi")
    assert parse_github_identifier("owner.name/repo_name") == ("owner.name", "repo_name")

    # Invalid
    with pytest.raises(ValueError):
        parse_github_identifier("invalid-string-without-slash")


def test_github_service_unauthenticated(tmp_path: Path):
    service = GitHubService(token=None, repos_dir=tmp_path)
    assert service.get_authenticated_user() is None
    assert service.list_user_repositories() == []


def test_github_service_login_and_user_info(tmp_path: Path):
    service = GitHubService(token="ghp_mock_token", repos_dir=tmp_path)

    mock_user_data = {
        "login": "testdev",
        "id": 12345,
        "name": "Test Developer",
        "avatar_url": "https://avatars.githubusercontent.com/u/12345",
        "html_url": "https://github.com/testdev",
        "public_repos": 10,
        "total_private_repos": 2,
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_user_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        user = service.get_authenticated_user()
        assert user is not None
        assert user.login == "testdev"
        assert user.name == "Test Developer"
        assert user.public_repos == 10


def test_github_service_import_via_zipball(tmp_path: Path):
    repos_dir = tmp_path / "repos"
    service = GitHubService(token=None, repos_dir=repos_dir)

    # Create a synthetic in-memory zip archive mimicking GitHub zipball
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("testowner-myrepo-abc1234/README.md", "# My Repo\nSample documentation\n")
        z.writestr("testowner-myrepo-abc1234/src/main.py", "def run():\n    return 'success'\n")
    zip_content = zip_buffer.getvalue()

    mock_resp = MagicMock()
    mock_resp.read.return_value = zip_content
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(service, "_clone_with_git", return_value=(False, "mock")):
        with patch.object(service, "check_repository_access", return_value=(True, None, None)):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                dest = service.import_repository("testowner/myrepo")
                assert dest.is_dir()
                assert (dest / "README.md").exists()
                assert (dest / "src" / "main.py").exists()
                assert "def run" in (dest / "src" / "main.py").read_text()


def test_api_github_user_and_login_flow(client: TestClient):
    # Initially check user status
    res = client.get("/api/github/user")
    assert res.status_code == 200

    # Test login endpoint with mock
    mock_user_data = {
        "login": "octocat",
        "id": 1,
        "name": "The Octocat",
        "avatar_url": "https://github.com/images/error/octocat_happy.gif",
        "html_url": "https://github.com/octocat",
        "public_repos": 8,
        "total_private_repos": 1,
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_user_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        login_res = client.post("/api/github/login", json={"token": "ghp_valid_mock_token"})
        assert login_res.status_code == 200
        data = login_res.json()
        assert data["status"] == "authenticated"
        assert data["user"]["login"] == "octocat"

        # Check /api/github/user reflects login
        user_res = client.get("/api/github/user")
        assert user_res.status_code == 200
        assert user_res.json()["authenticated"] is True

        # Test logout
        logout_res = client.post("/api/github/logout")
        assert logout_res.status_code == 200
        assert logout_res.json()["status"] == "logged_out"


def test_api_github_import(client: TestClient, tmp_path: Path):
    # Setup synthetic repo zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("testowner-quickrepo-123/module.py", "def greet(name: str):\n    return f'hello {name}'\n")
        z.writestr("testowner-quickrepo-123/README.md", "# Quick Repo\n")
    zip_content = zip_buffer.getvalue()

    mock_resp = MagicMock()
    mock_resp.read.return_value = zip_content
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(state.github_service, "_clone_with_git", return_value=(False, "mock")):
        with patch.object(state.github_service, "check_repository_access", return_value=(True, None, None)):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                resp = client.post(
                    "/api/github/import",
                    json={
                        "repository_url": "https://github.com/testowner/quickrepo",
                        "reindex": True,
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "imported"
                assert "quickrepo" in data["repository_name"]
                assert data["index"]["total_files"] >= 1
                assert data["index"]["total_chunks"] >= 1
