"""Comprehensive tests for URL validator, Authentication, Account Linking, and Repository Import."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from gitcontext.auth import AuthService, hash_password, verify_password
from gitcontext.db import DatabaseManager
from gitcontext.server.app import app
from gitcontext.server.routes import state
from gitcontext.url_validator import (
    GitHubUrlValidationError,
    validate_and_parse_github_url,
)


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    """Create an isolated SQLite database for test execution."""
    db_file = tmp_path / "test_gitcontext.db"
    return DatabaseManager(db_path=db_file)


@pytest.fixture
def auth_service(test_db: DatabaseManager) -> AuthService:
    """Create an AuthService backed by the isolated test database."""
    return AuthService(db=test_db)


@pytest.fixture
def client(test_db: DatabaseManager) -> TestClient:
    """Create FastAPI test client with isolated test database."""
    state.db = test_db
    state.auth_service = AuthService(db=test_db)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. URL Parser and Validator Tests
# ---------------------------------------------------------------------------
def test_url_validator_valid_cases():
    # Ordinary HTTPS
    res1 = validate_and_parse_github_url("https://github.com/pallets/flask")
    assert res1.owner == "pallets"
    assert res1.repo == "flask"
    assert res1.canonical_url == "https://github.com/pallets/flask"
    assert res1.clone_url == "https://github.com/pallets/flask.git"

    # Trailing slash
    res2 = validate_and_parse_github_url("https://github.com/pallets/flask/")
    assert res2.owner == "pallets"
    assert res2.repo == "flask"

    # .git suffix
    res3 = validate_and_parse_github_url("https://github.com/pallets/flask.git")
    assert res3.owner == "pallets"
    assert res3.repo == "flask"

    # Leading & trailing whitespace
    res4 = validate_and_parse_github_url("   https://github.com/tiangolo/fastapi   ")
    assert res4.owner == "tiangolo"
    assert res4.repo == "fastapi"

    # Short identifier
    res5 = validate_and_parse_github_url("psf/requests")
    assert res5.owner == "psf"
    assert res5.repo == "requests"

    # HTTP to HTTPS normalization
    res6 = validate_and_parse_github_url("http://github.com/django/django")
    assert res6.canonical_url == "https://github.com/django/django"


def test_url_validator_rejections():
    # Empty
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("   ")
    assert exc.value.code == "empty_url"

    # Profile URL (single path segment)
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("https://github.com/Adityax2711")
    assert exc.value.code == "profile_url"
    assert "user profile" in exc.value.message

    # Issue URL
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("https://github.com/pallets/flask/issues/42")
    assert exc.value.code == "issue_url"
    assert "issue page" in exc.value.message

    # Pull Request URL
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("https://github.com/pallets/flask/pull/101")
    assert exc.value.code == "pull_request_url"
    assert "pull request" in exc.value.message

    # File / Tree URL
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("https://github.com/pallets/flask/blob/main/README.md")
    assert exc.value.code == "file_or_branch_url"

    # Non-GitHub host
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("https://gitlab.com/owner/repo")
    assert exc.value.code == "unsupported_host"

    # Malformed / plain text
    with pytest.raises(GitHubUrlValidationError) as exc:
        validate_and_parse_github_url("just-a-plain-string")
    assert "Invalid repository identifier" in exc.value.message


# ---------------------------------------------------------------------------
# 2. Authentication & Password Tests
# ---------------------------------------------------------------------------
def test_password_hashing():
    pw = "SuperSecret123!"
    h1, salt1 = hash_password(pw)
    assert verify_password(pw, h1, salt1) is True
    assert verify_password("WrongPassword", h1, salt1) is False

    # Unique salts produce different hashes
    h2, salt2 = hash_password(pw)
    assert salt1 != salt2
    assert h1 != h2


def test_email_registration_and_login(auth_service: AuthService):
    # Register
    user = auth_service.register_email_user(
        email="developer@example.com",
        password="Password123",
        name="Alice Developer",
    )
    assert user["email"] == "developer@example.com"
    assert user["name"] == "Alice Developer"
    assert user["id"] is not None

    # Duplicate registration rejected
    with pytest.raises(ValueError):
        auth_service.register_email_user("developer@example.com", "AnotherPassword")

    # Login success
    logged_in = auth_service.authenticate_email("developer@example.com", "Password123")
    assert logged_in is not None
    assert logged_in["id"] == user["id"]

    # Login wrong password
    assert auth_service.authenticate_email("developer@example.com", "BadPassword") is None

    # Login nonexistent user
    assert auth_service.authenticate_email("nobody@example.com", "Password123") is None


def test_session_lifecycle(auth_service: AuthService):
    user = auth_service.register_email_user("session_user@example.com", "SecretPass123")
    token = auth_service.create_session(user["id"])

    # Lookup by session token
    fetched_user = auth_service.get_user_from_session(token)
    assert fetched_user is not None
    assert fetched_user["id"] == user["id"]

    # Delete session / logout
    assert auth_service.delete_session(token) is True
    assert auth_service.get_user_from_session(token) is None


# ---------------------------------------------------------------------------
# 3. Account Linking & Takeover Prevention Tests
# ---------------------------------------------------------------------------
def test_account_linking_and_disconnect(auth_service: AuthService):
    # Register email user
    user1 = auth_service.register_email_user("user1@example.com", "SecretPass123")

    github_profile = {
        "id": 99999,
        "login": "octo_alice",
        "avatar_url": "https://avatars.githubusercontent.com/u/99999",
        "name": "Octo Alice",
    }

    # Link GitHub account
    linked_user = auth_service.link_github_to_user(user1["id"], github_profile, token="ghp_mock_token_1")
    assert linked_user["github"]["connected"] is True
    assert linked_user["github"]["login"] == "octo_alice"

    # User 2 tries to link the same GitHub account (takeover attempt)
    user2 = auth_service.register_email_user("user2@example.com", "SecretPass456")
    with pytest.raises(ValueError) as exc:
        auth_service.link_github_to_user(user2["id"], github_profile, token="ghp_mock_token_2")
    assert "already linked to another user account" in str(exc.value)

    # Disconnect GitHub safely (user1 has email/password)
    disconnected = auth_service.disconnect_github_account(user1["id"])
    assert disconnected["github"]["connected"] is False

    # Disconnect when no password is set should fail
    user_no_pw = auth_service.login_or_create_github_user(
        {"id": 88888, "login": "oauth_only", "avatar_url": ""},
        token="ghp_token_3",
    )
    with pytest.raises(ValueError) as exc:
        auth_service.disconnect_github_account(user_no_pw["id"])
    assert "prevent being locked out" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. API Endpoints Tests
# ---------------------------------------------------------------------------
def test_api_auth_register_and_me(client: TestClient):
    # Register
    res = client.post(
        "/api/auth/register",
        json={"email": "api_test@example.com", "password": "SecurePassword123", "name": "API Tester"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    token = data["token"]
    assert token is not None

    # Check /api/auth/me with Bearer token
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == "api_test@example.com"


def test_api_validate_url(client: TestClient):
    # Valid
    res_valid = client.post(
        "/api/github/validate-url",
        json={"url": "https://github.com/pallets/flask"},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["valid"] is True
    assert res_valid.json()["owner"] == "pallets"
    assert res_valid.json()["repo"] == "flask"

    # Profile rejected with distinct message
    res_prof = client.post(
        "/api/github/validate-url",
        json={"url": "https://github.com/Adityax2711"},
    )
    assert res_prof.status_code == 200
    assert res_prof.json()["valid"] is False
    assert res_prof.json()["code"] == "profile_url"


def test_api_import_with_database_persistence(client: TestClient, tmp_path: Path):
    # Prepare synthetic repository zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("testowner-apirepo-1/main.py", "def compute():\n    return 42\n")
        z.writestr("testowner-apirepo-1/README.md", "# Test API Repo\n")
    zip_content = zip_buffer.getvalue()

    mock_resp = MagicMock()
    mock_resp.read.return_value = zip_content
    mock_resp.__enter__.return_value = mock_resp

    with patch.object(state.github_service, "_clone_with_git", return_value=(False, "no git")):
        with patch.object(state.github_service, "check_repository_access", return_value=(True, None, None)):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                import_res = client.post(
                    "/api/github/import",
                    json={"repository_url": "https://github.com/testowner/apirepo"},
                )
                assert import_res.status_code == 200
                data = import_res.json()
                assert data["status"] == "imported"
                assert data["owner"] == "testowner"
                assert data["repo"] == "apirepo"

                # Check that repository was persisted in SQLite DB
                with state.db.connection() as conn:
                    repo_row = conn.execute(
                        "SELECT * FROM repositories WHERE full_name = 'testowner/apirepo';"
                    ).fetchone()
                    assert repo_row is not None
                    assert repo_row["name"] == "apirepo"

                    job_row = conn.execute(
                        "SELECT * FROM indexing_jobs WHERE repo_id = ?;", (repo_row["id"],)
                    ).fetchone()
                    assert job_row is not None
                    assert job_row["status"] == "completed"
