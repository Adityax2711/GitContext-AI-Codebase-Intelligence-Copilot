"""GitHub integration service for user authentication, repository listing, and cloning/downloading."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from gitcontext.url_validator import (
    GitHubUrlValidationError,
    ParsedGitHubRepo,
    validate_and_parse_github_url,
)

logger = logging.getLogger(__name__)


@dataclass
class GitHubUser:
    """Authenticated GitHub user profile."""

    login: str
    id: int
    name: Optional[str]
    avatar_url: str
    html_url: str
    public_repos: int = 0
    total_private_repos: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GitHubRepoSummary:
    """Summary of a GitHub repository."""

    name: str
    full_name: str
    owner: str
    description: Optional[str]
    private: bool
    html_url: str
    clone_url: str
    default_branch: str
    stars: int = 0
    language: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_github_identifier(identifier: str) -> Tuple[str, str]:
    """Parse repository identifier or URL into (owner, repo_name) with rich validation.

    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/
    - https://github.com/owner/repo.git
    - owner/repo
    - Leading/trailing whitespace trimmed
    """
    try:
        parsed = validate_and_parse_github_url(identifier)
        return parsed.owner, parsed.repo
    except GitHubUrlValidationError as e:
        raise ValueError(e.message) from e


class GitHubService:
    """Handles GitHub authentication, repository exploration, and cloning."""

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None, repos_dir: Optional[Path] = None) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.repos_dir = (repos_dir or (Path.cwd() / "data" / "repos")).resolve()
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self._cached_user: Optional[GitHubUser] = None

    def set_token(self, token: Optional[str]) -> None:
        """Update active GitHub token."""
        self.token = token.strip() if token else None
        self._cached_user = None

    def _get_headers(self, override_token: Optional[str] = None) -> Dict[str, str]:
        """Prepare standard HTTP headers for GitHub API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitContext-AI-Copilot",
        }
        active_token = override_token or self.token
        if active_token:
            headers["Authorization"] = f"Bearer {active_token}"
        return headers

    def get_authenticated_user(self) -> Optional[GitHubUser]:
        """Fetch authenticated user profile using active token."""
        if not self.token:
            return None

        if self._cached_user is not None:
            return self._cached_user

        req = urllib.request.Request(f"{self.API_BASE}/user", headers=self._get_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                user = GitHubUser(
                    login=data.get("login", ""),
                    id=data.get("id", 0),
                    name=data.get("name"),
                    avatar_url=data.get("avatar_url", ""),
                    html_url=data.get("html_url", ""),
                    public_repos=data.get("public_repos", 0),
                    total_private_repos=data.get("total_private_repos", 0),
                )
                self._cached_user = user
                return user
        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.warning("GitHub token is invalid or expired.")
                return None
            logger.warning(f"GitHub API error {e.code}: {e.reason}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub user: {e}")
            return None

    def list_user_repositories(self, limit: int = 50) -> List[GitHubRepoSummary]:
        """List repositories accessible to the authenticated user."""
        if not self.token:
            return []

        url = f"{self.API_BASE}/user/repos?sort=updated&per_page={min(limit, 100)}"
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                items = json.loads(resp.read().decode("utf-8"))
                results: List[GitHubRepoSummary] = []
                for item in items:
                    owner_info = item.get("owner", {})
                    results.append(
                        GitHubRepoSummary(
                            name=item.get("name", ""),
                            full_name=item.get("full_name", ""),
                            owner=owner_info.get("login", ""),
                            description=item.get("description"),
                            private=bool(item.get("private", False)),
                            html_url=item.get("html_url", ""),
                            clone_url=item.get("clone_url", ""),
                            default_branch=item.get("default_branch", "main"),
                            stars=int(item.get("stargazers_count", 0)),
                            language=item.get("language"),
                        )
                    )
                return results
        except Exception as e:
            logger.warning(f"Failed to list GitHub repositories: {e}")
            return []

    def check_repository_access(
        self,
        owner: str,
        repo: str,
        token: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[GitHubRepoSummary]]:
        """Verify repository existence, accessibility, and permissions.

        Returns (is_accessible, error_message, repo_summary).
        """
        active_token = token or self.token
        url = f"{self.API_BASE}/repos/{owner}/{repo}"
        req = urllib.request.Request(url, headers=self._get_headers(active_token))

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                owner_info = data.get("owner", {})
                summary = GitHubRepoSummary(
                    name=data.get("name", repo),
                    full_name=data.get("full_name", f"{owner}/{repo}"),
                    owner=owner_info.get("login", owner),
                    description=data.get("description"),
                    private=bool(data.get("private", False)),
                    html_url=data.get("html_url", f"https://github.com/{owner}/{repo}"),
                    clone_url=data.get("clone_url", f"https://github.com/{owner}/{repo}.git"),
                    default_branch=data.get("default_branch", "main"),
                    stars=int(data.get("stargazers_count", 0)),
                    language=data.get("language"),
                )
                return True, None, summary
        except urllib.error.HTTPError as e:
            # Check rate limiting
            remaining = e.headers.get("X-RateLimit-Remaining") if e.headers else None
            if e.code == 403 and remaining == "0":
                return (
                    False,
                    "GitHub API rate limit exceeded. Please sign in with your GitHub account or provide a Personal Access Token to increase your request quota.",
                    None,
                )

            if e.code == 404:
                if not active_token:
                    return (
                        False,
                        f"Repository '{owner}/{repo}' was not found or is private. If this is a private repository, please sign in with GitHub or provide a Personal Access Token with 'repo' scope.",
                        None,
                    )
                return (
                    False,
                    f"Repository '{owner}/{repo}' does not exist on GitHub or your authenticated account does not have permission to view it.",
                    None,
                )
            if e.code == 401:
                return (
                    False,
                    "GitHub authentication failed. Your access token is invalid or has expired.",
                    None,
                )
            if e.code == 403:
                return (
                    False,
                    f"Access forbidden for '{owner}/{repo}'. Ensure your account or token has 'repo' permissions.",
                    None,
                )
            return (
                False,
                f"GitHub API returned error {e.code}: {e.reason}.",
                None,
            )
        except urllib.error.URLError as e:
            return (
                False,
                f"Network error connecting to GitHub: {e.reason}. Please check your internet connection.",
                None,
            )
        except Exception as e:
            return (
                False,
                f"Unexpected error inspecting repository '{owner}/{repo}': {e}",
                None,
            )

    def get_repository_details(self, owner: str, repo: str) -> Optional[GitHubRepoSummary]:
        """Fetch metadata for a public or accessible repository."""
        _, _, summary = self.check_repository_access(owner, repo)
        return summary

    def _clone_with_git(
        self,
        clone_url: str,
        target_dir: Path,
        branch: Optional[str] = None,
        override_token: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Attempt shallow clone using system git executable with non-interactive guards.

        Returns (success, log_message).
        """
        active_token = override_token or self.token
        auth_clone_url = clone_url
        if active_token and "github.com" in clone_url and "@" not in clone_url:
            auth_clone_url = clone_url.replace("https://github.com/", f"https://{active_token}@github.com/")

        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([auth_clone_url, str(target_dir)])

        # Set environment variables to strictly prevent GUI or interactive prompts
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if res.returncode == 0:
                return True, "Git clone succeeded."

            # Filter auth token out of logged stderr
            clean_stderr = res.stderr
            if active_token:
                clean_stderr = clean_stderr.replace(active_token, "***")
            logger.info(f"System git clone returned code {res.returncode}: {clean_stderr.strip()}")
            return False, clean_stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Git clone timed out after 120 seconds."
        except Exception as e:
            logger.info(f"System git clone not available or failed: {e}")
            return False, str(e)

    def _download_zipball(
        self,
        owner: str,
        repo: str,
        target_dir: Path,
        branch: Optional[str] = None,
        override_token: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Fallback: download repository zipball via GitHub API and extract.

        Returns (success, log_message).
        """
        active_token = override_token or self.token
        ref = branch or "main"
        url = f"{self.API_BASE}/repos/{owner}/{repo}/zipball/{ref}"
        req = urllib.request.Request(url, headers=self._get_headers(active_token))

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()

            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # GitHub zipballs have a top-level folder like 'owner-repo-commit'
                namelist = z.namelist()
                if not namelist:
                    return False, "Downloaded repository archive was empty."

                root_prefix = namelist[0].split("/")[0] + "/"
                for member in z.infolist():
                    if member.is_dir():
                        continue
                    rel_path = member.filename
                    if rel_path.startswith(root_prefix):
                        rel_path = rel_path[len(root_prefix) :]
                    if not rel_path:
                        continue
                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            return True, "Zipball archive downloaded and extracted successfully."
        except urllib.error.HTTPError as e:
            if ref == "main" and e.code == 404:
                # Try master branch
                try:
                    alt_url = f"{self.API_BASE}/repos/{owner}/{repo}/zipball/master"
                    req2 = urllib.request.Request(alt_url, headers=self._get_headers(active_token))
                    with urllib.request.urlopen(req2, timeout=60) as resp2:
                        content2 = resp2.read()
                    target_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(io.BytesIO(content2)) as z2:
                        root_prefix2 = z2.namelist()[0].split("/")[0] + "/"
                        for member2 in z2.infolist():
                            if member2.is_dir():
                                continue
                            rel_path2 = member2.filename
                            if rel_path2.startswith(root_prefix2):
                                rel_path2 = rel_path2[len(root_prefix2) :]
                            if not rel_path2:
                                continue
                            dest_file2 = target_dir / rel_path2
                            dest_file2.parent.mkdir(parents=True, exist_ok=True)
                            with z2.open(member2) as src2, open(dest_file2, "wb") as dst2:
                                shutil.copyfileobj(src2, dst2)
                    return True, "Master branch archive downloaded and extracted."
                except Exception:
                    pass
            return False, f"GitHub archive download failed with HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, f"Zipball archive download failed: {e}"

    def import_repository(
        self,
        identifier: str,
        branch: Optional[str] = None,
        token: Optional[str] = None,
        force_reclone: bool = False,
    ) -> Path:
        """Clone or download a repository, returning the local directory path.

        Raises ValueError for invalid URLs or RuntimeError for accessibility/network failures.
        """
        # 1. Strictly parse and validate URL
        parsed = validate_and_parse_github_url(identifier)
        owner, repo_name = parsed.owner, parsed.repo
        active_token = token or self.token

        repo_dest = self.repos_dir / f"{owner}_{repo_name}"

        # 2. Check if repository is already imported
        if repo_dest.is_dir() and not force_reclone:
            if any(repo_dest.iterdir()):
                logger.info(f"Using already imported repository at {repo_dest}")
                return repo_dest

        # 3. Verify repository accessibility on GitHub
        accessible, access_err, summary = self.check_repository_access(owner, repo_name, active_token)
        if not accessible and access_err:
            raise RuntimeError(access_err)

        target_branch = branch or (summary.default_branch if summary else None)

        # 4. Clean destination directory if force_reclone
        if repo_dest.exists():
            shutil.rmtree(repo_dest, ignore_errors=True)

        clone_url = parsed.clone_url

        # 5. Dual Strategy: Try git clone first
        success, clone_msg = self._clone_with_git(
            clone_url,
            repo_dest,
            branch=target_branch,
            override_token=active_token,
        )

        # 6. Fallback to API zipball download
        if not success:
            logger.info(f"Git clone did not succeed ({clone_msg}). Trying GitHub API zipball download...")
            success, zip_msg = self._download_zipball(
                owner,
                repo_name,
                repo_dest,
                branch=target_branch,
                override_token=active_token,
            )
            if not success:
                if repo_dest.exists():
                    shutil.rmtree(repo_dest, ignore_errors=True)
                raise RuntimeError(
                    f"Failed to download repository '{owner}/{repo_name}'. "
                    f"Clone failed: {clone_msg}. Zipball failed: {zip_msg}"
                )

        if not repo_dest.is_dir() or not any(repo_dest.iterdir()):
            if repo_dest.exists():
                shutil.rmtree(repo_dest, ignore_errors=True)
            raise RuntimeError(f"Repository directory for '{owner}/{repo_name}' is empty after import.")

        return repo_dest
