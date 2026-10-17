"""GitHub integration service for user authentication, repository listing, and cloning/downloading."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Regex to parse GitHub repository owner and name
GITHUB_URL_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+?)(?:\.git)?(?:/.*)?$"
)
GITHUB_SHORT_PATTERN = re.compile(r"^([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)$")


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
    """Parse repository identifier or URL into (owner, repo_name).

    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - github.com/owner/repo
    - owner/repo
    """
    clean_id = identifier.strip().rstrip("/")
    m_url = GITHUB_URL_PATTERN.match(clean_id)
    if m_url:
        return m_url.group(1), m_url.group(2)

    m_short = GITHUB_SHORT_PATTERN.match(clean_id)
    if m_short:
        return m_short.group(1), m_short.group(2)

    raise ValueError(f"Invalid GitHub repository identifier or URL: '{identifier}'")


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

    def _get_headers(self) -> Dict[str, str]:
        """Prepare standard HTTP headers for GitHub API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitContext-AI-Copilot",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_authenticated_user(self) -> Optional[GitHubUser]:
        """Fetch authenticated user profile using token."""
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

    def get_repository_details(self, owner: str, repo: str) -> Optional[GitHubRepoSummary]:
        """Fetch metadata for a public or accessible repository."""
        url = f"{self.API_BASE}/repos/{owner}/{repo}"
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                owner_info = data.get("owner", {})
                return GitHubRepoSummary(
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
        except Exception as e:
            logger.warning(f"Could not fetch details for {owner}/{repo}: {e}")
            return None

    def _clone_with_git(
        self,
        clone_url: str,
        target_dir: Path,
        branch: Optional[str] = None,
    ) -> bool:
        """Attempt shallow clone using system git executable."""
        auth_clone_url = clone_url
        if self.token and "github.com" in clone_url and "@" not in clone_url:
            auth_clone_url = clone_url.replace("https://github.com/", f"https://{self.token}@github.com/")

        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([auth_clone_url, str(target_dir)])

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return res.returncode == 0
        except Exception as e:
            logger.info(f"System git clone not available or failed: {e}")
            return False

    def _download_zipball(
        self,
        owner: str,
        repo: str,
        target_dir: Path,
        branch: Optional[str] = None,
    ) -> bool:
        """Fallback: download repository zipball via GitHub API and extract."""
        ref = branch or "main"
        url = f"{self.API_BASE}/repos/{owner}/{repo}/zipball/{ref}"
        req = urllib.request.Request(url, headers=self._get_headers())

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()

            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # GitHub zipballs have a top-level folder like 'owner-repo-commit'
                root_prefix = z.namelist()[0].split("/")[0] + "/"
                for member in z.infolist():
                    if member.is_dir():
                        continue
                    # Strip root folder prefix
                    rel_path = member.filename
                    if rel_path.startswith(root_prefix):
                        rel_path = rel_path[len(root_prefix) :]
                    if not rel_path:
                        continue
                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            return True
        except Exception as e:
            logger.warning(f"Zipball download failed for {owner}/{repo}: {e}")
            # If 'main' failed, try 'master'
            if ref == "main":
                try:
                    alt_url = f"{self.API_BASE}/repos/{owner}/{repo}/zipball/master"
                    req2 = urllib.request.Request(alt_url, headers=self._get_headers())
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
                    return True
                except Exception:
                    pass
            return False

    def import_repository(
        self,
        identifier: str,
        branch: Optional[str] = None,
        force_reclone: bool = False,
    ) -> Path:
        """Clone or download a repository, returning the local directory path."""
        owner, repo_name = parse_github_identifier(identifier)
        repo_dest = self.repos_dir / f"{owner}_{repo_name}"

        if repo_dest.is_dir() and not force_reclone:
            # If directory already has files, return existing
            if any(repo_dest.iterdir()):
                logger.info(f"Using already imported repository at {repo_dest}")
                return repo_dest

        # Clean destination if forcing reclone
        if repo_dest.exists():
            shutil.rmtree(repo_dest, ignore_errors=True)

        clone_url = f"https://github.com/{owner}/{repo_name}.git"

        # Try git clone first
        success = self._clone_with_git(clone_url, repo_dest, branch=branch)
        if not success:
            logger.info("Falling back to GitHub API zipball download...")
            success = self._download_zipball(owner, repo_name, repo_dest, branch=branch)

        if not success or not repo_dest.is_dir() or not any(repo_dest.iterdir()):
            shutil.rmtree(repo_dest, ignore_errors=True)
            raise RuntimeError(
                f"Failed to import GitHub repository '{identifier}'. "
                "Ensure the repository exists, is accessible, and your token (if private) has 'repo' permissions."
            )

        return repo_dest
